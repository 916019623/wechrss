# -*- coding: utf-8 -*-
"""微信读书 App 式续期（不依赖手机、不需要扫码）。

原理：用 deviceId + refreshToken 本地计算签名，POST /login 换新 accessToken。
签名算法复现自 libencrypt.so 的 nativeGetSignatures（详见 docs/token_rule.md）。

与 wechrss 原有的「Web 扫码会话续期」是两条独立通道：
  - Web 扫码：需要 skey，可长期无人值守，但初始必须人工扫码
  - App 式（本模块）：只需要 deviceId + refreshToken，首次播种后可长期自动换票
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import secrets
import time

import requests

logger = logging.getLogger(__name__)

BASE = "https://i.weread.qq.com"
GUEST_TOKEN = "5ecdcfd7f"
PROFILE = {
    "baseapi": "33",
    "appver": "10.2.2.10167650",
    "basever": "10.2.2.10167650",
    "osver": "13",
    "channelId": "0",
    "User-Agent": ("WeRead/10.2.2 WRBrand/other Dalvik/2.1.0 "
                   "(Linux; U; Android 13; Pixel 5 Build/TQ2A.230305.008.C1)"),
}

_PERMUTE = bytes.fromhex(
    "34 ca 55 40 1d b6 93 c6 31 30 29 35 32 a7 b8 11 c2 b5 16 fa 8b b1 24 a4 10 90 04 e9 08 f8 3b 8a "
    "9c 8c 44 f9 bc 5c 69 e2 a1 da d2 d3 75 89 f7 1e 2d 50 56 d7 72 53 bf 22 fb 20 0f 01 2e 45 87 6e "
    "66 48 f2 e0 cd fe 67 a9 43 f4 94 51 ce a5 4a ee 13 26 8e cc aa 33 14 5d 0e 39 bb cf 91 2b 81 4d "
    "ea 99 ec 1a 2c 85 c5 d9 36 74 4b 18 e1 f1 3d 9d 41 9f b4 17 0d d6 4c be dc af 97 28 77 f0 62 ff "
    "71 c1 c8 27 8f 6c 68 a8 9b e6 59 1c 1b 12 09 98 4e 3f 06 37 00 ba 1f 0a 19 2f c9 d5 d0 57 49 6f "
    "fd 25 e4 61 0c 42 cb 96 64 5f db ad 60 23 8d 9a 6d c3 c4 5e 3e b9 92 6a bd 5b 07 7f 76 95 ed 4f "
    "ab 84 7a 80 e7 78 c7 e5 eb 73 83 6b fc 38 46 7d 47 65 b3 52 63 3a 05 d1 ef a3 a6 de 9e 3c 02 ae "
    "b2 7b a0 f6 f3 2a c0 ac 86 03 5a 54 0b f5 82 d4 7e e3 df b0 d8 dd 21 e8 7c 88 a2 79 58 70 b7 15"
)
_SALT = b"5a6f1"


def _xor(b: bytes) -> int:
    return functools.reduce(lambda a, x: a ^ x, b, 0)


def _ror(b: bytes, n: int) -> bytes:
    if not b:
        return b
    n %= len(b)
    return b[-n:] + b[:-n]


def gen_signature(fields) -> str:
    elems = [bytes(_PERMUTE[c] for c in s.encode()) for s in fields] + [_SALT]
    elems.sort()
    m = b"".join(elems)
    h1 = hashlib.sha256(_ror(m, _xor(m) % 11)).hexdigest().encode()
    return hashlib.sha256(_ror(h1, _xor(h1) % 11)).hexdigest()


def refresh_signature(device_id: str, ts: int, rnd: int, refresh_token: str) -> str:
    return gen_signature([GUEST_TOKEN, device_id, str(ts), str(rnd), refresh_token])


def mint(credentials, *, timeout: float = 25.0):
    """用 deviceId + refreshToken 换新 accessToken。

    credentials: 需要 .deviceId / .refreshToken / .vid 属性。
    成功返回 (accessToken, refreshToken)，失败返回 None。
    """
    device_id = (getattr(credentials, "deviceId", "") or "").strip()
    refresh_token = (getattr(credentials, "refreshToken", "") or "").strip()
    if not device_id or not refresh_token:
        logger.warning("缺少 deviceId 或 refreshToken，无法 App 式续期")
        return None

    ts = int(time.time() * 1000)
    rnd = secrets.randbelow(1000)
    body = {
        "deviceId": device_id,
        "deviceName": getattr(credentials, "deviceName", "") or "Pixel 5",
        "inBackground": 0,
        "kickType": 0,
        "random": rnd,
        "refCgi": "",
        "refreshToken": refresh_token,
        "signature": refresh_signature(device_id, ts, rnd, refresh_token),
        "timestamp": ts,
        "trackId": "",
        "wxToken": 0,
        "virtualChannelId": "",
    }
    headers = dict(PROFILE)
    headers["Content-Type"] = "application/json; charset=UTF-8"
    try:
        resp = requests.post(BASE + "/login", headers=headers,
                             data=json.dumps(body, separators=(",", ":")).encode(),
                             timeout=timeout)
        payload = resp.json()
    except Exception as exc:
        logger.warning("App 式续期请求失败: %s", type(exc).__name__)
        return None

    token = payload.get("accessToken")
    if not token:
        logger.warning("App 式续期被拒: http=%s errcode=%s", resp.status_code, payload.get("errcode"))
        return None
    new_refresh = payload.get("refreshToken") or refresh_token
    logger.info("App 式续期成功: token=%s", token)
    return token, new_refresh
