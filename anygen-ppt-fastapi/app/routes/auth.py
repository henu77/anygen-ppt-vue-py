from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.auth import LoginRequest, AuthResponse
from app.services.auth import AuthService
from app.utils.jwt import extract_token_from_header, verify_token
from app.utils.response import ok
from loguru import logger

router = APIRouter(tags=["auth"])


@router.post("/auth")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """管理员登录"""
    if not AuthService.verify_password(request.password):
        logger.warning("登录失败: 密码错误")
        raise HTTPException(status_code=401, detail="密码错误")

    token = AuthService.generate_token()
    return ok(data={"valid": True, "token": token})


@router.get("/auth")
async def verify(authorization: str = Header(None), db: Session = Depends(get_db)):
    """验证 token 有效性"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供 token")

    token = extract_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token 格式错误")

    if not AuthService.verify_token_valid(token):
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    return ok(data={"valid": True})
