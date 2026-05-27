import json
import asyncio
from typing import AsyncGenerator
from sqlalchemy.orm import Session
from app.models.task import Task
from loguru import logger


async def stream_task_updates(task_id: int, db: Session) -> AsyncGenerator[str, None]:
    """SSE 流式更新任务状态"""
    try:
        while True:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            yield f"data: {json.dumps(task.to_dict())}\n\n"

            if task.status in ["done", "failed"]:
                break

            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"SSE 流式更新失败: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
