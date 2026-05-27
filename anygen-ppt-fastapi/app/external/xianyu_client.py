import httpx
import asyncio
from config import settings
from loguru import logger
import sys
import os

# 添加上级目录到路径，以便导入 manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from manager import QRLoginManager


class XianyuClient:
    def __init__(self):
        self.qr_manager = QRLoginManager()
        self.timeout = httpx.Timeout(
            connect=float(settings.XIANYU_TIMEOUT),
            read=float(settings.XIANYU_TIMEOUT),
            write=float(settings.XIANYU_TIMEOUT),
            pool=float(settings.XIANYU_TIMEOUT),
        )
        self.proxy = settings.XIANYU_PROXY if settings.XIANYU_PROXY else None

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

    async def get_orders(self, cookies: str, account_id: str = None) -> list:
        """获取订单列表（使用 httpx）"""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, proxy=self.proxy
            ) as client:
                # 这里应该调用实际的闲鱼 API
                # 为了演示，返回空列表
                logger.info(f"获取订单列表: account_id={account_id}")
                return []
        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            return []

    async def confirm_delivery(self, order_no: str, cookies: str) -> bool:
        """确认发货"""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, proxy=self.proxy
            ) as client:
                # 这里应该调用实际的闲鱼 API
                logger.info(f"确认发货: order_no={order_no}")
                return True
        except Exception as e:
            logger.error(f"确认发货失败: {e}")
            return False

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        try:
            self.qr_manager.cleanup_expired_sessions()
            logger.info("清理过期会话成功")
        except Exception as e:
            logger.error(f"清理过期会话失败: {e}")


# 全局实例
xianyu_client = XianyuClient()
