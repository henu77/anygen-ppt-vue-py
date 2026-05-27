import re
from typing import Tuple


def validate_url(url: str) -> Tuple[bool, str]:
    """验证 URL 格式"""
    url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
    if re.match(url_pattern, url):
        return True, ""
    return False, "URL 格式不正确"


def validate_email(email: str) -> Tuple[bool, str]:
    """验证邮箱格式"""
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if re.match(email_pattern, email):
        return True, ""
    return False, "邮箱格式不正确"


def validate_key(key: str) -> Tuple[bool, str]:
    """验证卡密格式"""
    if not key or len(key) < 4:
        return False, "卡密格式不正确"
    return True, ""
