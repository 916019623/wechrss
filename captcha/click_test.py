# -*- coding: utf-8 -*-
"""试验不同的点击方式，找出能真正触发「确定」的那一种。"""
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
bf = load("button_finder")
work = os.environ.get("CAPTCHA_WORK", os.path.join(os.path.dirname(CAP), "captcha_work"))

c = cp.CDP()


def shot(name):
    r = c.send("Page.captureScreenshot", format="png")
    p = os.path.join(work, name)
    with open(p, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    return p


def same(a, b):
    return open(a, "rb").read() == open(b, "rb").read()


before = shot("click_test_before.png")
pos = bf.find_submit_button(before)
print("按钮:", pos)

# 方式1：moved + press + release
x, y = pos
c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")
time.sleep(0.2)
for t in ("mousePressed", "mouseReleased"):
    c.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
    time.sleep(0.15)
time.sleep(2.5)
a1 = shot("click_test_1.png")
print("方式1 画面变化:", not same(before, a1))

# 方式2：带 clickCount=1 的 press/release 但坐标略微上移（按钮中心偏上）
y2 = y - 4
for t in ("mousePressed", "mouseReleased"):
    c.send("Input.dispatchMouseEvent", type=t, x=x, y=y2, button="left", clickCount=1)
    time.sleep(0.15)
time.sleep(2.5)
a2 = shot("click_test_2.png")
print("方式2 画面变化:", not same(a1, a2))

# 方式3：真实鼠标事件序列（moved->pressed->released，含 clicks/buttons 字段）
c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y2, button="none", buttons=0)
time.sleep(0.1)
c.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y2, button="left", buttons=1, clickCount=1)
time.sleep(0.1)
c.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y2, button="left", buttons=0, clickCount=1)
time.sleep(3)
a3 = shot("click_test_3.png")
print("方式3 画面变化:", not same(a2, a3))
print("result:", c.eval("JSON.stringify(window.__result)"))
