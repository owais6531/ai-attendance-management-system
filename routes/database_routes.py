from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from config.database import get_db
from config.auth import verify_api_key
from services.database_service import DatabaseService
from models.db_models import AttendanceRecord, UploadBatch
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/database",
    tags=["database"],
    dependencies=[Depends(verify_api_key)],
)

@router.get("/attendance/records", response_model=List[dict])
async def get_attendance_records(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    uid: Optional[str] = Query(None, description="Filter by user ID"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    db: Session = Depends(get_db)
):
    """Get attendance records with optional filtering and pagination"""
    try:
        db_service = DatabaseService(db)
        records = db_service.get_attendance_records(
            skip=skip, 
            limit=limit, 
            uid=uid, 
            batch_id=batch_id
        )
        
        # Convert to dictionaries
        return [record.to_dict() for record in records]
        
    except Exception as e:
        logger.error(f"Failed to get attendance records: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve attendance records")

@router.get("/attendance/records/count")
async def count_attendance_records(
    uid: Optional[str] = Query(None, description="Filter by user ID"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    db: Session = Depends(get_db)
):
    """Count attendance records with optional filtering"""
    try:
        db_service = DatabaseService(db)
        count = db_service.count_attendance_records(uid=uid, batch_id=batch_id)
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Failed to count attendance records: {e}")
        raise HTTPException(status_code=500, detail="Failed to count attendance records")

@router.get("/attendance/records/{record_id}", response_model=dict)
async def get_attendance_record(
    record_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific attendance record by ID"""
    try:
        db_service = DatabaseService(db)
        record = db_service.get_attendance_record(record_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Attendance record not found")
        
        return record.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get attendance record {record_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve attendance record")

@router.get("/batches", response_model=List[dict])
async def get_upload_batches(
    skip: int = Query(0, ge=0, description="Number of batches to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of batches to return"),
    db: Session = Depends(get_db)
):
    """Get upload batches with pagination"""
    try:
        db_service = DatabaseService(db)
        batches = db_service.get_upload_batches(skip=skip, limit=limit)
        
        # Convert to dictionaries
        return [batch.to_dict() for batch in batches]
        
    except Exception as e:
        logger.error(f"Failed to get upload batches: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve upload batches")

@router.get("/batches/{batch_id}", response_model=dict)
async def get_upload_batch(
    batch_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific upload batch by ID"""
    try:
        db_service = DatabaseService(db)
        batch = db_service.get_upload_batch(batch_id)
        
        if not batch:
            raise HTTPException(status_code=404, detail="Upload batch not found")
        
        return batch.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get upload batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve upload batch")

@router.get("/batches/{batch_id}/records", response_model=List[dict])
async def get_batch_records(
    batch_id: str,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """Get all attendance records for a specific batch"""
    try:
        # First verify the batch exists
        db_service = DatabaseService(db)
        batch = db_service.get_upload_batch(batch_id)
        
        if not batch:
            raise HTTPException(status_code=404, detail="Upload batch not found")
        
        # Get records for this batch
        records = db_service.get_attendance_records(
            skip=skip, 
            limit=limit, 
            batch_id=batch_id
        )
        
        # Convert to dictionaries
        return [record.to_dict() for record in records]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get records for batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve batch records")

@router.get("/health")
async def database_health_check(db: Session = Depends(get_db)):
    """Check database connection and health"""
    try:
        # Simple query to test connection
        result = db.execute(text("SELECT 1 as health_check"))
        row = result.fetchone()

        if row and row[0] == 1:
            return {
                "status": "healthy",
                "message": "Database connection is working",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Database health check failed")
            
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")