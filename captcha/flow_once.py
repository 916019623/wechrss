# -*- coding: utf-8 -*-
"""完整单轮：截图 → 模型选格 → 点击 → 截图 → 提交 → 截图。"""
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
sc = load("selection_check")
vh = load("vision_hook")
bf = load("button_finder")
work = os.environ.get("CAPTCHA_WORK", os.path.join(os.path.dirname(CAP), "captcha_work"))

if not cp.cdp_ping():
    cp.open_page()
    time.sleep(6)
c = cp.CDP()
c.send("Page.navigate", url="file://" + cp.PAGE)
time.sleep(9)


def shot(name):
    r = c.send("Page.captureScreenshot", format="png")
    p = os.path.join(work, name)
    with open(p, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    return p


before = shot("flow_1_before.png")
title = vh.read_title(before)
nums = vh.choose_tiles(before)
print("题目:", title)
print("选择:", nums)
if not nums:
    raise SystemExit("模型没给答案")

cent = sc.centers(before)
for n in nums:
    x, y = cent[n]
    c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none")
    time.sleep(0.15)
    for t in ("mousePressed", "mouseReleased"):
        c.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
        time.sleep(0.12)
    time.sleep(0.4)
time.sleep(1.2)
mid = shot("flow_2_selected.png")
print("实际勾选:", sc.changed_tiles(before, mid))

pos = bf.find_submit_button(mid)
print("确定:", pos)
c.send("Input.dispatchMouseEvent", type="mouseMoved", x=pos[0], y=pos[1], button="none")
time.sleep(0.15)
for t in ("mousePressed", "mouseReleased"):
    c.send("Input.dispatchMouseEvent", type=t, x=pos[0], y=pos[1], button="left", clickCount=1)
    time.sleep(0.15)
time.sleep(4)
after = shot("flow_3_after.png")
print("result:", c.eval("JSON.stringify(window.__result)"))
print("截图: flow_1_before / flow_2_selected / flow_3_after")
