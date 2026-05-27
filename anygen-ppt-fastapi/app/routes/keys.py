from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.key import (
    KeyResponse,
    KeyListResponse,
    CreateKeysRequest,
    UpdateKeyRequest,
    BatchKeyRequest,
)
from app.services.key import KeyService
from app.utils.jwt import extract_token_from_header, verify_token
from loguru import logger

router = APIRouter(tags=["keys"])


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


@router.get("/keys", response_model=KeyListResponse)
async def list_keys(
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取卡密列表"""
    keys = KeyService.list_keys(db)
    key_responses = [
        KeyResponse(
            id=key.id,
            key=key.key,
            max_uses=key.max_uses,
            used_count=key.used_count,
            is_super=int(key.is_super),
            status=key.status,
            created_at=key.created_at.isoformat() if key.created_at else None,
            updated_at=key.updated_at.isoformat() if key.updated_at else None,
        )
        for key in keys
    ]
    return KeyListResponse(keys=key_responses)


@router.post("/keys", response_model=KeyListResponse)
async def create_keys(
    request: CreateKeysRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """创建卡密"""
    if request.count <= 0 or request.count > 1000:
        raise HTTPException(status_code=400, detail="创建数量必须在 1-1000 之间")

    if request.max_uses <= 0:
        raise HTTPException(status_code=400, detail="最大使用次数必须大于 0")

    keys = KeyService.create_keys(db, request.count, request.max_uses, request.is_super)
    key_responses = [
        KeyResponse(
            id=key.id,
            key=key.key,
            max_uses=key.max_uses,
            used_count=key.used_count,
            is_super=int(key.is_super),
            status=key.status,
            created_at=key.created_at.isoformat() if key.created_at else None,
            updated_at=key.updated_at.isoformat() if key.updated_at else None,
        )
        for key in keys
    ]
    logger.info(f"创建 {request.count} 个卡密成功")
    return KeyListResponse(keys=key_responses)


@router.patch("/keys/{key_id}", response_model=KeyResponse)
async def update_key(
    key_id: int,
    request: UpdateKeyRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """更新卡密状态"""
    key = KeyService.update_key_status(db, key_id, request.status)
    if not key:
        raise HTTPException(status_code=404, detail="卡密不存在")

    logger.info(f"更新卡密 {key_id} 状态为 {request.status}")
    return KeyResponse(
        id=key.id,
        key=key.key,
        max_uses=key.max_uses,
        used_count=key.used_count,
        is_super=int(key.is_super),
        status=key.status,
        created_at=key.created_at.isoformat() if key.created_at else None,
        updated_at=key.updated_at.isoformat() if key.updated_at else None,
    )


@router.delete("/keys/{key_id}")
async def delete_key(
    key_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """删除卡密"""
    if not KeyService.delete_key(db, key_id):
        raise HTTPException(status_code=404, detail="卡密不存在")

    logger.info(f"删除卡密 {key_id}")
    return {"message": "删除成功"}


@router.post("/keys/batch")
async def batch_update_keys(
    request: BatchKeyRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """批量操作卡密"""
    count = KeyService.batch_update_keys(db, request.action, request.ids, request.value)
    logger.info(f"批量 {request.action} 卡密 {count} 个")
    return {"message": f"成功处理 {count} 个卡密"}
