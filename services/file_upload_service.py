import pandas as pd
import io
from typing import List, Dict, Any, Tuple
from datetime import datetime
from fastapi import UploadFile, HTTPException
from models.attendance_models import AttendanceRecord, UploadResponse
from services.database_service import DatabaseService
import logging

# Setup logging
logger = logging.getLogger(__name__)

class AttendanceFileUploadService:
    """Service for handling Excel/CSV file uploads and processing attendance data"""
    
    REQUIRED_COLUMNS = [
        'No', 'DN', 'UID', 'Name', 'Status', 'Action', 'APB', 'JobCode', 'DateTime'
    ]
    
    ALLOWED_FILE_TYPES = {
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
        'application/vnd.ms-excel',  # .xls
        'text/csv',  # .csv
        'application/csv'  # .csv alternative
    }
    
    @classmethod
    async def process_file(cls, file: UploadFile, save_to_db: bool = True) -> UploadResponse:
        """Process uploaded Excel/CSV file and return attendance records"""
        db_service = DatabaseService()
        upload_batch = None
        
        try:
            # Validate file type
            if not cls._is_valid_file_type(file):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type. Supported formats: Excel (.xlsx, .xls) and CSV (.csv)"
                )
            
            # Read file content
            content = await file.read()
            file_size = len(content)
            
            # Create upload batch if saving to database
            if save_to_db:
                upload_batch = db_service.create_upload_batch(
                    file_name=file.filename,
                    file_size=file_size
                )
                if not upload_batch:
                    logger.warning("Failed to create upload batch, proceeding without database save")
                    save_to_db = False
            
            # Parse file based on type
            df = cls._parse_file(content, file.filename)
            
            # Validate columns
            cls._validate_columns(df)
            
            # Process records
            records, errors = cls._process_records(df)
            
            # Save to database if requested
            db_result = None
            if save_to_db and upload_batch and records:
                try:
                    db_result = db_service.create_attendance_records_batch(
                        records_data=records,
                        file_name=file.filename,
                        batch_id=upload_batch.batch_id
                    )
                    
                    # Update batch statistics
                    db_service.update_upload_batch(
                        batch_id=upload_batch.batch_id,
                        total_records=len(df),
                        successful_records=db_result['successful'],
                        failed_records=db_result['failed'] + len(errors),
                        status='completed' if db_result['successful'] > 0 else 'failed',
                        error_message='; '.join(db_result['errors']) if db_result['errors'] else None
                    )
                    
                    logger.info(f"Saved {db_result['successful']} records to database for batch {upload_batch.batch_id}")
                    
                except Exception as db_error:
                    logger.error(f"Database save failed: {db_error}")
                    if upload_batch:
                        db_service.update_upload_batch(
                            batch_id=upload_batch.batch_id,
                            status='failed',
                            error_message=f"Database save failed: {str(db_error)}"
                        )
                    # Add database error to response errors
                    errors.append({
                        'row': 'Database',
                        'error': f"Failed to save to database: {str(db_error)}"
                    })
            
            # Prepare response message
            message_parts = [f"Successfully processed {len(records)} records"]
            if save_to_db and db_result:
                message_parts.append(f"Saved {db_result['successful']} to database")
            elif save_to_db:
                message_parts.append("Database save was not performed")
            
            return UploadResponse(
                message="; ".join(message_parts),
                total_records=len(df),
                successful_imports=len(records),
                failed_imports=len(errors),
                errors=errors,
                batch_id=upload_batch.batch_id if upload_batch else None
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing file {file.filename}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing file: {str(e)}"
            )
    
    @classmethod
    def _is_valid_file_type(cls, file: UploadFile) -> bool:
        """Check if file type is supported"""
        if file.content_type in cls.ALLOWED_FILE_TYPES:
            return True
        
        # Check file extension as fallback
        if file.filename:
            extension = file.filename.lower().split('.')[-1]
            return extension in ['xlsx', 'xls', 'csv']
        
        return False
    
    @classmethod
    def _parse_file(cls, content: bytes, filename: str) -> pd.DataFrame:
        """Parse file content into DataFrame"""
        try:
            if filename.lower().endswith('.csv'):
                # Try different encodings and delimiters for CSV
                for encoding in ['utf-16', 'utf-8', 'latin-1', 'cp1252']:
                    try:
                        # First try with automatic delimiter detection
                        df = pd.read_csv(io.BytesIO(content), encoding=encoding, sep=None, engine='python')
                        # If that fails, try common delimiters
                        if df.shape[1] == 1:
                            for delimiter in ['\t', ',', ';']:
                                try:
                                    df = pd.read_csv(io.BytesIO(content), encoding=encoding, sep=delimiter)
                                    if df.shape[1] > 1:
                                        break
                                except:
                                    continue
                        # Clean column names by stripping whitespace
                        df.columns = df.columns.str.strip()
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                else:
                    raise ValueError("Could not decode CSV file with any supported encoding")
            else:
                # Excel file
                df = pd.read_excel(io.BytesIO(content))
            
            return df
            
        except Exception as e:
            raise ValueError(f"Could not parse file: {str(e)}")
    
    @classmethod
    def _validate_columns(cls, df: pd.DataFrame) -> None:
        """Validate that all required columns are present"""
        missing_columns = [col for col in cls.REQUIRED_COLUMNS if col not in df.columns]
        
        if missing_columns:
            raise ValueError(
                f"Missing required columns: {', '.join(missing_columns)}. "
                f"Required columns: {', '.join(cls.REQUIRED_COLUMNS)}"
            )
    
    @classmethod
    def _process_records(cls, df: pd.DataFrame) -> Tuple[List[AttendanceRecord], List[Dict[str, Any]]]:
        """Process DataFrame rows into AttendanceRecord objects"""
        records = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Clean and validate data
                record_data = cls._clean_row_data(row, index)
                
                # Create AttendanceRecord
                record = AttendanceRecord(**record_data)
                records.append(record)
                
            except Exception as e:
                errors.append({
                    'row': index + 2,  # +2 because pandas is 0-indexed and Excel starts from row 2
                    'error': str(e),
                    'data': row.to_dict()
                })
        
        return records, errors
    
    @classmethod
    def _clean_row_data(cls, row: pd.Series, index: int) -> Dict[str, Any]:
        """Clean and validate individual row data"""
        try:
            # Handle NaN values and convert to appropriate types
            parsed_datetime = cls._parse_datetime(row['DateTime'])
            cleaned_name = cls._safe_str_convert(row['Name'])

            data = {
                'no': cls._safe_int_convert(row['No']),
                'dn': cls._safe_int_convert(row['DN']),
                'uid': cls._safe_int_convert(row['UID']),
                'name': cleaned_name,
                'status': cls._safe_int_convert(row['Status']),
                'action': cls._safe_int_convert(row['Action']),
                'apb': cls._safe_int_convert(row['APB']),
                'job_code': cls._safe_int_convert(row['JobCode']),
                'date_time': parsed_datetime.strftime('%Y/%m/%d %H:%M:%S')
            }
            
            return data
            
        except Exception as e:
            raise ValueError(f"Invalid data in row {index + 2}: {str(e)}")
    
    @classmethod
    def _safe_int_convert(cls, value) -> int:
        """Safely convert value to integer"""
        if pd.isna(value):
            raise ValueError("No field cannot be empty")
        try:
            return int(float(value))  # Convert via float to handle decimal strings
        except (ValueError, TypeError):
            raise ValueError(f"Invalid number format: {value}")
    
    @classmethod
    def _safe_str_convert(cls, value) -> str:
        """Safely convert value to string"""
        if pd.isna(value):
            return ""
        return str(value).strip()
    
    @classmethod
    def _parse_datetime(cls, value) -> datetime:
        """Parse datetime from various formats"""
        if pd.isna(value):
            raise ValueError("Date Time field cannot be empty")
        
        if isinstance(value, datetime):
            return value
        
        # Try different datetime formats
        formats = [
            '%d-%m-%y %H:%M',     # 01-07-25 9:47 (your CSV format)
            '%d-%m-%y %H:%M:%S',  # 01-07-25 9:47:30
            '%Y/%m/%d %H:%M:%S',  # 2024/01/15 09:00:00
            '%Y-%m-%d %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M:%S',
            '%Y/%m/%d %H:%M',     # 2024/01/15 09:00
            '%Y-%m-%d %H:%M',
            '%d/%m/%Y %H:%M',
            '%m/%d/%Y %H:%M',
            '%Y/%m/%d',           # 2024/01/15
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y'
        ]
        
        value_str = str(value).strip()
        
        for fmt in formats:
            try:
                return datetime.strptime(value_str, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse datetime: {value}")
    
    @classmethod
    def generate_template(cls) -> pd.DataFrame:
        """Generate a template DataFrame with sample data"""
        sample_data = {
            'No': [1, 2, 3],
            'DN': [1, 1, 1],
            'UID': [123456, 123457, 123458],
            'Name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
            'Status': [0, 0, 0],
            'Action': [1, 1, 1],
            'APB': [0, 0, 0],
            'JobCode': [0, 0, 0],
            'DateTime': [
                '2024/01/15 09:00:00',
                '2024/01/15 17:00:00',
                '2024/01/15 00:00:00'
            ]
        }
        
        return pd.DataFrame(sample_data)