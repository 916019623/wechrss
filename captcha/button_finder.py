# -*- coding: utf-8 -*-
"""在截图里定位「确定」按钮的坐标（蓝色按钮，位于弹窗右下角）。

不同题型弹窗高度会变（有的带「换一组」，有的不带），固定坐标会点空。
"""
from __future__ import annotations

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.getenv("CAPTCHA_WORK") or os.path.join(os.path.dirname(HERE), "captcha_work")


def find_submit_button(img_path: str, min_run: int = 40):
    """返回 (x, y)；找不到返回 None。"""
    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    px = im.load()

    def is_blue(p):
        r, g, b = p[0], p[1], p[2]
        return b > 170 and r < 90 and 100 <= g <= 190

    # 从弹窗下半部分往上扫，找第一条足够长的蓝色横条
    best = None
    y = h - 1
    while y > h // 2:
        run_start = None
        run_len = 0
        for x in range(w):
            if is_blue(px[x, y]):
                if run_start is None:
                    run_start = x
                run_len += 1
            else:
                if run_start is not None and run_len >= min_run:
                    if best is None:
                        best = (run_start, x - 1, y, run_len)
                    break
                run_start = None
                run_len = 0
        if best and best[2] - y > 14:      # 已经越过按钮高度，取中间行
            break
        y -= 1

    if not best:
        return None
    x0, x1, y_bottom, _ = best
    # 继续往上找按钮顶边，取中间
    top = y_bottom
    while top > 0:
        cnt = sum(1 for x in range(x0, x1 + 1) if is_blue(px[x, top - 1]))
        if cnt < (x1 - x0 + 1) // 2:
            break
        top -= 1
    return ((x0 + x1) // 2, (top + y_bottom) // 2)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "captcha_now.png")
    print(find_submit_button(p))
