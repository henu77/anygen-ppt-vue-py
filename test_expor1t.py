"""
AnyGen PPTX 自动导出脚本（优化版）

流程：
  1. 用 Playwright 打开登录页，自动获取最新 Cookie（含 _csrf_token）
  2. 请求 /api/page/file_system/{PAGE_ID}/files，动态推断 PPT 页数
  3. Playwright 打开编辑页面，注入统一 Cookie
  4. 扫 React Fiber，等待 editor.getClientVars() 稳定后抓取 export client_vars
  5. POST export-jobs 创建导出任务（_csrf_token 单独传 Header）
  6. 轮询任务状态（指数退避）
  7. 下载 PPTX 并校验合法性

依赖安装：
  pip install playwright requests
  python -m playwright install chromium

Cookie 说明：
  脚本会自动通过浏览器登录页刷新 Cookie，无需手动维护。
  如需跳过登录步骤（使用已有 Cookie），可设置环境变量：
    ANYGEN_COOKIE=<完整 Cookie 字符串>
  或在脚本同目录创建 cookie.txt，将完整 Cookie 粘贴进去。

用法：
  python anygen_export.py                         # 使用脚本内 PAGE_ID
  python anygen_export.py <page_id>               # 指定 page_id
  python anygen_export.py <page_id> -o out.pptx   # 指定输出文件
  python anygen_export.py <page_id> --headless    # 无头模式
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

@dataclass
class Config:
    # ---- 必填 ----
    page_id: str = "QobFpx5CxaOaO7gJKbll6LDkgzh"

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
    login_wait_seconds: int = 120       # 等待用户手动完成登录的最长时间

    # ---- 内部（运行时填充）----
    _fixed_cookie: str = field(default="", init=False, repr=False)
    _csrf_token: str = field(default="", init=False, repr=False)

    # ------------------------------------------------------------------
    # page_url
    # ------------------------------------------------------------------

    @property
    def page_url(self) -> str:
        return (
            "https://www.anygen.io/task/"
            f"magic-and-josephus-math-exploration-presentation-{self.page_id}"
        )

    # ------------------------------------------------------------------
    # Cookie 属性
    # ------------------------------------------------------------------

    @property
    def fixed_cookie(self) -> str:
        return self._fixed_cookie

    @property
    def csrf_token(self) -> str:
        return self._csrf_token

    def load_cookie_from_env_or_file(self) -> bool:
        """尝试从环境变量或 cookie.txt 读取 Cookie，成功返回 True。"""
        cookie = os.getenv("ANYGEN_COOKIE", "").strip()
        if not cookie:
            cookie_file = Path(__file__).with_name("cookie.txt")
            if cookie_file.exists():
                cookie = cookie_file.read_text(encoding="utf-8").strip()

        if cookie:
            self._set_cookie(cookie)
            return True
        return False

    def _set_cookie(self, raw_cookie: str) -> None:
        self._fixed_cookie = raw_cookie
        parsed = parse_cookie_str(raw_cookie)
        self._csrf_token = parsed.get("_csrf_token", "")
        if not self._csrf_token:
            log.info("Cookie 中没有 _csrf_token，将通过单独请求获取")


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
# 步骤 1：自动登录获取 Cookie
# ---------------------------------------------------------------------------

async def acquire_cookie_via_browser(cfg: Config) -> None:
    """
    打开登录页，等待用户手动登录（或已有 session 自动跳转），
    然后从浏览器提取最新 Cookie，回写到 cfg。
    每次打开时会清除浏览器已有 Cookie。
    """
    log.info("=== 步骤 1：获取最新 Cookie ===")

    proxy = {"server": cfg.proxy_server} if cfg.proxy_server else None

    async with async_playwright() as p:
        context: BrowserContext = await p.chromium.launch_persistent_context(
            cfg.user_data_dir,
            headless=cfg.headless,
            proxy=proxy,
            viewport={"width": 1280, "height": 900},
            args=_browser_args(),
        )

        # 每次打开浏览器时清除已有 Cookie
        await context.clear_cookies()
        log.info("已清除浏览器后台 Cookie")

        page = context.pages[0] if context.pages else await context.new_page()

        log.info("打开登录页：%s", cfg.login_url)
        await page.goto(cfg.login_url, wait_until="domcontentloaded", timeout=60_000)

        # 等待跳转到非登录页（说明已登录）
        deadline = time.time() + cfg.login_wait_seconds
        while time.time() < deadline:
            current_url = page.url
            if "/login" not in current_url and "anygen.io" in current_url:
                log.info("检测到已登录，当前 URL：%s", current_url)
                break
            log.info("等待登录完成... (%s)", current_url)
            await page.wait_for_timeout(3_000)
        else:
            raise TimeoutError(
                f"等待登录超时（{cfg.login_wait_seconds}s），"
                "请在浏览器窗口中完成登录操作。"
            )

        # 提取 Cookie
        all_cookies = await context.cookies("https://www.anygen.io")
        await context.close()

    if not all_cookies:
        raise RuntimeError("登录后未能获取到任何 Cookie")

    raw_cookie = browser_cookies_to_header(all_cookies)
    cfg._set_cookie(raw_cookie)

    # 持久化，方便下次跳过登录
    Path(cfg.debug_cookie).write_text(raw_cookie, encoding="utf-8")
    log.info("Cookie 已获取并保存到 %s", cfg.debug_cookie)
    log.info("_csrf_token = %s", cfg.csrf_token or "(未找到)")


# ---------------------------------------------------------------------------
# requests Session
# ---------------------------------------------------------------------------

def make_session(cfg: Config) -> requests.Session:
    """创建带 Cookie 的 requests Session。csrf_token 将在后续单独获取。"""
    if not cfg.fixed_cookie:
        raise RuntimeError("Cookie 未初始化，请先调用 acquire_cookie_via_browser()")

    session = requests.Session()
    session.trust_env = False

    if cfg.proxy_server:
        session.proxies.update({
            "http": cfg.proxy_server,
            "https": cfg.proxy_server,
        })

    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.anygen.io",
        "Referer": cfg.page_url,
        "Cookie": cfg.fixed_cookie,
        "x-csrftoken": cfg.csrf_token,   # 初始值，后续会通过 API 单独获取更新
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })

    return session


# ---------------------------------------------------------------------------
# 步骤 1.5：单独获取 csrf_token
# ---------------------------------------------------------------------------

def fetch_csrf_token(session: requests.Session, cfg: Config) -> str:
    """
    通过单独请求页面接口获取 csrf_token，不依赖浏览器直接提取。
    依次检查：响应 Cookie 中的 _csrf_token → 响应头 X-CSRFToken → 响应体 JSON。
    """
    url = f"https://www.anygen.io/api/page/file_system/{cfg.page_id}/files"
    log.info("=== 步骤 1.5：单独获取 csrf_token ===")

    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        log.warning("获取 csrf_token 的请求失败：%s", e)
        return ""

    # 1) 从响应 Set-Cookie 中提取
    csrf = resp.cookies.get("_csrf_token", "")
    if csrf:
        log.info("csrf_token 从响应 Cookie 获取：%s", csrf[:20] + "...")
        return csrf

    # 2) 从响应头中提取
    csrf = resp.headers.get("X-CSRFToken", "") or resp.headers.get("X-CSRF-Token", "")
    if csrf:
        log.info("csrf_token 从响应头获取：%s", csrf[:20] + "...")
        return csrf

    # 3) 从响应体 JSON 中提取
    try:
        body = resp.json()
        csrf = body.get("csrf_token", "") or body.get("data", {}).get("csrf_token", "")
        if csrf:
            log.info("csrf_token 从响应体获取：%s", csrf[:20] + "...")
            return csrf
    except ValueError:
        pass

    log.warning("未能通过单独请求获取 csrf_token，将使用 Cookie 中的值")
    return ""


# ---------------------------------------------------------------------------
# 步骤 2：file_system 推断页数
# ---------------------------------------------------------------------------

def fetch_file_system(session: requests.Session, cfg: Config) -> dict[str, Any]:
    """GET file_system 接口，带简单重试。"""
    url = f"https://www.anygen.io/api/page/file_system/{cfg.page_id}/files"

    for attempt in range(1, 4):
        log.info("[file_system] GET %s (attempt %d)", url, attempt)
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            body = resp.json()
            break
        except (requests.RequestException, ValueError) as e:
            if attempt == 3:
                raise
            log.warning("[file_system] 请求失败，%ds 后重试：%s", 2 ** attempt, e)
            time.sleep(2 ** attempt)

    if body.get("code") != 0:
        raise RuntimeError(
            "file_system 接口失败：" + json.dumps(body, ensure_ascii=False)[:2000]
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
        f for f in files
        if not f.get("is_directory")
        and str(f.get("path", "")).startswith(slide_dir)
        and re.match(r"slide_\d+\.xml$", str(f.get("name", "")))
    , key=lambda f: str(f.get("name", ""))
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
# 步骤 3 & 4：Playwright 打开编辑页，抓取 client_vars
# ---------------------------------------------------------------------------

# 注入到浏览器执行的 JS，等待 editor 完全加载后调用 getExportClientVars()
_GET_CLIENT_VARS_JS = r"""
async ({ minBlockCount, expectedSlideCount, stableMs, timeoutMs }) => {
  const TAG = "[AnyGenCV]";
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log = (...a) => console.log(TAG, ...a);

  // ---- 工具函数 ----

  function isObj(x) { return x && typeof x === "object"; }

  function isEditor(x) {
    return isObj(x) && typeof x.getExportClientVars === "function";
  }

  function isEditorRef(x) {
    return isObj(x) && isEditor(x.current);
  }

  function fiberOf(node) {
    if (!node) return null;
    const k = Object.keys(node).find(
      k => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$")
    );
    return k ? node[k] : null;
  }

  // 优先遍历的 key 列表
  const PRIORITY_KEYS = [
    "editorInstanceRef","editorRef","instanceRef","ref","current",
    "props","memoizedProps","pendingProps","memoizedState","stateNode",
    "return","child","sibling"
  ];

  // 跳过的 DOM 相关 key（避免循环引用炸堆栈）
  const SKIP_KEYS = new Set([
    "ownerDocument","parentNode","children","childNodes","document","window"
  ]);

  function scanValue(val, seen, maxDepth) {
    if (!isObj(val) || seen.has(val) || maxDepth < 0) return null;
    seen.add(val);

    if (isEditor(val))    return val;
    if (isEditorRef(val)) return val.current;

    for (const k of PRIORITY_KEYS) {
      try {
        if (k in val) {
          const r = scanValue(val[k], seen, maxDepth - 1);
          if (r) return r;
        }
      } catch {}
    }

    let keys;
    try { keys = Object.keys(val); } catch { return null; }

    for (const k of keys) {
      if (PRIORITY_KEYS.includes(k) || SKIP_KEYS.has(k)) continue;
      try {
        const r = scanValue(val[k], seen, maxDepth - 1);
        if (r) return r;
      } catch {}
    }
    return null;
  }

  function scanFiberTree(root) {
    const stack = [root];
    const seenFibers  = new WeakSet();
    const seenValues  = new WeakSet();   // 提升到 tree 级，避免重复扫描

    while (stack.length) {
      const fiber = stack.pop();
      if (!fiber || seenFibers.has(fiber)) continue;
      seenFibers.add(fiber);

      for (const field of ["memoizedProps","pendingProps","memoizedState","stateNode","ref"]) {
        try {
          const r = scanValue(fiber[field], seenValues, 8);
          if (r) return r;
        } catch {}
      }

      if (fiber.child)   stack.push(fiber.child);
      if (fiber.sibling) stack.push(fiber.sibling);
    }
    return null;
  }

  function findEditor(doc, label) {
    const candidates = [
      doc.getElementById("root"),
      doc.getElementById("__next"),
      doc.body,
      doc.documentElement,
      ...doc.querySelectorAll("div,section,main")
    ].filter(Boolean);

    for (const node of candidates) {
      const fiber = fiberOf(node);
      if (!fiber) continue;
      const editor = scanFiberTree(fiber);
      if (editor) { log("editor found in", label); return editor; }
    }
    return null;
  }

  function findEditorAnywhere() {
    let e = findEditor(document, "main");
    if (e) return e;

    for (let i = 0; i < document.querySelectorAll("iframe").length; i++) {
      try {
        const doc = document.querySelectorAll("iframe")[i].contentDocument;
        if (!doc) continue;
        e = findEditor(doc, "iframe-" + i);
        if (e) return e;
      } catch {}
    }
    return null;
  }

  // ---- 解析 clientVars ----

  function parseCV(cv) {
    if (!cv?.block_map) return { blockCount: 0, slideCount: 0, sig: "0:0" };
    const blockCount = Object.keys(cv.block_map).length;
    let root = cv.block_map[cv.id]?.data;
    if (!root || root.type !== "presentation") {
      root = Object.values(cv.block_map).find(b => b?.data?.type === "presentation")?.data;
    }
    const slideCount = Array.isArray(root?.slides) ? root.slides.length : 0;
    return { blockCount, slideCount, sig: `${slideCount}:${blockCount}` };
  }

  function isComplete(info) {
    const okSlides = !expectedSlideCount || info.slideCount >= expectedSlideCount;
    return okSlides && info.blockCount >= minBlockCount;
  }

  // ---- 主循环 ----

  log("start, expectedSlides=" + expectedSlideCount + " minBlocks=" + minBlockCount);

  const deadline = Date.now() + timeoutMs;
  let lastSig = "";
  let stableSince = 0;
  let lastInfo = null;

  while (Date.now() < deadline) {
    const editor = findEditorAnywhere();

    if (editor) {
      try {
        const cv = editor.getClientVars();
        const info = parseCV(cv);
        lastInfo = info;

        if (info.sig !== lastSig) {
          lastSig = info.sig;
          stableSince = Date.now();
        }

        const stableFor = Date.now() - stableSince;
        log(`slides=${info.slideCount} blocks=${info.blockCount} stableFor=${stableFor}ms`);

        if (isComplete(info) && stableFor >= stableMs) {
          log("stable & complete → calling getExportClientVars()");
          const exportCV = await editor.getExportClientVars();
          if (!exportCV) throw new Error("getExportClientVars() returned empty");

          const finalInfo = parseCV(exportCV);
          log("export done: slides=" + finalInfo.slideCount + " blocks=" + finalInfo.blockCount);

          if (expectedSlideCount && finalInfo.slideCount < expectedSlideCount)
            throw new Error("export slideCount insufficient: " + finalInfo.slideCount);
          if (finalInfo.blockCount < minBlockCount)
            throw new Error("export blockCount insufficient: " + finalInfo.blockCount);

          const str = JSON.stringify(exportCV);
          return {
            clientVarsString: str,
            blockCount: finalInfo.blockCount,
            slideCount: finalInfo.slideCount,
            stringLength: str.length,
            topKeys: Object.keys(exportCV),
            pageId: exportCV.id || ""
          };
        }
      } catch (e) {
        log("editor not ready:", String(e));
      }
    }

    await sleep(1000);
  }

  const msg = lastInfo
    ? `timeout: slides=${lastInfo.slideCount}/${expectedSlideCount} blocks=${lastInfo.blockCount}/${minBlockCount}`
    : "timeout: editor not found";
  throw new Error(msg);
}
"""


def _browser_args() -> list[str]:
    return [
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=Translate,BackForwardCache",
    ]


async def get_client_vars(cfg: Config) -> str:
    """打开编辑页，注入统一 Cookie，等待 editor 加载后抓取 export client_vars。"""
    log.info("=== 步骤 3&4：打开编辑页，抓取 client_vars ===")

    proxy = {"server": cfg.proxy_server} if cfg.proxy_server else None
    min_block_count = max(10, cfg.min_blocks_per_slide)  # 将在 JS 里乘以 slide_count

    async with async_playwright() as p:
        context: BrowserContext = await p.chromium.launch_persistent_context(
            cfg.user_data_dir,
            headless=cfg.headless,
            proxy=proxy,
            viewport={"width": 1440, "height": 1000},
            args=_browser_args(),
        )

        # 每次打开浏览器时清除已有 Cookie
        await context.clear_cookies()
        log.info("已清除浏览器后台 Cookie")

        # 统一注入 Cookie，与 requests session 保持一致
        cookie_dict = parse_cookie_str(cfg.fixed_cookie)
        await context.add_cookies(
            cookies_dict_to_playwright(cookie_dict, domain="www.anygen.io")
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # 过滤浏览器噪声日志
        def _on_console(msg):
            text = msg.text
            if "net::ERR_FAILED" in text or "net::ERR_CONNECTION_CLOSED" in text:
                return
            log.debug("[browser] %s", text)

        page.on("console", _on_console)

        try:
            log.info("[browser] 打开：%s", cfg.page_url)
            await page.goto(
                cfg.page_url,
                wait_until="domcontentloaded",
                timeout=90_000,
            )
            await page.wait_for_timeout(2_000)

            expected_slide_count = getattr(cfg, "_expected_slide_count", 0)
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
    log.info(
        "[client_vars] slide_count=%d block_count=%d string_length=%d",
        result["slideCount"], result["blockCount"], result["stringLength"],
    )

    Path(cfg.debug_client_vars).write_text(client_vars_str, encoding="utf-8")
    log.info("[client_vars] 已保存到 %s", cfg.debug_client_vars)

    return client_vars_str


# ---------------------------------------------------------------------------
# client_vars 校验
# ---------------------------------------------------------------------------

def validate_client_vars(client_vars_str: str, cfg: Config) -> None:
    """解析并校验 client_vars 的完整性。"""
    obj = json.loads(client_vars_str)
    expected_slide_count = getattr(cfg, "_expected_slide_count", 0)
    min_block_count = max(10, expected_slide_count * cfg.min_blocks_per_slide)

    if obj.get("type") != "CLIENT_VARS":
        raise RuntimeError(f"client_vars.type 异常：{obj.get('type')}")

    block_map = obj.get("block_map") or {}
    block_count = len(block_map)

    root_data = block_map.get(obj.get("id"), {}).get("data", {})
    if root_data.get("type") != "presentation":
        root_data = next(
            (b.get("data", {}) for b in block_map.values()
             if isinstance(b, dict) and b.get("data", {}).get("type") == "presentation"),
            {},
        )
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
# 步骤 5：创建导出任务
# ---------------------------------------------------------------------------

def create_export_job(
    session: requests.Session,
    cfg: Config,
    client_vars_str: str,
) -> tuple[str, int]:
    """POST 创建导出任务，_csrf_token 已在 session header 中单独传递。"""
    url = f"https://www.anygen.io/api/page/pages/{cfg.page_id}/export-jobs/"
    payload = {
        "export_type": 3,
        "extra_params": {"client_vars": client_vars_str},
    }

    for attempt in range(1, 4):
        log.info("[create_job] POST %s (attempt %d)", url, attempt)
        try:
            resp = session.post(url, json=payload, timeout=90)
            resp.raise_for_status()
            body = resp.json()
            break
        except (requests.RequestException, ValueError) as e:
            if attempt == 3:
                raise
            log.warning("[create_job] 请求失败，%ds 后重试：%s", 2 ** attempt, e)
            time.sleep(2 ** attempt)

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

    log.info("[create_job] job_id=%s job_timeout=%d", job_id, job_timeout)
    return job_id, job_timeout


# ---------------------------------------------------------------------------
# 步骤 6：轮询导出任务（指数退避）
# ---------------------------------------------------------------------------

def poll_export_job(
    session: requests.Session,
    job_id: str,
    max_wait_seconds: int,
) -> str:
    """轮询任务状态，返回 document_id 或 document_url。"""
    url = f"https://www.anygen.io/api/page/export-jobs/{job_id}"
    deadline = time.time() + max_wait_seconds
    interval = 3.0
    round_num = 0

    while time.time() < deadline:
        round_num += 1
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            body = resp.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("[poll %d] 请求异常：%s，%.0fs 后重试", round_num, e, interval)
            time.sleep(interval)
            interval = min(interval * 1.5, 30)
            continue

        if body.get("code") not in (0, None):
            raise RuntimeError("轮询失败：" + json.dumps(body, ensure_ascii=False))

        data = body.get("data") or body
        result = data.get("result") or {}
        job_status = data.get("job_status") or result.get("job_status")
        error = data.get("error") or result.get("error")

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

        if job_status in (1, 2):  # 排队 / 进行中
            time.sleep(interval)
            interval = min(interval * 1.5, 30)  # 指数退避，上限 30s
            continue

        raise RuntimeError(
            f"导出任务失败：job_status={job_status}"
            + (f", error={error}" if error else "")
            + "\n" + json.dumps(body, ensure_ascii=False)[:2000]
        )

    raise TimeoutError(f"导出超时（{max_wait_seconds}s）：job_id={job_id}")


# ---------------------------------------------------------------------------
# 步骤 7：下载并校验 PPTX
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

    for attempt in range(1, 4):
        try:
            resp = session.get(url, stream=True, timeout=180)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == 3:
                raise
            log.warning("[download] 请求失败，%ds 后重试：%s", 2 ** attempt, e)
            time.sleep(2 ** attempt)

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

    # ── 步骤 1：获取 Cookie ──────────────────────────────────────────
    if cfg.load_cookie_from_env_or_file():
        log.info("使用已有 Cookie（来自环境变量或 cookie.txt）")
        log.info("_csrf_token = %s", cfg.csrf_token or "(未找到)")
    else:
        log.info("未找到已有 Cookie，将通过浏览器登录获取")
        await acquire_cookie_via_browser(cfg)

    # ── 步骤 2：推断页数 ─────────────────────────────────────────────
    log.info("=== 步骤 2：推断 PPT 页数 ===")
    session = make_session(cfg)

    # ── 步骤 1.5：单独获取 csrf_token ────────────────────────────────
    fresh_token = fetch_csrf_token(session, cfg)
    if fresh_token:
        cfg._csrf_token = fresh_token
        session.headers["x-csrftoken"] = fresh_token
        log.info("已用单独获取的 csrf_token 更新 session")

    fs_json = fetch_file_system(session, cfg)
    slide_info = infer_slide_count(fs_json)
    cfg._expected_slide_count = slide_info["slide_count"]  # 运行时注入
    log.info("预期页数：%d", cfg._expected_slide_count)

    # ── 步骤 3&4：抓取 client_vars ───────────────────────────────────
    client_vars_str = await get_client_vars(cfg)

    # ── 校验 ─────────────────────────────────────────────────────────
    log.info("=== 校验 client_vars ===")
    validate_client_vars(client_vars_str, cfg)

    # ── 步骤 5：创建导出任务 ─────────────────────────────────────────
    log.info("=== 步骤 5：创建导出任务 ===")
    job_id, job_timeout = create_export_job(session, cfg, client_vars_str)

    # ── 步骤 6：轮询 ─────────────────────────────────────────────────
    log.info("=== 步骤 6：轮询导出任务 ===")
    max_wait = max(cfg.export_wait_seconds, job_timeout + 60)
    doc_id_or_url = poll_export_job(session, job_id, max_wait)

    # ── 步骤 7：下载 & 校验 ──────────────────────────────────────────
    log.info("=== 步骤 7：下载 PPTX ===")
    download_and_validate(session, doc_id_or_url, cfg.output_file)

    elapsed = time.time() - start
    log.info("=== 完成 ✓  耗时 %.1f 秒  输出：%s ===", elapsed, cfg.output_file)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="AnyGen PPTX 自动导出工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "page_id",
        nargs="?",
        default=Config.page_id,
        help="AnyGen Page ID",
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
    args = parser.parse_args()

    cfg = Config(
        page_id=args.page_id,
        output_file=args.output,
        headless=args.headless,
        proxy_server=None if args.no_proxy else args.proxy,
        stable_seconds=args.stable_seconds,
    )
    return cfg


if __name__ == "__main__":
    asyncio.run(main(parse_args()))