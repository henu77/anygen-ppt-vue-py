"""消息解析、去重、ACK、发送

参考 websocket/app/services/xianyu/message_handler.py + xianyu_async.py send_msg
"""
import asyncio
import base64
import json
import re
import time

from loguru import logger

from .config import (
    PAYMENT_KEYWORDS, PENDING_PAYMENT_KEYWORDS, FETCH_DETAIL_MESSAGES,
    MESSAGE_DEDUP_EXPIRY, MESSAGE_DEDUP_MAX_SIZE,
    SEND_MSG_MAX_RETRY, SEND_MSG_RETRY_DELAY,
)
from .crypto import decrypt, generate_mid, generate_uuid


class MessageHandler:
    """消息解析 + 去重 + ACK"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self._processed_ids: dict[str, float] = {}  # message_id -> timestamp
        self._pending_mid: dict[str, asyncio.Future] = {}  # LWP 请求-响应关联

    # ── ACK ───────────────────────────────────────────────

    async def send_ack(self, ws, message_data: dict):
        """发送 ACK 响应（必须在处理消息前发送，否则服务端可能断连）"""
        headers = message_data.get("headers", {})
        ack = {
            "code": 200,
            "headers": {
                "mid": headers.get("mid", generate_mid()),
                "sid": headers.get("sid", ""),
            },
        }
        for key in ["app-key", "ua", "dt"]:
            if key in headers:
                ack["headers"][key] = headers[key]
        try:
            await ws.send(json.dumps(ack))
        except Exception as e:
            logger.warning(f"[{self.account_id}] ACK 发送失败: {e}")

    # ── 消息分发入口 ───────────────────────────────────────

    def dispatch_mid_response(self, message_data: dict) -> bool:
        """检查是否为 LWP 请求的响应（mid 匹配），是则 resolve future"""
        mid = message_data.get("headers", {}).get("mid")
        if mid and mid in self._pending_mid:
            future = self._pending_mid.pop(mid)
            if not future.done():
                future.set_result(message_data)
            return True
        return False

    async def handle_message(self, message_data: dict, ws) -> dict | None:
        """处理一条 WebSocket 消息，返回解析后的事件或 None

        返回格式：
        - {"type": "payment", "order_id": ..., "item_id": ..., "chat_id": ..., "buyer_id": ..., "reminder_content": ...}
        - {"type": "pending_payment", ...}
        - None（忽略的消息）
        """
        # Sync 包或单条消息
        messages = self._extract_messages(message_data)
        for msg in messages:
            event = self._classify_message(msg)
            if event:
                return event
        return None

    # ── 消息提取与解密 ────────────────────────────────────

    def _extract_messages(self, message_data: dict) -> list[dict]:
        """从原始消息中提取单条消息列表（处理 sync 包解密）"""
        body = message_data.get("body", {})
        sync_pkg = body.get("syncPushPackage")

        if sync_pkg and "data" in sync_pkg and sync_pkg["data"]:
            results = []
            for item in sync_pkg["data"]:
                try:
                    decoded = self._decrypt_item(item)
                    if decoded:
                        results.append(decoded)
                except Exception as e:
                    logger.warning(f"[{self.account_id}] 解密消息失败: {e}")
            return results
        return [message_data] if "body" in message_data else []

    def _decrypt_item(self, sync_data: dict) -> dict | None:
        """解密单条 sync 数据"""
        data = sync_data.get("data", "")
        if not data:
            return None

        # 策略 1：base64 解码
        try:
            decoded = base64.b64decode(data).decode("utf-8")
            parsed = json.loads(decoded)
            if isinstance(parsed, dict) and "chatType" in parsed:
                return None  # 系统消息，跳过
            return parsed
        except Exception:
            pass

        # 策略 2：AES 解密
        try:
            decrypted = json.loads(decrypt(data))
            return decrypted
        except Exception:
            pass

        return None

    # ── 消息分类 ───────────────────────────────────────────

    def _classify_message(self, message: dict) -> dict | None:
        """分类消息：chat / card_update / card，提取订单事件"""
        if not isinstance(message, dict):
            return None

        # 去重
        msg_id = self._extract_message_id(message)
        if msg_id:
            if self._is_duplicate(msg_id):
                return None

        m1 = message.get("1")
        if not isinstance(m1, dict):
            # card_update 类型（message["1"] 是 string）
            if isinstance(m1, str):
                return self._parse_card_update(message)
            return None

        # chat 类型
        m1_10 = m1.get("10", {})
        if not isinstance(m1_10, dict):
            return None

        reminder_content = m1_10.get("reminderContent", "")
        if not reminder_content:
            return None

        # 提取 chat_id / buyer_id
        chat_id = m1_10.get("conversationId", "") or m1_10.get("toId", "")
        buyer_id = m1_10.get("fromId", "")

        return self._classify_by_content(message, reminder_content, chat_id, buyer_id)

    def _classify_by_content(self, message: dict, content: str, chat_id: str, buyer_id: str) -> dict | None:
        """根据消息内容分类"""
        order_id = self._extract_order_id(message)
        item_id = self._extract_item_id(message)

        # 付款关键词 → 触发发货
        if any(kw in content for kw in PAYMENT_KEYWORDS):
            return {
                "type": "payment",
                "order_id": order_id,
                "item_id": item_id,
                "chat_id": chat_id,
                "buyer_id": buyer_id,
                "reminder_content": content,
            }

        # 仅拍下待付款 → 记录
        if any(kw in content for kw in PENDING_PAYMENT_KEYWORDS):
            return {
                "type": "pending_payment",
                "order_id": order_id,
                "item_id": item_id,
                "chat_id": chat_id,
                "buyer_id": buyer_id,
                "reminder_content": content,
            }

        return None

    def _parse_card_update(self, message: dict) -> dict | None:
        """解析卡片更新消息（message["1"] 是 string，message["4"] 有 reminderContent）"""
        m4 = message.get("4", {})
        if not isinstance(m4, dict):
            return None

        reminder_content = m4.get("reminderContent", "")
        if not reminder_content:
            return None

        order_id = self._extract_order_id(message)
        item_id = self._extract_item_id(message)

        if any(kw in reminder_content for kw in PAYMENT_KEYWORDS):
            return {
                "type": "payment",
                "order_id": order_id,
                "item_id": item_id,
                "chat_id": "",
                "buyer_id": "",
                "reminder_content": reminder_content,
            }

        return None

    # ── 去重 ───────────────────────────────────────────────

    def _extract_message_id(self, message: dict) -> str | None:
        """从消息中提取唯一 message_id"""
        try:
            m1 = message.get("1")
            if isinstance(m1, dict):
                m1_10 = m1.get("10", {})
                if isinstance(m1_10, dict):
                    # 从 bizTag 提取
                    biz_tag = m1_10.get("bizTag", "")
                    if biz_tag:
                        try:
                            tag = json.loads(biz_tag) if isinstance(biz_tag, str) else biz_tag
                            mid = tag.get("messageId")
                            if mid:
                                return str(mid)
                        except Exception:
                            pass
                    # 从 extJson 提取
                    ext = m1_10.get("extJson", "")
                    if ext:
                        try:
                            ext_obj = json.loads(ext) if isinstance(ext, str) else ext
                            mid = ext_obj.get("messageId")
                            if mid:
                                return str(mid)
                        except Exception:
                            pass

            # card_update 类型
            if isinstance(m1, str):
                m4 = message.get("4", {})
                if isinstance(m4, dict):
                    ext = m4.get("extJson", "")
                    if ext:
                        try:
                            ext_obj = json.loads(ext) if isinstance(ext, str) else ext
                            mid = ext_obj.get("messageId")
                            if mid:
                                return str(mid)
                        except Exception:
                            pass
        except Exception:
            pass
        return None

    def _is_duplicate(self, message_id: str) -> bool:
        """检查消息是否已处理过"""
        self._cleanup_old_ids()
        if message_id in self._processed_ids:
            return True
        self._processed_ids[message_id] = time.time()
        return False

    def _cleanup_old_ids(self):
        """清理过期的去重记录"""
        if len(self._processed_ids) > MESSAGE_DEDUP_MAX_SIZE:
            cutoff = time.time() - MESSAGE_DEDUP_EXPIRY
            self._processed_ids = {
                k: v for k, v in self._processed_ids.items() if v > cutoff
            }

    # ── 订单 ID / 商品 ID 提取 ────────────────────────────

    def _extract_order_id(self, message: dict) -> str | None:
        """从消息中提取订单 ID"""
        # 方式 1：结构化路径 message["1"]["6"]["3"]["5"] → JSON → URL
        try:
            m1_6_3_5 = message.get("1", {}).get("6", {}).get("3", {}).get("5", "")
            if m1_6_3_5:
                content_data = json.loads(m1_6_3_5)
                target_url = (
                    content_data.get("dxCard", {})
                    .get("item", {})
                    .get("main", {})
                    .get("exContent", {})
                    .get("button", {})
                    .get("targetUrl", "")
                )
                if target_url:
                    m = re.search(r"orderId[=:](\d{10,})", target_url)
                    if m:
                        return m.group(1)
        except Exception:
            pass

        # 方式 2：card_update 的 message["4"]
        try:
            m4 = message.get("4", {})
            if isinstance(m4, dict):
                ext = m4.get("extJson", "")
                if ext:
                    ext_obj = json.loads(ext) if isinstance(ext, str) else ext
                    oid = ext_obj.get("orderId") or ext_obj.get("bizOrderId")
                    if oid:
                        return str(oid)
        except Exception:
            pass

        # 方式 3：正则搜索整个消息
        try:
            raw = json.dumps(message, ensure_ascii=False)
            patterns = [
                r"orderId[=:](\d{10,})",
                r"order_detail\?id=(\d{10,})",
                r'"id"\s*:\s*"?(\d{10,})"?',
                r"bizOrderId[=:](\d{10,})",
            ]
            for p in patterns:
                m = re.search(p, raw)
                if m:
                    return m.group(1)
        except Exception:
            pass

        return None

    def _extract_item_id(self, message: dict) -> str | None:
        """从消息中提取商品 ID"""
        try:
            m1_10 = message.get("1", {}).get("10", {})
            if isinstance(m1_10, dict):
                # reminderUrl
                url = m1_10.get("reminderUrl", "")
                if url:
                    m = re.search(r"itemId[=:](\d+)", url)
                    if m:
                        return m.group(1)

                # bizTag
                biz_tag = m1_10.get("bizTag", "")
                if biz_tag:
                    try:
                        tag = json.loads(biz_tag) if isinstance(biz_tag, str) else biz_tag
                        iid = tag.get("itemId")
                        if iid:
                            return str(iid)
                    except Exception:
                        pass

                # extJson
                ext = m1_10.get("extJson", "")
                if ext:
                    try:
                        ext_obj = json.loads(ext) if isinstance(ext, str) else ext
                        iid = ext_obj.get("itemId")
                        if iid:
                            return str(iid)
                    except Exception:
                        pass

            # card JSON
            m1_6_3_5 = message.get("1", {}).get("6", {}).get("3", {}).get("5", "")
            if m1_6_3_5:
                content_data = json.loads(m1_6_3_5)
                jump_url = content_data.get("dxCard", {}).get("item", {}).get("main", {}).get("jumpUrl", "")
                if jump_url:
                    m = re.search(r"itemId[=:](\d+)", jump_url)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        return None


class MessageSender:
    """通过 LWP 协议发送消息"""

    def __init__(self, account_id: str):
        self.account_id = account_id

    async def send_text(self, ws, chat_id: str, user_id: str, my_id: str, text: str) -> bool:
        """发送文本消息，重试 SEND_MSG_MAX_RETRY 次"""
        content_inner = json.dumps({"contentType": 1, "text": {"text": text}}, ensure_ascii=False)
        content_b64 = base64.b64encode(content_inner.encode("utf-8")).decode("utf-8")

        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{chat_id}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": content_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {
                    "actualReceivers": [
                        f"{user_id}@goofish",
                        f"{my_id}@goofish",
                    ]
                },
            ],
        }
        return await self._send_with_retry(ws, msg, "文本")

    async def send_image(self, ws, chat_id: str, user_id: str, my_id: str, image_url: str) -> bool:
        """发送图片消息"""
        content_inner = json.dumps(
            {"contentType": 2, "pics": [{"url": image_url}]}, ensure_ascii=False
        )
        content_b64 = base64.b64encode(content_inner.encode("utf-8")).decode("utf-8")

        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{chat_id}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 2, "data": content_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {
                    "actualReceivers": [
                        f"{user_id}@goofish",
                        f"{my_id}@goofish",
                    ]
                },
            ],
        }
        return await self._send_with_retry(ws, msg, "图片")

    async def _send_with_retry(self, ws, msg: dict, label: str) -> bool:
        """发送 LWP 消息，失败重试"""
        for attempt in range(SEND_MSG_MAX_RETRY):
            try:
                if ws.closed:
                    logger.error(f"[{self.account_id}] {label}消息发送失败: WS 已关闭")
                    return False
                await ws.send(json.dumps(msg))
                logger.info(f"[{self.account_id}] {label}消息发送成功")
                return True
            except Exception as e:
                logger.warning(f"[{self.account_id}] {label}消息发送失败 ({attempt + 1}/{SEND_MSG_MAX_RETRY}): {e}")
                if attempt < SEND_MSG_MAX_RETRY - 1:
                    await asyncio.sleep(SEND_MSG_RETRY_DELAY)
        return False
