# -*- coding: utf-8 -*-
"""单轮受控测试：只选不提交，输出「选择后」的截图，用于核对我们点的格子是否真的被选中。"""
import importlib.util
import os
import sys
import time

CAP = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("CAPTCHA_WORK", os.path.join(os.path.dirname(CAP), "captcha_work"))


def load(name):
    sp = importlib.util.spec_from_file_location(name, os.path.join(CAP, name + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


cp = load("captcha_pc")
vh = load("vision_hook")
bf = load("button_finder")

cp.kill_browser()
cp.open_page()
time.sleep(3)
c = cp.CDP()
c.send("Page.navigate", url="file://" + cp.PAGE.replace("\\", "/"))
time.sleep(8)

work = os.environ["CAPTCHA_WORK"]
shot = os.path.join(work, "round_before.png")
r = c.send("Page.captureScreenshot", format="png")
import base64
open(shot, "wb").write(base64.b64decode(r["data"]))
title = vh.read_title(shot)
print("题目:", title)
pts = vh.clicks_for(shot)
print("模型选择:", pts)
if not pts:
    sys.exit(1)

for x, y in pts:
    for t in ("mousePressed", "mouseReleased"):
        c.send("Input.dispatchMouseEvent", type=t, x=float(x), y=float(y), button="left", clickCount=1)
    time.sleep(0.4)
time.sleep(1)

after = os.path.join(work, "round_after.png")
r2 = c.send("Page.captureScreenshot", format="png")
open(after, "wb").write(base64.b64decode(r2["data"]))

pos = bf.find_submit_button(after)
print("确定按钮:", pos)
print("已保存:", after)

