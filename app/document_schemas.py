from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


DocumentStatus = Literal["active", "inactive"]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_key: str
    supersedes_id: int | None = None
    project_id: int
    stage_id: int
    uploaded_by_user_id: int | None = None
    title: str
    document_type: str
    version: str
    original_filename: str
    storage_key: str
    mime_type: str
    size_bytes: int
    file_hash: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
