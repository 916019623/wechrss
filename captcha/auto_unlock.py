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
sc = _load("selection_check")


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


WIN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _mimic_browser(c):
    """把浏览器伪装成 Windows 桌面 Chrome + 中国时区。"""
    try:
        c.send("Network.enable")
        c.send("Network.setUserAgentOverride", userAgent=WIN_UA,
               acceptLanguage="zh-CN,zh;q=0.9",
               platform="Win32")
    except Exception:
        pass
    for method, params in (
        ("Emulation.setTimezoneOverride", {"timezoneId": "Asia/Shanghai"}),
        ("Emulation.setLocaleOverride", {"locale": "zh-CN"}),
    ):
        try:
            c.send(method, **params)
        except Exception:
            pass


def _human_move(c, x, y):
    """模拟人手移动：分多步移动 + 轻微抖动。"""
    import math
    import random
    try:
        start = (random.randint(280, 620), random.randint(420, 700))
    except Exception:
        start = (450, 560)
    sx, sy = start
    steps = random.randint(14, 26)
    for i in range(1, steps + 1):
        t = i / steps
        # 缓动曲线，起手快、落点慢
        ease = 1 - (1 - t) ** 3
        nx = sx + (x - sx) * ease + random.uniform(-2.5, 2.5)
        ny = sy + (y - sy) * ease + random.uniform(-2.5, 2.5)
        try:
            c.send("Input.dispatchMouseEvent", type="mouseMoved",
                   x=round(nx, 1), y=round(ny, 1), button="none")
        except Exception:
            return
        time.sleep(random.uniform(0.008, 0.03))
    try:
        c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")
    except Exception:
        pass


def _human_click(c, x, y):
    """先移动再按下，按下与抬起之间留随机间隔。"""
    import random
    _human_move(c, x, y)
    time.sleep(random.uniform(0.05, 0.18))
    try:
        c.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
               button="left", buttons=1, clickCount=1)
    except Exception:
        pass
    time.sleep(random.uniform(0.06, 0.16))
    try:
        c.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
               button="left", buttons=0, clickCount=1)
    except Exception:
        pass
    time.sleep(random.uniform(0.1, 0.3))


def _apply_click(c, x, y):
    _human_click(c, float(x), float(y))


def _submit(c, pos=None):
    """点「确定」。按钮位置按截图动态定位，避免弹窗高度变化时点空。"""
    x, y = pos if pos else (582, 705)
    _apply_click(c, x, y)


def _kill_all_chrome():
    """兜底清理：杀掉所有带调试端口的浏览器进程树。"""
    import subprocess
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"],
                           capture_output=True, timeout=20)
        else:
            subprocess.run(["pkill", "-9", "-f", "remote-debugging-port"],
                           capture_output=True, timeout=20)
            subprocess.run(["pkill", "-9", "-f", "chrome-linux"],
                           capture_output=True, timeout=20)
    except Exception:
        pass


def solve(wait: int = 300, poll: int = 6):
    """对外入口：无论成功失败，结束后一定关掉浏览器，防止进程泄漏。"""
    try:
        return _solve_inner(wait=wait, poll=poll)
    finally:
        try:
            cp.kill_browser()
        except Exception:
            pass
        _kill_all_chrome()


def _solve_inner(wait: int = 300, poll: int = 6):
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

    _mimic_browser(c)

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
        # 页面可能还没渲染完（截到空白就检测不到宫格），这里重试
        for _try in range(30):
            try:
                if sc.detect_grid(__import__("PIL.Image", fromlist=["Image"]).open(SHOT).convert("RGB")):
                    break
            except Exception:
                pass
            log("  宫格未就绪，等待重截…")
            time.sleep(2)
            try:
                r_wait = c.send("Page.captureScreenshot", format="png")
                with open(SHOT, "wb") as f:
                    f.write(base64.b64decode(r_wait["data"]))
            except Exception:
                pass

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

        nums = None
        pts = None
        try:
            nums = vh.choose_tiles(SHOT, txt)
        except Exception as exc:
            log(f"  视觉模型异常 {type(exc).__name__}")
        if nums:
            try:
                cen = sc.centers(SHOT) or vh._centers()
            except Exception:
                cen = vh._centers()
            pts = [list(cen[n]) for n in nums if n in cen]
            log(f"  目标格子 {nums} → 坐标 {pts}")

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

        # 点击前拍基准帧，用于判断点击是否真的生效
        pre_path = os.path.join(WORK, "pre_click.png")
        try:
            r_pre = c.send("Page.captureScreenshot", format="png")
            with open(pre_path, "wb") as f:
                f.write(base64.b64decode(r_pre["data"]))
        except Exception:
            pre_path = None

        for x, y in pts:
            _apply_click(c, x, y)
            time.sleep(0.6)
        time.sleep(1)

        # 提交前核对勾选（用点击前后画面差异判断，避免颜色误判）
        if nums:
            try:
                chk_path = os.path.join(WORK, "check_selected.png")
                r_chk = c.send("Page.captureScreenshot", format="png")
                with open(chk_path, "wb") as f:
                    f.write(base64.b64decode(r_chk["data"]))
                got = sc.changed_tiles(pre_path or SHOT, chk_path)
                want = sorted(nums)
                if got != want:
                    log(f"  勾选不符：实际 {got}，期望 {want}，补点一次")
                    try:
                        cen2 = sc.centers(chk_path) or vh._centers()
                    except Exception:
                        cen2 = vh._centers()
                    for n in sorted(set(want) - set(got)):
                        if n in cen2:
                            _apply_click(c, cen2[n][0], cen2[n][1])
                            log(f"  补点第 {n} 格")
                            time.sleep(0.4)
                    time.sleep(0.8)
                    r_chk2 = c.send("Page.captureScreenshot", format="png")
                    with open(chk_path, "wb") as f:
                        f.write(base64.b64decode(r_chk2["data"]))
                    log(f"  补点后差异：{sc.changed_tiles(pre_path or SHOT, chk_path)}")
                else:
                    log("  勾选核对通过")
            except Exception as exc:
                log(f"  勾选核对异常 {type(exc).__name__}")
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
