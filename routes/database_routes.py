import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.auth import verify_api_key
from config.database import get_db
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database", tags=["database"], dependencies=[Depends(verify_api_key)])


@router.get("/attendance/records", response_model=List[dict])
def get_attendance_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    uid: Optional[str] = Query(None, description="Filter by employee code"),
    batch_id: Optional[str] = Query(None, description="Filter by upload batch"),
    date_from: Optional[datetime] = Query(None, description="Punches at or after (ISO date/time)"),
    date_to: Optional[datetime] = Query(None, description="Punches at or before (ISO date/time)"),
    db: Session = Depends(get_db),
):
    """List punches, newest first, with optional filters."""
    records = DatabaseService(db).get_attendance_records(skip, limit, uid, batch_id, date_from, date_to)
    return [r.to_dict() for r in records]


@router.get("/attendance/records/count")
def count_attendance_records(
    uid: Optional[str] = None,
    batch_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return {"count": DatabaseService(db).count_attendance_records(uid, batch_id, date_from, date_to)}


@router.get("/attendance/records/{record_id}", response_model=dict)
def get_attendance_record(record_id: int, db: Session = Depends(get_db)):
    record = DatabaseService(db).get_attendance_record(record_id)
    if not record:
        raise HTTPException(404, "Attendance record not found")
    return record.to_dict()


@router.get("/batches", response_model=List[dict])
def get_upload_batches(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                       db: Session = Depends(get_db)):
    return [b.to_dict() for b in DatabaseService(db).get_upload_batches(skip, limit)]


@router.get("/batches/{batch_id}", response_model=dict)
def get_upload_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = DatabaseService(db).get_upload_batch(batch_id)
    if not batch:
        raise HTTPException(404, "Upload batch not found")
    return batch.to_dict()


@router.get("/batches/{batch_id}/records", response_model=List[dict])
def get_batch_records(batch_id: str, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                      db: Session = Depends(get_db)):
    service = DatabaseService(db)
    if not service.get_upload_batch(batch_id):
        raise HTTPException(404, "Upload batch not found")
    return [r.to_dict() for r in service.get_attendance_records(skip, limit, batch_id=batch_id)]


@router.get("/health")
def database_health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        logger.exception("Database health check failed")
        raise HTTPException(503, "Database connection failed")
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
