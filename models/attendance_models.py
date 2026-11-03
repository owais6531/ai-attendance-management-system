from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AttendanceRecord(BaseModel):
    """One validated punch row from an uploaded file."""

    no: int = Field(..., description="Record number")
    dn: int = Field(..., description="Device number")
    uid: str = Field(..., min_length=1, description="Employee / user code (leading zeros kept)")
    name: str = Field("", description="Employee name")
    status: int = Field(..., description="Status code")
    action: int = Field(..., description="Action code")
    apb: int = Field(..., description="APB code")
    job_code: int = Field(..., description="Job code")
    punch_at: datetime = Field(..., description="Punch date and time")
    date_time: str = Field(..., description="Punch date and time as YYYY/MM/DD HH:MM:SS")


class RowError(BaseModel):
    row: int | str
    error: str
    data: dict[str, Any] = {}


class UploadResponse(BaseModel):
    """Result of an upload. ``saved`` is what actually reached the database."""

    message: str
    file_name: str
    total_records: int
    valid_records: int
    saved: int
    duplicates_skipped: int
    failed_imports: int
    errors: list[RowError] = []
    errors_truncated: bool = False
    preview: list[AttendanceRecord] = []
    batch_id: Optional[str] = None
