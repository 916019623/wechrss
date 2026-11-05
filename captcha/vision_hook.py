# -*- coding: utf-8 -*-
"""验证码识图：题目条读文字 + 六格判图（两步法）。

密钥/模型来自 ai_config（设置页），未配置时回退环境变量。
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.getenv("CAPTCHA_WORK") or os.path.join(os.path.dirname(HERE), "captcha_work")
LOG = os.path.join(WORK, "vision.log")

DEFAULT_BASE_URL = "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-vl-plus"

TITLE = (265, 368, 620, 490)
GRID = (272, 448, 597, 690)
SCALE_TITLE = 8
SCALE_TILE = 5

READ_PROMPT = ("读出图片里的中文题目。只回答题目本身，不要任何解释。"
               "如果是「包含文字：X」就原样回答：包含文字：X")

JUDGE_PROMPT = ("上面 6 张图是验证码的六宫格（第 1 行 1、2、3；第 2 行 4、5、6）。"
                "题目是「{key}」。请指出哪几格符合「{key}」。"
                "严格判断：主体必须是它，背景里类似元素、只是颜色相近的都不算；拿不准的不选。"
                "只输出 JSON：{{\"tiles\":[...]}}")


def _log(m):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        os.makedirs(WORK, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _cfg():
    """返回 (key, base_url, model)。"""
    key = base = model = ""
    try:
        import sys as _sys
        root = os.path.dirname(HERE)
        if root not in _sys.path:
            _sys.path.insert(0, root)
        import ai_config
        key = ai_config.vision_key()
        base = ai_config.vision_base_url()
        model = ai_config.vision_model()
    except Exception:
        pass
    key = key or os.getenv("DASHSCOPE_API_KEY", "").strip()
    base = base or os.getenv("DASHSCOPE_BASE_URL", "").strip() or DEFAULT_BASE_URL
    model = model or os.getenv("DASHSCOPE_VISION_MODEL", "").strip() or DEFAULT_MODEL
    return key, base, model


def _b64(img, scale):
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _centers():
    x0, y0, x1, y1 = GRID
    w = (x1 - x0) / 3.0
    h = (y1 - y0) / 2.0
    return {i: (round(x0 + w * ((i - 1) % 3 + 0.5), 1),
                round(y0 + h * ((i - 1) // 3 + 0.5), 1)) for i in range(1, 7)}


def _client():
    key, base, model = _cfg()
    if not key:
        _log("未配置视觉模型 API Key")
        return None, None
    try:
        from openai import OpenAI
    except ImportError:
        _log("openai 库缺失")
        return None, None
    return OpenAI(api_key=key, base_url=base, timeout=90), model


def _ask(client, model, content, retries=3):
    last = None
    for i in range(retries):
        try:
            r = client.chat.completions.create(model=model,
                                               messages=[{"role": "user", "content": content}],
                                               extra_body={"enable_thinking": True})
            return (r.choices[0].message.content or "").strip()
        except Exception as exc:
            last = exc
            _log(f"调用异常({i + 1}/{retries}) {type(exc).__name__}")
            if i < retries - 1:
                time.sleep(3 * (i + 1))
    raise last


def read_title(img_path, client=None, model=None):
    """只读题目，用于判断题型。"""
    if client is None:
        client, model = _client()
        if client is None:
            return ""
    try:
        im = Image.open(img_path).convert("RGB")
        txt = _ask(client, model, [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{_b64(im.crop(TITLE), SCALE_TITLE)}"}},
            {"type": "text", "text": READ_PROMPT},
        ])
        return txt.replace("\n", " ").strip()
    except Exception as exc:
        _log(f"read_title 失败 {type(exc).__name__}")
        return ""


def choose_tiles(img_path, challenge_text=""):
    """返回该点哪几格的**编号**（1..6）；失败返回 None。"""
    client, model = _client()
    if client is None:
        return None

    im = Image.open(img_path).convert("RGB")
    try:
        txt = _ask(client, model, [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{_b64(im.crop(TITLE), SCALE_TITLE)}"}},
            {"type": "text", "text": READ_PROMPT},
        ])
    except Exception as exc:
        _log(f"读题失败 {type(exc).__name__}: {str(exc)[:100]}")
        return None
    txt = txt.replace("\n", " ").strip()
    _log(f"题目: {txt[:60]}")

    kw = txt.replace("包含文字：", "").replace("包含文字:", "").strip()
    kw = re.sub(r"^[\s\"'“”「」]+|[\s\"'“”「」]+$", "", kw)

    x0, y0, x1, y1 = GRID
    w, h = (x1 - x0) / 3.0, (y1 - y0) / 2.0
    boxes = []
    for i in range(1, 7):
        r_, c_ = divmod(i - 1, 3)
        boxes.append((int(x0 + c_ * w), int(y0 + r_ * h),
                      int(x0 + (c_ + 1) * w), int(y0 + (r_ + 1) * h)))

    multi = ("所有" in txt) or ("全部" in txt)
    nums = []

    if multi:
        # 「选择所有符合的」用逐格二元判断：模型对单格是/否比一次多选准得多
        for idx, box in enumerate(boxes, 1):
            try:
                ans = _ask(client, model, [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{_b64(im.crop(box), SCALE_TILE)}"}},
                    {"type": "text", "text":
                        f"先用 2~4 个词写出这张图的主要物体；再判断这些物体里有没有「{kw}」"
                        f"（含同义词，例如 栅栏=围栏、列车=火车）。\n"
                        "严格按这个格式输出一行：物体1、物体2|是  或  物体1、物体2|否"},
                ])
            except Exception as exc:
                _log(f"第 {idx} 格判断失败 {type(exc).__name__}")
                continue
            a = ans.replace("\n", " ").strip()
            verdict = a.split("|")[-1].strip() if "|" in a else a
            hit = verdict.startswith("是")
            _log(f"  第{idx}格 -> {a[:40]} => {'选' if hit else '不选'}")
            if hit:
                nums.append(idx)
    else:
        content = []
        for i, box in enumerate(boxes, 1):
            content.append({"type": "text", "text": f"第 {i} 格："})
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{_b64(im.crop(box), SCALE_TILE)}"}})
        content.append({"type": "text", "text": JUDGE_PROMPT.format(key=kw)})
        try:
            out = _ask(client, model, content)
        except Exception as exc:
            _log(f"判断失败 {type(exc).__name__}: {str(exc)[:100]}")
            return None
        _log(f"判断: {out[:120]}")
        try:
            s = out[out.find("{"): out.rfind("}") + 1]
            nums = [int(x) for x in json.loads(s).get("tiles", [])]
        except Exception:
            nums = [int(x) for x in re.findall(r"[1-6]", out)]

    nums = sorted({n for n in nums if 1 <= n <= 6})
    if not nums:
        _log("没有可用编号")
        return None

    _log(f"选择格子: {nums}")
    return nums


def clicks_for(img_path, challenge_text=""):
    """兼容旧接口：返回格子中心坐标列表。"""
    nums = choose_tiles(img_path, challenge_text)
    if not nums:
        return None
    cen = _centers()
    return [list(cen[n]) for n in nums]
