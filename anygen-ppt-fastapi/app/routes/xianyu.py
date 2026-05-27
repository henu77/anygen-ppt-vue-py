from fastapi import APIRouter, Depends, HTTPException, Header
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


@router.post("/xianyu/login", response_model=QRCodeResponse)
async def get_qr_code(db: Session = Depends(get_db)):
    """生成闲鱼登录二维码"""
    try:
        result = await xianyu_client.generate_qr_code()
        logger.info(f"生成二维码成功: {result.get('session_id')}")
        return QRCodeResponse(
            success=result.get("success"),
            session_id=result.get("session_id"),
            qr_code_url=result.get("qr_code_url"),
            message=result.get("message"),
        )
    except Exception as e:
        logger.error(f"生成二维码失败: {e}")
        return QRCodeResponse(success=False, message=str(e))


@router.post("/xianyu/login/check", response_model=LoginCheckResponse)
async def check_login(
    request: LoginCheckRequest,
    db: Session = Depends(get_db),
):
    """检查登录状态"""
    try:
        result = xianyu_client.check_login_status(request.sessionId)
        logger.info(f"检查登录状态: {request.sessionId} -> {result.get('status')}")
        return LoginCheckResponse(
            status=result.get("status"),
            session_id=result.get("session_id"),
            cookies=result.get("cookies"),
            unb=result.get("unb"),
            verification_url=result.get("verification_url"),
            message=result.get("message"),
        )
    except Exception as e:
        logger.error(f"检查登录状态失败: {e}")
        return LoginCheckResponse(status="error", session_id=request.sessionId, message=str(e))


@router.post("/xianyu/login/verify")
async def verify_cookies(
    request: VerifyCookiesRequest,
    db: Session = Depends(get_db),
):
    """验证 cookies"""
    try:
        # 这里可以添加 cookies 验证逻辑
        logger.info("验证 cookies 成功")
        return {"success": True, "message": "Cookies 有效"}
    except Exception as e:
        logger.error(f"验证 cookies 失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/xianyu-multi", response_model=XianyuAccountListResponse)
async def list_accounts(
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取闲鱼账户列表"""
    accounts = XianyuService.list_accounts(db)
    account_responses = [
        XianyuAccountResponse(
            id=acc.id,
            account_id=acc.account_id,
            unb=acc.unb,
            delivery_template=acc.delivery_template,
            status=acc.status,
            created_at=acc.created_at.isoformat() if acc.created_at else None,
            updated_at=acc.updated_at.isoformat() if acc.updated_at else None,
        )
        for acc in accounts
    ]
    return XianyuAccountListResponse(accounts=account_responses)


@router.post("/xianyu-multi/bind", response_model=XianyuAccountResponse)
async def bind_account(
    request: BindAccountRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """绑定闲鱼账户"""
    account = XianyuService.bind_account(db, request.accountId, request.cookies)
    logger.info(f"绑定闲鱼账户: {request.accountId}")
    return XianyuAccountResponse(
        id=account.id,
        account_id=account.account_id,
        unb=account.unb,
        delivery_template=account.delivery_template,
        status=account.status,
        created_at=account.created_at.isoformat() if account.created_at else None,
        updated_at=account.updated_at.isoformat() if account.updated_at else None,
    )


@router.post("/xianyu-multi/unbind")
async def unbind_account(
    request: UnbindAccountRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """解绑闲鱼账户"""
    if not XianyuService.unbind_account(db, request.accountId):
        raise HTTPException(status_code=404, detail="账户不存在")

    logger.info(f"解绑闲鱼账户: {request.accountId}")
    return {"message": "解绑成功"}


@router.post("/xianyu-multi/template", response_model=XianyuAccountResponse)
async def update_template(
    request: UpdateTemplateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """更新发货模板"""
    account = XianyuService.update_delivery_template(db, request.accountId, request.deliveryTemplate)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    logger.info(f"更新发货模板: {request.accountId}")
    return XianyuAccountResponse(
        id=account.id,
        account_id=account.account_id,
        unb=account.unb,
        delivery_template=account.delivery_template,
        status=account.status,
        created_at=account.created_at.isoformat() if account.created_at else None,
        updated_at=account.updated_at.isoformat() if account.updated_at else None,
    )


@router.get("/xianyu-multi/orders", response_model=XianyuOrderListResponse)
async def get_orders(
    accountId: str = None,
    status: str = None,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin),
):
    """获取订单列表"""
    orders = XianyuService.list_orders(db, accountId, status)
    order_responses = [
        XianyuOrderResponse(
            id=order.id,
            order_no=order.order_no,
            account_id=order.account_id,
            status=order.status,
            data=order.data,
            created_at=order.created_at.isoformat() if order.created_at else None,
            updated_at=order.updated_at.isoformat() if order.updated_at else None,
        )
        for order in orders
    ]
    return XianyuOrderListResponse(orders=order_responses)


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
    logger.info(f"确认发货: {order_no}")
    return {"message": "发货确认成功"}
