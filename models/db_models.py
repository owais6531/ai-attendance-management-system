from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from config.database import Base
from datetime import datetime

class AttendanceRecord(Base):
    """SQLAlchemy model for attendance records"""
    
    __tablename__ = "attendance_records"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Attendance data fields (matching the Pydantic model)
    no = Column(Integer, nullable=False, comment="Record number")
    dn = Column(Integer, nullable=False, comment="Device number")
    uid = Column(String(50), nullable=False, comment="User ID")
    name = Column(String(100), nullable=True, comment="Employee name")
    date_time = Column(String(50), nullable=False, comment="Date and time of attendance")
    status = Column(Integer, nullable=False, comment="Attendance status")
    action = Column(Integer, nullable=False, comment="Action type")
    apb = Column(Integer, nullable=False, comment="APB status")
    job_code = Column(Integer, nullable=False, comment="Job code")
    
    # Metadata fields
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Record creation timestamp")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="Record update timestamp")
    
    # Optional fields for tracking
    file_name = Column(String(255), nullable=True, comment="Source file name")
    batch_id = Column(String(100), nullable=True, comment="Upload batch identifier")
    is_processed = Column(Boolean, default=True, comment="Whether record has been processed")
    
    def __repr__(self):
        return f"<AttendanceRecord(id={self.id}, uid='{self.uid}', date_time='{self.date_time}', status={self.status})>"
    
    def to_dict(self):
        """Convert model instance to dictionary"""
        return {
            'id': self.id,
            'no': self.no,
            'dn': self.dn,
            'uid': self.uid,
            'name': self.name,
            'date_time': self.date_time,
            'status': self.status,
            'action': self.action,
            'apb': self.apb,
            'job_code': self.job_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'file_name': self.file_name,
            'batch_id': self.batch_id,
            'is_processed': self.is_processed
        }

class UploadBatch(Base):
    """SQLAlchemy model for tracking upload batches"""
    
    __tablename__ = "upload_batches"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Batch information
    batch_id = Column(String(100), unique=True, nullable=False, comment="Unique batch identifier")
    file_name = Column(String(255), nullable=False, comment="Original file name")
    file_size = Column(Integer, nullable=True, comment="File size in bytes")
    
    # Processing statistics
    total_records = Column(Integer, default=0, comment="Total records in file")
    successful_records = Column(Integer, default=0, comment="Successfully processed records")
    failed_records = Column(Integer, default=0, comment="Failed records")
    
    # Status and metadata
    status = Column(String(50), default="processing", comment="Batch processing status")
    error_message = Column(Text, nullable=True, comment="Error message if processing failed")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Batch creation timestamp")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="Batch completion timestamp")
    
    def __repr__(self):
        return f"<UploadBatch(id={self.id}, batch_id='{self.batch_id}', file_name='{self.file_name}', status='{self.status}')>"
    
    def to_dict(self):
        """Convert model instance to dictionary"""
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'total_records': self.total_records,
            'successful_records': self.successful_records,
            'failed_records': self.failed_records,
            'status': self.status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }