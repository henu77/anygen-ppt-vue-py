from sqlalchemy.orm import Session
from app.models.task import Task
from app.services.task import TaskService
from loguru import logger


class ExportService:
    @staticmethod
    async def export_ppt(task_id: int, db: Session) -> bool:
        """导出 PPT（模拟）"""
        try:
            task = TaskService.get_task(db, task_id)
            if not task:
                return False

            # 更新任务状态为处理中
            TaskService.update_task_status(db, task_id, "processing")

            # 这里应该调用实际的导出服务
            # 例如：file_path = await call_ppt_export_api(task.url)
            # 为了演示，我们模拟一个成功的导出
            logger.info(f"开始导出任务 {task_id}: {task.url}")

            # 模拟导出完成
            file_path = f"/downloads/task_{task_id}.pptx"
            TaskService.update_task_status(db, task_id, "done", file_path=file_path)

            logger.info(f"导出任务 {task_id} 成功: {file_path}")
            return True

        except Exception as e:
            logger.error(f"导出任务 {task_id} 失败: {e}")
            TaskService.update_task_status(db, task_id, "failed", error_msg=str(e))
            return False

    @staticmethod
    async def process_export_task(task_id: int, db: Session):
        """后台处理导出任务"""
        await ExportService.export_ppt(task_id, db)
