from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.key import KeyInfoResponse
from app.services.key import KeyService
from app.utils.response import ok
from loguru import logger

router = APIRouter(tags=["query"])


@router.get("/query")
async def check_key(key: str, db: Session = Depends(get_db)):
    """查询卡密信息"""
    if not key:
        raise HTTPException(status_code=400, detail="卡密不能为空")

    key_info = KeyService.check_key(db, key)
    if not key_info.get("valid"):
        logger.warning(f"卡密查询失败: {key}")
        raise HTTPException(status_code=400, detail=key_info.get("message"))

    logger.info(f"卡密查询成功: {key}")
    return ok(data={
        "status": key_info.get("status"),
        "max_uses": key_info.get("max_uses"),
        "used_count": key_info.get("used_count"),
        "is_super": key_info.get("is_super"),
    })
