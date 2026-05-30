from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import BaseModel


class Task(BaseModel):
    __tablename__ = "tasks"

    key_id = Column(Integer, ForeignKey("keys.id", ondelete="SET NULL"), nullable=True)
    url = Column(String(500), nullable=False)
    email = Column(String(255), nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, done, failed
    file_path = Column(String(500), nullable=True)
    error_msg = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    key = relationship("Key", back_populates="tasks")

    def to_dict(self):
        return {
            "id": self.id,
            "key_id": self.key_id,
            "url": self.url,
            "email": self.email,
            "status": self.status,
            "file_path": self.file_path,
            "error_msg": self.error_msg,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
