# -*- coding: utf-8 -*-
"""风控自动解锁：撞到 -2041 时，调用验证码流程拿 ticket。

优先使用仓库内置的 captcha/auto_unlock（跨平台、Docker 里可直接跑）；
若设置了 WXREAD_HOME 且存在旧的外部实现，则回退到它。
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
BUILTIN = os.path.join(HERE, "captcha", "auto_unlock.py")
HOME = os.getenv("WXREAD_HOME", "").strip()
_LOCK = threading.Lock()
_mod = None


def _load():
    global _mod
    if _mod is not None:
        return _mod

    for p in (HERE, os.path.join(HERE, "captcha")):
        if p not in sys.path:
            sys.path.insert(0, p)

    if os.path.exists(BUILTIN):
        capdir = os.path.join(HERE, "captcha")
        if capdir not in sys.path:
            sys.path.insert(0, capdir)
        spec = importlib.util.spec_from_file_location("wxread_auto_unlock", BUILTIN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _mod = mod
        return _mod

    if HOME:
        path = os.path.join(HOME, "auto_unlock.py")
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("wxread_auto_unlock", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _mod = mod
            return _mod

    raise FileNotFoundError("找不到验证码解锁实现（repo/captcha/auto_unlock.py）")


def unlock(wait: int = 240):
    """执行一次解锁，返回 (ticket, randstr) 或 None。"""
    if not _LOCK.acquire(blocking=False):
        logger.warning("已有解锁流程在跑，跳过")
        return None
    try:
        try:
            import ai_config
            ai_config.apply_to_env()
        except Exception:
            pass
        mod = _load()
        data = mod.solve(wait=wait)
        if data and data.get("ticket"):
            logger.info("验证码已通过，拿到 ticket")
            return data["ticket"], data.get("randstr", "")
        logger.warning("解锁没拿到 ticket")
        return None
    except Exception as exc:
        logger.warning("解锁流程异常: %s: %s", type(exc).__name__, str(exc)[:120])
        return None
    finally:
        _LOCK.release()
