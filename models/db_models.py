import json

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from config.database import Base


class AttendanceRecord(Base):
    """One raw punch from a device export or spreadsheet."""

    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    no = Column(Integer, nullable=True, comment="Record number")
    dn = Column(Integer, nullable=True, comment="Device number")
    # Text, not int: employee/card codes keep their leading zeros ("0012" != "12").
    uid = Column(String(50), nullable=False, comment="Employee / user code")
    name = Column(String(100), nullable=True, comment="Employee name")
    # Real timestamp used for filtering, sorting and calculations.
    punch_at = Column(DateTime, nullable=True, comment="Punch date and time")
    # Legacy display string (YYYY/MM/DD HH:MM:SS), kept for backward compatibility.
    date_time = Column(String(50), nullable=False, comment="Date and time (text)")
    status = Column(Integer, nullable=True, comment="Attendance status")
    action = Column(Integer, nullable=True, comment="Action type")
    apb = Column(Integer, nullable=True, comment="APB status")
    job_code = Column(Integer, nullable=True, comment="Job code")

    # Columns the user did not map, as JSON, so a 100-column file loses nothing.
    extra = Column(Text, nullable=True, comment="Unmapped columns as JSON")
    # A day mark with no clock time (P, A, Leave); punch_at is then midnight of that day.
    day_status = Column(String(20), nullable=True, comment="Day status without a clock time")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    file_name = Column(String(255), nullable=True, comment="Source file name")
    batch_id = Column(String(100), nullable=True, index=True, comment="Upload batch identifier")
    is_processed = Column(Boolean, default=True)

    # Created by migration 0002 (unique when the existing data allows it).
    __table_args__ = (Index("ix_attendance_uid_punch", "uid", "punch_at"),)

    def __repr__(self):
        return f"<AttendanceRecord(id={self.id}, uid='{self.uid}', punch_at='{self.punch_at}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "no": self.no,
            "dn": self.dn,
            "uid": self.uid,
            "name": self.name,
            "punch_at": self.punch_at.isoformat() if self.punch_at else None,
            "date_time": self.date_time,
            "status": self.status,
            "action": self.action,
            "apb": self.apb,
            "job_code": self.job_code,
            "day_status": self.day_status,
            "extra": json.loads(self.extra) if self.extra else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "file_name": self.file_name,
            "batch_id": self.batch_id,
            "is_processed": self.is_processed,
        }


class UploadBatch(Base):
    """One uploaded file and its processing statistics."""

    __tablename__ = "upload_batches"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(String(100), unique=True, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)

    total_records = Column(Integer, default=0)
    successful_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)

    # completed | completed_with_errors | failed
    status = Column(String(50), default="processing")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<UploadBatch(batch_id='{self.batch_id}', file_name='{self.file_name}', status='{self.status}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "total_records": self.total_records,
            "successful_records": self.successful_records,
            "failed_records": self.failed_records,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ImportProfile(Base):
    """A saved column mapping, so next month's file imports in one click."""

    __tablename__ = "import_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    shape = Column(String(20), nullable=False)
    columns_json = Column(Text, nullable=False)
    date_order = Column(String(3), nullable=False, default="DMY")
    signature = Column(String(40), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "shape": self.shape,
            "columns": json.loads(self.columns_json),
            "date_order": self.date_order,
            "signature": self.signature,
        }


class AiUsage(Base):
    """One line per AI call. Local models are free, so there is no cost column."""

    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feature = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    prompt_version = Column(String(20), nullable=False)
    duration_ms = Column(Integer, nullable=False)
    ok = Column(Boolean, nullable=False)
    error = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
