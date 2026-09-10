from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

class AttendanceRecord(BaseModel):
    """Model for attendance log records"""
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%d-%m-%y %H:%M")}
    )

    no: int = Field(..., description="Record number")
    dn: int = Field(..., description="Device number")
    uid: int = Field(..., description="User ID")
    name: str = Field(..., description="Employee name")
    status: int = Field(..., description="Status code")
    action: int = Field(..., description="Action code")
    apb: int = Field(..., description="APB code")
    job_code: int = Field(..., description="Job code")
    date_time: str = Field(..., description="Date and time")

class UploadResponse(BaseModel):
    """Response model for upload operations"""
    message: str
    total_records: int
    successful_imports: int
    failed_imports: int
    errors: Optional[list] = []
    batch_id: Optional[str] = None