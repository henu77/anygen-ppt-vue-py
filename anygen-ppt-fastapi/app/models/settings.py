from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from .base import BaseModel


class Settings(BaseModel):
    __tablename__ = "settings"

    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    type = Column(String(50), nullable=False)  # string, number, boolean, json

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "type": self.type,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
