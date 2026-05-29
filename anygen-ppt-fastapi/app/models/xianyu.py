from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import BaseModel


class XianyuAccount(BaseModel):
    __tablename__ = "xianyu_accounts"

    account_id = Column(String(100), unique=True, nullable=False, index=True)
    unb = Column(String(255), nullable=True)
    nickname = Column(String(255), nullable=True)
    cookies = Column(Text, nullable=True)
    delivery_template = Column(Text, nullable=True)
    status = Column(String(50), default="active", nullable=False)  # active, disabled

    orders = relationship("XianyuOrder", back_populates="account")

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "unb": self.unb,
            "nickname": self.nickname,
            "delivery_template": self.delivery_template,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class XianyuOrder(BaseModel):
    __tablename__ = "xianyu_orders"

    order_no = Column(String(100), unique=True, nullable=False, index=True)
    account_id = Column(String(100), ForeignKey("xianyu_accounts.account_id"), nullable=False)
    status = Column(String(50), nullable=True)
    data = Column(JSON, nullable=True)

    account = relationship("XianyuAccount", back_populates="orders")

    def to_dict(self):
        return {
            "id": self.id,
            "order_no": self.order_no,
            "account_id": self.account_id,
            "status": self.status,
            "data": self.data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
