from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest
from app.services.settings import SettingsService
from app.utils.jwt import extract_token_from_header, verify_token
from loguru import logger
from typing import List

router = APIRouter(tags=["settings"])


def verify_admin(authorization: str = Header(None)):
    """验证管理员权限"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供 token")

    token = extract_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token 格式错误")

    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    return payload


@router.get("/settings", response_model=List[SettingsResponse])
async def get_settings(
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取系统设置"""
    from app.models.settings import Settings

    settings = db.query(Settings).all()
    return [
        SettingsResponse(
            id=s.id,
            key=s.key,
            value=s.value,
            type=s.type,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )
        for s in settings
    ]


@router.put("/settings")
async def update_settings(
    request: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """更新系统设置"""
    count = SettingsService.update_multiple_settings(db, request.settings)
    logger.info(f"更新 {count} 个设置")
    return {"message": f"成功更新 {count} 个设置"}
