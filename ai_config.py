# -*- coding: utf-8 -*-
"""AI 模型配置：文本模型（写摘要）与视觉模型（过验证码）的 API Key。

配置存在 app_settings 表，key 前缀 ai.；未配置时回退到环境变量 / 本地文件，
保证已有部署不受影响。
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULTS = {
    "ai.text_base_url": "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1",
    "ai.text_model": "qwen-plus",
    "ai.vision_base_url": "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1",
    "ai.vision_model": "qwen3-vl-plus",
}
SECRET_KEYS = ("ai.text_api_key", "ai.vision_api_key")

_db = None


def bind(db) -> None:
    """由 web_app 在启动时注入 AppDB 实例。"""
    global _db
    _db = db


def _get(key: str, default: str = "") -> str:
    if _db is not None:
        try:
            v = _db.get_setting(key, "")
            if v:
                return v
        except Exception:
            pass
    env = {"ai.text_api_key": "DASHSCOPE_API_KEY",
           "ai.vision_api_key": "DASHSCOPE_API_KEY",
           "ai.text_base_url": "DASHSCOPE_BASE_URL",
           "ai.vision_base_url": "DASHSCOPE_BASE_URL",
           "ai.text_model": "DASHSCOPE_TEXT_MODEL",
           "ai.vision_model": "DASHSCOPE_VISION_MODEL"}.get(key, "")
    if env and os.getenv(env):
        return os.getenv(env, "")
    return default


def _file_key() -> str:
    for p in (Path("data/dashscope_key.txt"), Path(__file__).with_name("data") / "dashscope_key.txt"):
        try:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def text_key() -> str:
    return (_get("ai.text_api_key") or _file_key()).strip()


def vision_key() -> str:
    return (_get("ai.vision_api_key") or text_key()).strip()


def text_base_url() -> str:
    return _get("ai.text_base_url", DEFAULTS["ai.text_base_url"]) or DEFAULTS["ai.text_base_url"]


def vision_base_url() -> str:
    return _get("ai.vision_base_url", DEFAULTS["ai.vision_base_url"]) or DEFAULTS["ai.vision_base_url"]


def text_model() -> str:
    return _get("ai.text_model", DEFAULTS["ai.text_model"]) or DEFAULTS["ai.text_model"]


def vision_model() -> str:
    return _get("ai.vision_model", DEFAULTS["ai.vision_model"]) or DEFAULTS["ai.vision_model"]


def save(**kwargs) -> None:
    """保存配置。只写入非空值；显式传空串表示清除。"""
    if _db is None:
        raise RuntimeError("ai_config 未绑定数据库")
    for key, value in kwargs.items():
        if value is None:
            continue
        _db.set_setting(key, str(value).strip())


def apply_to_env() -> None:
    """把视觉模型配置写进环境变量，供验证码模块（vision_hook）读取。"""
    vk = vision_key()
    if vk:
        os.environ["DASHSCOPE_API_KEY"] = vk
    os.environ["DASHSCOPE_BASE_URL"] = vision_base_url()
    os.environ["DASHSCOPE_VISION_MODEL"] = vision_model()


def masked(key: str) -> str:
    """用于界面显示：只露首尾。"""
    if not key:
        return ""
    if len(key) <= 10:
        return key[:2] + "***"
    return key[:6] + "..." + key[-4:]


def summary_for_ui() -> dict:
    tk = text_key()
    vk = vision_key()
    return {
        "text_key_set": bool(tk),
        "text_key_masked": masked(tk),
        "text_base_url": text_base_url(),
        "text_model": text_model(),
        "vision_key_set": bool(vk),
        "vision_key_masked": masked(vk),
        "vision_base_url": vision_base_url(),
        "vision_model": vision_model(),
        "vision_reuses_text": bool(tk) and tk == vk,
    }
