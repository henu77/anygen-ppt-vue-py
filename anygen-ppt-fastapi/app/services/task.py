from datetime import datetime
from sqlalchemy.orm import Session
from app.models.task import Task
from app.models.key import Key
from loguru import logger


class TaskService:
    @staticmethod
    def create_task(db: Session, key_id: int, url: str, email: str) -> Task:
        """创建导出任务"""
        task = Task(key_id=key_id, url=url, email=email, status="pending")
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info(f"创建任务 {task.id} 成功")
        return task

    @staticmethod
    def get_task(db: Session, task_id: int) -> Task:
        """获取任务详情"""
        return db.query(Task).filter(Task.id == task_id).first()

    @staticmethod
    def list_tasks(db: Session, limit: int = 50, offset: int = 0) -> tuple[list[Task], int]:
        """分页获取任务列表"""
        total = db.query(Task).count()
        tasks = db.query(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset).all()
        return tasks, total

    @staticmethod
    def update_task_status(db: Session, task_id: int, status: str, error_msg: str = None, file_path: str = None) -> Task:
        """更新任务状态"""
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = status
            if error_msg:
                task.error_msg = error_msg
            if file_path:
                task.file_path = file_path
            if status in ["done", "failed"]:
                task.completed_at = datetime.utcnow()
            db.commit()
            logger.info(f"更新任务 {task_id} 状态为 {status}")
        return task

    @staticmethod
    def get_task_stats(db: Session) -> dict:
        """获取任务统计"""
        total = db.query(Task).count()
        pending = db.query(Task).filter(Task.status == "pending").count()
        processing = db.query(Task).filter(Task.status == "processing").count()
        done = db.query(Task).filter(Task.status == "done").count()
        failed = db.query(Task).filter(Task.status == "failed").count()

        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "done": done,
            "failed": failed,
        }

    @staticmethod
    def retry_task(db: Session, task_id: int) -> Task:
        """重试失败任务"""
        task = db.query(Task).filter(Task.id == task_id).first()
        if task and task.status == "failed":
            task.status = "pending"
            task.error_msg = None
            task.completed_at = None
            db.commit()
            logger.info(f"重试任务 {task_id}")
        return task

    @staticmethod
    def cleanup_tasks(db: Session, days: int = 7) -> int:
        """清理过期任务"""
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)
        count = db.query(Task).filter(Task.completed_at < cutoff_date).delete()
        db.commit()
        logger.info(f"清理 {count} 个过期任务")
        return count
