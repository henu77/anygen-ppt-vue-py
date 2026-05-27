from pydantic import BaseModel
from typing import Optional, List


class ExportRequest(BaseModel):
    key: str
    url: str
    email: str


class ExportResponse(BaseModel):
    taskId: int
    status: str


class TaskResponse(BaseModel):
    id: int
    key_id: int
    url: str
    email: str
    status: str
    file_path: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskStats(BaseModel):
    total: int
    pending: int
    done: int
    failed: int


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    stats: TaskStats
