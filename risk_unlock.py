# -*- coding: utf-8 -*-
"""风控自动解锁：撞到 -2041 时，调用电脑端验证码流程拿 ticket。

依赖同机的 wxread 工程（默认 G:\\code-deepseek\\wxread，可用环境变量 WXREAD_HOME 覆盖），
其中 auto_unlock.solve() 会：
  1. 启动有界面 Chrome 打开本地验证码页
  2. 用 Qwen3-VL-Plus 读题 + 判图
  3. 点击提交，拿到 ticket / randstr

返回 (ticket, randstr)；失败返回 None。
"""
from __future__ import annotations

import importlib.util
import logging
import os
import threading

logger = logging.getLogger(__name__)

HOME = os.getenv("WXREAD_HOME", r"G:\code-deepseek\wxread")
_LOCK = threading.Lock()


def _load_auto_unlock():
    path = os.path.join(HOME, "auto_unlock.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到 {path}，请设置 WXREAD_HOME")
    spec = importlib.util.spec_from_file_location("wxread_auto_unlock", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def unlock(wait: int = 300):
    """执行一次解锁，返回 (ticket, randstr) 或 None。"""
    if not _LOCK.acquire(blocking=False):
        logger.warning("已有解锁流程在跑，跳过")
        return None
    try:
        try:
            import ai_config
            ai_config.apply_to_env()      # 视觉模型的 key/模型名/endpoint 注入环境变量
        except Exception:
            pass
        mod = _load_auto_unlock()
        data = mod.solve(wait=wait)
        if data and data.get("ticket"):
            logger.info("验证码已通过，拿到 ticket")
            return data["ticket"], data.get("randstr", "")
        logger.warning("解锁没拿到 ticket")
        return None
    except Exception as exc:
        logger.warning("解锁流程异常: %s", type(exc).__name__)
        return None
    finally:
        _LOCK.release()
