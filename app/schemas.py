from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    created_at: datetime


class StageCreate(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime


class ScanStatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None
    checked_by: Optional[str] = None


class ScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    stage_id: int
    original_filename: str
    stored_filename: str
    file_path: str
    file_hash: str
    status: str
    comment: Optional[str] = None
    checked_by: Optional[str] = None
    checked_at: Optional[datetime] = None
    created_at: datetime


class ScanAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scan_id: int
    old_status: Optional[str] = None
    new_status: str
    comment: Optional[str] = None
    changed_by: Optional[str] = None
    created_at: datetime
