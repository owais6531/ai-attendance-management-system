from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


DB_INT_MIN, DB_INT_MAX = -2_147_483_648, 2_147_483_647


def _db_int(description: str):
    """Optional whole number that fits the database column."""
    return Field(None, ge=DB_INT_MIN, le=DB_INT_MAX, description=description)


class AttendanceRecord(BaseModel):
    """One validated record from an uploaded file. Only employee code and date are always known."""

    no: Optional[int] = _db_int("Record number")
    dn: Optional[int] = _db_int("Device number")
    uid: str = Field(..., min_length=1, max_length=50, description="Employee / user code (leading zeros kept)")
    name: str = Field("", max_length=100, description="Employee name")
    status: Optional[int] = _db_int("In/out state: 0 = in, 1 = out")
    action: Optional[int] = _db_int("Action code")
    apb: Optional[int] = _db_int("APB code")
    job_code: Optional[int] = _db_int("Job code")
    punch_at: datetime = Field(..., description="Punch date and time")
    date_time: str = Field(..., description="Punch date and time as YYYY/MM/DD HH:MM:SS")
    extra: dict[str, Any] = Field(default_factory=dict, description="Columns not mapped to a field")
    day_status: Optional[str] = Field(None, max_length=20, description="Day mark with no clock time (P, A, Leave)")


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


class ImportResponse(UploadResponse):
    """Result of a flexible import. One file row can give several records (time in + time out)."""

    shape: str
    records_found: int = 0
    skipped_blank: int = 0
    warnings: list[str] = []
