"""单账户工作器 — WS 连接 + Token 管理 + 消息接收循环

参考 websocket/app/services/xianyu/xianyu_async.py 的 main() 方法
"""
import asyncio
import json
import time

from loguru import logger

from .config import (
    MAX_NETWORK_FAILURES, MAX_AUTH_FAILURES,
    IM_TOKEN_REFRESH_INTERVAL, IM_TOKEN_RETRY_INTERVAL,
    MESSAGE_SEMAPHORE_LIMIT,
)
from .connection import XianyuConnection
from .crypto import generate_device_id, get_user_id
from .delivery import DeliveryService
from .message import MessageHandler


class AccountWorker:
    """单个闲鱼账户的自动发货工作器"""

    def __init__(self, account_id: str, db_session_factory, delivery_service: DeliveryService):
        self.account_id = account_id
        self._db_factory = db_session_factory
        self._delivery = delivery_service
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._conn = XianyuConnection(account_id)
        self._msg_handler = MessageHandler(account_id)
        self._msg_semaphore = asyncio.Semaphore(MESSAGE_SEMAPHORE_LIMIT)

        # 账户运行时信息
        self._cookies_str: str = ""
        self._im_token: str = ""
        self._device_id: str = ""
        self._my_id: str = ""  # 自己的 user_id
        self._delivery_template: str = ""
        self._auto_item_id: str | None = None

    async def run(self):
        """主循环 — 连接 / 注册 / 接收 / 重连"""
        logger.info(f"[{self.account_id}] Worker 启动")

        while not self._stop_event.is_set():
            try:
                # 加载账户信息
                if not self._load_account():
                    logger.info(f"[{self.account_id}] 账户不存在或已禁用，停止 Worker")
                    break

                # 获取 IM Token
                token = await self._get_or_refresh_token()
                if not token:
                    logger.warning(f"[{self.account_id}] 获取 IM Token 失败，等待重试")
                    await self._interruptible_sleep(IM_TOKEN_RETRY_INTERVAL)
                    self._conn.auth_failures += 1
                    if self._conn.should_disable():
                        await self._disable_account("IM Token 获取失败次数过多")
                        break
                    continue

                self._im_token = token
                self._conn.auth_failures = 0

                # 建立 WebSocket
                ws = await self._conn.connect(self._cookies_str)
                self._conn.network_failures = 0

                # 注册
                await self._conn.register(ws, self._im_token, self._device_id)

                # 启动心跳
                heartbeat_stop = asyncio.Event()
                heartbeat_task = asyncio.create_task(
                    self._conn.heartbeat_loop(ws, heartbeat_stop)
                )

                # 启动 Token 刷新
                token_task = asyncio.create_task(
                    self._token_refresh_loop(ws, heartbeat_stop)
                )

                # 进入消息接收循环
                try:
                    await self._receive_loop(ws)
                finally:
                    heartbeat_stop.set()
                    for t in [heartbeat_task, token_task]:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                logger.info(f"[{self.account_id}] Worker 收到取消信号")
                break
            except Exception as e:
                self._conn.network_failures += 1
                logger.error(f"[{self.account_id}] Worker 异常 ({self._conn.network_failures}): {e}")

                if self._conn.network_failures >= MAX_NETWORK_FAILURES:
                    await self._disable_account("网络失败次数过多")
                    break

                delay = self._conn.calc_retry_delay(str(e))
                logger.info(f"[{self.account_id}] {delay}s 后重连")
                await self._interruptible_sleep(delay)
            finally:
                await self._conn.disconnect()

        logger.info(f"[{self.account_id}] Worker 已停止")

    async def _receive_loop(self, ws):
        """消息接收循环"""
        try:
            async for raw_message in ws:
                if self._stop_event.is_set():
                    break

                try:
                    message_data = json.loads(raw_message)
                except Exception:
                    continue

                # 心跳响应 → 跳过
                if self._conn.is_heartbeat_response(message_data):
                    continue

                # LWP 请求响应 → resolve future
                if self._msg_handler.dispatch_mid_response(message_data):
                    continue

                # 普通消息 → 异步处理（信号量控制并发）
                asyncio.create_task(
                    self._handle_with_semaphore(message_data, ws)
                )
        except Exception as e:
            logger.warning(f"[{self.account_id}] 接收循环退出: {e}")

    async def _handle_with_semaphore(self, message_data: dict, ws):
        """信号量控制的消息处理"""
        async with self._msg_semaphore:
            try:
                # 发送 ACK
                await self._msg_handler.send_ack(ws, message_data)

                # 解析消息
                event = await self._msg_handler.handle_message(message_data, ws)
                if not event:
                    return

                # 付款消息 → 触发发货
                if event["type"] == "payment":
                    logger.info(f"[{self.account_id}] 检测到付款: order={event.get('order_id')}, content={event.get('reminder_content', '')[:50]}")
                    asyncio.create_task(
                        self._delivery.process_order(
                            account_id=self.account_id,
                            order_id=event.get("order_id", ""),
                            item_id=event.get("item_id"),
                            chat_id=event.get("chat_id", ""),
                            buyer_id=event.get("buyer_id", ""),
                            ws=ws,
                            my_id=self._my_id,
                            cookies_str=self._cookies_str,
                            delivery_template=self._delivery_template,
                            auto_item_id=self._auto_item_id,
                        )
                    )
                elif event["type"] == "pending_payment":
                    logger.info(f"[{self.account_id}] 检测到待付款: order={event.get('order_id')}")

            except Exception as e:
                logger.error(f"[{self.account_id}] 消息处理异常: {e}")

    # ── Token 管理 ──────────────────────────────────────────

    async def _get_or_refresh_token(self) -> str | None:
        """获取 IM Token"""
        from app.external.xianyu_client import xianyu_client
        token, updated_cookies = await xianyu_client.get_im_token(self._cookies_str, self._my_id)
        # 如果 Set-Cookie 更新了 token，同步到内存
        if updated_cookies != self._cookies_str:
            self._cookies_str = updated_cookies
        return token

    async def _token_refresh_loop(self, ws, stop_event: asyncio.Event):
        """定期刷新 IM Token（每 20 小时）"""
        try:
            while not stop_event.is_set():
                try:
                    await self._interruptible_sleep(IM_TOKEN_REFRESH_INTERVAL)
                    if stop_event.is_set():
                        break

                    new_token = await self._get_or_refresh_token()
                    if new_token:
                        self._im_token = new_token
                        logger.info(f"[{self.account_id}] IM Token 已刷新")
                    else:
                        logger.warning(f"[{self.account_id}] IM Token 刷新失败")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"[{self.account_id}] Token 刷新异常: {e}")
                    await self._interruptible_sleep(IM_TOKEN_RETRY_INTERVAL)
        except asyncio.CancelledError:
            pass

    # ── 账户管理 ────────────────────────────────────────────

    def _load_account(self) -> bool:
        """从 DB 加载账户信息，返回是否可继续运行"""
        db = self._db_factory()
        try:
            from app.models.xianyu import XianyuAccount
            account = db.query(XianyuAccount).filter(
                XianyuAccount.account_id == self.account_id
            ).first()
            if not account:
                return False
            if account.status != "active":
                return False
            if not account.cookies:
                return False

            self._cookies_str = account.cookies
            self._my_id = get_user_id(account.cookies) or account.unb or ""
            self._device_id = generate_device_id(self._my_id)
            self._delivery_template = account.delivery_template or ""
            self._auto_item_id = account.auto_item_id
            return True
        finally:
            db.close()

    async def _disable_account(self, reason: str):
        """禁用账户"""
        logger.error(f"[{self.account_id}] 禁用账户: {reason}")
        db = self._db_factory()
        try:
            from app.models.xianyu import XianyuAccount
            account = db.query(XianyuAccount).filter(
                XianyuAccount.account_id == self.account_id
            ).first()
            if account:
                account.status = "disabled"
                db.commit()
        finally:
            db.close()
        self._stop_event.set()

    def stop(self):
        """通知 Worker 停止"""
        self._stop_event.set()

    def _interruptible_sleep(self, seconds: float):
        """可中断的 sleep"""
        async def _sleep():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            except asyncio.TimeoutError:
                pass
        return _sleep()
