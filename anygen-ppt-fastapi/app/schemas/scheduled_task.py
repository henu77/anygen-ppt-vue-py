from pydantic import BaseModel
from typing import Optional, Dict, Any


class ScheduledTaskUpdateRequest(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
