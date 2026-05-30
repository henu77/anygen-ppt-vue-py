"""PPT 导出服务

完整流程（参照 test_expor1t.py）：
  1. Playwright 打开页面获取 Cookie
  2. file_system API 推断 PPT 页数
  3. Playwright 注入 Cookie 等待 editor 加载，抓取 client_vars
  4. POST 创建导出任务（需要 csrf_token）
  5. 轮询任务状态
  6. 下载 PPTX 并校验
"""
import asyncio
import json
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from playwright.async_api import BrowserContext, async_playwright

from app.services.task import TaskService

# 加载 client_vars 抓取 JS
_JS_PATH = Path(__file__).parent.parent / "assets" / "get_client_vars.js"
_GET_CLIENT_VARS_JS = _JS_PATH.read_text(encoding="utf-8")

UNIFIED_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'zh-CN', 'zh'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
"""

BROWSER_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=Translate,BackForwardCache",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]

RETRYABLE_STATUS = {500, 502, 503, 504, 429}
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "downloads")


# ==================== Cookie 工具 ====================

def _parse_cookies(raw: str) -> dict[str, str]:
    result = {}
    for item in raw.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _cookies_to_pw(cookies: dict, domain: str = "www.anygen.io") -> list[dict]:
    return [{"name": k, "value": v, "domain": domain, "path": "/"} for k, v in cookies.items()]


def _browser_cookies_to_header(cookies: list[dict]) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


# ==================== HTTP 重试 ====================

async def _retry_request(fn, *args, max_attempts=3, backoff_base=2, label="", **kwargs):
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status not in RETRYABLE_STATUS:
                raise
            last_exc = e
            if attempt == max_attempts:
                raise
            wait = backoff_base ** attempt
            logger.warning(f"[{label}] HTTP {status}，{wait}s 后重试")
            await asyncio.sleep(wait)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
            last_exc = e
            if attempt == max_attempts:
                raise
            wait = backoff_base ** attempt
            logger.warning(f"[{label}] 网络错误，{wait}s 后重试: {e}")
            await asyncio.sleep(wait)
    raise last_exc


# ==================== 步骤 1+2+3：浏览器获取 Cookie + 页数 + client_vars ====================

async def _acquire_all(
    page_url: str,
    proxy: str = None,
    headless: bool = True,
    user_data_dir: str = "",
    editor_wait_sec: int = 90,
    stable_sec: int = 12,
    min_blocks_per_slide: int = 4,
    export_wait_sec: int = 480,
) -> tuple[str, str, int]:
    """单次浏览器启动，完成 Cookie 获取 + file_system 页数推断 + client_vars 抓取。

    Returns: (cookie_str, client_vars_str, actual_slide_count)
    """
    proxy_cfg = {"server": proxy} if proxy else None

    async with async_playwright() as p:
        context: BrowserContext = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            proxy=proxy_cfg,
            user_agent=UNIFIED_USER_AGENT,
            viewport={"width": 1440, "height": 1000},
            args=BROWSER_ARGS,
        )
        await context.add_init_script(STEALTH_JS)

        # 清除旧 Cookie，避免残留过期 Cookie 导致 403
        await context.clear_cookies()

        page = context.pages[0] if context.pages else await context.new_page()

        try:
            logger.info(f"[browser] 打开: {page_url}")
            await page.goto(page_url, wait_until="load", timeout=editor_wait_sec * 1000)
            await page.wait_for_timeout(3_000)

            # 提取 Cookie
            all_cookies = await context.cookies("https://www.anygen.io")
            if not all_cookies:
                raise RuntimeError("未能获取到任何 Cookie")
            cookie_str = _browser_cookies_to_header(all_cookies)
            logger.info(f"[browser] 获取到 {len(all_cookies)} 个 Cookie")

            # file_system 请求推断页数
            page_id = _extract_page_id(page_url)
            logger.info(f"[browser] 开始推断页数，page_id={page_id}")
            expected_slide_count = await _fetch_slide_count(cookie_str, page_id, proxy)
            logger.info(f"[browser] 预估页数: {expected_slide_count}")
            # 抓取 client_vars
            min_block_count = max(10, expected_slide_count * min_blocks_per_slide)
            logger.info(f"[inject] expectedSlides={expected_slide_count} minBlocks={min_block_count}")

            result = await page.evaluate(
                _GET_CLIENT_VARS_JS,
                {
                    "minBlockCount": min_block_count,
                    "expectedSlideCount": expected_slide_count,
                    "stableMs": stable_sec * 1000,
                    "timeoutMs": export_wait_sec * 1000,
                },
            )

        finally:
            await context.close()

    client_vars_str = result["clientVarsString"]
    actual_slide_count = result.get("actualSlideCount", result["slideCount"])
    logger.info(
        f"[client_vars] slides={result['slideCount']} blocks={result['blockCount']} "
        f"actual={actual_slide_count} len={result['stringLength']}"
    )
    return cookie_str, client_vars_str, actual_slide_count


def _extract_page_id(page_url: str) -> str:
    """从 URL 中提取 page_id（最后一个 - 后面的字符串），URL后可能会有？参数，需先去掉"""
    slug = page_url.rstrip("/").split("/")[-1].split("?")[0]
    parts = slug.rsplit("-", 1)
    if len(parts) == 2 and len(parts[1]) > 10:
        return parts[1]
    return slug


async def _fetch_slide_count(cookie_str: str, page_id: str, proxy: str = None) -> int:
    """调用 file_system API 推断 PPT 页数"""
    url = f"https://www.anygen.io/api/page/file_system/{page_id}/files"
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_str,
        "User-Agent": UNIFIED_USER_AGENT,
    }
    proxy_url = proxy or None

    async def _do_request():
        async with httpx.AsyncClient(timeout=60, proxy=proxy_url, trust_env=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    body = await _retry_request(_do_request, label="file_system")

    if body.get("code") != 0:
        raise RuntimeError(f"file_system 失败: {json.dumps(body, ensure_ascii=False)[:500]}")

    files = body.get("data", {}).get("files", [])
    manifests = [
        f for f in files
        if not f.get("is_directory")
        and str(f.get("name", "")).endswith(".slides")
        and str(f.get("path", "")).startswith("/home/user/workspace/slides/")
    ]
    if not manifests:
        raise RuntimeError("未找到 .slides 主文件")

    manifests.sort(
        key=lambda f: (
            f.get("folder_visibility") == "visible",
            int(f.get("modified_time") or 0),
            int(f.get("size") or 0),
        ),
        reverse=True,
    )
    manifest_path = str(manifests[0].get("path", ""))
    deck_base = re.sub(r"\.slides$", "", manifest_path.rsplit("/", 1)[-1])
    slide_dir = f"{manifest_path.rsplit('/', 1)[0]}/{deck_base}/"

    slide_files = [
        f for f in files
        if not f.get("is_directory")
        and str(f.get("path", "")).startswith(slide_dir)
        and re.match(r"slide_\w+\.xml$", str(f.get("name", "")))
    ]
    count = len(slide_files)
    logger.info(f"[file_system] slide_count={count}")
    return count


# ==================== 步骤 4：创建导出任务 ====================

async def _create_export_job(cookie_str: str, page_id: str, client_vars_str: str, proxy: str = None, extra_cookie: str = "", page_url: str = "") -> tuple[str, int]:
    url = f"https://www.anygen.io/api/page/pages/{page_id}/export-jobs/"
    # extra_cookie（系统设置中的高优先级 Cookie）与浏览器 Cookie 合并
    # extra_cookie 的 key 优先，避免重复 key 导致服务端解析异常
    if extra_cookie:
        base = _parse_cookies(cookie_str)
        override = _parse_cookies(extra_cookie)
        base.update(override)
        merged = "; ".join(f"{k}={v}" for k, v in base.items())
    else:
        merged = cookie_str
    cookie_dict = _parse_cookies(merged)
    csrf_token = cookie_dict.get("_csrf_token", "")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": merged,
        "User-Agent": UNIFIED_USER_AGENT,
        "Origin": "https://www.anygen.io",
        "Referer": page_url or f"https://www.anygen.io/task/{page_id}",
        "x-csrftoken": csrf_token,
    }
    payload = {"export_type": 3, "extra_params": {"client_vars": client_vars_str}}
    proxy_url = proxy or None

    async def _do_request():
        async with httpx.AsyncClient(timeout=90, proxy=proxy_url, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    body = await _retry_request(_do_request, label="create_job")
    data = body.get("data") or body
    job_id = data.get("job_id") or data.get("ticket") or body.get("job_id")
    job_timeout = int(data.get("job_timeout") or body.get("job_timeout") or 90)

    if not job_id:
        raise RuntimeError(f"创建导出任务失败: {json.dumps(body, ensure_ascii=False)[:500]}")

    logger.info(f"[create_job] job_id={job_id}")
    return job_id, job_timeout


# ==================== 步骤 5：轮询导出任务 ====================

async def _poll_export_job(cookie_str: str, job_id: str, max_wait: int = 360, proxy: str = None, extra_cookie: str = "") -> str:
    url = f"https://www.anygen.io/api/page/export-jobs/{job_id}"

    # 轮询使用与创建任务相同的合并 Cookie（与 test_expor1t.py 保持一致）
    if extra_cookie:
        base = _parse_cookies(cookie_str)
        override = _parse_cookies(extra_cookie)
        base.update(override)
        merged = "; ".join(f"{k}={v}" for k, v in base.items())
    else:
        merged = cookie_str

    headers = {
        "Accept": "application/json",
        "Cookie": merged,
        "User-Agent": UNIFIED_USER_AGENT,
        "Referer": f"https://www.anygen.io/",
    }
    proxy_url = proxy or None
    deadline = time.time() + max_wait
    queued_interval = 3.0
    running_interval = 3.0
    consecutive_errors = 0

    async with httpx.AsyncClient(timeout=30, proxy=proxy_url, trust_env=False) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                consecutive_errors += 1
                logger.warning(f"[poll] HTTP {status} 错误，连续错误 {consecutive_errors}/3")
                if consecutive_errors >= 3:
                    raise RuntimeError(f"轮询连续3次 HTTP 错误: {status}")
                await asyncio.sleep(queued_interval)
                continue
            except (httpx.ConnectError, httpx.Timeout) as e:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    raise RuntimeError(f"轮询连续3次网络异常: {e}")
                await asyncio.sleep(queued_interval)
                continue

            if body.get("code") not in (0, None):
                consecutive_errors += 1
                code = body.get("code")
                msg = body.get("message") or body.get("msg") or ""
                logger.warning(f"[poll] 服务端返回 code={code} msg={msg}，连续错误 {consecutive_errors}/3，body={json.dumps(body, ensure_ascii=False)[:300]}")
                if consecutive_errors >= 3:
                    raise RuntimeError(f"轮询连续3次服务端错误: code={code} msg={msg} body={json.dumps(body, ensure_ascii=False)[:500]}")
                await asyncio.sleep(queued_interval)
                continue

            consecutive_errors = 0
            data = body.get("data") or body
            result = data.get("result") or {}
            job_status = data.get("job_status")
            if job_status is None:
                job_status = result.get("job_status")

            if job_status == 0:  # 成功
                doc_id = result.get("document_id") or data.get("document_id")
                doc_url = result.get("document_url") or data.get("document_url")
                if doc_id or doc_url:
                    return doc_id or doc_url
                raise RuntimeError("任务成功但无 document_id")

            if job_status == 1:  # 排队中
                await asyncio.sleep(queued_interval)
                queued_interval = min(queued_interval * 1.5, 30)
                continue

            if job_status == 2:  # 进行中
                await asyncio.sleep(running_interval)
                continue

            error = data.get("error") or result.get("error") or ""
            raise RuntimeError(f"导出失败: job_status={job_status}, error={error}")

    raise TimeoutError(f"导出超时 ({max_wait}s)")


# ==================== 步骤 6：下载并校验 ====================

async def _download_and_validate(cookie_str: str, doc_id_or_url: str, output_path: str, proxy: str = None) -> None:
    if doc_id_or_url.startswith("http"):
        url = doc_id_or_url
    else:
        url = f"https://www.anygen.io/space/api/box/stream/download/all/{doc_id_or_url}"

    headers = {"Cookie": cookie_str, "User-Agent": UNIFIED_USER_AGENT}
    proxy_url = proxy or None

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    async with httpx.AsyncClient(timeout=180, proxy=proxy_url, trust_env=False, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            total = 0
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)

    logger.info(f"[download] 写入 {total} 字节 -> {output_path}")

    # 校验 PPTX
    try:
        with zipfile.ZipFile(output_path) as zf:
            if "ppt/presentation.xml" not in zf.namelist():
                raise RuntimeError("下载的文件不是有效 PPTX")
    except zipfile.BadZipFile:
        raise RuntimeError(f"下载的文件不是合法 ZIP，大小 {total} 字节")

    logger.info("[download] PPTX 校验通过")


# ==================== 主入口 ====================

async def export_ppt(task_id: int, db, key_str: str = None) -> bool:
    """导出 PPT 主流程（后台任务调用）"""
    from sqlalchemy.orm import Session
    from app.services.key import KeyService
    from app.services.settings import SettingsService

    try:
        task = TaskService.get_task(db, task_id)
        if not task:
            return False

        TaskService.update_task_status(db, task_id, "processing")
        page_url = task.url
        page_id = _extract_page_id(page_url)

        # 读取系统设置
        cfg = SettingsService.get_all_settings(db)
        use_proxy = str(cfg.get("anygen_use_proxy", "false")).lower() == "true"
        proxy = cfg.get("anygen_proxy") if use_proxy else None
        headless = str(cfg.get("playwright_headless", "true")).lower() == "true"
        user_data_dir = cfg.get("playwright_user_data_dir", "") or ""
        editor_wait_sec = int(cfg.get("editor_wait_seconds", 90))
        stable_sec = int(cfg.get("stable_seconds", 12))
        min_blocks_per_slide = int(cfg.get("min_blocks_per_slide", 4))
        export_wait_sec = int(cfg.get("export_wait_seconds", 480))
        extra_cookie = cfg.get("anygen_cookie", "") or ""

        # 输出路径
        output_path = os.path.join(DOWNLOAD_DIR, f"export_{task_id}.pptx")

        logger.info(f"[export] 开始导出任务 {task_id}: {page_url}")

        # 步骤 1+2+3：浏览器获取 Cookie + 页数 + client_vars
        cookie_str, client_vars_str, slide_count = await _acquire_all(
            page_url, proxy=proxy, headless=headless, user_data_dir=user_data_dir,
            editor_wait_sec=editor_wait_sec, stable_sec=stable_sec,
            min_blocks_per_slide=min_blocks_per_slide, export_wait_sec=export_wait_sec,
        )
        logger.info(f"[export] 获取到 cookie 和 client_vars，slide_count={slide_count}")
        logger.info(f"[export] 创建导出任务中，use_proxy={use_proxy} proxy={proxy} headless={headless} extra_cookie={'yes' if extra_cookie else 'no'}")
        # 步骤 4：创建导出任务（anygen_cookie 仅用于此步骤）
        job_id, job_timeout = await _create_export_job(cookie_str, page_id, client_vars_str, proxy=proxy, extra_cookie=extra_cookie, page_url=page_url)
        logger.info(f"[export] 导出任务创建成功，job_id={job_id} job_timeout={job_timeout}s")
        # 步骤 5：轮询
        doc_id_or_url = await _poll_export_job(cookie_str, job_id, max_wait=max(360, job_timeout + 60), proxy=proxy, extra_cookie=extra_cookie)

        # 步骤 6：下载并校验
        await _download_and_validate(cookie_str, doc_id_or_url, output_path, proxy=proxy)

        # 导出成功后才消耗卡密
        if key_str:
            KeyService.use_key(db, key_str)

        # 更新任务状态
        TaskService.update_task_status(db, task_id, "done", file_path=output_path)
        logger.info(f"[export] 任务 {task_id} 完成: {output_path}")
        return True

    except Exception as e:
        logger.error(f"[export] 任务 {task_id} 失败: {e}")
        TaskService.update_task_status(db, task_id, "failed", error_msg=str(e))
        return False


class ExportService:
    """导出服务（兼容路由层调用）"""

    @staticmethod
    async def export_ppt(task_id: int, db, key_str: str = None) -> bool:
        return await export_ppt(task_id, db, key_str)
