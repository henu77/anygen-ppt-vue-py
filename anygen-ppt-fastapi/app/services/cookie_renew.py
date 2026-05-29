"""Cookie 续期核心服务

降级链路（按 XIANYU_SESSION_KEEPALIVE.md）：
① API 三步续期（hasLogin → silentHasLogin → setLoginSettings）
    失败 → 2 秒重试一次
② 浏览器续期（Playwright 无头 Chromium）
    成功 → setLoginSettings 验证长登录令牌
③ 标记失败
"""
import asyncio
import random
import time
from typing import Optional
from loguru import logger
import httpx

PASSPORT_HOST = "https://passport.goofish.com"
TARGET_URL = "https://www.goofish.com/"
COOKIE_DOMAINS = [".goofish.com", ".taobao.com", ".alipay.com"]

HEADERS_BASE = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


# ==================== Cookie 工具函数 ====================

def parse_cookies(cookies_str: str) -> dict:
    cookies = {}
    for part in cookies_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def cookies_to_str(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def merge_set_cookies(cookies_str: str, set_cookie_headers: list[str]) -> tuple[str, list[str]]:
    """将 Set-Cookie 响应头合并到 Cookie 字符串，返回 (新cookie串, 变更的key列表)"""
    cookies = parse_cookies(cookies_str)
    updated = []
    for raw in set_cookie_headers:
        name_value = raw.split(";")[0]
        if "=" not in name_value:
            continue
        name, value = name_value.split("=", 1)
        name, value = name.strip(), value.strip()
        if "Max-Age=0" in raw:
            continue
        if cookies.get(name) != value:
            cookies[name] = value
            updated.append(name)
    return cookies_to_str(cookies), updated


# ==================== API 三步续期 ====================

async def _step1_has_login(cookies_str: str) -> tuple[bool, list[str]]:
    """hasLogin.do — 确认 Web 登录态"""
    cd = parse_cookies(cookies_str)
    t = str(int(time.time() * 1000))
    rand_num = str(int(100000 + 900000 * random.random()))

    data = {
        "hid": cd.get("unb", ""),
        "ltl": "true",
        "appName": "xianyu",
        "appEntrance": "web",
        "_csrf_token": cd.get("_tb_token_", ""),
        "umidToken": cd.get("_uab_collina", "") or cd.get("cna", ""),
        "hsiz": cd.get("cookie2", ""),
        "bizParams": "taobaoBizLoginFrom%3Dweb%26renderRefer%3Dhttps%253A%252F%252Fwww.goofish.com%252F",
        "mainPage": "false",
        "isMobile": "false",
        "lang": "zh_CN",
        "returnUrl": "",
        "fromSite": "77",
        "isIframe": "true",
        "documentReferer": "https%3A%2F%2Fwww.goofish.com%2F",
        "defaultView": "hasLogin",
        "umidTag": "SERVER",
        "deviceId": "",
        "pageTraceId": f"21504{t}{rand_num}",
    }

    headers = {
        **HEADERS_BASE,
        "accept": "application/json, text/plain, */*",
        "content-type": "application/x-www-form-urlencoded",
        "referer": f"{PASSPORT_HOST}/mini_login.htm",
        "cookie": cookies_str,
    }
    xsrf = cd.get("XSRF-TOKEN", "")
    if xsrf:
        headers["x-xsrf-token"] = xsrf

    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        resp = await client.post(
            f"{PASSPORT_HOST}/newlogin/hasLogin.do",
            params={"appName": "xianyu", "fromSite": "77"},
            data=data,
            headers=headers,
        )
        set_cookies = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
        result = resp.json()
        success = result.get("content", {}).get("success", False)
        return success, set_cookies


async def _step2_silent_has_login(cookies_str: str) -> tuple[bool, list[str]]:
    """silentHasLogin.do — 静默登录确认"""
    headers = {
        **HEADERS_BASE,
        "accept": "*/*",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "referer": TARGET_URL,
        "cookie": cookies_str,
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        resp = await client.post(
            f"{PASSPORT_HOST}/newlogin/silentHasLogin.do",
            params={
                "documentReferer": TARGET_URL,
                "appName": "xianyu",
                "appEntrance": "xianyu_sdkSilent",
                "fromSite": "0",
                "ltl": "true",
            },
            headers=headers,
        )
        set_cookies = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
        result = resp.json()
        success = result.get("content", {}).get("success", False)
        return success, set_cookies


async def _step3_set_login_settings(cookies_str: str) -> list[str]:
    """setLoginSettings.do — 获取 30 天长登录令牌（关键步骤）"""
    headers = {
        **HEADERS_BASE,
        "accept": "application/json, text/plain, */*",
        "content-type": "application/x-www-form-urlencoded",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "referer": TARGET_URL,
        "cookie": cookies_str,
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        resp = await client.post(
            f"{PASSPORT_HOST}/ac/account/setLoginSettings.do",
            params={"fromSite": "77", "appName": "xianyu", "bizEntrance": "web"},
            data={"status": "0"},
            headers=headers,
        )
        return [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]


async def _do_api_renew(cookies_str: str) -> dict:
    """执行三步 API 续期，返回 {success, new_cookies, message, long_login_has_cookies}"""
    current = cookies_str

    # Step 1: hasLogin.do
    ok1, sc1 = await _step1_has_login(current)
    if sc1:
        current, _ = merge_set_cookies(current, sc1)
    if not ok1:
        return {"success": False, "new_cookies": current, "message": "hasLogin.do 失败", "long_login_has_cookies": False}

    # Step 2: silentHasLogin.do
    ok2, sc2 = await _step2_silent_has_login(current)
    if sc2:
        current, _ = merge_set_cookies(current, sc2)

    # Step 3: setLoginSettings.do（判断成功的关键）
    sc3 = await _step3_set_login_settings(current)
    long_login_has = bool(sc3 and any("Max-Age=0" not in c for c in sc3))
    if sc3:
        current, _ = merge_set_cookies(current, sc3)

    if long_login_has:
        return {"success": True, "new_cookies": current, "message": "API续期成功", "long_login_has_cookies": True}
    else:
        return {"success": False, "new_cookies": current, "message": "setLoginSettings未返回长登录令牌", "long_login_has_cookies": False}


async def _do_api_renew_with_retry(cookies_str: str) -> dict:
    """API 续期 + 失败重试一次（2 秒延迟）"""
    for attempt in range(2):
        result = await _do_api_renew(cookies_str)
        if result["long_login_has_cookies"]:
            return result
        if attempt == 0:
            logger.info(f"API续期首次失败，2秒后重试...")
            await asyncio.sleep(2)
    return result


# ==================== 浏览器续期 ====================

async def _do_browser_renew(cookies_str: str) -> dict:
    """Playwright 浏览器续期：注入 Cookie → 打开 goofish.com → 提取新 Cookie"""
    try:
        result = await asyncio.to_thread(_sync_browser_renew, cookies_str)
        return result
    except Exception as e:
        logger.error(f"浏览器续期异常: {e}")
        return {"success": False, "new_cookies": cookies_str, "message": f"浏览器续期异常: {e}"}


def _sync_browser_renew(cookies_str: str) -> dict:
    """同步浏览器续期（在线程中运行）"""
    from playwright.sync_api import sync_playwright

    cookie_dict = parse_cookies(cookies_str)
    new_cookies_str = cookies_str

    with sync_playwright() as p:
        browser = None
        context = None
        page = None
        try:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                user_agent=HEADERS_BASE["user-agent"],
            )

            # 反检测
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
                window.chrome = { runtime: {} };
            """)

            # 注入 Cookie 到三个域名
            for domain in COOKIE_DOMAINS:
                pw_cookies = [
                    {"name": k, "value": v, "domain": domain, "path": "/"}
                    for k, v in cookie_dict.items()
                ]
                context.add_cookies(pw_cookies)

            page = context.new_page()

            # 导航到 goofish.com
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 检测登录弹窗（Session 过期标志）
            modal = page.query_selector(".ant-modal-body")
            if modal:
                logger.warning("浏览器续期: 检测到登录弹窗，Session 已过期")
                return {"success": False, "new_cookies": cookies_str, "message": "浏览器检测到登录弹窗，Session已过期"}

            # 重载页面以触发 Cookie 刷新
            for _ in range(3):
                page.reload(wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)

            # 再次检查
            modal = page.query_selector(".ant-modal-body")
            if modal:
                return {"success": False, "new_cookies": cookies_str, "message": "重载后检测到登录弹窗"}

            # 提取所有浏览器 Cookie
            all_cookies = context.cookies()
            if not all_cookies:
                return {"success": False, "new_cookies": cookies_str, "message": "浏览器未返回Cookie"}

            merged = parse_cookies(cookies_str)
            for c in all_cookies:
                name = c.get("name", "")
                value = c.get("value", "")
                if name and value:
                    merged[name] = value

            new_cookies_str = cookies_to_str(merged)
            logger.info(f"浏览器续期: 提取到 {len(all_cookies)} 个Cookie")
            return {"success": True, "new_cookies": new_cookies_str, "message": "浏览器续期成功"}

        except Exception as e:
            logger.error(f"浏览器续期执行异常: {e}")
            return {"success": False, "new_cookies": cookies_str, "message": str(e)}
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass


# ==================== 总入口 ====================

async def renew(cookies_str: str, account_id: str = "", source: str = "") -> dict:
    """执行续期（完整降级链路）

    Returns: {success: bool, new_cookies: str, message: str}
    """
    # ① API 三步续期（含重试）
    logger.info(f"[{account_id}] 开始Cookie续期...")
    api_result = await _do_api_renew_with_retry(cookies_str)

    if api_result["success"]:
        logger.info(f"[{account_id}] API续期成功")
        return {"success": True, "new_cookies": api_result["new_cookies"], "message": "API续期成功"}

    # 即使 API 续期失败，也可能拿到了部分新 Cookie，保留
    partial_cookies = api_result["new_cookies"]
    logger.info(f"[{account_id}] API续期失败: {api_result['message']}，降级到浏览器续期")

    # ② 浏览器续期
    browser_result = await _do_browser_renew(partial_cookies)

    if browser_result["success"]:
        # 浏览器续期成功后，再调用 setLoginSettings 验证长登录令牌
        logger.info(f"[{account_id}] 浏览器续期成功，验证长登录令牌...")
        verify_sc = await _step3_set_login_settings(browser_result["new_cookies"])
        verify_has = bool(verify_sc and any("Max-Age=0" not in c for c in verify_sc))
        if verify_sc:
            final_cookies, _ = merge_set_cookies(browser_result["new_cookies"], verify_sc)
        else:
            final_cookies = browser_result["new_cookies"]

        if verify_has:
            logger.info(f"[{account_id}] 浏览器续期+验证通过")
            return {"success": True, "new_cookies": final_cookies, "message": "浏览器续期+验证成功"}
        else:
            logger.warning(f"[{account_id}] 浏览器续期成功但setLoginSettings验证失败")
            return {"success": False, "new_cookies": final_cookies, "message": "浏览器续期成功但长登录令牌验证失败"}

    # ③ 全部失败
    logger.warning(f"[{account_id}] API+浏览器续期均失败: {browser_result['message']}")
    return {"success": False, "new_cookies": browser_result["new_cookies"], "message": f"续期失败: {api_result['message']} + {browser_result['message']}"}
