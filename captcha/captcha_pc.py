# -*- coding: utf-8 -*-
"""验证码浏览器控制（跨平台）：启动 Chrome/Chromium，通过 CDP 截图与点击。

环境变量：
  CAPTCHA_PORT        调试端口，默认 9223
  CAPTCHA_HEADLESS    1=无头（默认 0，容器里配合 Xvfb 用有头）
  CHROME_PATH         浏览器可执行文件路径（默认自动探测）
  CAPTCHA_WORK        工作目录（默认 <repo>/captcha_work）
"""
from __future__ import annotations

import base64
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

IS_WIN = platform.system() == "Windows"

PORT = int(os.getenv("CAPTCHA_PORT", "9223"))
HEADLESS = os.getenv("CAPTCHA_HEADLESS", "0").strip() in ("1", "true", "yes")
APPID = "2044038556"

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.getenv("CAPTCHA_WORK") or os.path.join(os.path.dirname(HERE), "captcha_work")
PROFILE = os.getenv("CAPTCHA_PROFILE") or os.path.join(
    tempfile.gettempdir(), "wxread-chrome-profile")
PAGE = os.path.join(WORK, "tcaptcha.html")
SHOT = os.path.join(WORK, "captcha_now.png")

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script>
var s=document.createElement("script");
s.src="https://ssl.captcha.qq.com/TCaptcha.js?v="+Date.now();
document.head.appendChild(s);
window.__result=null;
window.onload=function(){
  setTimeout(function(){
    window.__tc=new TencentCaptcha("%s", function(res){ window.__result=res; }, {});
    window.__tc.show();
  }, 800);
};
</script></head><body style="background:#fff"></body></html>
""" % APPID


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def find_chrome() -> str:
    env = os.getenv("CHROME_PATH", "").strip()
    if env:
        return env
    if IS_WIN:
        for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
            if os.path.exists(p):
                return p
        return "chrome.exe"
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    # playwright 自带 chromium（容器里常见）
    import glob
    for pat in ("/ms-playwright/chromium-*/chrome-linux/chrome",
                os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    raise RuntimeError("找不到 Chrome/Chromium，请设置 CHROME_PATH")


def _pids_on_port(port: int) -> list[str]:
    """返回监听该端口的进程 PID（Linux 用 ss，Windows 用 netstat）。"""
    pids: set[str] = set()
    try:
        if IS_WIN:
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=15).stdout
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    m = re.search(r"(\d+)\s*$", line.strip())
                    if m:
                        pids.add(m.group(1))
        else:
            out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=15).stdout
            for line in out.splitlines():
                if f":{port}" in line:
                    for m in re.finditer(r"pid=(\d+)", line):
                        pids.add(m.group(1))
    except Exception:
        pass
    return list(pids)


def kill_browser():
    """杀掉占用调试端口的浏览器进程。"""
    for pid in _pids_on_port(PORT):
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/F", "/PID", pid, "/T"], capture_output=True, timeout=20)
            else:
                subprocess.run(["kill", "-9", pid], capture_output=True, timeout=10)
        except Exception:
            pass
    time.sleep(1.5)


def http_json(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def target():
    pages = http_json("/json/list")
    for t in pages:
        if t.get("type") == "page" and "tcaptcha" in (t.get("url") or ""):
            return t
    for t in pages:
        if t.get("type") == "page":
            return t
    raise SystemExit("没有可用的页面")


class CDP:
    def __init__(self, timeout: int = 30):
        t = target()
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=timeout)
        self.i = 0
        try:
            self.send("Emulation.setDeviceMetricsOverride", width=884, height=1105,
                      deviceScaleFactor=1, mobile=False)
        except Exception:
            pass

    def send(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        deadline = time.time() + 60
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg.get("result", {})
        raise TimeoutError(f"CDP {method} 超时")

    def eval(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def cdp_ping(timeout: int = 4) -> bool:
    try:
        t = target()
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=timeout)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": "1+1", "returnByValue": True}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                ws.close()
                return msg.get("result", {}).get("result", {}).get("value") == 2
        ws.close()
        return False
    except Exception:
        return False


def _clear_profile_locks():
    """清掉 Chrome 的 Singleton 锁（容器重建后旧锁会让 Chrome 拒绝启动）。"""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            os.remove(os.path.join(PROFILE, name))
        except OSError:
            pass


def open_page():
    os.makedirs(PROFILE, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    _clear_profile_locks()
    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(HTML)
    chrome = find_chrome()

    # Linux 上如果没有显示（没装 Xvfb），自动退化为无头，避免直接失败
    headless = HEADLESS
    if not IS_WIN and not headless and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        log("未检测到 DISPLAY，自动改用无头模式")
        headless = True

    args = [
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
        "--window-size=900,1200",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--lang=zh-CN",
    ]
    if headless:
        args.append("--headless=new")
    if not IS_WIN:
        # 容器里通常是 root，必须关沙箱，否则 chrome 直接退出
        args.extend(["--no-sandbox", "--disable-setuid-sandbox"])
    args.append("file://" + PAGE.replace("\\", "/"))
    os.makedirs(WORK, exist_ok=True)
    errlog = open(os.path.join(WORK, "chrome.log"), "ab")
    subprocess.Popen([chrome] + args,
                     stdout=errlog, stderr=errlog,
                     start_new_session=not IS_WIN)

    # 等调试端口真正就绪（容器里冷启动可能要 10~30 秒，固定 sleep 不可靠）
    deadline = time.time() + int(os.getenv("CAPTCHA_START_TIMEOUT", "45"))
    waited = 0.0
    while time.time() < deadline:
        try:
            http_json("/json/version")
            log(f"Chrome 已就绪（等待 {waited:.0f}s）")
            return
        except Exception:
            time.sleep(1.5)
            waited += 1.5
    log("Chrome 启动超时（45s 内未开调试端口）")
    raise RuntimeError("Chrome 启动超时")


def screenshot(path: str | None = None) -> str:
    c = CDP()
    r = c.send("Page.captureScreenshot", format="png")
    out = path or SHOT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    c.close()
    return out


def self_check() -> int:
    """环境自检：浏览器、显示、端口、依赖。"""
    ok = True
    print(f"平台      : {'Windows' if IS_WIN else 'Linux/其它'}")
    print(f"工作目录  : {WORK}")
    print(f"profile   : {PROFILE}")
    print(f"调试端口  : {PORT}")
    try:
        print(f"浏览器    : {find_chrome()}")
    except Exception as exc:
        ok = False
        print(f"浏览器    : 未找到（{exc}）")
    if not IS_WIN:
        disp = os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY") or ""
        print(f"DISPLAY   : {disp or '（无，将自动使用无头模式）'}")
    try:
        import websocket  # noqa: F401
        from PIL import Image  # noqa: F401
        print("依赖      : websocket-client / Pillow 正常")
    except Exception as exc:
        ok = False
        print(f"依赖      : 缺失 {type(exc).__name__}")
    print(f"端口占用  : {'有进程' if _pids_on_port(PORT) else '空闲'}")
    print("结论      :", "可用" if ok else "需要处理")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "open"
    if cmd == "open":
        open_page()
    elif cmd == "close":
        kill_browser()
        log("已关闭")
    elif cmd == "shot":
        print(screenshot(sys.argv[2] if len(sys.argv) > 2 else None))
    elif cmd == "ping":
        print("alive" if cdp_ping() else "dead")
    elif cmd == "check":
        raise SystemExit(self_check())
