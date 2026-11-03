import pandas as pd
import pytest

from services.file_upload_service import AttendanceFileUploadService as S, UploadError


def test_generate_template_has_required_columns():
    assert list(S.generate_template().columns) == S.REQUIRED_COLUMNS


def test_validate_columns_raises_for_missing_column():
    df = S.generate_template().drop(columns=["Name"])
    with pytest.raises(UploadError, match="Missing required columns: Name"):
        S._validate_columns(df)


def test_parse_csv_utf8_comma():
    content = b"No,DN,UID,Name,Status,Action,APB,JobCode,DateTime\n1,1,100,A,0,1,0,0,2024/01/15 09:00:00\n"
    assert S._parse_file(content, "a.csv").shape == (1, 9)


def test_parse_csv_utf16_tab_device_export():
    text = ("No\tDN\tUID\tName\tStatus\tAction\tAPB\tJobCode\tDateTime\n"
            "1\t1\t0007\tA\t0\t1\t0\t0\t2024/01/15 09:00:00\n")
    df = S._parse_file(text.encode("utf-16"), "device.csv")
    assert df.iloc[0]["UID"] == "0007"


def test_process_records_converts_valid_rows():
    records, errors = S._process_records(S.generate_template())
    assert errors == []
    assert len(records) == 3
    assert records[0].uid == "0001"
    assert records[0].punch_at.hour == 9


def test_leading_zeros_in_employee_code_are_kept():
    row = {"No": "000001", "DN": "0001", "UID": "000000000000000001", "Name": "A", "Status": "00",
           "Action": "01", "APB": "0", "JobCode": "000", "DateTime": "2025/01/18 09:00:00"}
    assert S._clean_row_data(row)["uid"] == "000000000000000001"


def test_excel_float_codes_drop_only_the_dot_zero():
    assert S._safe_code_convert(123456.0) == "123456"
    assert S._safe_code_convert("123.0") == "123"
    assert S._safe_code_convert("0012") == "0012"
    assert S._safe_code_convert("EMP-7") == "EMP-7"


def test_bad_row_reports_excel_row_number_and_field():
    df = S.generate_template()
    df.loc[0, "DateTime"] = "not-a-date"
    df.loc[1, "Status"] = None
    records, errors = S._process_records(df)
    assert len(records) == 1
    assert [e.row for e in errors] == [2, 3]
    assert "DateTime" in errors[0].error
    assert errors[1].error == "Status cannot be empty"


@pytest.mark.parametrize("order,month,day", [("DMY", 4, 3), ("MDY", 3, 4)])
def test_ambiguous_dates_follow_selected_order(order, month, day):
    parsed = S._parse_datetime("03/04/2025 09:00", order)
    assert (parsed.month, parsed.day) == (month, day)


def test_device_short_date_format():
    parsed = S._parse_datetime("01-07-25 9:47")
    assert (parsed.year, parsed.month, parsed.day, parsed.hour) == (2025, 7, 1, 9)


def test_pandas_timestamp_accepted():
    assert S._parse_datetime(pd.Timestamp("2025-01-01 08:30")).minute == 30


def test_rejects_unknown_extension_and_oversize(monkeypatch):
    with pytest.raises(UploadError, match="Invalid file type"):
        S.parse_and_validate(b"x", "evil.exe")
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.0001")
    with pytest.raises(UploadError) as exc:
        S.parse_and_validate(b"x" * 1000, "big.csv")
    assert exc.value.status_code == 413
