# -*- coding: utf-8 -*-
"""验证码自动解锁（跨平台）：撞到 -2041 时开浏览器 → 视觉模型判图 → 拿 ticket。

流程：
  1. 杀掉旧浏览器，重新打开验证码页（每轮都全新，避免累积卡死）
  2. 等页面真正渲染完（跳过「安全检测中」）
  3. 视觉模型读题 + 判图，点击提交
  4. 成功拿 ticket/randstr，写入 captcha_work/captcha.json

无图形界面时（容器里）配合 Xvfb 使用；也可以用 CAPTCHA_HEADLESS=1 走无头。
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import platform
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.getenv("CAPTCHA_WORK") or os.path.join(os.path.dirname(HERE), "captcha_work")
SHOT = os.path.join(WORK, "captcha_now.png")
CLICKS = os.path.join(WORK, "captcha_clicks.json")
TICKET = os.path.join(WORK, "captcha.json")
FLAG = os.path.join(WORK, "CAPTCHA_NEEDED")
LOG = os.path.join(WORK, "auto_unlock.log")

IS_WIN = platform.system() == "Windows"


def _load(name: str):
    sp = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


cp = _load("captcha_pc")
vh = _load("vision_hook")
bf = _load("button_finder")


def log(m):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        os.makedirs(WORK, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def ensure_page() -> bool:
    """每次都用全新浏览器。"""
    try:
        cp.kill_browser()
    except Exception:
        pass
    log("启动全新的验证码浏览器")
    try:
        cp.open_page()
        time.sleep(6)
        return True
    except Exception as exc:
        log(f"启动失败 {type(exc).__name__}: {str(exc)[:100]}")
        return False


def challenge_text(c) -> str:
    try:
        return c.eval("document.body.innerText") or ""
    except Exception:
        return ""


def dump_result(c):
    try:
        res = c.eval("JSON.stringify(window.__result)")
    except Exception:
        return None
    if not res or res == "null":
        return None
    data = json.loads(res)
    if data.get("ret") == 0 and data.get("ticket"):
        os.makedirs(WORK, exist_ok=True)
        with open(TICKET, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    return None


def bring_front():
    """有界面时把验证码窗口顶到最前（Linux/容器里没有也能继续）。"""
    if not IS_WIN:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, lparam):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if "tcaptcha" in buf.value.lower():
                    found.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        for hwnd in found:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _apply_click(c, x, y):
    for t in ("mousePressed", "mouseReleased"):
        c.send("Input.dispatchMouseEvent", type=t, x=float(x), y=float(y),
               button="left", clickCount=1)


def _submit(c, pos=None):
    """点「确定」。按钮位置按截图动态定位，避免弹窗高度变化时点空。"""
    x, y = pos if pos else (582, 705)
    _apply_click(c, x, y)


def solve(wait: int = 300, poll: int = 6):
    if not ensure_page():
        return None
    c = None
    for attempt in range(3):
        try:
            c = cp.CDP()
            break
        except Exception as exc:
            log(f"连接浏览器失败 {type(exc).__name__}（第 {attempt + 1} 次）")
            time.sleep(5)
    if c is None:
        return None

    try:
        c.send("Page.enable")
        c.send("Page.navigate", url="file://" + cp.PAGE.replace("\\", "/"))
        time.sleep(8)
    except Exception as exc:
        log(f"导航失败 {type(exc).__name__}")

    # 等验证码真正渲染完
    for i in range(25):
        if "安全检测中" not in challenge_text(c):
            break
        if i % 5 == 0:
            log("验证码加载中，等待…")
        time.sleep(1.2)

    end = time.time() + wait
    round_no = 0
    last_title = ""
    same_streak = 0

    while time.time() < end:
        round_no += 1
        txt = challenge_text(c)
        try:
            r = c.send("Page.captureScreenshot", format="png")
            os.makedirs(WORK, exist_ok=True)
            with open(SHOT, "wb") as f:
                f.write(base64.b64decode(r["data"]))
            with open(FLAG, "w", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{SHOT}\n")
        except Exception as exc:
            log(f"截图失败 {type(exc).__name__}，重开浏览器")
            return None
        log(f"第 {round_no} 题：{txt.strip()[:40]!r} 截图已就绪")

        try:
            title = vh.read_title(SHOT) if vh is not None else ""
        except Exception:
            title = ""
        kw = title.split("：")[-1].split(":")[-1].strip().strip('“”"「」')
        if title:
            log(f"  题目内容: {title[:50]}")
        if title and title == last_title:
            same_streak += 1
            if same_streak >= 3:
                log(f"  同一题连续 {same_streak} 次没变化，判定点击无效，放弃")
                return None
        else:
            same_streak = 0
            last_title = title
        if "包含文字" in title and kw:
            bring_front()

        pts = None
        try:
            pts = vh.clicks_for(SHOT, txt)
        except Exception as exc:
            log(f"  视觉模型异常: {type(exc).__name__}")

        if not pts:
            # 人工兜底：等 CAPTCHA_NEEDED 对应的点击方案，最多 120 秒
            waited = 0
            while not pts and time.time() < end and waited < 120:
                if os.path.exists(CLICKS):
                    try:
                        pts = json.load(open(CLICKS, encoding="utf-8"))
                    except Exception:
                        pts = []
                    try:
                        os.remove(CLICKS)
                    except Exception:
                        pass
                    if pts:
                        log(f"  收到人工方案 {pts}")
                        break
                time.sleep(poll)
                waited += poll

        if not pts:
            log("  没有可用方案，本轮放弃")
            return None

        for x, y in pts:
            _apply_click(c, x, y)
            time.sleep(0.6)
        time.sleep(1)
        pos = None
        try:
            pos = bf.find_submit_button(SHOT)
        except Exception:
            pos = None
        if pos:
            log(f"  确定按钮位置: {pos}")
        _submit(c, pos)
        time.sleep(4)
        data = dump_result(c)
        if data:
            log(f"拿到 ticket: {data['ticket'][:24]}...")
            try:
                if os.path.exists(FLAG):
                    os.remove(FLAG)
            except Exception:
                pass
            return data
        log("  进入下一轮")

    log("等待超时")
    return None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=int, default=300)
    args = ap.parse_args()
    log("auto_unlock 启动")
    d = solve(wait=args.wait)
    log("解锁成功" if d else "未拿到 ticket")
    try:
        cp.kill_browser()
    except Exception:
        pass
