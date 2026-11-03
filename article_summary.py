# -*- coding: utf-8 -*-
"""文章摘要：抓取公众号正文并用 qwen-plus 生成 60~90 字摘要。

用于企业微信推送时在标题下附一行摘要。
密钥：环境变量 DASHSCOPE_API_KEY 或 data/dashscope_key.txt
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_URL = "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1"
MODEL = "qwen-plus"
MAX_CHARS = 3500
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
PROMPT = ("下面是一篇公众号文章。请用 60~90 个汉字概括它的核心信息，"
          "要求：直接说事实（谁、做了什么、数字、结论），不要写“本文”“文章提到”之类，"
          "不要分点，不要换行。只输出摘要本身。\n\n文章正文：\n")


def _key() -> str:
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    for p in (Path("data/dashscope_key.txt"), Path(__file__).with_name("data") / "dashscope_key.txt"):
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def _fetch_text(url: str, timeout: float = 15.0) -> str:
    import requests

    resp = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                        timeout=timeout)
    resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text
    m = re.search(r'<div[^>]+id="js_content"[^>]*>(.*?)</div>\s*<script', html, re.S)
    body = m.group(1) if m else html
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"</p>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        body = body.replace(a, b)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    return re.sub(r"\n{2,}", "\n", body).strip()


def summary_of_url(url: str) -> str:
    """返回摘要；任何失败都返回空串，绝不抛异常。"""
    if not url.startswith("http"):
        return ""
    key = _key()
    if not key:
        return ""
    try:
        text = _fetch_text(url)
    except Exception:
        return ""
    if len(text) < 80:
        return ""
    try:
        from openai import OpenAI
        cli = OpenAI(api_key=key, base_url=BASE_URL, timeout=60)
        r = cli.chat.completions.create(model=MODEL, messages=[
            {"role": "user", "content": PROMPT + text[:MAX_CHARS]}])
        s = (r.choices[0].message.content or "").strip()
        return re.sub(r"\s+", " ", s)[:180]
    except Exception as exc:
        logger.warning("摘要生成失败: %s", type(exc).__name__)
        return ""
