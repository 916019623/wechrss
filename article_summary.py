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
# 移动端微信 UA 才拿得到正文；桌面 UA 常被拦成「环境异常」
UA_WECHAT = ("Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Version/4.0 Chrome/111.0.5563.116 Mobile Safari/537.36 "
             "MicroMessenger/8.0.40.2420(0x2800283D) WeChat/arm64 Weixin NetType/WIFI")
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# 只有这些字样才说明抓到的是拦截页；
# 注意「微信扫一扫可打开此内容」在正常文章页里也有（分享浮层），不能算。
BLOCK_MARKS = (
    "扫码即可使用完整服务",
    "请在微信客户端打开链接",
    "环境异常",
    "该内容已被发布者删除",
    "此内容因违规无法查看",
    "参数错误",
)
PROMPT = ("下面是一篇公众号文章。请用 60~90 个汉字概括它的核心信息，"
          "要求：直接说事实（谁、做了什么、数字、结论），不要写“本文”“文章提到”之类，"
          "不要分点，不要换行。只输出摘要本身。\n\n文章正文：\n")


def _key() -> str:
    try:
        import ai_config
        k = ai_config.text_key()
        if k:
            return k
    except Exception:
        pass
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


def _is_block_page(html: str) -> bool:
    """判断抓到的是不是微信的拦截/提示页：有正文容器就不算。"""
    if 'id="js_content"' in html or "rich_media_content" in html:
        return False
    return any(mark in html for mark in BLOCK_MARKS)


def _og_description(html: str) -> str:
    """从 og:description / msg_desc 里取文章摘要（新版图文页常见）。"""
    for pat in (r'<meta property="og:description" content="(.*?)"',
                r'var msg_desc = "(.*?)"'):
        m = re.search(pat, html, re.S)
        if not m:
            continue
        text = m.group(1)
        text = text.replace("\\x0a", "\n").replace("\\n", "\n")
        for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                     ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
            text = text.replace(a, b)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        if len(text) >= 40:
            return text
    return ""


def _fetch_html(url: str, timeout: float = 15.0) -> str:
    """抓正文：两种 UA × 多轮重试（拦截是间歇性的）。"""
    import time

    for attempt in range(3):
        html = _fetch_once(url, timeout)
        if html:
            return html
        if attempt < 2:
            time.sleep(4 * (attempt + 1))
    return ""


def _fetch_once(url: str, timeout: float = 15.0) -> str:
    import requests

    for ua in (UA_WECHAT, UA_DESKTOP):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9",
                         "Referer": "https://mp.weixin.qq.com/"},
                timeout=timeout,
            )
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception:
            continue
        html = resp.text or ""
        if _is_block_page(html):
            logger.info("摘要跳过：命中微信拦截页（UA=%s）", "wechat" if ua is UA_WECHAT else "desktop")
            continue
        if 'id="js_content"' in html or "rich_media_content" in html:
            return html
        # 新版图文/小绿书没有 js_content，用 og:description 兜底
        desc = _og_description(html)
        if desc:
            return "<html><body><p>" + desc + "</p></body></html>"
    return ""


def _fetch_text(url: str, timeout: float = 15.0) -> str:
    html = _fetch_html(url, timeout=timeout)
    if not html:
        return ""
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
    if len(text) < 40:
        return ""
    try:
        from openai import OpenAI
        try:
            import ai_config
            base, model = ai_config.text_base_url(), ai_config.text_model()
        except Exception:
            base, model = BASE_URL, MODEL
        cli = OpenAI(api_key=key, base_url=base, timeout=60)
        r = cli.chat.completions.create(model=model, messages=[
            {"role": "user", "content": PROMPT + text[:MAX_CHARS]}])
        s = (r.choices[0].message.content or "").strip()
        s = re.sub(r"\s+", " ", s)[:180]
        if any(mark in s for mark in ("轻点两下", "扫码", "环境异常", "完整服务")):
            logger.info("摘要命中拦截页文案，已丢弃")
            return ""
        return s
    except Exception as exc:
        logger.warning("摘要生成失败: %s", type(exc).__name__)
        return ""

def fetch_and_summarize(urls) -> tuple[str, str]:
    """依次尝试多个链接，返回 (可用链接, 摘要)。

    - 链接能抓到正文 → 用它做摘要，并作为推送链接
    - 都抓不到 → 返回 ("", "")，调用方自行决定用哪个链接兜底
    """
    for url in urls:
        if not url or not url.startswith("http"):
            continue
        try:
            text = _fetch_text(url)
        except Exception:
            text = ""
        if len(text) < 40:
            continue
        summ = _summarize_text(text)
        return url, summ
    return "", ""


def _summarize_text(text: str) -> str:
    """把正文交给模型生成 60~90 字摘要；失败返回空串。"""
    key = _key()
    if not key:
        return ""
    try:
        from openai import OpenAI
        try:
            import ai_config
            base, model = ai_config.text_base_url(), ai_config.text_model()
        except Exception:
            base, model = BASE_URL, MODEL
        cli = OpenAI(api_key=key, base_url=base, timeout=60)
        r = cli.chat.completions.create(model=model, messages=[
            {"role": "user", "content": PROMPT + text[:MAX_CHARS]}])
        out = (r.choices[0].message.content or "").strip()
        out = re.sub(r"\s+", " ", out)[:180]
        if any(mark in out for mark in ("轻点两下", "扫码", "环境异常", "完整服务")):
            return ""
        return out
    except Exception as exc:
        logger.warning("摘要生成失败: %s", type(exc).__name__)
        return ""
