# -*- coding: utf-8 -*-
"""动态识别验证码弹窗的六宫格位置，并按对勾颜色判断哪些格子已选中。

不用固定坐标：不同题型弹窗高度差 20+ 像素，固定坐标会点空/误判。
"""
from __future__ import annotations

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def _is_header_blue(p) -> bool:
    r, g, b = p[0], p[1], p[2]
    return b > 200 and r < 60 and 80 <= g <= 170


def _is_check_blue(p) -> bool:
    """对勾圆圈的蓝色（比标题栏略深）。"""
    r, g, b = p[0], p[1], p[2]
    # 对勾实测 (21,93,212)；标题栏是 (0,122,255)，用 g/b 区间区分
    return r < 60 and 70 <= g <= 118 and 175 <= b <= 240


def detect_grid(img) -> tuple[int, int, int, int] | None:
    """返回六宫格外框 (x0, y0, x1, y1)。"""
    px = img.load()
    w, h = img.size

    # 1) 找标题栏：连续多行有长段蓝色
    header_rows = []
    for y in range(0, int(h * 0.75)):
        run = 0
        best = 0
        for x in range(0, w, 2):
            if _is_header_blue(px[x, y]):
                run += 1
                best = max(best, run)
            else:
                run = 0
        if best * 2 >= 240:
            header_rows.append(y)
    if not header_rows:
        return None
    grid_top = max(header_rows) + 8

    # 2) 找「确定」按钮，其上方 10px 就是宫格底边
    button_top = None
    run_min = 40
    for y in range(h - 1, grid_top, -1):
        run = 0
        found = False
        for x in range(w):
            if _is_header_blue(px[x, y]) or _is_check_blue(px[x, y]):
                run += 1
                if run >= run_min:
                    found = True
                    break
            else:
                run = 0
        if found:
            button_top = y
            break
    if button_top is None:
        return None
    grid_bottom = button_top - 14

    # 3) 左右边界：取标题栏的横向范围，向内收 8px
    xs = [x for x in range(w) if _is_header_blue(px[x, (max(header_rows) + min(header_rows)) // 2])]
    if not xs:
        return None
    x0, x1 = min(xs) + 6, max(xs) - 6

    if grid_bottom - grid_top < 120:
        return None
    return x0, grid_top, x1, grid_bottom


def tile_boxes(grid):
    x0, y0, x1, y1 = grid
    w = (x1 - x0) / 3.0
    h = (y1 - y0) / 2.0
    return [(int(x0 + c * w), int(y0 + r * h),
             int(x0 + (c + 1) * w), int(y0 + (r + 1) * h))
            for r in range(2) for c in range(3)]


def selected_tiles(img_path: str) -> list[int]:
    im = Image.open(img_path).convert("RGB")
    grid = detect_grid(im)
    if not grid:
        return []
    px = im.load()
    out = []
    for idx, (x0, y0, x1, y1) in enumerate(tile_boxes(grid), 1):
        # 在右上角 40x40 区域统计对勾蓝色像素数（圆约 20px 直径 ≈ 250 像素）
        blue = 0
        for x in range(max(0, x1 - 40), min(im.width, x1 - 2)):
            for y in range(max(0, y0 + 2), min(im.height, y0 + 40)):
                if _is_check_blue(px[x, y]):
                    blue += 1
        if blue >= 90:
            out.append(idx)
    return out


def centers(img_path: str) -> dict[int, tuple[float, float]]:
    """返回每格中心坐标（供点击）。"""
    im = Image.open(img_path).convert("RGB")
    grid = detect_grid(im)
    if not grid:
        return {}
    return {i: (round((b[0] + b[2]) / 2, 1), round((b[1] + b[3]) / 2, 1))
            for i, b in enumerate(tile_boxes(grid), 1)}


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(HERE), "captcha_work", "captcha_now.png")
    im = Image.open(p).convert("RGB")
    print("grid:", detect_grid(im))
    print("已选:", selected_tiles(p))

def changed_tiles(before_path: str, after_path: str, threshold: float = 12.0) -> list[int]:
    """对比两帧，返回画面发生明显变化的格子编号（即被点击选中的格）。"""
    a = Image.open(before_path).convert("RGB")
    b = Image.open(after_path).convert("RGB")
    grid = detect_grid(b) or detect_grid(a)
    if not grid:
        return []
    pa, pb = a.load(), b.load()
    out = []
    for idx, (x0, y0, x1, y1) in enumerate(tile_boxes(grid), 1):
        total = 0.0
        cnt = 0
        step = 3
        for x in range(x0 + 4, x1 - 4, step):
            for y in range(y0 + 4, y1 - 4, step):
                if x < a.width and y < a.height and x < b.width and y < b.height:
                    ca, cb = pa[x, y], pb[x, y]
                    total += abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])
                    cnt += 1
        if cnt and (total / cnt) >= threshold:
            out.append(idx)
    return out
