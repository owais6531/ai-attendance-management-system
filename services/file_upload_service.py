import io
import logging
import math
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from models.attendance_models import AttendanceRecord, RowError

logger = logging.getLogger(__name__)


class UploadError(ValueError):
    """A problem with the uploaded file that the user can fix (HTTP 400/413)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class AttendanceFileUploadService:
    """Parse and validate Excel/CSV attendance files. No database access here."""

    REQUIRED_COLUMNS = ['No', 'DN', 'UID', 'Name', 'Status', 'Action', 'APB', 'JobCode', 'DateTime']
    ALLOWED_EXTENSIONS = ('xlsx', 'xls', 'csv')
    MAX_ERRORS_RETURNED = 500
    PREVIEW_ROWS = 10

    _DATE_TIME_FORMATS = {
        # Unambiguous year-first formats are always tried first.
        "common": ['%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y-%m-%d %H:%M',
                   '%Y/%m/%d', '%Y-%m-%d'],
        "DMY": ['%d-%m-%y %H:%M', '%d-%m-%y %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
                '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%d/%m/%Y', '%d-%m-%Y'],
        "MDY": ['%m-%d-%y %H:%M', '%m-%d-%y %H:%M:%S', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',
                '%m-%d-%Y %H:%M:%S', '%m-%d-%Y %H:%M', '%m/%d/%Y', '%m-%d-%Y'],
    }

    @staticmethod
    def max_upload_bytes() -> int:
        return int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024)

    # ---------- public ----------
    @classmethod
    def parse_and_validate(cls, content: bytes, filename: str, date_order: str = "DMY"
                           ) -> Tuple[pd.DataFrame, List[AttendanceRecord], List[RowError]]:
        """Return (dataframe, valid records, row errors). Raises UploadError."""
        if not cls.is_allowed_filename(filename):
            raise UploadError("Invalid file type. Supported formats: Excel (.xlsx, .xls) and CSV (.csv)")
        if len(content) > cls.max_upload_bytes():
            raise UploadError(f"File is too large. Maximum size is {os.getenv('MAX_UPLOAD_MB', '20')} MB", 413)
        if not content:
            raise UploadError("The file is empty")
        df = cls._parse_file(content, filename)
        cls._validate_columns(df)
        if df.empty:
            raise UploadError("The file has headers but no data rows")
        records, errors = cls._process_records(df, date_order)
        return df, records, errors

    @classmethod
    def is_allowed_filename(cls, filename: str | None) -> bool:
        return bool(filename) and filename.lower().rsplit('.', 1)[-1] in cls.ALLOWED_EXTENSIONS

    # ---------- parsing ----------
    @classmethod
    def _parse_file(cls, content: bytes, filename: str) -> pd.DataFrame:
        try:
            if filename.lower().endswith('.csv'):
                df = cls._parse_csv(content)
            else:
                # dtype=str keeps codes such as "0012" intact.
                df = pd.read_excel(io.BytesIO(content), dtype=str)
        except UploadError:
            raise
        except Exception as e:  # noqa: BLE001 - any parser failure is a bad file
            logger.info("Could not parse %s: %s", filename, e)
            raise UploadError("Could not read the file. Make sure it is a valid Excel or CSV file.")
        df.columns = [str(c).strip() for c in df.columns]
        return df

    @staticmethod
    def _parse_csv(content: bytes) -> pd.DataFrame:
        for encoding in ['utf-8-sig', 'utf-16', 'cp1252', 'latin-1']:
            try:
                text = content.decode(encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
            try:
                df = pd.read_csv(io.StringIO(text), sep=None, engine='python', dtype=str)
            except Exception:  # noqa: BLE001 - fall back to explicit delimiters
                df = None
            if df is None or df.shape[1] == 1:
                for delimiter in ['\t', ',', ';']:
                    try:
                        candidate = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str)
                    except Exception:  # noqa: BLE001
                        continue
                    if candidate.shape[1] > 1:
                        df = candidate
                        break
            if df is not None:
                return df
        raise UploadError("Could not decode the CSV file (tried UTF-8, UTF-16, Windows-1252, Latin-1)")

    @classmethod
    def _validate_columns(cls, df: pd.DataFrame) -> None:
        missing = [col for col in cls.REQUIRED_COLUMNS if col not in df.columns]
        if missing:
            raise UploadError(
                f"Missing required columns: {', '.join(missing)}. "
                f"Required columns: {', '.join(cls.REQUIRED_COLUMNS)}"
            )

    # ---------- rows ----------
    @classmethod
    def _process_records(cls, df: pd.DataFrame, date_order: str = "DMY"
                         ) -> Tuple[List[AttendanceRecord], List[RowError]]:
        records, errors = [], []
        for index, row in enumerate(df.to_dict(orient="records")):
            excel_row = index + 2  # header is row 1
            try:
                records.append(AttendanceRecord(**cls._clean_row_data(row, date_order)))
            except Exception as e:  # noqa: BLE001 - collect every row problem
                errors.append(RowError(row=excel_row, error=cls._short_error(e), data=cls._json_safe(row)))
        return records, errors

    @classmethod
    def _clean_row_data(cls, row: Dict[str, Any], date_order: str = "DMY") -> Dict[str, Any]:
        punch_at = cls._parse_datetime(row['DateTime'], date_order)
        return {
            'no': cls._safe_int_convert(row['No'], 'No'),
            'dn': cls._safe_int_convert(row['DN'], 'DN'),
            'uid': cls._safe_code_convert(row['UID'], 'UID'),
            'name': cls._safe_str_convert(row['Name']),
            'status': cls._safe_int_convert(row['Status'], 'Status'),
            'action': cls._safe_int_convert(row['Action'], 'Action'),
            'apb': cls._safe_int_convert(row['APB'], 'APB'),
            'job_code': cls._safe_int_convert(row['JobCode'], 'JobCode'),
            'punch_at': punch_at,
            'date_time': punch_at.strftime('%Y/%m/%d %H:%M:%S'),
        }

    @staticmethod
    def _is_blank(value) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        return isinstance(value, str) and not value.strip()

    @classmethod
    def _safe_int_convert(cls, value, field: str = "Value") -> int:
        if cls._is_blank(value):
            raise ValueError(f"{field} cannot be empty")
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            raise ValueError(f"{field} must be a number (got '{value}')")

    @classmethod
    def _safe_code_convert(cls, value, field: str = "UID") -> str:
        """Employee codes are text: keep leading zeros, drop Excel's trailing '.0'."""
        if cls._is_blank(value):
            raise ValueError(f"{field} cannot be empty")
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        text = str(value).strip()
        if text.endswith('.0') and text[:-2].isdigit():
            text = text[:-2]
        return text

    @classmethod
    def _safe_str_convert(cls, value) -> str:
        return "" if cls._is_blank(value) else str(value).strip()

    @classmethod
    def _parse_datetime(cls, value, date_order: str = "DMY") -> datetime:
        if cls._is_blank(value):
            raise ValueError("DateTime cannot be empty")
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        if isinstance(value, datetime):
            return value
        order = "MDY" if str(date_order).upper() == "MDY" else "DMY"
        value_str = str(value).strip()
        for fmt in cls._DATE_TIME_FORMATS["common"] + cls._DATE_TIME_FORMATS[order]:
            try:
                return datetime.strptime(value_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Could not read DateTime '{value_str}' (expected e.g. 2025/01/18 09:00:00)")

    @staticmethod
    def _short_error(exc: Exception) -> str:
        # Pydantic errors are verbose; keep the first useful line.
        return str(exc).strip().splitlines()[0][:300]

    @classmethod
    def _json_safe(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {str(k): (None if cls._is_blank(v) else str(v)) for k, v in row.items()}

    # ---------- template ----------
    @classmethod
    def generate_template(cls) -> pd.DataFrame:
        """Template with clearly fake sample data."""
        return pd.DataFrame({
            'No': [1, 2, 3],
            'DN': [1, 1, 1],
            'UID': ['0001', '0002', '0001'],
            'Name': ['Demo Employee A', 'Demo Employee B', 'Demo Employee A'],
            'Status': [0, 0, 1],
            'Action': [1, 1, 1],
            'APB': [0, 0, 0],
            'JobCode': [0, 0, 0],
            'DateTime': ['2025/01/15 09:00:00', '2025/01/15 09:12:00', '2025/01/15 17:05:00'],
        })
