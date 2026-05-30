"""自动发货业务逻辑 + 三层并发控制

关键词触发 → mtop 验证订单状态 → 生成卡密 → 发消息 → 确认发货
"""
import asyncio
from weakref import WeakValueDictionary

from loguru import logger
from sqlalchemy import text

from .config import (
    MAX_CONCURRENT_DELIVERIES,
    ORDER_STATUS_WAIT_SELLER_SEND,
    ORDER_STATUS_WAIT_BUYER_PAY,
    ORDER_STATUS_TRADE_CLOSED,
)
from .message import MessageSender


class DeliveryService:
    """自动发货服务 — 并发安全"""

    def __init__(self, db_session_factory):
        self._db_factory = db_session_factory
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_DELIVERIES)
        self._order_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._delivered_orders: set[str] = set()  # 内存去重

    def _get_order_lock(self, order_id: str) -> asyncio.Lock:
        """懒创建订单级锁"""
        lock = self._order_locks.get(order_id)
        if lock is None:
            lock = asyncio.Lock()
            self._order_locks[order_id] = lock
        return lock

    def _is_delivered_in_db(self, order_id: str) -> bool:
        """查询 DB 是否已发货"""
        db = self._db_factory()
        try:
            result = db.execute(
                text("SELECT 1 FROM xianyu_orders WHERE order_no = :oid AND status = 'delivered'"),
                {"oid": order_id},
            )
            return result.fetchone() is not None
        finally:
            db.close()

    async def process_order(
        self,
        account_id: str,
        order_id: str,
        item_id: str | None,
        chat_id: str,
        buyer_id: str,
        ws,
        my_id: str,
        cookies_str: str,
        delivery_template: str,
        auto_item_id: str | None,
    ):
        """处理一个订单 — 三层防重 + 状态验证"""
        if not order_id:
            logger.warning(f"[{account_id}] 收到付款消息但无法提取 order_id，跳过")
            return

        # 第 1 层：内存去重
        if order_id in self._delivered_orders:
            logger.info(f"[{account_id}] 订单 {order_id} 已在内存去重中，跳过")
            return

        # 第 2 层：DB 去重
        if self._is_delivered_in_db(order_id):
            self._delivered_orders.add(order_id)
            logger.info(f"[{account_id}] 订单 {order_id} 已在 DB 中标记发货，跳过")
            return

        # 第 3 层：订单级锁 + 全局信号量
        async with self._semaphore:
            async with self._get_order_lock(order_id):
                # Double-check（锁内再查一次内存）
                if order_id in self._delivered_orders:
                    return
                await self._do_delivery(
                    account_id, order_id, item_id,
                    chat_id, buyer_id, ws, my_id,
                    cookies_str, delivery_template, auto_item_id,
                )

    async def _do_delivery(
        self,
        account_id: str,
        order_id: str,
        item_id: str | None,
        chat_id: str,
        buyer_id: str,
        ws,
        my_id: str,
        cookies_str: str,
        delivery_template: str,
        auto_item_id: str | None,
    ):
        """执行发货（在锁内调用）"""
        from app.external.xianyu_client import xianyu_client
        from app.services.key import KeyService

        sender = MessageSender(account_id)

        # ① mtop API 验证订单真实状态
        order_detail = await self._fetch_order_with_retry(cookies_str, order_id)
        if not order_detail:
            logger.warning(f"[{account_id}] 无法获取订单 {order_id} 详情，跳过")
            return

        # 如果 Set-Cookie 更新了 token，使用更新后的 cookies
        updated_cookies = order_detail.pop("updated_cookies", cookies_str)

        order_status = order_detail.get("order_status", "")
        if order_status != ORDER_STATUS_WAIT_SELLER_SEND:
            logger.info(f"[{account_id}] 订单 {order_id} 状态为 {order_status}，非待发货，跳过")
            return

        # ② 验证商品 ID 匹配
        detail_item_id = order_detail.get("item_id", "") or item_id or ""
        if auto_item_id and detail_item_id and detail_item_id != auto_item_id:
            logger.info(f"[{account_id}] 订单 {order_id} 商品 {detail_item_id} 不匹配自动发货商品 {auto_item_id}，跳过")
            return

        # ③ 从 API 响应提取买家信息
        buyer_nick = order_detail.get("buyer_nick", "") or ""
        amount = order_detail.get("total_amount", "") or ""

        # ④ 生成卡密
        db = self._db_factory()
        try:
            keys = KeyService.create_keys(db, count=1, max_uses=1)
            if not keys:
                # 无卡密：给买家发"处理中"消息
                logger.warning(f"[{account_id}] 订单 {order_id} 无可用卡密")
                if chat_id and buyer_id:
                    await sender.send_text(ws, chat_id, buyer_id, my_id, "订单已收到，正在处理中，请稍候...")
                self._save_pending_order(db, account_id, order_id, buyer_nick, amount, detail_item_id)
                return

            key_obj = keys[0]
            key_str = key_obj.key

            # ⑤ 渲染发货模板
            template = delivery_template or "您的卡密为：{key}\n\n自助导出网站：https://caimaapi.ccwu.cc"
            message_text = (
                template
                .replace("{key}", key_str)
                .replace("{buyer}", buyer_nick)
                .replace("{amount}", amount)
            )

            # ⑥ 发送消息
            sent = False
            if chat_id and buyer_id:
                sent = await sender.send_text(ws, chat_id, buyer_id, my_id, message_text)
            else:
                logger.warning(f"[{account_id}] 订单 {order_id} 无 chat_id/buyer_id，无法发送消息")

            # ⑦ 确认发货
            confirmed, final_cookies = await self._confirm_delivery_with_retry(updated_cookies, order_id)

            # ⑧ 保存到 DB（幂等）
            self._save_delivered_order(db, account_id, order_id, key_obj.id, buyer_nick, amount, detail_item_id)

            # ⑨ 标记内存去重
            self._delivered_orders.add(order_id)

            logger.info(f"[{account_id}] 订单 {order_id} 发货完成 (消息={'成功' if sent else '失败'}, 确认={'成功' if confirmed else '失败'})")

        except Exception as e:
            logger.error(f"[{account_id}] 订单 {order_id} 发货异常: {e}")
            db.rollback()
        finally:
            db.close()

    async def _fetch_order_with_retry(self, cookies_str: str, order_id: str, max_retry: int = 2) -> dict | None:
        """获取订单详情，失败重试"""
        from app.external.xianyu_client import xianyu_client

        current_cookies = cookies_str
        for attempt in range(max_retry + 1):
            try:
                result, current_cookies = await xianyu_client.fetch_order_detail(current_cookies, order_id)
                if result.get("success"):
                    detail = result.get("detail", {})
                    return {
                        "order_status": self._extract_status(detail),
                        "item_id": detail.get("item_id", ""),
                        "buyer_nick": detail.get("receiver_name", ""),
                        "total_amount": detail.get("price", ""),
                        "updated_cookies": current_cookies,
                    }
                logger.warning(f"[{order_id}] 获取订单详情失败 (attempt {attempt}): {result.get('error')}")
            except Exception as e:
                logger.warning(f"[{order_id}] 获取订单详情异常 (attempt {attempt}): {e}")
        return None

    def _extract_status(self, detail: dict) -> str:
        """从订单详情中提取状态"""
        status_nodes = detail.get("status_nodes", [])
        # 找到最后一个已完成的节点
        for node in reversed(status_nodes):
            if node.get("completed"):
                title = node.get("title", "")
                if "发货" in title or "待发货" in title:
                    return ORDER_STATUS_WAIT_SELLER_SEND
                if "付款" in title or "待付款" in title:
                    return ORDER_STATUS_WAIT_BUYER_PAY
                if "关闭" in title or "退款" in title:
                    return ORDER_STATUS_TRADE_CLOSED
                if "签收" in title or "完成" in title:
                    return "TRADE_FINISHED"
        return "UNKNOWN"

    async def _confirm_delivery_with_retry(self, cookies_str: str, order_id: str, max_retry: int = 2) -> tuple[bool, str]:
        """确认发货，失败重试，返回 (success, updated_cookies)"""
        from app.external.xianyu_client import xianyu_client

        current_cookies = cookies_str
        for attempt in range(max_retry + 1):
            try:
                success, current_cookies = await xianyu_client.confirm_delivery_api(current_cookies, order_id)
                if success:
                    return True, current_cookies
            except Exception as e:
                logger.warning(f"[{order_id}] 确认发货异常 (attempt {attempt}): {e}")
        return False, current_cookies

    def _save_delivered_order(self, db, account_id: str, order_id: str,
                              key_id: int, buyer_nick: str, amount: str, item_id: str):
        """幂等保存已发货订单"""
        try:
            from app.models.base import now_cn
            db.execute(
                text("""
                    INSERT INTO xianyu_orders (order_no, account_id, status, key_id, buyer_nick, amount, item_id, delivered_at)
                    VALUES (:oid, :acc, 'delivered', :kid, :bn, :amt, :iid, :dt)
                    ON CONFLICT(order_no) DO NOTHING
                """),
                {
                    "oid": order_id,
                    "acc": account_id,
                    "kid": key_id,
                    "bn": buyer_nick,
                    "amt": amount,
                    "iid": item_id,
                    "dt": now_cn(),
                },
            )
            db.commit()
        except Exception as e:
            logger.error(f"保存已发货订单失败: {e}")
            db.rollback()

    def _save_pending_order(self, db, account_id: str, order_id: str,
                            buyer_nick: str, amount: str, item_id: str):
        """保存待处理订单（无卡密）"""
        try:
            db.execute(
                text("""
                    INSERT INTO xianyu_orders (order_no, account_id, status, buyer_nick, amount, item_id)
                    VALUES (:oid, :acc, 'pending_key', :bn, :amt, :iid)
                    ON CONFLICT(order_no) DO NOTHING
                """),
                {
                    "oid": order_id,
                    "acc": account_id,
                    "bn": buyer_nick,
                    "amt": amount,
                    "iid": item_id,
                },
            )
            db.commit()
        except Exception as e:
            logger.error(f"保存待处理订单失败: {e}")
            db.rollback()
