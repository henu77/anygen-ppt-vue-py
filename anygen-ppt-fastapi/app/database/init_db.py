from app.models.base import Base
from app.models.task import Task
from app.models.key import Key
from app.models.settings import Settings
from app.models.xianyu import XianyuAccount, XianyuOrder
from app.models.scheduled_task import ScheduledTask, ScheduledTaskLog
from app.database.db import engine, SessionLocal
from loguru import logger
import json


def init_db():
    """初始化数据库"""
    logger.info("初始化数据库...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建成功")

    # 数据库迁移
    migrate_db()
    logger.info("数据库迁移完成")

    # 初始化默认设置
    init_default_settings()
    logger.info("数据库初始化完成")


def migrate_db():
    """数据库迁移：为已有表添加新列"""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        # tasks.key_id 改为允许 NULL（删除卡密时保留任务）
        result = db.execute(text("PRAGMA table_info(tasks)"))
        columns = {row[1]: row for row in result.fetchall()}
        if "key_id" in columns and columns["key_id"][3] == 1:  # 1 = NOT NULL
            logger.info("迁移 tasks.key_id 为可空...")
            # 获取原表所有列名
            col_names = list(columns.keys())
            # 重命名旧表
            db.execute(text("ALTER TABLE tasks RENAME TO tasks_old"))
            # 创建新表（key_id 允许 NULL）
            db.execute(text("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    key_id INTEGER,
                    url VARCHAR(500) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    file_path VARCHAR(500),
                    error_msg TEXT,
                    completed_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            # 按列名复制数据
            cols_csv = ", ".join(col_names)
            db.execute(text(f"INSERT INTO tasks ({cols_csv}) SELECT {cols_csv} FROM tasks_old"))
            db.execute(text("DROP TABLE tasks_old"))
            db.commit()
            logger.info("tasks.key_id 迁移完成")
    except Exception as e:
        logger.warning(f"tasks 迁移检查: {e}")
        db.rollback()
    try:
        # 检查 xianyu_accounts 已有列
        result = db.execute(text("PRAGMA table_info(xianyu_accounts)"))
        columns = [row[1] for row in result.fetchall()]
        if "nickname" not in columns:
            db.execute(text("ALTER TABLE xianyu_accounts ADD COLUMN nickname VARCHAR(255)"))
            db.commit()
            logger.info("已为 xianyu_accounts 添加 nickname 列")
        if "auto_delivery" not in columns:
            db.execute(text("ALTER TABLE xianyu_accounts ADD COLUMN auto_delivery BOOLEAN DEFAULT 0"))
            db.commit()
            logger.info("已为 xianyu_accounts 添加 auto_delivery 列")
        if "auto_item_id" not in columns:
            db.execute(text("ALTER TABLE xianyu_accounts ADD COLUMN auto_item_id VARCHAR(100)"))
            db.commit()
            logger.info("已为 xianyu_accounts 添加 auto_item_id 列")
    except Exception as e:
        logger.warning(f"xianyu_accounts 迁移检查: {e}")
        db.rollback()

    # xianyu_orders 新列迁移
    try:
        result = db.execute(text("PRAGMA table_info(xianyu_orders)"))
        order_columns = [row[1] for row in result.fetchall()]
        new_order_cols = {
            "key_id": "INTEGER",
            "buyer_nick": "VARCHAR(100)",
            "amount": "VARCHAR(50)",
            "item_id": "VARCHAR(100)",
            "delivered_at": "DATETIME",
        }
        for col_name, col_type in new_order_cols.items():
            if col_name not in order_columns:
                db.execute(text(f"ALTER TABLE xianyu_orders ADD COLUMN {col_name} {col_type}"))
                db.commit()
                logger.info(f"已为 xianyu_orders 添加 {col_name} 列")
    except Exception as e:
        logger.warning(f"xianyu_orders 迁移检查: {e}")
        db.rollback()

    # 设置默认发货模板（为空的账户）
    try:
        default_template = "您的卡密为：{key}\n\n自助导出网站：https://caimaapi.ccwu.cc"
        result = db.execute(text("SELECT id, delivery_template FROM xianyu_accounts WHERE delivery_template IS NULL OR delivery_template = ''"))
        rows = result.fetchall()
        if rows:
            for row in rows:
                db.execute(text("UPDATE xianyu_accounts SET delivery_template = :t WHERE id = :id"), {"t": default_template, "id": row[0]})
            db.commit()
            logger.info(f"已为 {len(rows)} 个账户设置默认发货模板")
    except Exception as e:
        logger.warning(f"设置默认发货模板: {e}")
        db.rollback()

    db.close()


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
