import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import desc, select, tuple_
from sqlalchemy.orm import Session

from models.attendance_models import AttendanceRecord as PunchRow
from models.db_models import AttendanceRecord, UploadBatch

logger = logging.getLogger(__name__)


class DatabaseService:
    """Database operations. The caller owns the session (FastAPI ``get_db``)."""

    def __init__(self, db: Session):
        self.db = db

    # ---------- writes ----------
    def save_upload(self, *, file_name: str, file_size: int, total_rows: int,
                    rows: List[PunchRow], failed_rows: int) -> dict:
        """Save one upload atomically: the batch and its punches, or nothing.

        Punches already in the database (same employee code + timestamp) or
        repeated inside the file are skipped, so re-uploading a file is safe.
        Raises SQLAlchemyError on database failure (after rolling back).
        """
        try:
            unique_rows, in_file_dupes = self._dedupe_in_file(rows)
            existing = self._existing_keys(unique_rows)
            new_rows = [r for r in unique_rows if (r.uid, r.punch_at) not in existing]
            duplicates = in_file_dupes + (len(unique_rows) - len(new_rows))

            batch = UploadBatch(
                batch_id=str(uuid.uuid4()),
                file_name=file_name,
                file_size=file_size,
                total_records=total_rows,
                successful_records=len(new_rows),
                failed_records=failed_rows,
                status="completed" if failed_rows == 0 else "completed_with_errors",
                completed_at=datetime.now(timezone.utc),
            )
            if not new_rows and failed_rows:
                batch.status = "failed"
            self.db.add(batch)
            self.db.add_all(
                AttendanceRecord(
                    no=r.no, dn=r.dn, uid=r.uid, name=r.name, punch_at=r.punch_at,
                    date_time=r.date_time, status=r.status, action=r.action, apb=r.apb,
                    job_code=r.job_code, file_name=file_name, batch_id=batch.batch_id,
                )
                for r in new_rows
            )
            self.db.commit()
            logger.info("Batch %s: %s saved, %s duplicates, %s failed",
                        batch.batch_id, len(new_rows), duplicates, failed_rows)
            return {"batch_id": batch.batch_id, "saved": len(new_rows), "duplicates": duplicates}
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _dedupe_in_file(rows: List[PunchRow]):
        seen, unique = set(), []
        for r in rows:
            key = (r.uid, r.punch_at)
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique, len(rows) - len(unique)

    def _existing_keys(self, rows: List[PunchRow]) -> set:
        if not rows:
            return set()
        keys = {(r.uid, r.punch_at) for r in rows}
        lo = min(k[1] for k in keys)
        hi = max(k[1] for k in keys)
        uids = list({k[0] for k in keys})
        found = set()
        # Chunk the IN list to stay under parameter limits (SQLite: 999).
        for i in range(0, len(uids), 500):
            stmt = select(AttendanceRecord.uid, AttendanceRecord.punch_at).where(
                AttendanceRecord.uid.in_(uids[i:i + 500]),
                AttendanceRecord.punch_at >= lo,
                AttendanceRecord.punch_at <= hi,
            )
            found.update((u, p) for u, p in self.db.execute(stmt))
        return found & keys

    # ---------- reads ----------
    def _records_query(self, uid=None, batch_id=None, date_from=None, date_to=None):
        query = self.db.query(AttendanceRecord)
        if uid:
            query = query.filter(AttendanceRecord.uid == uid)
        if batch_id:
            query = query.filter(AttendanceRecord.batch_id == batch_id)
        if date_from:
            query = query.filter(AttendanceRecord.punch_at >= date_from)
        if date_to:
            query = query.filter(AttendanceRecord.punch_at <= date_to)
        return query

    def get_attendance_records(self, skip: int = 0, limit: int = 100, uid: str = None,
                               batch_id: str = None, date_from: datetime = None,
                               date_to: datetime = None) -> List[AttendanceRecord]:
        return (self._records_query(uid, batch_id, date_from, date_to)
                .order_by(desc(AttendanceRecord.punch_at), desc(AttendanceRecord.id))
                .offset(skip).limit(limit).all())

    def count_attendance_records(self, uid: str = None, batch_id: str = None,
                                 date_from: datetime = None, date_to: datetime = None) -> int:
        return self._records_query(uid, batch_id, date_from, date_to).count()

    def get_attendance_record(self, record_id: int) -> Optional[AttendanceRecord]:
        return self.db.get(AttendanceRecord, record_id)

    def get_upload_batch(self, batch_id: str) -> Optional[UploadBatch]:
        return self.db.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()

    def get_upload_batches(self, skip: int = 0, limit: int = 50) -> List[UploadBatch]:
        return (self.db.query(UploadBatch).order_by(desc(UploadBatch.created_at), desc(UploadBatch.id))
                .offset(skip).limit(limit).all())
