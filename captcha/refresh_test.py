# -*- coding: utf-8 -*-
"""点「换一组」看是否会换题（判断是否被服务端判死）。"""
import base64
import importlib.util
import os
import time

CAP = os.path.dirname(os.path.abspath(__file__))


def load(n):
    sp = importlib.util.spec_from_file_location(n, os.path.join(CAP, n + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


cp = load("captcha_pc")
work = os.environ.get("CAPTCHA_WORK", os.path.join(os.path.dirname(CAP), "captcha_work"))
c = cp.CDP()


def shot(name):
    r = c.send("Page.captureScreenshot", format="png")
    p = os.path.join(work, name)
    with open(p, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    return p


print("before:", shot("refresh_before.png"))
# 换一组按钮：底部左侧第二个图标附近
for x, y in ((324, 705), (325, 700)):
    c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")
    time.sleep(0.15)
    c.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
    time.sleep(0.12)
    c.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
    time.sleep(2.5)
print("after:", shot("refresh_after.png"))
print("result:", c.eval("JSON.stringify(window.__result)"))
