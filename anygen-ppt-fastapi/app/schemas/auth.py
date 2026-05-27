from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    password: str


class AuthResponse(BaseModel):
    valid: bool
    token: Optional[str] = None
    message: Optional[str] = None
