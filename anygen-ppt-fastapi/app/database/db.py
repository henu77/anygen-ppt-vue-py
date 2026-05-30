from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
import os
from config import settings

# 创建数据库目录
os.makedirs("data", exist_ok=True)

# SQLite 数据库引擎
# 使用 NullPool 避免连接池导致的并发阻塞（SSE 长轮询会占住 StaticPool 的唯一连接）
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
)


# 启用 WAL 模式，允许并发读写
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
