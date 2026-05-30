from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.xianyu import (
    QRCodeResponse,
    LoginCheckRequest,
    LoginCheckResponse,
    VerifyCookiesRequest,
    XianyuAccountListResponse,
    XianyuAccountResponse,
    BindAccountRequest,
    UnbindAccountRequest,
    UpdateTemplateRequest,
    XianyuOrderListResponse,
    XianyuOrderResponse,
)
from app.services.xianyu import XianyuService
from app.external.xianyu_client import xianyu_client
from app.utils.jwt import extract_token_from_header, verify_token
from app.utils.response import ok
from loguru import logger

router = APIRouter(tags=["xianyu"])


def verify_admin(authorization: str = Header(None)):
    """验证管理员权限"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供 token")

    token = extract_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Token 格式错误")

    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    return payload


@router.post("/xianyu/login")
async def get_qr_code(db: Session = Depends(get_db)):
    """生成闲鱼登录二维码"""
    try:
        result = await xianyu_client.generate_qr_code()
    except Exception as e:
        logger.error(f"生成二维码失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成二维码失败: {e}")

    if not result.get("success") or not result.get("session_id"):
        msg = result.get("message", "生成二维码失败")
        logger.error(f"生成二维码失败: {msg}")
        raise HTTPException(status_code=500, detail=msg)

    logger.info(f"生成二维码成功: {result.get('session_id')}")
    return ok(data={
        "sessionId": result.get("session_id"),
        "qrCode": result.get("qr_code_url"),
        "message": result.get("message"),
    })


@router.post("/xianyu/login/check")
async def check_login(
    request: LoginCheckRequest,
    db: Session = Depends(get_db),
):
    """检查登录状态"""
    try:
        result = xianyu_client.check_login_status(request.sessionId)
        logger.info(f"检查登录状态: {request.sessionId} -> {result.get('status')}")
        return ok(data={
            "status": result.get("status"),
            "sessionId": result.get("session_id"),
            "cookies": result.get("cookies"),
            "unb": result.get("unb"),
            "verificationUrl": result.get("verification_url"),
            "message": result.get("message"),
            "error": result.get("error"),
        })
    except Exception as e:
        logger.error(f"检查登录状态失败: {e}")
        return ok(data={"status": "error", "session_id": request.sessionId, "message": str(e)})


@router.post("/xianyu/login/verify")
async def verify_cookies(
    request: VerifyCookiesRequest,
    db: Session = Depends(get_db),
):
    """验证 cookies 是否有效"""
    result, updated_cookies = await xianyu_client.verify_cookies(request.cookies)
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("message", "Cookies 无效"))
    return ok(data={
        "valid": True,
        "message": result.get("message", "Cookies 有效"),
        "nickname": result.get("nickname", ""),
        "user_data": result.get("user_data", {}),
    })


@router.get("/xianyu-multi")
async def list_accounts(
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取闲鱼账户列表"""
    accounts = XianyuService.list_accounts(db)
    account_responses = [
        {
            "id": acc.id,
            "account_id": acc.account_id,
            "unb": acc.unb,
            "nickname": acc.nickname,
            "delivery_template": acc.delivery_template,
            "status": acc.status,
            "auto_delivery": acc.auto_delivery,
            "auto_item_id": acc.auto_item_id,
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
        }
        for acc in accounts
    ]
    return ok(data={"accounts": account_responses})


@router.post("/xianyu-multi/bind")
async def bind_account(
    request: BindAccountRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """绑定闲鱼账户"""
    account = XianyuService.bind_account(db, request.accountId, request.cookies, nickname=request.nickname)
    logger.info(f"[{account.nickname or '-'}] 绑定请求: {request.accountId}")
    return ok(data={
        "id": account.id,
        "account_id": account.account_id,
        "unb": account.unb,
        "nickname": account.nickname,
        "delivery_template": account.delivery_template,
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    })


@router.post("/xianyu-multi/unbind")
async def unbind_account(
    request: UnbindAccountRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """解绑闲鱼账户"""
    account = XianyuService.get_account(db, request.accountId)
    nickname = account.nickname if account else None
    if not XianyuService.unbind_account(db, request.accountId):
        raise HTTPException(status_code=404, detail="账户不存在")

    logger.info(f"[{nickname or '-'}] 解绑请求: {request.accountId}")
    return ok(message="解绑成功")


@router.post("/xianyu-multi/relogin")
async def relogin_account(
    request: BindAccountRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """重新登录（更新已有账户的 Cookie）"""
    account = XianyuService.get_account(db, request.accountId)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    account.cookies = request.cookies
    account.status = "active"
    if request.nickname:
        account.nickname = request.nickname
    db.commit()

    # 重启该账户的续期任务（如果之前被禁用了）
    try:
        from app.services.scheduled_task import ScheduledTaskService
        from app import scheduler as task_scheduler
        task = ScheduledTaskService.get_task_by_type_and_config(db, "xianyu_cookie_renew", request.accountId)
        if task and not task.enabled:
            ScheduledTaskService.update_task(db, task.id, enabled=True)
            task_scheduler.resume_job(task.id)
    except Exception as e:
        logger.warning(f"恢复续期任务失败: {e}")

    logger.info(f"[{account.nickname or '-'}] 重新登录: {request.accountId}")
    return ok(data={
        "id": account.id,
        "account_id": account.account_id,
        "nickname": account.nickname,
        "status": account.status,
    })


@router.post("/xianyu-multi/template")
async def update_template(
    request: UpdateTemplateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """更新发货模板"""
    account = XianyuService.update_delivery_template(db, request.accountId, request.deliveryTemplate)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    logger.info(f"[{account.nickname or '-'}] 更新模板请求: {request.accountId}")
    return ok(data={
        "id": account.id,
        "account_id": account.account_id,
        "unb": account.unb,
        "nickname": account.nickname,
        "delivery_template": account.delivery_template,
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    })


@router.get("/xianyu/orders/sold")
async def get_sold_orders(
    accountId: str,
    page: int = 1,
    pageSize: int = 30,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """从闲鱼API获取已卖出的订单列表"""
    account = XianyuService.get_account(db, accountId)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    if not account.cookies:
        raise HTTPException(status_code=400, detail="账户无Cookie")

    result, updated_cookies = await xianyu_client.fetch_sold_orders(account.cookies, page=page, page_size=pageSize)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取订单失败"))

    # 如果 Set-Cookie 更新了 token，持久化到数据库
    if updated_cookies != account.cookies:
        account.cookies = updated_cookies
        db.commit()

    return ok(data={
        "items": result["items"],
        "totalCount": result["total_count"],
        "hasNext": result["has_next"],
    })


@router.get("/xianyu/orders/{order_id}/detail")
async def get_order_detail(
    order_id: str,
    accountId: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """从闲鱼API获取订单详情"""
    account = XianyuService.get_account(db, accountId)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    if not account.cookies:
        raise HTTPException(status_code=400, detail="账户无Cookie")

    result, updated_cookies = await xianyu_client.fetch_order_detail(account.cookies, order_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取订单详情失败"))

    # 如果 Set-Cookie 更新了 token，持久化到数据库
    if updated_cookies != account.cookies:
        account.cookies = updated_cookies
        db.commit()

    return ok(data=result["detail"])


@router.get("/xianyu-multi/orders")
async def get_orders(
    accountId: str = None,
    status: str = None,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取订单列表"""
    orders = XianyuService.list_orders(db, accountId, status)
    order_responses = [
        {
            "id": order.id,
            "order_no": order.order_no,
            "account_id": order.account_id,
            "status": order.status,
            "data": order.data,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }
        for order in orders
    ]
    return ok(data={"orders": order_responses})


@router.post("/xianyu/orders/{order_no}/confirm-delivery")
async def confirm_delivery(
    order_no: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """确认发货"""
    order = XianyuService.get_order(db, order_no)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    XianyuService.update_order_status(db, order_no, "delivered")
    account = XianyuService.get_account(db, order.account_id)
    acc_name = account.nickname if account else "-"
    logger.info(f"[{acc_name or '-'}] 确认发货: {order_no} (账户: {order.account_id})")
    return ok(message="发货确认成功")


# ── 自动发货相关接口 ──────────────────────────────────────


class AutoDeliveryRequest(BaseModel):
    accountId: str
    autoDelivery: bool
    autoItemId: str | None = None


@router.put("/xianyu-multi/auto-delivery")
async def update_auto_delivery(
    body: AutoDeliveryRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
    fastapi_request: Request = None,
):
    """更新自动发货配置"""
    account = XianyuService.get_account(db, body.accountId)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    account.auto_delivery = body.autoDelivery
    if body.autoItemId is not None:
        account.auto_item_id = body.autoItemId
    db.commit()
    db.refresh(account)

    # 动态管理 Worker
    live_manager = fastapi_request.app.state.live_manager if fastapi_request else None
    if live_manager:
        if body.autoDelivery and account.status == "active":
            await live_manager.add_account(body.accountId)
        else:
            await live_manager.remove_account(body.accountId)

    logger.info(f"[{account.nickname or '-'}] 自动发货: {'开启' if body.autoDelivery else '关闭'}, 商品: {body.autoItemId or '全部'}")
    return ok(data=account.to_dict())


@router.get("/xianyu/items")
async def get_listed_items(
    accountId: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取在售商品列表"""
    account = XianyuService.get_account(db, accountId)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    if not account.cookies:
        raise HTTPException(status_code=400, detail="账户无 Cookie")

    result, updated_cookies = await xianyu_client.fetch_listed_items(account.cookies, account.account_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取商品失败"))

    # 如果 Set-Cookie 更新了 token，持久化到数据库
    if updated_cookies != account.cookies:
        account.cookies = updated_cookies
        db.commit()

    return ok(data={"items": result["items"]})


@router.get("/xianyu/pending-orders")
async def get_pending_orders(
    accountId: str = None,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取待处理订单（无卡密跳过的）"""
    from app.models.xianyu import XianyuOrder
    query = db.query(XianyuOrder).filter(XianyuOrder.status == "pending_key")
    if accountId:
        query = query.filter(XianyuOrder.account_id == accountId)
    orders = query.order_by(XianyuOrder.id.desc()).limit(100).all()
    return ok(data={"orders": [o.to_dict() for o in orders]})
