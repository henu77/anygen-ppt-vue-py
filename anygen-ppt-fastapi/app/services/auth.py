from datetime import timedelta
from config import settings
from app.utils.jwt import create_access_token, verify_token
from loguru import logger


class AuthService:
    @staticmethod
    def verify_password(password: str) -> bool:
        """验证管理员密码"""
        return password == settings.ADMIN_PASSWORD

    @staticmethod
    def generate_token(admin_id: int = 1) -> str:
        """生成 JWT token"""
        data = {"sub": str(admin_id), "type": "admin"}
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        token = create_access_token(data, expires_delta)
        logger.info(f"生成 token 成功")
        return token

    @staticmethod
    def verify_token_valid(token: str) -> bool:
        """验证 token 有效性"""
        payload = verify_token(token)
        return payload is not None
