from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import BaseModel


class Key(BaseModel):
    __tablename__ = "keys"

    key = Column(String(100), unique=True, nullable=False, index=True)
    max_uses = Column(Integer, nullable=False)
    used_count = Column(Integer, default=0, nullable=False)
    is_super = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), default="active", nullable=False)  # active, disabled, expired

    tasks = relationship("Task", back_populates="key")

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "max_uses": self.max_uses,
            "used_count": self.used_count,
            "is_super": int(self.is_super),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
