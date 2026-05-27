from pydantic import BaseModel
from typing import Optional, List


class KeyResponse(BaseModel):
    id: int
    key: str
    max_uses: int
    used_count: int
    is_super: int
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class KeyListResponse(BaseModel):
    keys: List[KeyResponse]


class KeyInfoResponse(BaseModel):
    status: str
    max_uses: int
    used_count: int
    is_super: int


class CreateKeysRequest(BaseModel):
    count: int
    max_uses: int
    is_super: bool = False


class UpdateKeyRequest(BaseModel):
    status: str


class BatchKeyRequest(BaseModel):
    action: str  # disable, enable, delete
    ids: List[int]
    value: Optional[int] = None
