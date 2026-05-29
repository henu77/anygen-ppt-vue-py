from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import BaseModel


class ScheduledTask(BaseModel):
    __tablename__ = "scheduled_tasks"

    name = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    interval_seconds = Column(Integer, nullable=False, default=3600)
    config = Column(JSON, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(20), nullable=True)  # success / failed / running
    last_run_message = Column(Text, nullable=True)
    run_count = Column(Integer, default=0, nullable=False)

    logs = relationship("ScheduledTaskLog", back_populates="task", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "config": self.config,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_status": self.last_run_status,
            "last_run_message": self.last_run_message,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ScheduledTaskLog(BaseModel):
    __tablename__ = "scheduled_task_logs"

    task_id = Column(Integer, ForeignKey("scheduled_tasks.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # success / failed
    message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=False)

    task = relationship("ScheduledTask", back_populates="logs")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
