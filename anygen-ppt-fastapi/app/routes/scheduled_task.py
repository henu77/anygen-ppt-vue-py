from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.scheduled_task import ScheduledTaskUpdateRequest
from app.services.scheduled_task import ScheduledTaskService
from app.utils.jwt import extract_token_from_header, verify_token
from app.utils.response import ok
from app import scheduler as task_scheduler
from loguru import logger

router = APIRouter(tags=["scheduled-tasks"])


def verify_admin(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供 token")
    token = extract_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token 格式错误")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    return payload


@router.get("/scheduled-tasks")
async def list_tasks(
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    tasks = ScheduledTaskService.list_tasks(db)
    return ok(data={"tasks": [t.to_dict() for t in tasks]})


@router.put("/scheduled-tasks/{task_id}")
async def update_task(
    task_id: int,
    request: ScheduledTaskUpdateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    task = ScheduledTaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.interval_seconds is not None:
        update_data["interval_seconds"] = request.interval_seconds
    if request.config is not None:
        update_data["config"] = request.config

    # 处理启用/禁用
    if request.enabled is not None:
        update_data["enabled"] = request.enabled
        if request.enabled:
            task_scheduler.resume_job(task_id)
            # 如果调度器中没有该任务（比如之前被删除了），重新添加
            if not task_scheduler.scheduler.get_job(f"scheduled_task_{task_id}"):
                interval = request.interval_seconds or task.interval_seconds
                task_scheduler.add_job(task_id, task.task_type, interval, task.config)
        else:
            task_scheduler.pause_job(task_id)

    if request.interval_seconds is not None and task.enabled:
        task_scheduler.update_job_interval(task_id, request.interval_seconds)

    updated = ScheduledTaskService.update_task(db, task_id, **update_data)
    logger.info(f"更新定时任务 [{task_id}]")
    return ok(data=updated.to_dict())


@router.post("/scheduled-tasks/{task_id}/run")
async def run_task(
    task_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    task = ScheduledTaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_scheduler.run_job_now(task_id)
    logger.info(f"手动触发定时任务 [{task_id}]")
    return ok(message="任务已触发")


@router.get("/scheduled-tasks/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    task = ScheduledTaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    logs = ScheduledTaskService.list_logs(db, task_id)
    return ok(data={"logs": [l.to_dict() for l in logs]})
