from app.models.base import Base
from app.models.task import Task
from app.models.key import Key
from app.models.settings import Settings
from app.models.xianyu import XianyuAccount, XianyuOrder
from app.database.db import engine, SessionLocal
from loguru import logger
import json


def init_db():
    """初始化数据库"""
    logger.info("初始化数据库...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建成功")

    # 初始化默认设置
    init_default_settings()
    logger.info("数据库初始化完成")


def init_default_settings():
    """初始化默认设置"""
    db = SessionLocal()
    try:
        # 检查是否已初始化
        existing = db.query(Settings).first()
        if existing:
            logger.info("数据库已初始化，跳过默认设置")
            return

        # 创建默认设置
        default_settings = [
            Settings(key="app_name", value="Anygen PPT", type="string"),
            Settings(key="app_version", value="1.0.0", type="string"),
            Settings(key="max_concurrent_tasks", value="5", type="number"),
            Settings(key="task_timeout", value="3600", type="number"),
            Settings(key="enable_xianyu", value="false", type="boolean"),
        ]

        db.add_all(default_settings)
        db.commit()
        logger.info("默认设置初始化成功")
    except Exception as e:
        logger.error(f"初始化默认设置失败: {e}")
        db.rollback()
    finally:
        db.close()
