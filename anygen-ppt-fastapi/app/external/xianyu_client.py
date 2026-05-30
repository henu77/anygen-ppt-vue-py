import httpx
import json
import re
import time
import hashlib
from config import settings
from loguru import logger
from app.utils.qr_login import QRLoginManager


def _get_h5_tk_token(cookies_str: str) -> str:
    """从 Cookie 字符串中提取 _m_h5_tk 的 token 部分"""
    for part in cookies_str.split(";"):
        part = part.strip()
        if part.startswith("_m_h5_tk=") or part.startswith("m_h5_tk="):
            value = part.split("=", 1)[1]
            return value.split("_")[0] if "_" in value else value
    return ""


def _merge_cookies(original: str, new_cookies: dict) -> str:
    """将 Set-Cookie 中的新字段合并到现有 Cookie 字符串"""
    existing = {}
    for part in original.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            existing[k.strip()] = v.strip()
    existing.update(new_cookies)
    return "; ".join(f"{k}={v}" for k, v in existing.items())


def _extract_set_cookies(resp) -> dict:
    """从 httpx Response 提取 Set-Cookie 头中的 cookie 键值对"""
    result = {}
    for header_value in resp.headers.get_list("set-cookie"):
        if "=" in header_value:
            name, value = header_value.split(";")[0].split("=", 1)
            result[name.strip()] = value.strip()
    return result


class XianyuClient:
    H5API_BASE = "https://h5api.m.goofish.com/h5"

    def __init__(self):
        self.qr_manager = QRLoginManager()
        self.timeout = httpx.Timeout(
            connect=float(settings.XIANYU_TIMEOUT),
            read=float(settings.XIANYU_TIMEOUT),
            write=float(settings.XIANYU_TIMEOUT),
            pool=float(settings.XIANYU_TIMEOUT),
        )
        self.proxy = None

    async def generate_qr_code(self) -> dict:
        """生成二维码"""
        try:
            result = await self.qr_manager.generate_qr_code()
            logger.info(f"生成二维码成功: {result.get('session_id')}")
            return result
        except Exception as e:
            logger.error(f"生成二维码失败: {e}")
            return {"success": False, "message": str(e)}

    def check_login_status(self, session_id: str) -> dict:
        """检查登录状态"""
        try:
            result = self.qr_manager.get_session_status(session_id)
            logger.info(f"检查登录状态: {session_id} -> {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return {"status": "error", "message": str(e)}

    def get_session_cookies(self, session_id: str) -> dict:
        """获取会话 cookies"""
        try:
            result = self.qr_manager.get_session_cookies(session_id)
            if result:
                logger.info(f"获取会话 cookies 成功: {session_id}")
                return result
            return {"success": False, "message": "Session not found or not authenticated"}
        except Exception as e:
            logger.error(f"获取会话 cookies 失败: {e}")
            return {"success": False, "message": str(e)}

    async def _mtop_request(
        self,
        api: str,
        version: str,
        data: dict,
        cookies_str: str,
        type_: str = "originaljson",
        extra_params: dict = None,
        extra_headers: dict = None,
        referer: str = "https://www.goofish.com/",
    ) -> tuple[dict, str]:
        """发起 mtop API 请求，自动处理 Set-Cookie 更新和令牌过期重试。

        Returns: (json_response, updated_cookies_str)
        """
        current_cookies = cookies_str
        max_retry = 1  # 令牌过期最多重试1次

        for attempt in range(max_retry + 1):
            timestamp = str(int(time.time() * 1000))
            data_val = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
            token = _get_h5_tk_token(current_cookies)

            if not token:
                logger.warning(f"mtop请求 [{api}]: _m_h5_tk 为空! Cookie前200字符: {current_cookies[:200]}")

            app_key = "34839810"
            sign = hashlib.md5(f"{token}&{timestamp}&{app_key}&{data_val}".encode()).hexdigest()

            params = {
                "jsv": "2.7.2",
                "appKey": app_key,
                "t": timestamp,
                "sign": sign,
                "v": version,
                "type": type_,
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": api,
                "sessionOption": "AutoLoginOnly",
            }
            if extra_params:
                params.update(extra_params)

            headers = {
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "cookie": current_cookies,
                "referer": referer,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36",
            }
            if extra_headers:
                headers.update(extra_headers)

            url = f"{self.H5API_BASE}/{api}/{version}/"

            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, proxies=self.proxy, trust_env=False
            ) as client:
                resp = await client.post(
                    url,
                    params=params,
                    data={"data": data_val},
                    headers=headers,
                )

            # 提取 Set-Cookie，更新本地 cookies（参照 websocket 端 _handle_response_cookies）
            new_cookies = _extract_set_cookies(resp)
            if new_cookies:
                current_cookies = _merge_cookies(current_cookies, new_cookies)
                logger.info(f"mtop [{api}] 从 Set-Cookie 更新了 {len(new_cookies)} 个字段")

            result = resp.json()

            # 令牌过期：用更新后的 cookies 重试
            if attempt < max_retry:
                ret = result.get("ret", [])
                ret_str = ret[0] if ret else ""
                if "FAIL_SYS_TOKEN_EXOIRED" in ret_str or "FAIL_SYS_TOKEN_EXPIRED" in ret_str:
                    logger.info(f"mtop [{api}] 令牌过期，用新 token 重试 ({attempt + 1}/{max_retry})")
                    continue

            return result, current_cookies

    async def verify_cookies(self, cookies: str) -> tuple[dict, str]:
        """验证 cookies 是否有效，返回 (result_dict, updated_cookies)"""
        api = "mtop.taobao.idlemessage.pc.loginuser.get"
        version = "1.0"
        data = {"bizScene": "home"}

        try:
            result, updated_cookies = await self._mtop_request(api, version, data, cookies)

            ret = result.get("ret", [])
            ret_str = ret[0] if ret else ""
            logger.info(f"verify_cookies: ret={ret_str}")

            if "SUCCESS" in ret_str.upper():
                user_data = result.get("data", {})
                nickname = await self._get_user_nickname(updated_cookies)
                logger.info(f"[{nickname or '-'}] Cookies 验证有效")
                return {
                    "valid": True,
                    "message": "Cookies 有效",
                    "nickname": nickname,
                    "user_data": user_data,
                }, updated_cookies

            if "SESSION_EXPIRED" in ret_str:
                logger.warning(f"Cookies 已过期: {ret_str}")
                return {"valid": False, "message": "Cookies 已过期，请重新登录"}, updated_cookies

            logger.warning(f"Cookies 验证失败: {ret_str}")
            return {"valid": False, "message": f"Cookies 无效: {ret_str}"}, updated_cookies

        except Exception as e:
            logger.error(f"Cookies 验证异常: {e}")
            return {"valid": False, "message": f"验证失败: {str(e)}"}, cookies

    async def _get_user_nickname(self, cookies_str: str) -> str:
        """获取当前用户的昵称

        优先从 Cookie 的 tracknick 字段解码，失败则尝试 pc.user.query。
        """
        # 方式 1：从 tracknick cookie 提取（最可靠）
        import urllib.parse
        m = re.search(r"(?:^|;\s*)tracknick=([^;]+)", cookies_str)
        if m:
            nick = urllib.parse.unquote(m.group(1)).strip()
            if nick:
                logger.info(f"从 tracknick 获取昵称: {nick}")
                return nick

        # 方式 2：从 unb 尝试 pc.user.query（备用，通常对自己无效）
        unb_match = re.search(r"(?:^|;\s*)unb=(\d+)", cookies_str)
        if not unb_match:
            logger.warning("获取昵称失败: Cookie 中未找到 unb 和 tracknick")
            return ""
        unb = unb_match.group(1)

        data = {
            "type": 0,
            "sessionType": 1,
            "sessionId": unb,
            "isOwner": False,
        }
        try:
            result, _ = await self._mtop_request(
                api="mtop.taobao.idlemessage.pc.user.query",
                version="4.0",
                data=data,
                cookies_str=cookies_str,
                type_="originaljson",
            )
            ret = result.get("ret", [])
            if any("SUCCESS" in r for r in ret):
                user_info = result.get("data", {}).get("userInfo", {})
                nickname = user_info.get("fishNick") or user_info.get("nick") or ""
                logger.info(f"从 pc.user.query 获取昵称: {nickname or '(空)'}")
                return nickname
        except Exception as e:
            logger.warning(f"获取用户昵称异常: {e}")

        return ""

    async def fetch_sold_orders(self, cookies_str: str, page: int = 1, page_size: int = 30) -> tuple[dict, str]:
        """获取卖家已卖出的订单列表，返回 (result, updated_cookies)"""
        data = {
            "pageNumber": page,
            "rowsPerPage": page_size,
            "orderIds": "",
            "queryCode": "ALL",
            "orderSearchParam": "{}",
        }
        try:
            result, updated_cookies = await self._mtop_request(
                api="mtop.taobao.idle.trade.merchant.sold.get",
                version="1.0",
                data=data,
                cookies_str=cookies_str,
                type_="json",
                extra_params={"type": "json", "valueType": "string"},
                extra_headers={"idle_site_biz_code": "COMMONPRO"},
                referer="https://seller.goofish.com/",
            )
            ret = result.get("ret", [])
            if not any("SUCCESS" in r for r in ret):
                return {"success": False, "error": ret[0] if ret else "未知错误", "items": []}, updated_cookies

            module = result.get("data", {}).get("module", {})
            items = module.get("items", [])
            next_page = module.get("nextPage", "false") == "true"
            total_count = int(module.get("totalCount", "0"))

            parsed = []
            for item in items:
                common = item.get("commonData", {})
                buyer = item.get("buyerInfoVO", {})
                price = item.get("priceVO", {})
                parsed.append({
                    "order_id": common.get("orderId", ""),
                    "item_title": common.get("itemTitle", ""),
                    "item_pic": common.get("itemPicUrl", ""),
                    "order_status": common.get("orderStatus", ""),
                    "create_time": common.get("createTime", ""),
                    "total_amount": price.get("totalPrice", ""),
                    "quantity": price.get("buyNum", "1"),
                    "buyer_nick": buyer.get("buyerNick", ""),
                    "buyer_id": buyer.get("buyerId", ""),
                })

            return {"success": True, "items": parsed, "total_count": total_count, "has_next": next_page}, updated_cookies
        except Exception as e:
            logger.error(f"获取已卖出订单失败: {e}")
            return {"success": False, "error": str(e), "items": []}, cookies_str

    async def fetch_order_detail(self, cookies_str: str, order_id: str) -> tuple[dict, str]:
        """获取订单详情，返回 (result, updated_cookies)"""
        data = {"tid": order_id}
        try:
            result, updated_cookies = await self._mtop_request(
                api="mtop.idle.web.trade.order.detail",
                version="1.0",
                data=data,
                cookies_str=cookies_str,
                type_="originaljson",
                extra_params={"spm_cnt": "a21ybx.order-detail.0.0"},
                extra_headers={
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "origin": "https://www.goofish.com",
                },
            )
            ret = result.get("ret", [])
            if not any("SUCCESS" in r for r in ret):
                return {"success": False, "error": ret[0] if ret else "未知错误"}, updated_cookies

            components = result.get("data", {}).get("components", [])
            detail = {"order_id": order_id}

            for comp in components:
                render = comp.get("render", "")
                comp_data = comp.get("data", {})

                if render == "orderInfoVO":
                    item_info = comp_data.get("itemInfo", {})
                    detail["item_title"] = item_info.get("title", "")
                    detail["price"] = item_info.get("price", "")
                    detail["buy_amount"] = item_info.get("buyAmount", 1)
                    detail["sku_info"] = item_info.get("skuInfo", "")
                    detail["item_pic"] = item_info.get("picUrl", "")
                    detail["order_info_list"] = comp_data.get("orderInfoList", [])

                elif render == "addressInfoVO":
                    detail["receiver_name"] = comp_data.get("name", "")
                    detail["phone_number"] = comp_data.get("phoneNumber", "")
                    detail["address"] = comp_data.get("address", "")

                elif render == "orderStatusVO":
                    status_nodes = comp_data.get("orderStatusNodeList", [])
                    detail["status_nodes"] = [
                        {"title": n.get("title", ""), "completed": n.get("completed", False)}
                        for n in status_nodes
                    ]

            detail["peer_user_id"] = result.get("data", {}).get("peerUserId", "")
            detail["item_id"] = result.get("data", {}).get("itemId", "")

            return {"success": True, "detail": detail}, updated_cookies
        except Exception as e:
            logger.error(f"获取订单详情失败: {e}")
            return {"success": False, "error": str(e)}, cookies_str

    async def confirm_delivery(self, order_no: str, cookies: str) -> tuple[bool, str]:
        """确认发货，返回 (success, updated_cookies)"""
        return await self.confirm_delivery_api(cookies, order_no)

    async def confirm_delivery_api(self, cookies_str: str, order_id: str) -> tuple[bool, str]:
        """调用 consign.dummy 确认发货，返回 (success, updated_cookies)"""
        data = {"orderId": order_id}
        try:
            result, updated_cookies = await self._mtop_request(
                api="mtop.taobao.idle.logistic.consign.dummy",
                version="1.0",
                data=data,
                cookies_str=cookies_str,
                type_="originaljson",
            )
            ret = result.get("ret", [])
            if any("SUCCESS" in r for r in ret):
                logger.info(f"确认发货成功: {order_id}")
                return True, updated_cookies
            logger.warning(f"确认发货失败: {order_id}, ret={ret}")
            return False, updated_cookies
        except Exception as e:
            logger.error(f"确认发货异常: {order_id}, {e}")
            return False, cookies_str

    async def get_im_token(self, cookies_str: str, user_id: str) -> tuple[str | None, str]:
        """获取 IM Token，返回 (token_or_none, updated_cookies)"""
        data = {
            "appKey": "444e9908a51d1cb236a27862abc769c9",
            "deviceId": f"web-{user_id}",
            "userId": user_id,
        }
        try:
            result, updated_cookies = await self._mtop_request(
                api="mtop.taobao.idlemessage.pc.login.token",
                version="1.0",
                data=data,
                cookies_str=cookies_str,
                type_="originaljson",
            )
            ret = result.get("ret", [])
            if any("SUCCESS" in r for r in ret):
                token = result.get("data", {}).get("accessToken")
                if token:
                    logger.info(f"获取 IM Token 成功: {user_id}")
                    return token, updated_cookies
                logger.warning(f"获取 IM Token 响应中无 accessToken: {result.get('data')}")
                return None, updated_cookies
            logger.warning(f"获取 IM Token 失败: {ret}")
            return None, updated_cookies
        except Exception as e:
            logger.error(f"获取 IM Token 异常: {e}")
            return None, cookies_str

    async def fetch_listed_items(self, cookies_str: str, user_id: str) -> tuple[dict, str]:
        """获取在售商品列表，返回 (result, updated_cookies)"""
        all_items = []
        page = 1
        page_size = 20
        current_cookies = cookies_str

        try:
            while True:
                data = {
                    "userId": user_id,
                    "pageNumber": page,
                    "pageSize": page_size,
                }
                result, current_cookies = await self._mtop_request(
                    api="mtop.idle.web.xyh.item.list",
                    version="1.0",
                    data=data,
                    cookies_str=current_cookies,
                    type_="json",
                    extra_params={"type": "json", "valueType": "string"},
                )
                ret = result.get("ret", [])
                if not any("SUCCESS" in r for r in ret):
                    if page == 1:
                        return {"success": False, "error": ret[0] if ret else "未知错误", "items": []}, current_cookies
                    break

                module = result.get("data", {}).get("module", {})
                items = module.get("items", [])
                for item in items:
                    all_items.append({
                        "item_id": item.get("itemId", ""),
                        "title": item.get("title", ""),
                        "price": item.get("price", ""),
                        "pic_url": item.get("picUrl", ""),
                        "status": item.get("status", ""),
                    })

                has_next = module.get("hasNext", False) or module.get("nextPage", "false") == "true"
                if not has_next or not items:
                    break
                page += 1

            return {"success": True, "items": all_items}, current_cookies
        except Exception as e:
            logger.error(f"获取在售商品失败: {e}")
            return {"success": False, "error": str(e), "items": []}, current_cookies

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        try:
            self.qr_manager.cleanup_expired_sessions()
            logger.info("清理过期会话成功")
        except Exception as e:
            logger.error(f"清理过期会话失败: {e}")


# 全局实例
xianyu_client = XianyuClient()
