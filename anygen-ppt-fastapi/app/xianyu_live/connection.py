"""WebSocket 连接管理 — 连接 / 注册 / 心跳 / 重连

参考 websocket/app/services/xianyu/connection_manager.py
"""
import asyncio
import json
import random
import time

from loguru import logger

from .config import (
    WS_URL, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT,
    MAX_NETWORK_FAILURES, MAX_AUTH_FAILURES, APP_KEY,
)
from .crypto import generate_mid


class XianyuConnection:
    """单账户 WebSocket 连接管理"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.ws = None
        self.network_failures = 0
        self.auth_failures = 0
        self.last_heartbeat_time = 0.0
        self.last_heartbeat_response = 0.0
        self._connected_at = 0.0
        self._short_disconnect_times: list[float] = []

    # ── 连接 ──────────────────────────────────────────────

    async def connect(self, cookies_str: str) -> object:
        """建立 WebSocket 连接，返回 ws 对象"""
        import websockets

        headers = {"Cookie": cookies_str}
        ws_url = WS_URL

        try:
            ws = await websockets.connect(
                ws_url,
                extra_headers=headers,
                open_timeout=30,
                ping_interval=20,
                ping_timeout=15,
            )
            self.ws = ws
            self._connected_at = time.time()
            logger.info(f"[{self.account_id}] WebSocket 连接成功")
            return ws
        except Exception as e:
            self.network_failures += 1
            logger.error(f"[{self.account_id}] WebSocket 连接失败 ({self.network_failures}): {e}")
            raise

    # ── 注册 ──────────────────────────────────────────────

    async def register(self, ws, im_token: str, device_id: str) -> bool:
        """发送 /reg 注册 + /r/SyncStatus/ackDiff"""
        # 消息 1：注册
        reg_msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": APP_KEY,
                "token": im_token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": device_id,
                "mid": generate_mid(),
            },
        }
        await ws.send(json.dumps(reg_msg))
        logger.info(f"[{self.account_id}] 已发送 /reg 注册消息")

        # 消息 2：同步确认
        ts = int(time.time())
        ack_msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": ts * 1000,
                    "seq": 0,
                    "timestamp": ts,
                }
            ],
        }
        await ws.send(json.dumps(ack_msg))
        logger.info(f"[{self.account_id}] 已发送 SyncStatus/ackDiff")
        return True

    # ── 心跳 ──────────────────────────────────────────────

    async def heartbeat_loop(self, ws, stop_event: asyncio.Event):
        """后台心跳协程，每 15 秒发送一次，连续失败 3 次则退出"""
        consecutive_failures = 0
        max_failures = 3

        try:
            while not stop_event.is_set():
                try:
                    if ws.closed:
                        logger.warning(f"[{self.account_id}] WS 已关闭，停止心跳")
                        break

                    msg = {
                        "lwp": "/!",
                        "headers": {"mid": generate_mid()},
                    }
                    await asyncio.wait_for(ws.send(json.dumps(msg)), timeout=2.0)
                    self.last_heartbeat_time = time.time()
                    consecutive_failures = 0
                except asyncio.TimeoutError:
                    consecutive_failures += 1
                    logger.warning(f"[{self.account_id}] 心跳超时 ({consecutive_failures}/{max_failures})")
                    if consecutive_failures >= max_failures:
                        logger.error(f"[{self.account_id}] 心跳连续失败 {max_failures} 次，退出")
                        break
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"[{self.account_id}] 心跳异常 ({consecutive_failures}): {e}")
                    if consecutive_failures >= max_failures:
                        break

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
                    break  # stop_event 被设置
                except asyncio.TimeoutError:
                    pass  # 正常超时，继续下一次心跳
        except asyncio.CancelledError:
            pass
        finally:
            logger.info(f"[{self.account_id}] 心跳循环已退出")

    def is_heartbeat_response(self, message_data: dict) -> bool:
        """判断是否为心跳响应"""
        if "body" in message_data:
            return False
        if message_data.get("code") == 200:
            self.last_heartbeat_response = time.time()
            return True
        return False

    # ── 断连检测 ────────────────────────────────────────────

    def check_short_disconnect(self) -> bool:
        """检测短时间频繁断连，返回 True 表示应禁用账户"""
        duration = time.time() - self._connected_at
        if duration >= 30:
            self._short_disconnect_times.clear()
            return False

        now = time.time()
        self._short_disconnect_times.append(now)
        window_start = now - 300  # 5 分钟窗口
        self._short_disconnect_times = [t for t in self._short_disconnect_times if t >= window_start]

        if len(self._short_disconnect_times) >= 5:
            logger.error(f"[{self.account_id}] 5 分钟内频繁短连接断开 {len(self._short_disconnect_times)} 次")
            return True
        return False

    def should_disable(self) -> bool:
        """是否应禁用该账户"""
        return self.auth_failures >= MAX_AUTH_FAILURES

    def calc_retry_delay(self, error_msg: str = "") -> float:
        """计算重连延迟（指数退避 + 抖动）"""
        failures = max(1, self.network_failures)
        if "no close frame" in error_msg:
            base = min(2 ** failures, 30)
        elif "refused" in error_msg.lower() or "timeout" in error_msg.lower():
            base = min(2 * (2 ** failures), 90)
        else:
            base = min(2 ** failures, 45)
        jitter = random.uniform(0, base * 0.3)
        return round(base + jitter, 1)

    async def disconnect(self):
        """优雅断开"""
        if self.ws and not self.ws.closed:
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        logger.info(f"[{self.account_id}] WebSocket 已断开")
