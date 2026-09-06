from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: int
    stage_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    assigned_to_user_id: int | None = None
    created_by_user_id: int | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority | None = None
    assigned_to_user_id: int | None = None
    due_at: datetime | None = None


class TaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: TaskStatus
    changed_by_user_id: int | None = None
    comment: str | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    stage_id: int | None = None
    assigned_to_user_id: int | None = None
    created_by_user_id: int | None = None
    title: str
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    old_status: TaskStatus | None = None
    new_status: TaskStatus
    comment: str | None = None
    changed_by_user_id: int | None = None
    created_at: datetime
