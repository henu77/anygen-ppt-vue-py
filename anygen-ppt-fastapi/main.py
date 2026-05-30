import os
import sys
import asyncio

# 解决 asyncio 子进程支持问题（Playwright 需要 ProactorEventLoop）
# uvicorn 在 reload 模式下会强制设置 WindowsSelectorEventLoopPolicy，导致 Playwright 无法创建子进程
# 需要在 uvicorn 运行前 patch 掉这个行为
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # Monkey-patch uvicorn 的事件循环设置，阻止它覆盖为 SelectorEventLoop
    try:
        import uvicorn.loops.asyncio as _uvloop_asyncio
        _uvloop_asyncio.asyncio_setup = lambda use_subprocess=False: None
    except ImportError:
        pass
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException, RequestValidationError
from app.database.init_db import init_db
from app.routes import auth, export, tasks, query, keys, settings, xianyu, scheduled_task
from app.utils.logger import logger
from app.utils.response import fail
from app.utils.exceptions import ApiError
from config import settings as app_settings

# 初始化数据库
init_db()

# Lifespan 事件处理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    from app.scheduler import start as start_scheduler, shutdown as stop_scheduler
    from app.xianyu_live import XianyuLiveManager
    from app.database.db import SessionLocal

    logger.info("应用启动成功")
    logger.info(f"API 文档: http://{app_settings.HOST}:{app_settings.PORT}/docs")
    start_scheduler()

    # 启动闲鱼自动发货服务
    live_manager = XianyuLiveManager(db_session_factory=SessionLocal)
    app.state.live_manager = live_manager
    await live_manager.start()

    yield

    await live_manager.stop()
    stop_scheduler()
    logger.info("应用关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="Anygen PPT API",
    description="PPT 导出和闲鱼管理系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 统一异常处理
@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.code, content=fail(exc.code, exc.message))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=fail(exc.status_code, str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0].get("msg", "参数错误") if errors else "参数错误"
    return JSONResponse(status_code=422, content=fail(422, msg))


# 注册路由
app.include_router(auth.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(keys.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(xianyu.router, prefix="/api")
app.include_router(scheduled_task.router, prefix="/api")

# 提供前端静态文件 (SPA 模式)
static_dir = os.path.join(os.path.dirname(__file__), "static")

if os.path.exists(static_dir):
    # 只挂载 assets 子目录，避免覆盖 SPA 路由
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA 回退：所有非 API 路由都返回 index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str, request: Request):
        # 跳过 API 路径（理论上不会到这里，但做双重保险）
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        
        file_path = os.path.join(static_dir, full_path) if full_path else ""
        # 如果请求的是存在的静态文件（非 assets 目录下的），直接返回
        if full_path and not full_path.startswith("assets/") and os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # 否则回退到 index.html（SPA 路由）
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"detail": "Not Found"}
else:
    logger.warning(f"静态文件目录不存在: {static_dir}")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    logger.info(f"启动服务器: {app_settings.HOST}:{app_settings.PORT}")
    uvicorn.run(
        "main:app",
        host=app_settings.HOST,
        port=app_settings.PORT,
        reload=app_settings.DEBUG,
        log_level=app_settings.LOG_LEVEL.lower(),
    )
