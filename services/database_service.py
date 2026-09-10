from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, or_, desc, asc
from datetime import datetime
import uuid
import logging

from config.database import get_db, SessionLocal
from models.db_models import AttendanceRecord, UploadBatch
from models.attendance_models import AttendanceRecord as PydanticAttendanceRecord

# Setup logging
logger = logging.getLogger(__name__)

class DatabaseService:
    """Service class for database operations"""
    
    def __init__(self, db: Session = None):
        """Initialize database service"""
        self.db = db
    
    def _get_session(self) -> Session:
        """Get database session"""
        if self.db:
            return self.db
        return SessionLocal()
    
    def _close_session(self, session: Session, created_here: bool = False):
        """Close database session if created here"""
        if created_here and session:
            session.close()

    # Attendance Record Operations
    def create_attendance_record(self, record_data: PydanticAttendanceRecord, 
                               file_name: str = None, batch_id: str = None) -> Optional[AttendanceRecord]:
        """Create a new attendance record"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            db_record = AttendanceRecord(
                no=record_data.no,
                dn=record_data.dn,
                uid=record_data.uid,
                name=record_data.name,
                date_time=record_data.date_time,
                status=record_data.status,
                action=record_data.action,
                apb=record_data.apb,
                job_code=record_data.job_code,
                file_name=file_name,
                batch_id=batch_id
            )
            
            session.add(db_record)
            session.commit()
            session.refresh(db_record)
            
            logger.info(f"Created attendance record: {db_record.id}")
            return db_record
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to create attendance record: {e}")
            return None
        finally:
            self._close_session(session, created_here)
    
    def create_attendance_records_batch(self, records_data: List[PydanticAttendanceRecord], 
                                      file_name: str = None, batch_id: str = None) -> Dict[str, Any]:
        """Create multiple attendance records in a batch"""
        session = self._get_session()
        created_here = self.db is None
        
        result = {
            'successful': 0,
            'failed': 0,
            'errors': [],
            'created_records': []
        }
        
        try:
            for i, record_data in enumerate(records_data):
                try:
                    db_record = AttendanceRecord(
                        no=record_data.no,
                        dn=record_data.dn,
                        uid=record_data.uid,
                        name=record_data.name,  # Added missing name field
                        date_time=record_data.date_time,
                        status=record_data.status,
                        action=record_data.action,
                        apb=record_data.apb,
                        job_code=record_data.job_code,
                        file_name=file_name,
                        batch_id=batch_id
                    )
                    
                    session.add(db_record)
                    result['created_records'].append(db_record)
                    result['successful'] += 1
                    
                except Exception as e:
                    result['failed'] += 1
                    result['errors'].append(f"Record {i+1}: {str(e)}")
                    logger.error(f"Failed to prepare record {i+1}: {e}")
            
            # Commit all records at once
            session.commit()
            
            # Refresh all created records
            for record in result['created_records']:
                session.refresh(record)
            
            logger.info(f"Batch created: {result['successful']} successful, {result['failed']} failed")
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to create batch records: {e}")
            result['failed'] = len(records_data)
            result['successful'] = 0
            result['errors'].append(f"Database error: {str(e)}")
            result['created_records'] = []
        finally:
            self._close_session(session, created_here)
        
        return result
    
    def get_attendance_record(self, record_id: int) -> Optional[AttendanceRecord]:
        """Get attendance record by ID"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            record = session.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
            return record
        except SQLAlchemyError as e:
            logger.error(f"Failed to get attendance record {record_id}: {e}")
            return None
        finally:
            self._close_session(session, created_here)
    
    def get_attendance_records(self, skip: int = 0, limit: int = 100, 
                             uid: str = None, batch_id: str = None) -> List[AttendanceRecord]:
        """Get attendance records with optional filtering"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            query = session.query(AttendanceRecord)
            
            # Apply filters
            if uid:
                query = query.filter(AttendanceRecord.uid == uid)
            if batch_id:
                query = query.filter(AttendanceRecord.batch_id == batch_id)
            
            # Apply pagination and ordering
            records = query.order_by(desc(AttendanceRecord.created_at)).offset(skip).limit(limit).all()
            return records
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to get attendance records: {e}")
            return []
        finally:
            self._close_session(session, created_here)
    
    def count_attendance_records(self, uid: str = None, batch_id: str = None) -> int:
        """Count attendance records with optional filtering"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            query = session.query(AttendanceRecord)
            
            # Apply filters
            if uid:
                query = query.filter(AttendanceRecord.uid == uid)
            if batch_id:
                query = query.filter(AttendanceRecord.batch_id == batch_id)
            
            count = query.count()
            return count
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to count attendance records: {e}")
            return 0
        finally:
            self._close_session(session, created_here)
    
    # Upload Batch Operations
    def create_upload_batch(self, file_name: str, file_size: int = None) -> Optional[UploadBatch]:
        """Create a new upload batch"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            batch_id = str(uuid.uuid4())
            
            db_batch = UploadBatch(
                batch_id=batch_id,
                file_name=file_name,
                file_size=file_size,
                status="processing"
            )
            
            session.add(db_batch)
            session.commit()
            session.refresh(db_batch)
            
            logger.info(f"Created upload batch: {batch_id}")
            return db_batch
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to create upload batch: {e}")
            return None
        finally:
            self._close_session(session, created_here)
    
    def update_upload_batch(self, batch_id: str, **kwargs) -> Optional[UploadBatch]:
        """Update upload batch with new data"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            batch = session.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()
            if not batch:
                logger.warning(f"Upload batch not found: {batch_id}")
                return None
            
            # Update fields
            for key, value in kwargs.items():
                if hasattr(batch, key):
                    setattr(batch, key, value)
            
            # Set completion time if status is completed
            if kwargs.get('status') == 'completed':
                batch.completed_at = datetime.utcnow()
            
            session.commit()
            session.refresh(batch)
            
            logger.info(f"Updated upload batch: {batch_id}")
            return batch
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to update upload batch {batch_id}: {e}")
            return None
        finally:
            self._close_session(session, created_here)
    
    def get_upload_batch(self, batch_id: str) -> Optional[UploadBatch]:
        """Get upload batch by ID"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            batch = session.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()
            return batch
        except SQLAlchemyError as e:
            logger.error(f"Failed to get upload batch {batch_id}: {e}")
            return None
        finally:
            self._close_session(session, created_here)
    
    def get_upload_batches(self, skip: int = 0, limit: int = 50) -> List[UploadBatch]:
        """Get upload batches with pagination"""
        session = self._get_session()
        created_here = self.db is None
        
        try:
            batches = session.query(UploadBatch).order_by(desc(UploadBatch.created_at)).offset(skip).limit(limit).all()
            return batches
        except SQLAlchemyError as e:
            logger.error(f"Failed to get upload batches: {e}")
            return []
        finally:
            self._close_session(session, created_here)

# Global database service instance
db_service = DatabaseService()