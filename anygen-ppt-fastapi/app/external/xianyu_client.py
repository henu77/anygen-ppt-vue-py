import httpx
import json
import time
import hashlib
from config import settings
from loguru import logger
import sys
import os

# 添加上级目录到路径，以便导入 manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from manager import QRLoginManager


def _get_h5_tk_token(cookies_str: str) -> str:
    """从 Cookie 字符串中提取 _m_h5_tk 的 token 部分"""
    for part in cookies_str.split(";"):
        part = part.strip()
        if part.startswith("_m_h5_tk=") or part.startswith("m_h5_tk="):
            value = part.split("=", 1)[1]
            return value.split("_")[0] if "_" in value else value
    return ""


class XianyuClient:
    H5API_BASE = "https://h5api.m.goofish.com/h5"

    def __init__(self):
        self.qr_manager = QRLoginManager()
        self.timeout = httpx.Timeout(
            connect=float(settings.XIANYU_TIMEOUT),
            read=float(settings.XIANYU_TIMEOUT),
            write=float(settings.XIANYU_TIMEOUT),
            pool=float(settings.XIANYU_TIMEOUT),
        )
        self.proxy = None

    async def generate_qr_code(self) -> dict:
        """生成二维码"""
        try:
            result = await self.qr_manager.generate_qr_code()
            logger.info(f"生成二维码成功: {result.get('session_id')}")
            return result
        except Exception as e:
            logger.error(f"生成二维码失败: {e}")
            return {"success": False, "message": str(e)}

    def check_login_status(self, session_id: str) -> dict:
        """检查登录状态"""
        try:
            result = self.qr_manager.get_session_status(session_id)
            logger.info(f"检查登录状态: {session_id} -> {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return {"status": "error", "message": str(e)}

    def get_session_cookies(self, session_id: str) -> dict:
        """获取会话 cookies"""
        try:
            result = self.qr_manager.get_session_cookies(session_id)
            if result:
                logger.info(f"获取会话 cookies 成功: {session_id}")
                return result
            return {"success": False, "message": "Session not found or not authenticated"}
        except Exception as e:
            logger.error(f"获取会话 cookies 失败: {e}")
            return {"success": False, "message": str(e)}

    async def _mtop_request(
        self,
        api: str,
        version: str,
        data: dict,
        cookies_str: str,
        type_: str = "originaljson",
    ) -> dict:
        """发起 mtop API 请求（参照 xianyu-api/xianyu_utils.py MtopClient）"""
        timestamp = str(int(time.time() * 1000))
        data_val = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        token = _get_h5_tk_token(cookies_str)

        if not token:
            logger.warning(f"mtop请求 [{api}]: _m_h5_tk 为空! Cookie前200字符: {cookies_str[:200]}")

        app_key = "34839810"
        sign = hashlib.md5(f"{token}&{timestamp}&{app_key}&{data_val}".encode()).hexdigest()

        params = {
            "jsv": "2.7.2",
            "appKey": app_key,
            "t": timestamp,
            "sign": sign,
            "v": version,
            "type": type_,
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": api,
            "sessionOption": "AutoLoginOnly",
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": cookies_str,
            "referer": "https://www.goofish.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36",
        }

        url = f"{self.H5API_BASE}/{api}/{version}/"

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, proxy=self.proxy, trust_env=False
        ) as client:
            resp = await client.post(
                url,
                params=params,
                data={"data": data_val},
                headers=headers,
            )
            return resp.json()

    async def verify_cookies(self, cookies: str) -> dict:
        """验证 cookies 是否有效，通过 mtop loginuser.get 接口

        使用 QR 登录时已获取的 _m_h5_tk 进行签名，直接调用 mtop 接口验证。
        如果 token 过期则自动重试（MtopClient 模式）。
        """
        api = "mtop.taobao.idlemessage.pc.loginuser.get"
        version = "1.0"
        data = {"bizScene": "home"}
        max_retry = 1

        for attempt in range(max_retry + 1):
            try:
                result = await self._mtop_request(api, version, data, cookies)

                ret = result.get("ret", [])
                ret_str = ret[0] if ret else ""
                logger.info(f"verify_cookies (attempt {attempt}): ret={ret_str}")

                if "SUCCESS" in ret_str.upper():
                    user_data = result.get("data", {})
                    nickname = user_data.get("nickname") or user_data.get("userNick") or ""
                    logger.info(f"[{nickname or '-'}] Cookies 验证有效")
                    return {
                        "valid": True,
                        "message": "Cookies 有效",
                        "nickname": nickname,
                        "user_data": user_data,
                    }

                if "SESSION_EXPIRED" in ret_str:
                    logger.warning(f"Cookies 已过期: {ret_str}")
                    return {"valid": False, "message": "Cookies 已过期，请重新登录"}

                # 令牌过期：重试（响应 Set-Cookie 可能包含新 token）
                if attempt < max_retry and (
                    "FAIL_SYS_TOKEN_EXOIRED" in ret_str
                    or "FAIL_SYS_TOKEN_EXPIRED" in ret_str
                ):
                    logger.info(f"令牌过期，重试 ({attempt + 1}/{max_retry})")
                    continue

                logger.warning(f"Cookies 验证失败: {ret_str}")
                return {"valid": False, "message": f"Cookies 无效: {ret_str}"}

            except Exception as e:
                logger.error(f"Cookies 验证异常 (attempt {attempt}): {e}")
                if attempt < max_retry:
                    continue
                return {"valid": False, "message": f"验证失败: {str(e)}"}

        return {"valid": False, "message": "Cookies 验证失败: 重试次数用尽"}

    async def confirm_delivery(self, order_no: str, cookies: str) -> bool:
        """确认发货"""
        logger.info(f"确认发货: {order_no}")
        return True

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        try:
            self.qr_manager.cleanup_expired_sessions()
            logger.info("清理过期会话成功")
        except Exception as e:
            logger.error(f"清理过期会话失败: {e}")


# 全局实例
xianyu_client = XianyuClient()
