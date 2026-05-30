"""
闲鱼扫码登录管理器

基于API接口实现二维码生成和Cookie获取
参照 xianyu-api/qr_login.py 重构
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
import uuid
from io import BytesIO
from random import random
from typing import Any, Dict, Optional

import httpx
import qrcode
import qrcode.constants
from loguru import logger

H5_TK_URL = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"
PASSPORT_HOST = "https://passport.goofish.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": "https://passport.goofish.com/",
    "Origin": "https://passport.goofish.com",
}


class GetLoginParamsError(Exception):
    """获取登录参数错误"""


class GetLoginQRCodeError(Exception):
    """获取登录二维码失败"""


class NotLoginError(Exception):
    """未登录错误"""


class QRLoginSession:
    """二维码登录会话"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.status = "waiting"  # waiting, scanned, success, expired, cancelled, verification_required
        self.qr_code_url: Optional[str] = None
        self.qr_content: Optional[str] = None
        self.cookies: Dict[str, str] = {}
        self.unb: Optional[str] = None
        self.created_time = time.time()
        self.expire_time = 300  # 5分钟过期
        self.params: Dict[str, Any] = {}
        self.verification_url: Optional[str] = None

    def is_expired(self) -> bool:
        return time.time() - self.created_time > self.expire_time

    def cookie_keys(self) -> str:
        """调试用：列出所有 Cookie 的 key"""
        return ", ".join(sorted(self.cookies.keys()))


class QRLoginManager:
    """二维码登录管理器"""

    def __init__(self):
        self.sessions: Dict[str, QRLoginSession] = {}
        self.timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=60.0)
        self.proxy: Optional[str] = None

    @staticmethod
    def _cookie_marshal(cookies: Dict[str, str]) -> str:
        """将Cookie字典转换为字符串"""
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    # ==================== 内部方法 ====================

    async def _get_mh5tk(self, session: QRLoginSession):
        """获取 m_h5_tk 和 m_h5_tk_enc（匿名会话令牌）

        第一次 GET 请求获取初始 Cookie，第二次 POST 确认会话。
        """
        data = {"bizScene": "home"}
        data_str = json.dumps(data, separators=(",", ":"))
        t = str(int(time.time() * 1000))
        app_key = "34839810"

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, proxy=self.proxy, trust_env=False
        ) as client:
            logger.info(f"是否使用代理{self.proxy}")
            # GET: 从 Set-Cookie 中获取 m_h5_tk
            resp = await client.get(H5_TK_URL, headers=HEADERS)
            cookies = {k: v for k, v in resp.cookies.items()}
            session.cookies.update(cookies)

            m_h5_tk = cookies.get("_m_h5_tk", "") or cookies.get("m_h5_tk", "")
            token = m_h5_tk.split("_")[0] if "_" in m_h5_tk else ""
            logger.info(f"_get_mh5tk GET: 获得 {len(cookies)} 个 Cookie, keys=[{', '.join(cookies.keys())}], m_h5_tk={'有' if m_h5_tk else '空'}")

            # POST: 用签名确认会话
            sign = hashlib.md5(f"{token}&{t}&{app_key}&{data_str}".encode()).hexdigest()
            params = {
                "jsv": "2.7.2", "appKey": app_key, "t": t, "sign": sign,
                "v": "1.0", "type": "originaljson", "dataType": "json",
                "timeout": 20000,
                "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
                "data": data_str,
            }
            resp2 = await client.post(
                H5_TK_URL, params=params, headers=HEADERS, cookies=session.cookies
            )
            # POST 响应可能更新 m_h5_tk
            post_cookies = {k: v for k, v in resp2.cookies.items()}
            if post_cookies:
                session.cookies.update(post_cookies)
                logger.info(f"_get_mh5tk POST: 更新了 {len(post_cookies)} 个 Cookie")
            logger.info(f"_get_mh5tk 完成: session.cookies keys=[{session.cookie_keys()}]")

    async def _get_login_params(self, session: QRLoginSession) -> Dict[str, Any]:
        """从登录页 HTML 中提取表单参数"""
        params = {
            "lang": "zh_cn", "appName": "xianyu", "appEntrance": "web",
            "styleType": "vertical", "bizParams": "",
            "notLoadSsoView": False, "notKeepLogin": False,
            "isMobile": False, "qrCodeFirst": False, "stie": 77, "rnd": random(),
        }

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.timeout, proxy=self.proxy, trust_env=False
        ) as client:
            resp = await client.get(
                f"{PASSPORT_HOST}/mini_login.htm",
                params=params, cookies=session.cookies, headers=HEADERS,
            )
            # 登录页可能返回新的 Cookie
            page_cookies = {k: v for k, v in resp.cookies.items()}
            if page_cookies:
                session.cookies.update(page_cookies)
                logger.info(f"_get_login_params: 页面返回了 {len(page_cookies)} 个 Cookie")

            match = re.search(r"window\.viewData\s*=\s*(\{.*?\});", resp.text)
            if not match:
                raise GetLoginParamsError("获取登录参数失败：未找到 viewData")

            view_data = json.loads(match.group(1))
            login_form = view_data.get("loginFormData")
            if not login_form:
                raise GetLoginParamsError("获取登录参数失败：未找到 loginFormData")

            login_form["umidTag"] = "SERVER"
            session.params.update(login_form)

    async def _monitor_qr_status(self, session_id: str):
        """后台监控二维码状态"""
        session = self.sessions.get(session_id)
        if not session:
            return

        logger.info(f"[{session_id[:8]}] 开始监控二维码状态")
        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < 300:
            try:
                if session_id not in self.sessions:
                    break

                poll_count += 1

                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=self.timeout, trust_env=False
                ) as client:
                    resp = await client.post(
                        f"{PASSPORT_HOST}/newlogin/qrcode/query.do",
                        data=session.params,
                        cookies=session.cookies,
                        headers=HEADERS,
                    )
                    result = resp.json()

                qr_status = (
                    result.get("content", {}).get("data", {}).get("qrCodeStatus")
                )

                if poll_count % 10 == 1:
                    logger.info(f"[{session_id[:8]}] 轮询#{poll_count}: status={qr_status}")

                if qr_status == "CONFIRMED":
                    data = result.get("content", {}).get("data", {})
                    logger.info(f"[{session_id[:8]}] 扫码确认! iframeRedirect={data.get('iframeRedirect')}")

                    if data.get("iframeRedirect") is True:
                        session.status = "verification_required"
                        session.verification_url = data.get("iframeRedirectUrl")
                        logger.warning(f"[{session_id[:8]}] 风控拦截，需要验证: {session.verification_url}")
                    else:
                        # 登录成功：从 query.do 响应中提取 Cookie，**合并**到已有 Cookie 中
                        resp_cookies = {k: v for k, v in resp.cookies.items()}
                        logger.info(f"[{session_id[:8]}] query.do 响应 Cookie: {list(resp_cookies.keys())}")

                        # 合并而非覆盖：保留 m_h5_tk 等早期获取的 Cookie
                        for k, v in resp_cookies.items():
                            session.cookies[k] = v
                            if k == "unb":
                                session.unb = v

                        m_h5_tk = session.cookies.get("_m_h5_tk", "") or session.cookies.get("m_h5_tk", "")
                        logger.info(
                            f"[{session_id[:8]}] 登录成功: unb={session.unb}, "
                            f"m_h5_tk={'有' if m_h5_tk else '缺失!'}, "
                            f"cookie keys=[{session.cookie_keys()}]"
                        )
                        session.status = "success"
                    break

                elif qr_status == "SCANED":
                    if session.status == "waiting":
                        session.status = "scanned"
                        logger.info(f"[{session_id[:8]}] 已扫码，等待确认")

                elif qr_status == "EXPIRED":
                    session.status = "expired"
                    logger.info(f"[{session_id[:8]}] 二维码已过期")
                    break

                elif qr_status is None or qr_status not in ("NEW", "SCANED"):
                    session.status = "cancelled"
                    logger.info(f"[{session_id[:8]}] 登录取消，qr_status={qr_status}")
                    break

                await asyncio.sleep(0.8)

            except Exception as e:
                logger.warning(f"[{session_id[:8]}] 轮询异常: {e}")
                await asyncio.sleep(2)

        if session.status not in ("success", "expired", "cancelled", "verification_required"):
            session.status = "expired"
            logger.info(f"[{session_id[:8]}] 监控超时，标记过期")

    # ==================== 公开接口 ====================

    async def generate_qr_code(self) -> Dict[str, Any]:
        """生成二维码"""
        try:
            session_id = str(uuid.uuid4())
            session = QRLoginSession(session_id)
            logger.info(f"[{session_id[:8]}] 开始生成二维码")

            # 步骤 1: 获取 m_h5_tk
            await self._get_mh5tk(session)
            logger.info(f"[{session_id[:8]}] 步骤1完成 - Cookie: [{session.cookie_keys()}]")

            # 步骤 2: 获取登录表单参数
            await self._get_login_params(session)
            logger.info(f"[{session_id[:8]}] 步骤2完成 - params keys: {list(session.params.keys())}")

            # 步骤 3: 请求生成二维码
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self.timeout, trust_env=False
            ) as client:
                resp = await client.get(
                    f"{PASSPORT_HOST}/newlogin/qrcode/generate.do",
                    params=session.params, headers=HEADERS,
                )
                results = resp.json()

                if results.get("content", {}).get("success") is not True:
                    logger.error(f"[{session_id[:8]}] 二维码接口返回失败")
                    return {"success": False, "message": "获取登录二维码失败"}

                data = results["content"]["data"]
                session.params.update({"t": data["t"], "ck": data["ck"]})
                session.qr_content = data["codeContent"]

                qr = qrcode.QRCode(
                    version=5,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10, border=2,
                )
                qr.add_data(session.qr_content)
                qr.make()
                buffer = BytesIO()
                qr.make_image().save(buffer, format="PNG")
                qr_base64 = base64.b64encode(buffer.getvalue()).decode()
                session.qr_code_url = f"data:image/png;base64,{qr_base64}"
                session.status = "waiting"

                self.sessions[session_id] = session
                asyncio.create_task(self._monitor_qr_status(session_id))

                logger.info(f"[{session_id[:8]}] 二维码生成成功，开始监控")
                return {
                    "success": True,
                    "session_id": session_id,
                    "qr_code_url": session.qr_code_url,
                }

        except httpx.ConnectTimeout as e:
            logger.error(f"连接超时: {e}")
            return {"success": False, "message": "连接超时，请检查网络或尝试使用代理"}
        except httpx.ReadTimeout as e:
            logger.error(f"读取超时: {e}")
            return {"success": False, "message": "读取超时，服务器响应过慢"}
        except httpx.ConnectError as e:
            logger.error(f"连接错误: {e}")
            return {"success": False, "message": "连接错误，请检查网络或代理设置"}
        except Exception as e:
            logger.exception("二维码生成过程中发生异常")
            return {"success": False, "message": f"生成二维码失败: {str(e)}"}

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        session = self.sessions.get(session_id)
        if not session:
            return {"status": "not_found"}

        if session.is_expired() and session.status != "success":
            session.status = "expired"

        result: Dict[str, Any] = {"status": session.status, "session_id": session_id}

        if session.status == "verification_required" and session.verification_url:
            result["verification_url"] = session.verification_url
            result["message"] = "账号被风控，需要手机验证"

        if session.status == "success" and session.cookies and session.unb:
            cookie_str = self._cookie_marshal(session.cookies)
            m_h5_tk = session.cookies.get("_m_h5_tk", "") or session.cookies.get("m_h5_tk", "")
            logger.info(
                f"[{session_id[:8]}] 返回 Cookie: {len(session.cookies)} 个, "
                f"m_h5_tk={'有' if m_h5_tk else '缺失!'}, unb={session.unb}, "
                f"keys=[{session.cookie_keys()}]"
            )
            result["cookies"] = cookie_str
            result["unb"] = session.unb

        return result

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        expired_sessions = [
            sid for sid, sess in self.sessions.items() if sess.is_expired()
        ]
        for session_id in expired_sessions:
            del self.sessions[session_id]
            logger.info(f"清理过期会话: {session_id}")

    def get_session_cookies(self, session_id: str) -> Optional[Dict[str, str]]:
        """获取会话Cookie"""
        session = self.sessions.get(session_id)
        if session and session.status == "success":
            return {"cookies": self._cookie_marshal(session.cookies), "unb": session.unb}
        return None


# 全局二维码登录管理器实例
qr_login_manager = QRLoginManager()
