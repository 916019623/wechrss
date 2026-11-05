# -*- coding: utf-8 -*-
"""只截图当前题目（不点击、不提交），供人工核对。"""
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
p = os.path.join(work, "q_now.png")
r = c.send("Page.captureScreenshot", format="png")
open(p, "wb").write(base64.b64decode(r["data"]))
print("截图:", p)
print("按钮:", bf.find_submit_button(p))
print("题目:", vh.read_title(p))
print("模型选择:", vh.choose_tiles(p))
