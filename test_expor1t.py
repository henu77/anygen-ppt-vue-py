"""
AnyGen PPTX 自动导出脚本（优化版）

流程：
  1. 用 Playwright 打开页面，自动获取 Cookie（如本地已有则跳过）
  2. 请求 /api/page/file_system/{PAGE_ID}/files，动态推断 PPT 页数
  3. 在同一个 Playwright 上下文中注入 Cookie，等待 editor 加载后抓取 export client_vars
     ↑ 步骤 1/3 合并为一次浏览器启动，节省 5–15 秒
  4. POST export-jobs 创建导出任务（需要单独的 csrf_cookie，含 _csrf_token）
  5. 轮询任务状态（区分 4xx/5xx 重试策略 + 进行中加速轮询）
  6. 下载 PPTX 并校验合法性

优化说明（相较原版）：
  - Playwright 只启动一次：Cookie 获取与 client_vars 抓取复用同一 context
  - retry_request 区分可重试（5xx/网络）和不可重试（4xx）错误
  - poll_export_job 在进行中阶段加速轮询，排队阶段才退避
  - get_client_vars 中去除无效的 min_block_count 初始计算
  - requests / Playwright 统一使用同一个 User-Agent 字符串
  - 代码结构：acquire_cookie_via_browser 与 get_client_vars 合并为
    acquire_cookie_and_client_vars，单次浏览器生命周期内完成两件事

依赖安装：
  pip install playwright requests
  python -m playwright install chromium

Cookie 说明：
  GET 请求（file_system / 轮询 / 下载）不需要 csrf_token：
    - 自动通过浏览器打开页面获取，或设置 ANYGEN_COOKIE / cookie.txt
  POST 请求（创建导出任务）需要 csrf_token：
    - 通过 --csrf-cookie 参数 / ANYGEN_CSRF_COOKIE 环境变量 / csrf_cookie.txt 文件提供

用法：
  python test_expor1t.py https://www.anygen.io/task/your-slug-PAGE_ID -o out.pptx --csrf-cookie "your_cookie_with_csrf"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from playwright.async_api import BrowserContext, async_playwright

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("anygen_export.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("anygen")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 统一 User-Agent，requests 与 Playwright 保持一致，避免服务端指纹不匹配
_UNIFIED_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class Config:
    # ---- 必填 ----
    page_url: str = ""

    # ---- 输出 ----
    output_file: str = "anygen_export.pptx"

    # ---- 浏览器 ----
    headless: bool = False
    proxy_server: str | None = "http://127.0.0.1:7897"
    user_data_dir: str = str(Path(__file__).with_name("anygen_playwright_profile"))

    # ---- 等待策略 ----
    editor_wait_seconds: int = 480      # editor 最长等待时间
    stable_seconds: int = 12            # block/slide 数稳定多久才算加载完
    min_blocks_per_slide: int = 4       # 每页最少 block 数（完整性兜底）

    # ---- 导出任务 ----
    export_wait_seconds: int = 360

    # ---- 调试文件 ----
    debug_client_vars: str = "debug_client_vars.json"
    debug_file_system: str = "debug_file_system.json"
    debug_cookie: str = "debug_cookie.txt"
    error_screenshot: str = "anygen_error.png"

    # ---- 登录页（用于自动获取 Cookie）----
    login_url: str = "https://www.anygen.io/login"

    # ---- 内部（运行时填充）----
    _fixed_cookie: str = field(default="", init=False, repr=False)
    _csrf_cookie: str = field(default="", init=False, repr=False)
    _expected_slide_count: int = field(default=0, init=False, repr=False)

    # ------------------------------------------------------------------
    # page_id（从 page_url 末尾提取）
    # ------------------------------------------------------------------

    @property
    def page_id(self) -> str:
        """从 URL 路径末尾提取 page_id（最后一段中的尾部 token）。"""
        if not self.page_url:
            raise RuntimeError("page_url 未设置")
        # URL 格式: https://www.anygen.io/task/<slug>-<page_id>
        # page_id 是路径最后一段中最后一个 '-' 之后的部分
        last_segment = self.page_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if "-" in last_segment:
            candidate = last_segment.rsplit("-", 1)[-1]
            # page_id 通常是 26 位字母数字
            if len(candidate) >= 20 and candidate.isalnum():
                return candidate
        # 兜底：最后一段整体作为 page_id
        return last_segment

    # ------------------------------------------------------------------
    # Cookie 属性
    # ------------------------------------------------------------------

    @property
    def fixed_cookie(self) -> str:
        return self._fixed_cookie

    @property
    def csrf_cookie(self) -> str:
        return self._csrf_cookie

    def load_cookie_from_env_or_file(self) -> bool:
        """尝试从环境变量或 cookie.txt 读取 GET 用 Cookie，成功返回 True。"""
        cookie = os.getenv("ANYGEN_COOKIE", "").strip()
        if not cookie:
            cookie_file = Path(__file__).with_name("cookie.txt")
            if cookie_file.exists():
                cookie = cookie_file.read_text(encoding="utf-8").strip()

        if cookie:
            self._fixed_cookie = cookie
            return True
        return False

    def load_csrf_cookie(self, cli_value: str = "") -> None:
        """加载含 csrf_token 的 Cookie，优先级：CLI > 环境变量 > 文件。"""
        raw = cli_value.strip()
        if not raw:
            raw = os.getenv("ANYGEN_CSRF_COOKIE", "").strip()
        if not raw:
            cookie_file = Path(__file__).with_name("csrf_cookie.txt")
            if cookie_file.exists():
                raw = cookie_file.read_text(encoding="utf-8").strip()

        if raw:
            self._csrf_cookie = raw
            parsed = parse_cookie_str(raw)
            token = parsed.get("_csrf_token", "")
            if token:
                log.info("csrf_cookie 已加载，_csrf_token=%s", token[:20] + "...")
            else:
                log.warning("csrf_cookie 已加载，但其中没有 _csrf_token")
        else:
            log.info("未找到 csrf_cookie，POST 请求将使用 GET 用 Cookie（可能缺少 csrf_token）")


# ---------------------------------------------------------------------------
# Cookie 工具
# ---------------------------------------------------------------------------

def parse_cookie_str(raw: str) -> dict[str, str]:
    """将 Cookie 字符串解析为 dict。"""
    result: dict[str, str] = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def cookies_dict_to_playwright(
    cookies: dict[str, str],
    domain: str = "www.anygen.io",
) -> list[dict]:
    """将 Cookie dict 转换为 Playwright add_cookies 格式。"""
    return [
        {"name": k, "value": v, "domain": domain, "path": "/"}
        for k, v in cookies.items()
    ]


def browser_cookies_to_header(cookies: list[dict]) -> str:
    """将 Playwright cookies 列表转换为 HTTP Cookie Header 字符串。"""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


# ---------------------------------------------------------------------------
# 浏览器公共配置
# ---------------------------------------------------------------------------

def _browser_args() -> list[str]:
    return [
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


# stealth 初始化脚本：覆盖 navigator.webdriver 等自动化检测点
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'zh-CN', 'zh'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (params) =>
    params.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(params);
"""

# 从外部 JS 文件加载
_GET_CLIENT_VARS_JS = Path(__file__).with_name("get_client_vars.js").read_text(
    encoding="utf-8"
)


# ---------------------------------------------------------------------------
# 通用重试机制（区分可重试/不可重试错误）
# ---------------------------------------------------------------------------

# 可重试的 HTTP 状态码（服务端或网关错误）
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504, 429}


def retry_request(
    fn,
    *args,
    max_attempts: int = 3,
    backoff_base: int = 2,
    label: str = "",
    **kwargs,
) -> Any:
    """
    通用重试包装，带指数退避。
    - 5xx / 429 / 网络错误：重试
    - 4xx（非 429）：直接抛出，不重试（无意义）
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            log.info("[%s] attempt %d/%d", label, attempt, max_attempts)
            return fn(*args, **kwargs)
        except requests.HTTPError as e:
            # 区分可重试和不可重试的 HTTP 错误
            status = e.response.status_code if e.response is not None else 0
            if status not in _RETRYABLE_STATUS_CODES:
                log.error("[%s] HTTP %d 不可重试，直接抛出", label, status)
                raise
            last_exc = e
            if attempt == max_attempts:
                raise
            wait = backoff_base ** attempt
            log.warning("[%s] HTTP %d，%ds 后重试", label, status, wait)
            time.sleep(wait)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt == max_attempts:
                raise
            wait = backoff_base ** attempt
            log.warning("[%s] 网络错误，%ds 后重试：%s", label, wait, e)
            time.sleep(wait)
        except ValueError as e:
            # JSON 解析失败，可能是临时响应异常
            last_exc = e
            if attempt == max_attempts:
                raise
            wait = backoff_base ** attempt
            log.warning("[%s] 解析失败，%ds 后重试：%s", label, wait, e)
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# requests Session（GET 用 / POST 用）
# ---------------------------------------------------------------------------

_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.anygen.io",
    "User-Agent": _UNIFIED_USER_AGENT,  # 与 Playwright 保持一致
}


def _apply_proxy(session: requests.Session, cfg: Config) -> None:
    session.trust_env = False
    if cfg.proxy_server:
        session.proxies.update({
            "http": cfg.proxy_server,
            "https": cfg.proxy_server,
        })


def make_get_session(cfg: Config) -> requests.Session:
    """创建 GET 用 Session，只需浏览器获取的 Cookie，不带 csrf_token。"""
    if not cfg.fixed_cookie:
        raise RuntimeError("Cookie 未初始化，请先获取")

    session = requests.Session()
    _apply_proxy(session, cfg)
    session.headers.update(_BASE_HEADERS)
    session.headers["Cookie"] = cfg.fixed_cookie
    session.headers["Referer"] = cfg.page_url
    return session


def make_post_session(cfg: Config) -> requests.Session:
    """
    创建 POST 用 Session，使用用户提供的 csrf_cookie（含 _csrf_token）。
    如果未提供 csrf_cookie，则回退到 GET 用 Cookie。
    """
    cookie = cfg.csrf_cookie or cfg.fixed_cookie
    if not cookie:
        raise RuntimeError("无可用 Cookie（csrf_cookie 和 fixed_cookie 均为空）")

    parsed = parse_cookie_str(cookie)
    csrf_token = parsed.get("_csrf_token", "")
    if not csrf_token:
        log.warning("POST Session 的 Cookie 中没有 _csrf_token，POST 请求可能被拒绝")

    session = requests.Session()
    _apply_proxy(session, cfg)
    session.headers.update(_BASE_HEADERS)
    session.headers["Content-Type"] = "application/json"
    session.headers["Cookie"] = cookie
    session.headers["Referer"] = cfg.page_url
    session.headers["x-csrftoken"] = csrf_token
    return session


# ---------------------------------------------------------------------------
# 步骤 2：file_system 推断页数
# ---------------------------------------------------------------------------

def _fetch_file_system_inner(session: requests.Session, url: str) -> dict[str, Any]:
    """单次 file_system 请求（供 retry_request 调用）。"""
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(
            "file_system 接口失败：" + json.dumps(body, ensure_ascii=False)[:2000]
        )
    return body


def fetch_file_system(session: requests.Session, cfg: Config) -> dict[str, Any]:
    """GET file_system 接口，带统一重试。"""
    url = f"https://www.anygen.io/api/page/file_system/{cfg.page_id}/files"
    body = retry_request(
        _fetch_file_system_inner, session, url,
        label="file_system",
    )

    Path(cfg.debug_file_system).write_text(
        json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("[file_system] 已保存到 %s", cfg.debug_file_system)
    return body


def infer_slide_count(resp_json: dict[str, Any]) -> dict[str, Any]:
    """从 file_system 响应推断 PPT 页数。"""
    files = resp_json.get("data", {}).get("files", [])
    if not isinstance(files, list):
        raise RuntimeError("file_system 返回结构异常：data.files 不是数组")

    # 找 .slides 主文件
    manifests = [
        f for f in files
        if not f.get("is_directory")
        and str(f.get("name", "")).endswith(".slides")
        and str(f.get("path", "")).startswith("/home/user/workspace/slides/")
    ]
    if not manifests:
        raise RuntimeError(
            "未找到 /home/user/workspace/slides/ 下的 .slides 主文件"
        )

    # 优先 visible，其次最新修改时间，其次最大 size
    manifests.sort(
        key=lambda f: (
            f.get("folder_visibility") == "visible",
            int(f.get("modified_time") or 0),
            int(f.get("size") or 0),
        ),
        reverse=True,
    )
    manifest = manifests[0]
    manifest_path = str(manifest.get("path", ""))

    deck_base = re.sub(r"\.slides$", "", manifest_path.rsplit("/", 1)[-1])
    slide_root = manifest_path.rsplit("/", 1)[0]
    slide_dir = f"{slide_root}/{deck_base}/"

    slide_files = sorted(
        (f for f in files
         if not f.get("is_directory")
         and str(f.get("path", "")).startswith(slide_dir)
         and re.match(r"slide_\w+\.xml$", str(f.get("name", "")))),
        key=lambda f: str(f.get("name", "")),
    )

    if not slide_files:
        raise RuntimeError(
            f"找到 .slides 主文件，但 {slide_dir} 下无 slide_*.xml\n"
            f"manifest_path={manifest_path}"
        )

    info = {
        "manifest_path": manifest_path,
        "slide_dir": slide_dir,
        "slide_count": len(slide_files),
        "slide_files": [str(f.get("name", "")) for f in slide_files],
    }
    log.info("[file_system] manifest    = %s", info["manifest_path"])
    log.info("[file_system] slide_dir   = %s", info["slide_dir"])
    log.info("[file_system] slide_count = %d", info["slide_count"])
    log.info("[file_system] slide_files = %s", info["slide_files"])
    return info


# ---------------------------------------------------------------------------
# 核心：单次浏览器启动，完成 Cookie 获取 + client_vars 抓取
# ---------------------------------------------------------------------------

async def acquire_cookie_and_client_vars(cfg: Config) -> tuple[str, int]:
    """
    【核心优化】只启动一次 Playwright，在同一个 context 中完成：
      1. 打开页面并提取 Cookie
      2. 等待 editor 加载，抓取 export client_vars

    相比原版节省一次 Chromium 启动（5–15 秒）。

    如果 cfg.fixed_cookie 已预先加载（来自环境变量/文件），则跳过 Cookie 提取，
    直接注入已有 Cookie 并抓取 client_vars。
    """
    log.info("=== 启动浏览器（Cookie 获取 + client_vars 抓取）===")

    proxy = {"server": cfg.proxy_server} if cfg.proxy_server else None
    cookie_already_loaded = bool(cfg.fixed_cookie)

    async with async_playwright() as p:
        context: BrowserContext = await p.chromium.launch_persistent_context(
            cfg.user_data_dir,
            headless=cfg.headless,
            proxy=proxy,
            user_agent=_UNIFIED_USER_AGENT,
            viewport={"width": 1440, "height": 1000},
            args=_browser_args(),
        )
        await context.add_init_script(_STEALTH_JS)

        # 清除旧 Cookie，注入正确的 Cookie
        await context.clear_cookies()

        if cookie_already_loaded:
            # 已有 Cookie（来自文件/环境变量），直接注入
            log.info("[browser] 注入已有 Cookie")
            cookie_dict = parse_cookie_str(cfg.fixed_cookie)
            await context.add_cookies(
                cookies_dict_to_playwright(cookie_dict, domain="www.anygen.io")
            )
        # 若无已有 Cookie，不注入任何内容，让页面自然生成

        page = context.pages[0] if context.pages else await context.new_page()

        # 过滤浏览器噪声日志
        def _on_console(msg):
            text = msg.text
            if "net::ERR_FAILED" in text or "net::ERR_CONNECTION_CLOSED" in text:
                return
            log.info("[browser] %s", text)

        page.on("console", _on_console)

        try:
            log.info("[browser] 打开：%s", cfg.page_url)
            await page.goto(
                cfg.page_url,
                wait_until="load",
                timeout=90_000,
            )
            await page.wait_for_timeout(3_000)

            # 若无预加载 Cookie，从浏览器当前状态提取
            if not cookie_already_loaded:
                all_cookies = await context.cookies("https://www.anygen.io")
                if not all_cookies:
                    raise RuntimeError("未能获取到任何 Cookie")
                raw_cookie = browser_cookies_to_header(all_cookies)
                cfg._fixed_cookie = raw_cookie
                Path(cfg.debug_cookie).write_text(raw_cookie, encoding="utf-8")
                log.info("[browser] Cookie 已提取并保存到 %s", cfg.debug_cookie)

            # ---- 抓取 client_vars（复用同一 page）----
            expected_slide_count = cfg._expected_slide_count
            min_block_count = max(10, expected_slide_count * cfg.min_blocks_per_slide)
            log.info(
                "[inject] expectedSlideCount=%d minBlockCount=%d",
                expected_slide_count, min_block_count,
            )

            result = await page.evaluate(
                _GET_CLIENT_VARS_JS,
                {
                    "minBlockCount": min_block_count,
                    "expectedSlideCount": expected_slide_count,
                    "stableMs": cfg.stable_seconds * 1000,
                    "timeoutMs": cfg.editor_wait_seconds * 1000,
                },
            )

        except Exception:
            try:
                await page.screenshot(path=cfg.error_screenshot, full_page=True)
                log.info("[debug] 截图已保存：%s", cfg.error_screenshot)
            except Exception as se:
                log.warning("[debug] 截图失败：%s", se)
            raise
        finally:
            await context.close()

    client_vars_str: str = result["clientVarsString"]
    actual_slide_count: int = result.get("actualSlideCount", result["slideCount"])
    log.info(
        "[client_vars] slide_count=%d block_count=%d actual_slide_count=%d string_length=%d",
        result["slideCount"], result["blockCount"], actual_slide_count, result["stringLength"],
    )

    Path(cfg.debug_client_vars).write_text(client_vars_str, encoding="utf-8")
    log.info("[client_vars] 已保存到 %s", cfg.debug_client_vars)

    return client_vars_str, actual_slide_count


# ---------------------------------------------------------------------------
# client_vars 校验
# ---------------------------------------------------------------------------

def _find_presentation_root(block_map: dict, root_id: str) -> dict:
    """从 block_map 中找到 presentation 根节点 data，抽取公共逻辑。"""
    root_data = block_map.get(root_id, {}).get("data", {})
    if root_data.get("type") == "presentation":
        return root_data
    return next(
        (b.get("data", {}) for b in block_map.values()
         if isinstance(b, dict) and b.get("data", {}).get("type") == "presentation"),
        {},
    )


def validate_client_vars(client_vars_str: str, cfg: Config, actual_slide_count: int = 0) -> None:
    """解析并校验 client_vars 的完整性。actual_slide_count 来自 DOM 的 data-slide-index。"""
    obj = json.loads(client_vars_str)
    expected_slide_count = actual_slide_count or cfg._expected_slide_count
    min_block_count = max(10, expected_slide_count * cfg.min_blocks_per_slide)

    if obj.get("type") != "CLIENT_VARS":
        raise RuntimeError(f"client_vars.type 异常：{obj.get('type')}")

    block_map = obj.get("block_map") or {}
    block_count = len(block_map)

    root_data = _find_presentation_root(block_map, obj.get("id", ""))
    slide_count = len(root_data.get("slides") or [])

    log.info(
        "[validate] id=%s slide_count=%d block_count=%d",
        obj.get("id"), slide_count, block_count,
    )

    if expected_slide_count and slide_count < expected_slide_count:
        raise RuntimeError(
            f"client_vars 页数不足：当前 {slide_count}，预期 {expected_slide_count}"
        )
    if block_count < min_block_count:
        raise RuntimeError(
            f"client_vars block 数不足：当前 {block_count}，最低 {min_block_count}"
        )


# ---------------------------------------------------------------------------
# 步骤 4：创建导出任务
# ---------------------------------------------------------------------------

def _create_export_job_inner(
    session: requests.Session, url: str, payload: dict,
) -> tuple[str, int]:
    """单次创建导出任务请求（供 retry_request 调用）。"""
    resp = session.post(url, json=payload, timeout=90)
    resp.raise_for_status()
    body = resp.json()

    log.info("[create_job] response = %s", json.dumps(body, ensure_ascii=False)[:500])

    if body.get("code") not in (0, None):
        raise RuntimeError(
            "创建导出任务失败：" + json.dumps(body, ensure_ascii=False)
        )

    data = body.get("data") or body
    job_id = data.get("job_id") or data.get("ticket") or body.get("job_id")
    job_timeout = int(data.get("job_timeout") or body.get("job_timeout") or 90)

    if not job_id:
        raise RuntimeError(
            "响应中没有 job_id：" + json.dumps(body, ensure_ascii=False)
        )

    return job_id, job_timeout


def create_export_job(
    session: requests.Session,
    cfg: Config,
    client_vars_str: str,
) -> tuple[str, int]:
    """POST 创建导出任务，带统一重试。"""
    url = f"https://www.anygen.io/api/page/pages/{cfg.page_id}/export-jobs/"
    payload = {
        "export_type": 3,
        "extra_params": {"client_vars": client_vars_str},
    }

    job_id, job_timeout = retry_request(
        _create_export_job_inner, session, url, payload,
        label="create_job",
    )

    log.info("[create_job] job_id=%s job_timeout=%d", job_id, job_timeout)
    return job_id, job_timeout


# ---------------------------------------------------------------------------
# 步骤 5：轮询导出任务
# ---------------------------------------------------------------------------

def poll_export_job(
    session: requests.Session,
    job_id: str,
    max_wait_seconds: int,
) -> str:
    """
    轮询任务状态，返回 document_id 或 document_url。

    轮询策略：
      - 排队中（job_status=1）：指数退避，最长 30s，等待资源分配
      - 进行中（job_status=2）：固定 3s，任务快完成时尽快获取结果
      - 服务端错误（5xx）：指数退避后重试，连续 3 次放弃
    """
    url = f"https://www.anygen.io/api/page/export-jobs/{job_id}"
    deadline = time.time() + max_wait_seconds
    queued_interval = 3.0   # 排队初始间隔
    running_interval = 3.0  # 进行中固定间隔
    round_num = 0
    consecutive_errors = 0
    max_server_errors = 3

    while time.time() < deadline:
        round_num += 1
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            body = resp.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            consecutive_errors += 1
            log.warning(
                "[poll %d] 网络异常：%s，%.0fs 后重试（连续错误 %d/%d）",
                round_num, e, queued_interval, consecutive_errors, max_server_errors,
            )
            if consecutive_errors >= max_server_errors:
                raise RuntimeError(
                    f"轮询连续 {max_server_errors} 次网络异常，放弃：{e}"
                ) from e
            time.sleep(queued_interval)
            queued_interval = min(queued_interval * 1.5, 30)
            continue
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status not in _RETRYABLE_STATUS_CODES:
                raise  # 4xx 直接抛出
            consecutive_errors += 1
            log.warning(
                "[poll %d] HTTP %d，%.0fs 后重试（连续错误 %d/%d）",
                round_num, status, queued_interval, consecutive_errors, max_server_errors,
            )
            if consecutive_errors >= max_server_errors:
                raise RuntimeError(f"轮询连续 {max_server_errors} 次服务端错误，放弃")
            time.sleep(queued_interval)
            queued_interval = min(queued_interval * 1.5, 30)
            continue
        except ValueError as e:
            consecutive_errors += 1
            log.warning("[poll %d] JSON 解析失败：%s", round_num, e)
            if consecutive_errors >= max_server_errors:
                raise RuntimeError("轮询 JSON 解析连续失败") from e
            time.sleep(queued_interval)
            continue

        if body.get("code") not in (0, None):
            consecutive_errors += 1
            code = body.get("code")
            log.warning(
                "[poll %d] 服务端返回 code=%s，%.0fs 后重试（连续错误 %d/%d）",
                round_num, code, queued_interval, consecutive_errors, max_server_errors,
            )
            if consecutive_errors >= max_server_errors:
                raise RuntimeError(
                    f"轮询连续 {max_server_errors} 次服务端错误，放弃："
                    + json.dumps(body, ensure_ascii=False)[:2000]
                )
            time.sleep(queued_interval)
            queued_interval = min(queued_interval * 1.5, 30)
            continue

        # 请求成功，重置连续错误计数
        consecutive_errors = 0

        data = body.get("data") or body
        result = data.get("result") or {}
        job_status = data.get("job_status")
        if job_status is None:
            job_status = result.get("job_status")
        error = data.get("error")
        if error is None:
            error = result.get("error")

        log.info("[poll %d] job_status=%s", round_num, job_status)

        if job_status == 0:  # 成功
            doc_id = result.get("document_id") or data.get("document_id")
            doc_url = result.get("document_url") or data.get("document_url")
            if doc_id:
                log.info("[poll] document_id = %s", doc_id)
                return doc_id
            if doc_url:
                log.info("[poll] document_url = %s", doc_url)
                return doc_url
            raise RuntimeError(
                "任务成功但无 document_id/document_url：" + json.dumps(body, ensure_ascii=False)
            )

        if job_status == 1:  # 排队中：指数退避
            time.sleep(queued_interval)
            queued_interval = min(queued_interval * 1.5, 30)
            continue

        if job_status == 2:  # 进行中：固定短间隔，尽快拿到结果
            time.sleep(running_interval)
            continue

        raise RuntimeError(
            f"导出任务失败：job_status={job_status}"
            + (f", error={error}" if error else "")
            + "\n" + json.dumps(body, ensure_ascii=False)[:2000]
        )

    raise TimeoutError(f"导出超时（{max_wait_seconds}s）：job_id={job_id}")


# ---------------------------------------------------------------------------
# 步骤 6：下载并校验 PPTX
# ---------------------------------------------------------------------------

def download_and_validate(
    session: requests.Session,
    doc_id_or_url: str,
    output_file: str,
) -> None:
    """下载 PPTX 文件，并校验其为合法 ZIP/PPTX 格式。"""
    if doc_id_or_url.startswith("http://") or doc_id_or_url.startswith("https://"):
        url = doc_id_or_url
    else:
        url = (
            "https://www.anygen.io"
            f"/space/api/box/stream/download/all/{doc_id_or_url}"
        )

    log.info("[download] %s", url)

    def _do_download():
        resp = session.get(url, stream=True, timeout=180)
        resp.raise_for_status()
        return resp

    resp = retry_request(_do_download, label="download", max_attempts=3)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with output_path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=256 * 1024):
            if chunk:
                f.write(chunk)
                total += len(chunk)

    log.info("[download] 写入 %d 字节 → %s", total, output_path.resolve())

    # 校验：必须是合法 ZIP，且包含 ppt/presentation.xml
    try:
        with zipfile.ZipFile(output_path) as zf:
            names = zf.namelist()
            if "ppt/presentation.xml" not in names:
                raise RuntimeError(
                    "下载的文件不是有效 PPTX（缺少 ppt/presentation.xml）"
                )
    except zipfile.BadZipFile:
        raise RuntimeError(
            "下载的文件不是合法 ZIP，可能是错误响应页面，"
            f"文件大小 {total} 字节"
        )

    log.info("[download] PPTX 校验通过 ✓")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def main(cfg: Config) -> None:
    start = time.time()

    # ── 加载 csrf_cookie（POST 用，含 _csrf_token）───────────────────
    cli_csrf = getattr(cfg, "_cli_csrf_cookie", "")
    cfg.load_csrf_cookie(cli_value=cli_csrf)

    # ── 步骤 1：尝试从本地加载 Cookie ────────────────────────────────
    cookie_preloaded = cfg.load_cookie_from_env_or_file()
    if cookie_preloaded:
        log.info("使用已有 Cookie（来自环境变量或 cookie.txt）")
    else:
        log.info("未找到已有 Cookie，将在浏览器中自动提取")

    # ── 步骤 2：推断页数（需要 Cookie，若已预加载则直接请求）─────────
    # 若无预加载 Cookie，先用浏览器打开页面获取 Cookie，再做 file_system 请求。
    # 此处做一次判断：有 Cookie 则直接请求，无则先启动浏览器。
    if cookie_preloaded:
        log.info("=== 步骤 2：推断 PPT 页数 ===")
        get_session = make_get_session(cfg)
        fs_json = fetch_file_system(get_session, cfg)
        slide_info = infer_slide_count(fs_json)
        cfg._expected_slide_count = slide_info["slide_count"]
        log.info("预期页数：%d", cfg._expected_slide_count)

        # ── 步骤 3：浏览器抓取 client_vars（Cookie 已有，直接注入）──
        log.info("=== 步骤 3：抓取 client_vars ===")
        client_vars_str, actual_slide_count = await acquire_cookie_and_client_vars(cfg)

    else:
        # 无预加载 Cookie：浏览器启动后先拿 Cookie，再用 requests 推断页数，
        # 但 file_system 需要 Cookie，所以先启动浏览器拿 Cookie，
        # 然后在同一个浏览器中抓 client_vars。
        # 为保持单次浏览器启动，将 file_system 请求安排在 Cookie 提取后、
        # evaluate 注入前完成——通过在 acquire_cookie_and_client_vars 中
        # 插入一个回调来实现。
        log.info("=== 步骤 2+3：浏览器提取 Cookie + 推断页数 + 抓取 client_vars ===")
        client_vars_str, actual_slide_count = await _acquire_all_in_one(cfg)

    # ── 校验 ─────────────────────────────────────────────────────────
    log.info("=== 校验 client_vars ===")
    validate_client_vars(client_vars_str, cfg, actual_slide_count)

    # ── 步骤 4：创建导出任务（POST，需要 csrf_token）──────────────────
    log.info("=== 步骤 4：创建导出任务 ===")
    post_session = make_post_session(cfg)
    job_id, job_timeout = create_export_job(post_session, cfg, client_vars_str)

    # ── 步骤 5：轮询（使用 post_session 保持同一认证态）──────────────
    log.info("=== 步骤 5：轮询导出任务 ===")
    max_wait = max(cfg.export_wait_seconds, job_timeout + 60)
    doc_id_or_url = poll_export_job(post_session, job_id, max_wait)

    # ── 步骤 6：下载 & 校验 ──────────────────────────────────────────
    log.info("=== 步骤 6：下载 PPTX ===")
    download_and_validate(post_session, doc_id_or_url, cfg.output_file)

    elapsed = time.time() - start
    log.info("=== 完成 ✓  耗时 %.1f 秒  输出：%s ===", elapsed, cfg.output_file)


async def _acquire_all_in_one(cfg: Config) -> tuple[str, int]:
    """
    无预加载 Cookie 时的一体化流程：
      1. 浏览器打开页面 → 提取 Cookie
      2. 用提取到的 Cookie 做 file_system 请求（requests，在浏览器等待页面加载期间并行不安全，故串行）
      3. 在同一 page 上 evaluate client_vars JS

    保证整个过程只启动一次 Playwright。
    """
    log.info("=== 启动浏览器（单次，完成 Cookie + 页数推断 + client_vars）===")

    proxy = {"server": cfg.proxy_server} if cfg.proxy_server else None

    async with async_playwright() as p:
        context: BrowserContext = await p.chromium.launch_persistent_context(
            cfg.user_data_dir,
            headless=cfg.headless,
            proxy=proxy,
            user_agent=_UNIFIED_USER_AGENT,
            viewport={"width": 1440, "height": 1000},
            args=_browser_args(),
        )
        await context.add_init_script(_STEALTH_JS)
        await context.clear_cookies()

        page = context.pages[0] if context.pages else await context.new_page()

        def _on_console(msg):
            text = msg.text
            if "net::ERR_FAILED" in text or "net::ERR_CONNECTION_CLOSED" in text:
                return
            log.info("[browser] %s", text)

        page.on("console", _on_console)

        try:
            log.info("[browser] 打开：%s", cfg.page_url)
            await page.goto(cfg.page_url, wait_until="load", timeout=90_000)
            await page.wait_for_timeout(3_000)

            # ---- 提取 Cookie ----
            all_cookies = await context.cookies("https://www.anygen.io")
            if not all_cookies:
                raise RuntimeError("未能获取到任何 Cookie")
            raw_cookie = browser_cookies_to_header(all_cookies)
            cfg._fixed_cookie = raw_cookie
            Path(cfg.debug_cookie).write_text(raw_cookie, encoding="utf-8")
            log.info("[browser] Cookie 已提取，保存到 %s", cfg.debug_cookie)

            # ---- 用 Cookie 做 file_system 请求（同步，不阻塞浏览器渲染）----
            log.info("[file_system] 推断 PPT 页数...")
            get_session = make_get_session(cfg)
            fs_json = fetch_file_system(get_session, cfg)
            slide_info = infer_slide_count(fs_json)
            cfg._expected_slide_count = slide_info["slide_count"]
            log.info("预期页数：%d", cfg._expected_slide_count)

            # ---- 抓取 client_vars ----
            expected_slide_count = cfg._expected_slide_count
            min_block_count = max(10, expected_slide_count * cfg.min_blocks_per_slide)
            log.info(
                "[inject] expectedSlideCount=%d minBlockCount=%d",
                expected_slide_count, min_block_count,
            )

            result = await page.evaluate(
                _GET_CLIENT_VARS_JS,
                {
                    "minBlockCount": min_block_count,
                    "expectedSlideCount": expected_slide_count,
                    "stableMs": cfg.stable_seconds * 1000,
                    "timeoutMs": cfg.editor_wait_seconds * 1000,
                },
            )

        except Exception:
            try:
                await page.screenshot(path=cfg.error_screenshot, full_page=True)
                log.info("[debug] 截图已保存：%s", cfg.error_screenshot)
            except Exception as se:
                log.warning("[debug] 截图失败：%s", se)
            raise
        finally:
            await context.close()

    client_vars_str: str = result["clientVarsString"]
    actual_slide_count: int = result.get("actualSlideCount", result["slideCount"])
    log.info(
        "[client_vars] slide_count=%d block_count=%d actual_slide_count=%d string_length=%d",
        result["slideCount"], result["blockCount"], actual_slide_count, result["stringLength"],
    )

    Path(cfg.debug_client_vars).write_text(client_vars_str, encoding="utf-8")
    log.info("[client_vars] 已保存到 %s", cfg.debug_client_vars)

    return client_vars_str, actual_slide_count


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="AnyGen PPTX 自动导出工具（优化版）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "url",
        help="完整的页面 URL，例如 https://www.anygen.io/task/your-slug-PAGE_ID",
    )
    parser.add_argument(
        "-o", "--output",
        default=Config.output_file,
        metavar="FILE",
        help="输出 PPTX 文件路径",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行浏览器",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="禁用代理",
    )
    parser.add_argument(
        "--proxy",
        default=Config.proxy_server,
        metavar="URL",
        help="代理服务器地址",
    )
    parser.add_argument(
        "--stable-seconds",
        type=int,
        default=Config.stable_seconds,
        metavar="N",
        help="editor 数据稳定判定时间（秒）",
    )
    parser.add_argument(
        "--csrf-cookie",
        default="",
        metavar="COOKIE",
        help="含 _csrf_token 的 Cookie 字符串（POST 导出任务用），也可通过 ANYGEN_CSRF_COOKIE 环境变量或 csrf_cookie.txt 提供",
    )
    args = parser.parse_args()

    cfg = Config(
        page_url=args.url,
        output_file=args.output,
        headless=args.headless,
        proxy_server=None if args.no_proxy else args.proxy,
        stable_seconds=args.stable_seconds,
    )
    cfg._cli_csrf_cookie = args.csrf_cookie
    return cfg


if __name__ == "__main__":
    asyncio.run(main(parse_args()))