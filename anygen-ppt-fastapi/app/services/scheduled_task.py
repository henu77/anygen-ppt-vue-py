from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.scheduled_task import ScheduledTask, ScheduledTaskLog
from app.models.base import now_cn
from loguru import logger


class ScheduledTaskService:
    @staticmethod
    def list_tasks(db: Session) -> list[ScheduledTask]:
        return db.query(ScheduledTask).order_by(ScheduledTask.id).all()

    @staticmethod
    def get_task(db: Session, task_id: int) -> ScheduledTask:
        return db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()

    @staticmethod
    def get_task_by_type_and_config(db: Session, task_type: str, account_id: str) -> ScheduledTask:
        return db.query(ScheduledTask).filter(
            ScheduledTask.task_type == task_type,
            ScheduledTask.config["account_id"].as_string() == account_id,
        ).first()

    @staticmethod
    def create_task(db: Session, name: str, task_type: str, interval_seconds: int = 3600, config: dict = None) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            task_type=task_type,
            interval_seconds=interval_seconds,
            config=config or {},
            enabled=True,
            run_count=0,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info(f"创建定时任务: [{task.id}] {name}")
        return task

    @staticmethod
    def update_task(db: Session, task_id: int, **kwargs) -> ScheduledTask:
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key) and value is not None:
                setattr(task, key, value)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def delete_task(db: Session, task_id: int) -> bool:
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        if not task:
            return False
        db.delete(task)
        db.commit()
        logger.info(f"删除定时任务: [{task_id}]")
        return True

    @staticmethod
    def delete_by_type_and_account(db: Session, task_type: str, account_id: str) -> bool:
        task = db.query(ScheduledTask).filter(
            ScheduledTask.task_type == task_type,
            ScheduledTask.config["account_id"].as_string() == account_id,
        ).first()
        if not task:
            return False
        task_id = task.id
        db.delete(task)
        db.commit()
        logger.info(f"删除定时任务: [{task_id}] (账户: {account_id})")
        return True

    @staticmethod
    def record_run(db: Session, task_id: int, status: str, message: str, duration_ms: int, started_at: datetime):
        log = ScheduledTaskLog(
            task_id=task_id,
            status=status,
            message=message,
            duration_ms=duration_ms,
            started_at=started_at,
        )
        db.add(log)

        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        if task:
            task.last_run_at = now_cn()
            task.last_run_status = status
            task.last_run_message = message
            task.run_count = (task.run_count or 0) + 1
        db.commit()

    @staticmethod
    def list_logs(db: Session, task_id: int, limit: int = 50) -> list[ScheduledTaskLog]:
        return (
            db.query(ScheduledTaskLog)
            .filter(ScheduledTaskLog.task_id == task_id)
            .order_by(desc(ScheduledTaskLog.id))
            .limit(limit)
            .all()
        )
