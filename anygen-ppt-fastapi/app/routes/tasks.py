from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.task import TaskResponse, TaskListResponse, TaskStats
from app.services.task import TaskService
from app.utils.jwt import extract_token_from_header, verify_token
from loguru import logger

router = APIRouter(tags=["tasks"])


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


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """获取任务列表"""
    tasks, total = TaskService.list_tasks(db, limit, offset)
    stats = TaskService.get_task_stats(db)

    task_responses = [
        TaskResponse(
            id=task.id,
            key_id=task.key_id,
            url=task.url,
            email=task.email,
            status=task.status,
            file_path=task.file_path,
            error_msg=task.error_msg,
            created_at=task.created_at.isoformat() if task.created_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
        )
        for task in tasks
    ]

    return TaskListResponse(
        tasks=task_responses,
        stats=TaskStats(
            total=stats["total"],
            pending=stats["pending"],
            done=stats["done"],
            failed=stats["failed"],
        ),
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """获取任务详情"""
    task = TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskResponse(
        id=task.id,
        key_id=task.key_id,
        url=task.url,
        email=task.email,
        status=task.status,
        file_path=task.file_path,
        error_msg=task.error_msg,
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.post("/retry/{task_id}", response_model=TaskResponse)
async def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """重试失败任务"""
    task = TaskService.retry_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    logger.info(f"重试任务: {task_id}")
    return TaskResponse(
        id=task.id,
        key_id=task.key_id,
        url=task.url,
        email=task.email,
        status=task.status,
        file_path=task.file_path,
        error_msg=task.error_msg,
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.post("/cleanup")
async def cleanup_tasks(
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """清理过期任务"""
    count = TaskService.cleanup_tasks(db)
    logger.info(f"清理过期任务: {count} 个")
    return {"message": f"清理 {count} 个过期任务"}
