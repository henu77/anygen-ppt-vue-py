"""多账户 Worker 生命周期管理器"""
import asyncio

from loguru import logger

from .delivery import DeliveryService
from .worker import AccountWorker


class XianyuLiveManager:
    """管理所有账户的 Worker 生命周期"""

    def __init__(self, db_session_factory):
        self._db_factory = db_session_factory
        self._delivery_service = DeliveryService(db_session_factory)
        self._workers: dict[str, AccountWorker] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self):
        """启动：从 DB 加载所有 auto_delivery=True 的账户"""
        db = self._db_factory()
        try:
            from app.models.xianyu import XianyuAccount
            accounts = db.query(XianyuAccount).filter(
                XianyuAccount.auto_delivery == True,
                XianyuAccount.status == "active",
            ).all()

            for acc in accounts:
                await self.add_account(acc.account_id)

            logger.info(f"[LiveManager] 启动完成，加载 {len(accounts)} 个自动发货账户")
        finally:
            db.close()

    async def stop(self):
        """停止所有 Worker"""
        logger.info(f"[LiveManager] 正在停止 {len(self._workers)} 个 Worker...")

        for worker in self._workers.values():
            worker.stop()

        if self._tasks:
            done, pending = await asyncio.wait(
                list(self._tasks.values()), timeout=10
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        self._workers.clear()
        self._tasks.clear()
        logger.info("[LiveManager] 已停止")

    async def add_account(self, account_id: str):
        """动态添加账户"""
        if account_id in self._workers:
            logger.warning(f"[LiveManager] 账户 {account_id} 已存在，跳过")
            return

        worker = AccountWorker(account_id, self._db_factory, self._delivery_service)
        self._workers[account_id] = worker
        task = asyncio.create_task(worker.run())
        self._tasks[account_id] = task

        # task 完成时自动清理
        task.add_done_callback(lambda _t, aid=account_id: self._on_task_done(aid))

        logger.info(f"[LiveManager] 已添加账户 {account_id}")

    async def remove_account(self, account_id: str):
        """动态移除账户"""
        worker = self._workers.pop(account_id, None)
        if worker:
            worker.stop()

        task = self._tasks.pop(account_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info(f"[LiveManager] 已移除账户 {account_id}")

    async def restart_account(self, account_id: str):
        """重启单个账户（Cookie 更新后调用）"""
        await self.remove_account(account_id)
        await self.add_account(account_id)

    def is_running(self, account_id: str) -> bool:
        """检查账户是否在运行"""
        task = self._tasks.get(account_id)
        return task is not None and not task.done()

    def get_status(self) -> dict:
        """获取所有 Worker 状态"""
        return {
            aid: {
                "running": self.is_running(aid),
                "network_failures": w._conn.network_failures,
                "auth_failures": w._conn.auth_failures,
            }
            for aid, w in self._workers.items()
        }

    def _on_task_done(self, account_id: str):
        """Worker task 完成回调（自动清理）"""
        self._workers.pop(account_id, None)
        self._tasks.pop(account_id, None)
        logger.info(f"[LiveManager] 账户 {account_id} Worker 已退出并清理")
