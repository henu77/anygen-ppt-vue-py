// get_client_vars.js
// 注入到浏览器执行，等待 editor 完全加载后调用 getExportClientVars()
// 参数: { minBlockCount, expectedSlideCount, stableMs, timeoutMs }
//
// 优化项：
//   - editor 引用缓存，找到后不再重复扫描 Fiber 树
//   - PRIORITY_KEYS 改为 Set，Object.keys 遍历过滤已处理的 key（O(1) 查找）
//   - iframe 列表缓存，避免每次调用重复 querySelectorAll
//   - 自适应轮询间隔：未找到 editor 时 500ms，找到后 100ms，数据稳定后 500ms

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

  // 优先遍历的 key 列表（改为 Set，O(1) 查找）
  const PRIORITY_KEYS = [
    "editorInstanceRef","editorRef","instanceRef","ref","current",
    "props","memoizedProps","pendingProps","memoizedState","stateNode",
    "return","child","sibling"
  ];
  const PRIORITY_KEY_SET = new Set(PRIORITY_KEYS);

  // 跳过的 DOM 相关 key（避免循环引用炸堆栈）
  const SKIP_KEYS = new Set([
    "ownerDocument","parentNode","children","childNodes","document","window"
  ]);

  function scanValue(val, seen, maxDepth) {
    if (!isObj(val) || seen.has(val) || maxDepth < 0) return null;
    seen.add(val);

    if (isEditor(val))    return val;
    if (isEditorRef(val)) return val.current;

    // 优先遍历高优先级 key
    for (const k of PRIORITY_KEYS) {
      try {
        if (k in val) {
          const r = scanValue(val[k], seen, maxDepth - 1);
          if (r) return r;
        }
      } catch {}
    }

    // 兜底遍历其余 key，跳过已处理的优先 key 和 DOM key
    let keys;
    try { keys = Object.keys(val); } catch { return null; }

    for (const k of keys) {
      if (PRIORITY_KEY_SET.has(k) || SKIP_KEYS.has(k)) continue; // O(1)
      try {
        const r = scanValue(val[k], seen, maxDepth - 1);
        if (r) return r;
      } catch {}
    }
    return null;
  }

  function scanFiberTree(root, seenFibers, seenValues) {
    const stack = [root];

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

  function findEditor(doc, label, seenFibers, seenValues) {
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
      const editor = scanFiberTree(fiber, seenFibers, seenValues);
      if (editor) { log("editor found in", label); return editor; }
    }
    return null;
  }

  // 缓存 iframe 列表，避免每次循环重新 querySelectorAll
  function buildIframeCache() {
    return Array.from(document.querySelectorAll("iframe"));
  }

  function findEditorAnywhere(iframeCache) {
    const seenFibers = new WeakSet();
    const seenValues = new WeakSet();

    let e = findEditor(document, "main", seenFibers, seenValues);
    if (e) return e;

    for (let i = 0; i < iframeCache.length; i++) {
      try {
        const doc = iframeCache[i].contentDocument;
        if (!doc) continue;
        e = findEditor(doc, "iframe-" + i, seenFibers, seenValues);
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

  // 缓存 editor 引用，找到后不再重复扫描 Fiber 树
  let cachedEditor = null;
  // 缓存 iframe 列表（每 5 秒刷新一次，以应对动态加载的 iframe）
  let iframeCache = buildIframeCache();
  let iframeCacheTime = Date.now();
  const IFRAME_CACHE_TTL = 5000;

  while (Date.now() < deadline) {
    // 按需刷新 iframe 缓存
    if (Date.now() - iframeCacheTime > IFRAME_CACHE_TTL) {
      iframeCache = buildIframeCache();
      iframeCacheTime = Date.now();
    }

    // editor 未缓存时才做全量扫描
    if (!cachedEditor) {
      cachedEditor = findEditorAnywhere(iframeCache);
    }

    if (cachedEditor) {
      try {
        const cv = cachedEditor.getClientVars();
        const info = parseCV(cv);
        lastInfo = info;

        if (info.sig !== lastSig) {
          lastSig = info.sig;
          stableSince = Date.now();
        }

        const stableFor = Date.now() - stableSince;
        log(`slides=${info.slideCount} blocks=${info.blockCount} stableFor=${stableFor}ms`);

        // 10 秒数据没变，或达到预期数量且稳定超过 stableMs，即认为加载完毕
        const timeoutStable = stableFor >= 10000;
        if (timeoutStable || (isComplete(info) && stableFor >= stableMs)) {
          log("stable & complete → calling getExportClientVars()");
          const exportCV = await cachedEditor.getExportClientVars();
          if (!exportCV) throw new Error("getExportClientVars() returned empty");

          const finalInfo = parseCV(exportCV);
          log("export done: slides=" + finalInfo.slideCount + " blocks=" + finalInfo.blockCount);

          // 10 秒稳定触发时跳过严格验证，使用实际数据
          if (!timeoutStable) {
            if (expectedSlideCount && finalInfo.slideCount < expectedSlideCount)
              throw new Error("export slideCount insufficient: " + finalInfo.slideCount);
            if (finalInfo.blockCount < minBlockCount)
              throw new Error("export blockCount insufficient: " + finalInfo.blockCount);
          }

          // 从 DOM 读取实际渲染的 slide 数量（data-slide-index 最大值 + 1）
          let actualSlideCount = 0;
          document.querySelectorAll("[data-slide-index]").forEach(el => {
            const idx = parseInt(el.getAttribute("data-slide-index"), 10);
            if (!isNaN(idx) && idx >= actualSlideCount) actualSlideCount = idx + 1;
          });
          log("actualSlideCount from DOM=" + actualSlideCount);

          const str = JSON.stringify(exportCV);
          return {
            clientVarsString: str,
            blockCount: finalInfo.blockCount,
            slideCount: finalInfo.slideCount,
            actualSlideCount: actualSlideCount || finalInfo.slideCount,
            stringLength: str.length,
            topKeys: Object.keys(exportCV),
            pageId: exportCV.id || ""
          };
        }

        // 数据稳定后降低轮询频率，减少 CPU 占用
        const pollInterval = stableFor > 2000 ? 500 : 100;
        await sleep(pollInterval);
        continue;

      } catch (e) {
        // editor 调用失败时清除缓存，下次循环重新扫描
        cachedEditor = null;
        log("editor lost or not ready, rescanning:", String(e));
      }
    }

    // 未找到 editor 时，降低轮询频率
    await sleep(cachedEditor ? 100 : 500);
  }

  const msg = lastInfo
    ? `timeout: slides=${lastInfo.slideCount}/${expectedSlideCount} blocks=${lastInfo.blockCount}/${minBlockCount}`
    : "timeout: editor not found";
  throw new Error(msg);
}