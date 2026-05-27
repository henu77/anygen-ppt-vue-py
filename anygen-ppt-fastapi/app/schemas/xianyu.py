from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class QRCodeResponse(BaseModel):
    success: bool
    session_id: Optional[str] = None
    qr_code_url: Optional[str] = None
    message: Optional[str] = None


class LoginCheckRequest(BaseModel):
    sessionId: str


class LoginCheckResponse(BaseModel):
    status: str
    session_id: str
    cookies: Optional[str] = None
    unb: Optional[str] = None
    verification_url: Optional[str] = None
    message: Optional[str] = None


class VerifyCookiesRequest(BaseModel):
    cookies: str


class XianyuAccountResponse(BaseModel):
    id: int
    account_id: str
    unb: Optional[str] = None
    delivery_template: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XianyuAccountListResponse(BaseModel):
    accounts: List[XianyuAccountResponse]


class BindAccountRequest(BaseModel):
    accountId: str
    cookies: str


class UnbindAccountRequest(BaseModel):
    accountId: str


class UpdateTemplateRequest(BaseModel):
    accountId: str
    deliveryTemplate: str


class XianyuOrderResponse(BaseModel):
    id: int
    order_no: str
    account_id: str
    status: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XianyuOrderListResponse(BaseModel):
    orders: List[XianyuOrderResponse]
