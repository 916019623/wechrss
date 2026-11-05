# -*- coding: utf-8 -*-
"""诊断：多次截图，看页面状态与宫格检测结果。"""
import base64
import importlib.util
import os
import time

CAP = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("CAPTCHA_WORK", os.path.join(os.path.dirname(CAP), "captcha_work"))


def load(n):
    sp = importlib.util.spec_from_file_location(n, os.path.join(CAP, n + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


cp = load("captcha_pc")
sc = load("selection_check")
from PIL import Image

cp.kill_browser()
cp.open_page()
time.sleep(2)
c = cp.CDP()
c.send("Page.navigate", url="file://" + cp.PAGE.replace("\\", "/"))
work = os.environ["CAPTCHA_WORK"]

for i in range(8):
    time.sleep(3)
    try:
        txt = c.eval("document.body.innerText") or ""
    except Exception:
        txt = "<eval failed>"
    r = c.send("Page.captureScreenshot", format="png")
    p = os.path.join(work, f"diag_{i}.png")
    open(p, "wb").write(base64.b64decode(r["data"]))
    im = Image.open(p).convert("RGB")
    g = sc.detect_grid(im)
    print(f"[{i}] body={txt.strip()[:20]!r} grid={g}")
print("done")
