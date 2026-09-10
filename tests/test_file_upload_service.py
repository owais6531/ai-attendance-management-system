import io

import pandas as pd
import pytest

from services.file_upload_service import AttendanceFileUploadService


def test_generate_template_has_required_columns():
    df = AttendanceFileUploadService.generate_template()
    assert list(df.columns) == AttendanceFileUploadService.REQUIRED_COLUMNS


def test_validate_columns_passes_for_valid_dataframe():
    df = AttendanceFileUploadService.generate_template()
    AttendanceFileUploadService._validate_columns(df)  # should not raise


def test_validate_columns_raises_for_missing_column():
    df = AttendanceFileUploadService.generate_template().drop(columns=["Name"])
    with pytest.raises(ValueError, match="Missing required columns"):
        AttendanceFileUploadService._validate_columns(df)


def test_parse_file_reads_csv_bytes():
    csv_bytes = (
        "No,DN,UID,Name,Status,Action,APB,JobCode,DateTime\n"
        "1,1,100,John Doe,0,1,0,0,2024/01/15 09:00:00\n"
    ).encode("utf-8")

    df = AttendanceFileUploadService._parse_file(csv_bytes, "attendance.csv")

    assert df.shape[0] == 1
    assert df.iloc[0]["Name"] == "John Doe"


def test_process_records_converts_valid_rows():
    df = AttendanceFileUploadService.generate_template()

    records, errors = AttendanceFileUploadService._process_records(df)

    assert len(errors) == 0
    assert len(records) == 3
    assert records[0].name == "John Doe"
    assert records[0].uid == 123456


def test_process_records_reports_errors_for_bad_row():
    df = AttendanceFileUploadService.generate_template()
    df.loc[0, "DateTime"] = "not-a-date"

    records, errors = AttendanceFileUploadService._process_records(df)

    assert len(records) == 2
    assert len(errors) == 1
    assert errors[0]["row"] == 2


def test_safe_int_convert_rejects_missing_value():
    with pytest.raises(ValueError, match="cannot be empty"):
        AttendanceFileUploadService._safe_int_convert(float("nan"))


def test_parse_datetime_supports_multiple_formats():
    parsed = AttendanceFileUploadService._parse_datetime("01-07-25 9:47")
    assert parsed.year == 2025 and parsed.month == 7 and parsed.day == 1
