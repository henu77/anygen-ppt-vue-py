import json
import asyncio
from typing import AsyncGenerator
from app.database.db import SessionLocal
from app.models.task import Task
from loguru import logger


async def stream_task_updates(task_id: int, db=None) -> AsyncGenerator[str, None]:
    """SSE 流式更新任务状态"""
    try:
        while True:
            # 每次轮询创建新 session，避免长连接持有数据库锁
            session = SessionLocal()
            try:
                task = session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                    break

                yield f"data: {json.dumps(task.to_dict())}\n\n"
                status = task.status
            finally:
                session.close()

            if status in ["done", "failed"]:
                break

            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"SSE 流式更新失败: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
