"""闲鱼 WebSocket 协议工具函数

来源于 app/utils/xianyu_utils.py，供 xianyu_live 模块使用。
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import struct
import time
from typing import Any, Dict, List


# ── Cookie 解析 ───────────────────────────────────────────


def trans_cookies(cookies_str: str) -> Dict[str, str]:
    """将 Cookie 字符串解析为字典"""
    if not cookies_str:
        raise ValueError("cookies不能为空")
    cookies = {}
    for cookie in cookies_str.split("; "):
        if "=" in cookie:
            key, value = cookie.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def get_user_id(cookies_str: str) -> str:
    """从 Cookie 中提取用户 ID（unb 字段）"""
    if not cookies_str:
        return ""
    cookie_map: Dict[str, str] = {}
    for cookie in cookies_str.split(";"):
        cookie = cookie.strip()
        if "=" not in cookie:
            continue
        key, value = cookie.split("=", 1)
        cookie_map[key.strip()] = value.strip()
    return str(cookie_map.get("unb") or cookie_map.get("munb") or "").strip()


# ── ID 生成 ───────────────────────────────────────────────


def generate_mid() -> str:
    """生成 LWP 协议消息 ID"""
    random_part = int(1000 * random.random())
    timestamp = int(time.time() * 1000)
    return f"{random_part}{timestamp} 0"


def generate_uuid() -> str:
    """生成消息 body.uuid"""
    timestamp = int(time.time() * 1000)
    return f"-{timestamp}1"


def generate_device_id(user_id: str) -> str:
    """生成设备 ID（UUID v4 格式，末尾附加 user_id）"""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []
    for i in range(36):
        if i in [8, 13, 18, 23]:
            result.append("-")
        elif i == 14:
            result.append("4")
        else:
            if i == 19:
                rand_val = int(16 * random.random())
                result.append(chars[(rand_val & 0x3) | 0x8])
            else:
                rand_val = int(16 * random.random())
                result.append(chars[rand_val])
    return "".join(result) + "-" + user_id


def generate_sign(t: str, token: str, data: str) -> str:
    """生成 mtop API 签名"""
    app_key = "34839810"
    msg = f"{token}&{t}&{app_key}&{data}"
    return hashlib.md5(msg.encode("utf-8")).hexdigest()


# ── MessagePack 解码器 ────────────────────────────────────


class MessagePackDecoder:
    """MessagePack 解码器的纯 Python 实现"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.length = len(data)

    def read_byte(self) -> int:
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")
        byte = self.data[self.pos]
        self.pos += 1
        return byte

    def read_bytes(self, count: int) -> bytes:
        if self.pos + count > self.length:
            raise ValueError("Unexpected end of data")
        result = self.data[self.pos : self.pos + count]
        self.pos += count
        return result

    def read_uint8(self) -> int:
        return self.read_byte()

    def read_uint16(self) -> int:
        return struct.unpack(">H", self.read_bytes(2))[0]

    def read_uint32(self) -> int:
        return struct.unpack(">I", self.read_bytes(4))[0]

    def read_uint64(self) -> int:
        return struct.unpack(">Q", self.read_bytes(8))[0]

    def read_int8(self) -> int:
        return struct.unpack(">b", self.read_bytes(1))[0]

    def read_int16(self) -> int:
        return struct.unpack(">h", self.read_bytes(2))[0]

    def read_int32(self) -> int:
        return struct.unpack(">i", self.read_bytes(4))[0]

    def read_int64(self) -> int:
        return struct.unpack(">q", self.read_bytes(8))[0]

    def read_float32(self) -> float:
        return struct.unpack(">f", self.read_bytes(4))[0]

    def read_float64(self) -> float:
        return struct.unpack(">d", self.read_bytes(8))[0]

    def read_string(self, length: int) -> str:
        return self.read_bytes(length).decode("utf-8")

    def decode_value(self) -> Any:
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")

        fmt = self.read_byte()

        if fmt <= 0x7F:
            return fmt
        elif 0x80 <= fmt <= 0x8F:
            return self.decode_map(fmt & 0x0F)
        elif 0x90 <= fmt <= 0x9F:
            return self.decode_array(fmt & 0x0F)
        elif 0xA0 <= fmt <= 0xBF:
            return self.read_string(fmt & 0x1F)
        elif fmt == 0xC0:
            return None
        elif fmt == 0xC2:
            return False
        elif fmt == 0xC3:
            return True
        elif fmt == 0xC4:
            return self.read_bytes(self.read_uint8())
        elif fmt == 0xC5:
            return self.read_bytes(self.read_uint16())
        elif fmt == 0xC6:
            return self.read_bytes(self.read_uint32())
        elif fmt == 0xCA:
            return self.read_float32()
        elif fmt == 0xCB:
            return self.read_float64()
        elif fmt == 0xCC:
            return self.read_uint8()
        elif fmt == 0xCD:
            return self.read_uint16()
        elif fmt == 0xCE:
            return self.read_uint32()
        elif fmt == 0xCF:
            return self.read_uint64()
        elif fmt == 0xD0:
            return self.read_int8()
        elif fmt == 0xD1:
            return self.read_int16()
        elif fmt == 0xD2:
            return self.read_int32()
        elif fmt == 0xD3:
            return self.read_int64()
        elif fmt == 0xD9:
            return self.read_string(self.read_uint8())
        elif fmt == 0xDA:
            return self.read_string(self.read_uint16())
        elif fmt == 0xDB:
            return self.read_string(self.read_uint32())
        elif fmt == 0xDC:
            return self.decode_array(self.read_uint16())
        elif fmt == 0xDD:
            return self.decode_array(self.read_uint32())
        elif fmt == 0xDE:
            return self.decode_map(self.read_uint16())
        elif fmt == 0xDF:
            return self.decode_map(self.read_uint32())
        elif fmt >= 0xE0:
            return fmt - 0x100

        raise ValueError(f"Unknown format byte: {fmt:02x}")

    def decode_array(self, size: int) -> List[Any]:
        return [self.decode_value() for _ in range(size)]

    def decode_map(self, size: int) -> Dict[Any, Any]:
        result = {}
        for _ in range(size):
            key = self.decode_value()
            value = self.decode_value()
            result[key] = value
        return result

    def decode(self) -> Any:
        return self.decode_value()


# ── 消息解密 ──────────────────────────────────────────────


def decrypt(data: str) -> str:
    """解密消息数据：base64 → MessagePack → JSON

    Args:
        data: Base64 编码的 MessagePack 数据

    Returns:
        解密后的 JSON 字符串

    Raises:
        Exception: 解密失败时抛出异常
    """
    if not isinstance(data, str):
        data = str(data)

    # 清理数据
    try:
        data.encode("ascii")
    except UnicodeEncodeError:
        data = data.encode("utf-8", errors="ignore").decode("ascii", errors="ignore")

    # Base64 解码（自动补 padding）
    try:
        decoded_data = base64.b64decode(data)
    except Exception:
        missing_padding = len(data) % 4
        if missing_padding:
            data += "=" * (4 - missing_padding)
        decoded_data = base64.b64decode(data)

    # MessagePack 解码
    decoder = MessagePackDecoder(decoded_data)
    decoded_value = decoder.decode()

    # 转换为 JSON 字符串
    if isinstance(decoded_value, dict):
        def _json_serializer(obj):
            if isinstance(obj, bytes):
                return obj.decode("utf-8", errors="ignore")
            raise TypeError(f"Type {type(obj)} not serializable")

        return json.dumps(decoded_value, default=_json_serializer, ensure_ascii=False)

    return str(decoded_value)
