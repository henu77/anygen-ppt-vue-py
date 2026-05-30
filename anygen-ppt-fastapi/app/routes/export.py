from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.key import Key
from app.schemas.task import ExportRequest, ExportResponse
from app.services.task import TaskService
from app.services.key import KeyService
from app.services.export import ExportService
from app.utils.validators import validate_url, validate_email, validate_key
from app.utils.sse import stream_task_updates
from app.utils.response import ok
from loguru import logger
import os

router = APIRouter(tags=["export"])


@router.post("/export")
async def submit_export(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """提交导出任务"""
    # 验证输入
    valid, msg = validate_url(request.url)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    valid, msg = validate_email(request.email)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    valid, msg = validate_key(request.key)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    # 检查卡密
    key_info = KeyService.check_key(db, request.key)
    if not key_info.get("valid"):
        logger.warning(f"卡密检查失败: {request.key} - {key_info.get('message')}")
        raise HTTPException(status_code=400, detail=key_info.get("message"))

    # 获取卡密 ID
    key = db.query(Key).filter(Key.key == request.key).first()
    if not key:
        raise HTTPException(status_code=400, detail="卡密不存在")

    # 创建任务
    task = TaskService.create_task(db, key.id, request.url, request.email)

    # 后台处理导出（卡密在导出成功后才消耗，失败不浪费次数）
    background_tasks.add_task(ExportService.export_ppt, task.id, db, request.key)

    logger.info(f"提交导出任务成功: {task.id}")
    return ok(data={"taskId": task.id, "status": "pending"})


@router.get("/download/{task_id}")
async def download_file(task_id: int, db: Session = Depends(get_db)):
    """下载 PPT 文件"""
    task = TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != "done":
        raise HTTPException(status_code=400, detail="任务未完成")

    if not task.file_path or not os.path.exists(task.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    logger.info(f"下载文件: {task_id}")
    return FileResponse(task.file_path, filename=f"export_{task_id}.pptx")


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: int, db: Session = Depends(get_db)):
    """SSE 实时任务更新"""
    task = TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    logger.info(f"开始 SSE 流式更新: {task_id}")
    return StreamingResponse(
        stream_task_updates(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
