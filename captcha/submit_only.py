# -*- coding: utf-8 -*-
"""只提交当前已选内容，返回结果与截图（人工验证用）。"""
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
before = os.path.join(work, "s_before.png")
r = c.send("Page.captureScreenshot", format="png")
open(before, "wb").write(base64.b64decode(r["data"]))
pos = bf.find_submit_button(before)
print("确定按钮:", pos)
for t in ("mousePressed", "mouseReleased"):
    c.send("Input.dispatchMouseEvent", type=t, x=pos[0], y=pos[1], button="left", clickCount=1)
time.sleep(4)
after = os.path.join(work, "s_after.png")
r2 = c.send("Page.captureScreenshot", format="png")
open(after, "wb").write(base64.b64decode(r2["data"]))
print("result:", c.eval("JSON.stringify(window.__result)"))
print("截图:", after)
