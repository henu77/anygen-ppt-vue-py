from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Boolean
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
    auto_delivery = Column(Boolean, default=False, nullable=False)  # 是否开启自动发货
    auto_item_id = Column(String(100), nullable=True)              # 自动发货的商品 ID

    orders = relationship("XianyuOrder", back_populates="account")

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "unb": self.unb,
            "nickname": self.nickname,
            "delivery_template": self.delivery_template,
            "status": self.status,
            "auto_delivery": self.auto_delivery,
            "auto_item_id": self.auto_item_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class XianyuOrder(BaseModel):
    __tablename__ = "xianyu_orders"

    order_no = Column(String(100), unique=True, nullable=False, index=True)
    account_id = Column(String(100), ForeignKey("xianyu_accounts.account_id"), nullable=False)
    status = Column(String(50), nullable=True)
    data = Column(JSON, nullable=True)
    key_id = Column(Integer, nullable=True)                # 关联的卡密 ID
    buyer_nick = Column(String(100), nullable=True)         # 买家昵称
    amount = Column(String(50), nullable=True)              # 订单金额
    item_id = Column(String(100), nullable=True)            # 商品 ID
    delivered_at = Column(DateTime, nullable=True)          # 发货时间

    account = relationship("XianyuAccount", back_populates="orders")

    def to_dict(self):
        return {
            "id": self.id,
            "order_no": self.order_no,
            "account_id": self.account_id,
            "status": self.status,
            "data": self.data,
            "key_id": self.key_id,
            "buyer_nick": self.buyer_nick,
            "amount": self.amount,
            "item_id": self.item_id,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
