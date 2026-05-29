"""APScheduler 封装 — 定时任务生命周期管理"""
import asyncio
import importlib
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.models.base import now_cn
from loguru import logger

# task_type → 执行函数的映射
TASK_REGISTRY: dict[str, str] = {
    "xianyu_cookie_renew": "app.tasks.xianyu_cookie_renew.run",
}

scheduler = AsyncIOScheduler()


def _resolve_task_func(task_type: str):
    """根据 task_type 动态导入执行函数"""
    path = TASK_REGISTRY.get(task_type)
    if not path:
        return None
    module_path, func_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def _make_wrapper(task_id: int, task_type: str, config: dict):
    """生成 APScheduler 回调：执行任务 + 记录日志"""
    async def wrapper():
        from app.database.db import SessionLocal
        from app.services.scheduled_task import ScheduledTaskService

        func = _resolve_task_func(task_type)
        if not func:
            logger.error(f"未知任务类型: {task_type}")
            return

        db = SessionLocal()
        started_at = now_cn()
        t0 = asyncio.get_event_loop().time()
        try:
            ScheduledTaskService.update_task(db, task_id, last_run_status="running")
            db.commit()

            if asyncio.iscoroutinefunction(func):
                result = await func(config)
            else:
                result = func(config)

            duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
            status = result.get("status", "success")
            message = result.get("message", "")
            ScheduledTaskService.record_run(db, task_id, status, message, duration_ms, started_at)
        except Exception as e:
            duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
            logger.error(f"任务 [{task_id}] 执行异常: {e}")
            ScheduledTaskService.record_run(db, task_id, "failed", str(e), duration_ms, started_at)
        finally:
            db.close()

    return wrapper


def add_job(task_id: int, task_type: str, interval_seconds: int, config: dict = None):
    """向调度器添加一个任务"""
    job_id = f"scheduled_task_{task_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    wrapper = _make_wrapper(task_id, task_type, config or {})
    scheduler.add_job(
        wrapper,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id=job_id,
        name=f"task_{task_id}",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"注册定时任务: [{task_id}] type={task_type}, interval={interval_seconds}s")


def remove_job(task_id: int):
    """从调度器移除一个任务"""
    job_id = f"scheduled_task_{task_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"移除定时任务: [{task_id}]")


def pause_job(task_id: int):
    job_id = f"scheduled_task_{task_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.pause()


def resume_job(task_id: int):
    job_id = f"scheduled_task_{task_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.resume()


def update_job_interval(task_id: int, interval_seconds: int):
    """更新任务间隔"""
    job_id = f"scheduled_task_{task_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.reschedule(trigger=IntervalTrigger(seconds=interval_seconds))


def run_job_now(task_id: int):
    """手动触发一次任务"""
    job_id = f"scheduled_task_{task_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.modify(next_run_time=now_cn())


def start():
    """启动调度器，从数据库加载所有启用的任务"""
    from app.database.db import SessionLocal
    from app.models.scheduled_task import ScheduledTask

    db = SessionLocal()
    try:
        tasks = db.query(ScheduledTask).filter(ScheduledTask.enabled == True).all()
        for task in tasks:
            add_job(task.id, task.task_type, task.interval_seconds, task.config)
        logger.info(f"调度器启动，加载 {len(tasks)} 个任务")
    finally:
        db.close()

    scheduler.start()


def shutdown():
    scheduler.shutdown(wait=False)
    logger.info("调度器已停止")
