from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from datetime import datetime, timezone, timedelta

Base = declarative_base()

# 中国时区 UTC+8，不依赖系统时区
_CN_TZ = timezone(timedelta(hours=8))


def now_cn() -> datetime:
    """返回中国时间（UTC+8）"""
    return datetime.now(_CN_TZ).replace(tzinfo=None)


class BaseModel(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=now_cn, nullable=False)
    updated_at = Column(DateTime, default=now_cn, onupdate=now_cn)
