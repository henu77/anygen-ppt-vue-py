from pydantic import BaseModel
from typing import Optional, Dict, Any


class SettingsResponse(BaseModel):
    id: int
    key: str
    value: Optional[str] = None
    type: str
    updated_at: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]
