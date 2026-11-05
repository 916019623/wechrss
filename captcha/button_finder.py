# -*- coding: utf-8 -*-
"""button_finder：用连通域找「确定」按钮（右下角、宽 50~80、高 22~36 的蓝色块）。"""
from __future__ import annotations

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.getenv("CAPTCHA_WORK") or os.path.join(os.path.dirname(HERE), "captcha_work")


def _is_blue(c) -> bool:
    r, g, b = c[0], c[1], c[2]
    return b > 170 and r < 90 and 100 <= g <= 200


def find_submit_button(img_path: str):
    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    px = im.load()

    seen = [[False] * h for _ in range(w)]
    best = None  # (x1, x0, y0, y1)
    for sx in range(0, w, 2):
        for sy in range(int(h * 0.45), h, 2):
            if seen[sx][sy] or not _is_blue(px[sx, sy]):
                continue
            stack = [(sx, sy)]
            seen[sx][sy] = True
            x0 = x1 = sx
            y0 = y1 = sy
            count = 0
            while stack and count < 20000:
                x, y = stack.pop()
                count += 1
                x0, x1 = min(x0, x), max(x1, x)
                y0, y1 = min(y0, y), max(y1, y)
                for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and not seen[nx][ny] and _is_blue(px[nx, ny]):
                        seen[nx][ny] = True
                        stack.append((nx, ny))
            bw, bh = x1 - x0, y1 - y0
            # 按钮特征：宽度 45~90，高度 20~40，且靠右下
            if 45 <= bw <= 90 and 18 <= bh <= 40:
                if best is None or x1 > best[0]:
                    best = (x1, x0, y0, y1)

    if not best:
        return None
    x1, x0, y0, y1 = best
    return ((x0 + x1) // 2, (y0 + y1) // 2)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "captcha_now.png")
    print(find_submit_button(p))
