from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    location: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class StageCreate(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None


class StageResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScanStatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None
    checked_by: Optional[str] = None


class ScanResponse(BaseModel):
    id: int
    project_id: int
    stage_id: int
    original_filename: str
    stored_filename: str
    file_path: str
    file_hash: str
    status: str
    comment: Optional[str]
    checked_by: Optional[str]
    checked_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ScanAuditLogResponse(BaseModel):
    id: int
    scan_id: int
    old_status: Optional[str]
    new_status: str
    comment: Optional[str]
    changed_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True