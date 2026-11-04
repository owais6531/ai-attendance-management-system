"""Flexible import: any file shape, 2 to 100+ columns. All data here is fake."""
import io
import json

import pandas as pd
import pytest
from sqlalchemy import text

from config.database import engine
from services.ai import ollama_client, smart_mapping
from services.column_mapping import DateParser, detect_period, match_header
from services.file_reader import read_table


def _analyze(client, content, name="t.csv", **form):
    r = client.post("/import/analyze", files={"file": (name, content, "text/csv")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


def _targets(analysis):
    return {c["name"]: c["target"] for c in analysis["columns"]}


def _run(client, content, analysis=None, name="t.csv", dry_run=False, **overrides):
    analysis = analysis or _analyze(client, content, name)
    plan = {"shape": analysis["shape"], "columns": _targets(analysis), "period": analysis["period"],
            "sheet": analysis["sheet"], "header_row": analysis["header_row"], **overrides}
    return client.post("/import/run", files={"file": (name, content, "text/csv")},
                       data={"plan": json.dumps(plan), "dry_run": str(dry_run).lower()})


def _records(client):
    return client.get("/api/database/attendance/records", params={"limit": 1000}).json()


# ---------- punch logs ----------
def test_two_column_file_is_enough(client):
    content = b"Emp ID,Punch Time\n0012,2025-01-15 09:00:00\n0013,15/01/2025 09:05\n"
    analysis = _analyze(client, content)
    assert _targets(analysis) == {"Emp ID": "employee_code", "Punch Time": "punch_datetime"}
    assert analysis["shape"] == "punch_log"

    body = _run(client, content, analysis).json()
    assert (body["saved"], body["failed_imports"]) == (2, 0)
    rows = {r["uid"]: r for r in _records(client)}
    assert rows["0012"]["punch_at"] == "2025-01-15T09:00:00"  # leading zeros kept
    assert rows["0013"]["punch_at"] == "2025-01-15T09:05:00"
    assert rows["0012"]["no"] is None and rows["0012"]["status"] is None


def test_original_nine_column_layout_maps_itself(client, make_csv):
    content = make_csv("7,3,0001,Demo A,0,1,0,5,2025/01/18 09:00:00")
    assert _run(client, content).json()["saved"] == 1
    row = _records(client)[0]
    assert (row["no"], row["dn"], row["status"], row["action"], row["apb"], row["job_code"]) == (7, 3, 0, 1, 0, 5)
    assert row["extra"] == {}


def test_title_rows_and_blank_rows_are_skipped_and_row_numbers_stay_true(client):
    content = (b"Demo Company Pvt Ltd\nAttendance Report\n\nAC-No.,Name,Date/Time\n"
               b"1,Demo A,2025-01-15 09:00:00\n2,Demo B,not-a-date\n")
    analysis = _analyze(client, content)
    assert analysis["header_row"] == 4
    body = _run(client, content, analysis).json()
    assert body["saved"] == 1
    assert body["errors"][0]["row"] == 6
    assert body["errors"][0]["data"]["Name"] == "Demo B"


def test_header_row_can_be_set_by_hand(client):
    content = b"a,b\nUID,DateTime\n1,2025-01-15 09:00\n"
    assert _analyze(client, content, header_row="2")["header_row"] == 2


def test_hundred_columns_nothing_lost(client):
    headers = ["Emp Code", "Punch Time"] + [f"Custom {i}" for i in range(98)]
    values = ["0007", "2025-03-01 08:30:00"] + [f"v{i}" for i in range(98)]
    content = (",".join(headers) + "\n" + ",".join(values) + "\n").encode()
    assert _run(client, content).json()["saved"] == 1
    extra = _records(client)[0]["extra"]
    assert len(extra) == 98 and extra["Custom 97"] == "v97"


def test_ignored_column_is_not_stored(client):
    content = b"UID,DateTime,CNIC\n1,2025-01-15 09:00,00000-0000000-0\n"
    analysis = _analyze(client, content)
    columns = {**_targets(analysis), "CNIC": "ignore"}
    assert _run(client, content, analysis, columns=columns).json()["saved"] == 1
    assert _records(client)[0]["extra"] == {}


def test_separate_date_and_time_columns(client):
    content = b"Badge,Date,Time\n5,15-Jan-2025,9:05 AM\n"
    analysis = _analyze(client, content)
    assert set(_targets(analysis).values()) == {"employee_code", "date", "time"}
    assert _run(client, content, analysis).json()["saved"] == 1
    assert _records(client)[0]["punch_at"] == "2025-01-15T09:05:00"


def test_status_words_become_codes_and_bad_numbers_are_kept_as_extra(client):
    content = b"UID,DateTime,State,DN\n1,2025-01-15 09:00,C/In,MAIN-GATE\n1,2025-01-15 17:00,C/Out,2\n"
    assert _run(client, content).json()["saved"] == 2
    rows = sorted(_records(client), key=lambda r: r["punch_at"])
    assert [r["status"] for r in rows] == [0, 1]
    assert rows[0]["dn"] is None and rows[0]["extra"]["DN"] == "MAIN-GATE"
    assert rows[1]["dn"] == 2


def test_value_too_big_for_database_does_not_break_the_batch(client):
    content = b"UID,DateTime,No\n1,2025-01-15 09:00,99999999999999\n"
    assert _run(client, content).json()["saved"] == 1
    assert _records(client)[0]["extra"]["No"] == "99999999999999"


def test_too_long_employee_code_is_a_row_error(client):
    content = f"UID,DateTime\n{'9' * 51},2025-01-15 09:00\n2,2025-01-15 09:00\n".encode()
    body = _run(client, content).json()
    assert body["saved"] == 1 and "too long" in body["errors"][0]["error"]


def test_repeated_header_inside_data_is_ignored(client):
    content = b"UID,DateTime\n1,2025-01-15 09:00\nUID,DateTime\n2,2025-01-15 09:05\n"
    body = _run(client, content).json()
    assert body["saved"] == 2 and body["failed_imports"] == 0


def test_reimport_skips_duplicates_and_dry_run_saves_nothing(client):
    content = b"UID,DateTime\n1,2025-01-15 09:00\n"
    assert _run(client, content, dry_run=True).json()["saved"] == 0
    assert _records(client) == []
    assert _run(client, content).json()["saved"] == 1
    second = _run(client, content).json()
    assert (second["saved"], second["duplicates_skipped"]) == (0, 1)


def test_date_order_setting_is_used(client):
    content = b"UID,DateTime\n1,03/04/2025 09:00\n"
    _run(client, content, date_order="MDY")
    assert _records(client)[0]["punch_at"] == "2025-03-04T09:00:00"


# ---------- daily sheets ----------
def test_daily_sheet_gives_in_and_out_records(client):
    content = (b"Code,Name,Date,Check In,Check Out,Department\n"
               b"1,Demo A,2025-01-15,09:00,17:30,Sales\n"
               b"2,Demo B,2025-01-15,09:10,,Sales\n"
               b"3,Demo C,2025-01-15,,,Sales\n")
    analysis = _analyze(client, content)
    assert analysis["shape"] == "daily"
    body = _run(client, content, analysis).json()
    assert (body["records_found"], body["saved"], body["skipped_blank"]) == (3, 3, 1)
    rows = sorted(_records(client), key=lambda r: (r["uid"], r["punch_at"]))
    assert [(r["uid"], r["status"]) for r in rows] == [("1", 0), ("1", 1), ("2", 0)]
    assert rows[0]["extra"] == {"Department": "Sales"}


def test_daily_night_shift_moves_out_to_next_day_and_warns(client):
    content = b"Code,Date,In,Out\n1,2025-01-15,22:00,06:00\n"
    body = _run(client, content).json()
    assert body["saved"] == 2 and "night shift" in body["warnings"][0]
    assert max(r["punch_at"] for r in _records(client)) == "2025-01-16T06:00:00"


def test_daily_status_without_times(client):
    content = b"Code,Date,Attendance\n1,2025-01-15,A\n"
    analysis = _analyze(client, content)
    assert analysis["shape"] == "daily"
    assert _run(client, content, analysis).json()["saved"] == 1
    row = _records(client)[0]
    assert row["day_status"] == "A" and row["punch_at"] == "2025-01-15T00:00:00"


def test_one_bad_time_adds_nothing_for_that_row(client):
    content = b"Code,Date,In,Out\n1,2025-01-15,09:00,late\n"
    body = _run(client, content).json()
    assert body["records_found"] == 0 and body["failed_imports"] == 1


# ---------- monthly matrix ----------
def _matrix(days=31, cells=None, title=b"Attendance for January 2025\n"):
    header = ",".join(["Emp Code", "Name", "Department"] + [str(d) for d in range(1, days + 1)])
    cells = cells or {}
    row = ["0001", "Demo A", "Sales"] + [cells.get(d, "") for d in range(1, days + 1)]
    return title + (header + "\n" + ",".join(row) + "\n").encode()


def test_matrix_is_detected_and_month_read_from_title(client):
    content = _matrix(cells={1: "09:00-17:00", 2: "P", 3: "A", 4: "-"})
    analysis = _analyze(client, content)
    assert analysis["shape"] == "monthly_matrix" and analysis["period"] == "2025-01"
    assert analysis["header_row"] == 2
    body = _run(client, content, analysis).json()
    assert body["saved"] == 4
    rows = sorted(_records(client), key=lambda r: r["punch_at"])
    assert [(r["punch_at"], r["status"], r["day_status"]) for r in rows] == [
        ("2025-01-01T09:00:00", 0, None), ("2025-01-01T17:00:00", 1, None),
        ("2025-01-02T00:00:00", None, "P"), ("2025-01-03T00:00:00", None, "A"),
    ]
    assert rows[0]["extra"] == {"Department": "Sales"}


def test_matrix_needs_a_month_when_headers_have_none(client):
    content = _matrix(cells={1: "P"}, title=b"")
    r = _run(client, content)
    assert r.status_code == 400 and "month" in r.json()["detail"]
    assert _run(client, content, period="2025-02").json()["saved"] == 1
    assert _records(client)[0]["punch_at"].startswith("2025-02-01")


def test_matrix_with_full_date_headers_needs_no_month(client):
    days = [f"2025-03-{d:02d}" for d in range(1, 9)]
    content = (",".join(["UID"] + days) + "\n" + ",".join(["1"] + ["P"] * 8) + "\n").encode()
    assert _run(client, content, period=None).json()["saved"] == 8


def test_matrix_day_not_in_month_warns_and_is_ignored(client):
    body = _run(client, _matrix(cells={30: "P", 1: "P"}), period="2025-02").json()
    assert body["saved"] == 1
    assert "do not exist" in body["warnings"][0]


def test_matrix_times_cell_with_am_pm(client):
    assert _run(client, _matrix(cells={5: "9:00 AM 5:30 PM"})).json()["saved"] == 2
    assert max(r["punch_at"] for r in _records(client)) == "2025-01-05T17:30:00"


# ---------- Excel ----------
def _excel(frames):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, sheet_name=name, index=False, header=False)
    return buffer.getvalue()


def test_excel_with_title_row_and_second_sheet(client):
    notes = pd.DataFrame([["ignore me"]])
    data = pd.DataFrame([["Monthly export", None], ["User ID", "Punch Time"],
                         ["0009", pd.Timestamp("2025-01-15 09:00:00")]])
    content = _excel({"Notes": notes, "Data": data})
    analysis = _analyze(client, content, name="f.xlsx", sheet="Data")
    assert analysis["sheets"] == ["Notes", "Data"] and analysis["header_row"] == 2
    assert _run(client, content, analysis, name="f.xlsx").json()["saved"] == 1
    assert _records(client)[0]["uid"] == "0009"


def test_excel_unknown_sheet_is_400(client):
    r = client.post("/import/analyze", files={"file": ("f.xlsx", _excel({"A": pd.DataFrame([["x", "y"]])}))},
                    data={"sheet": "Nope"})
    assert r.status_code == 400


def test_utf16_device_export(client):
    content = "UID\tDateTime\n1\t2025-01-15 09:00\n".encode("utf-16")
    assert _run(client, content).json()["saved"] == 1


def test_urdu_headers(client):
    content = "ملازم کوڈ,نام,تاریخ,آمد,روانگی\n1,Demo,2025-01-15,09:00,17:00\n".encode("utf-8")
    analysis = _analyze(client, content)
    assert analysis["shape"] == "daily"
    assert _run(client, content, analysis).json()["saved"] == 2


# ---------- mapping problems ----------
def test_missing_employee_code_is_explained(client):
    content = b"Foo,DateTime\n1,2025-01-15 09:00\n"
    r = _run(client, content)
    assert r.status_code == 400 and "Employee code" in r.json()["detail"]


def test_same_field_twice_is_rejected(client):
    content = b"A,B,DateTime\n1,2,2025-01-15 09:00\n"
    columns = {"A": "employee_code", "B": "employee_code", "DateTime": "punch_datetime"}
    r = _run(client, content, columns=columns)
    assert r.status_code == 400 and "more than one" in r.json()["detail"]


def test_unknown_field_and_broken_plan_are_rejected(client):
    content = b"UID,DateTime\n1,2025-01-15 09:00\n"
    assert _run(client, content, columns={"UID": "drop_table"}).status_code == 400
    r = client.post("/import/run", files={"file": ("t.csv", content)}, data={"plan": "{not json"})
    assert r.status_code == 400


def test_bad_files_are_rejected(client):
    r = client.post("/import/analyze", files={"file": ("evil.exe", b"MZ")})
    assert r.status_code == 400
    r = client.post("/import/analyze", files={"file": ("empty.csv", b"")})
    assert r.status_code == 400
    r = client.post("/import/analyze", files={"file": ("fake.xlsx", b"not excel")})
    assert r.status_code == 400


def test_import_requires_api_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    assert client.post("/import/analyze", files={"file": ("t.csv", b"a,b\n")}).status_code == 401
    assert client.get("/import/profiles").status_code == 401
    assert client.get("/import/ai/status").status_code == 401


# ---------- profiles ----------
PROFILE = {"name": "Head office", "shape": "punch_log", "date_order": "DMY", "headers": ["Foo", "Bar"],
           "columns": {"Foo": "employee_code", "Bar": "punch_datetime"}}


def test_profile_is_recognised_for_the_next_file(client):
    assert client.post("/import/profiles", json=PROFILE).status_code == 200
    content = b"Bar,Foo\n2025-01-15 09:00,1\n"  # column order does not matter
    match = _analyze(client, content)["matched_profile"]
    assert match["name"] == "Head office" and match["columns"]["Foo"] == "employee_code"
    assert _analyze(client, b"Other,Foo\n1,2\n")["matched_profile"] is None


def test_profile_same_name_replaces_and_delete_works(client):
    first = client.post("/import/profiles", json=PROFILE).json()
    again = client.post("/import/profiles", json={**PROFILE, "date_order": "MDY"}).json()
    assert again["id"] == first["id"] and again["date_order"] == "MDY"
    assert len(client.get("/import/profiles").json()) == 1
    assert client.delete(f"/import/profiles/{first['id']}").status_code == 200
    assert client.delete(f"/import/profiles/{first['id']}").status_code == 404


def test_matrix_profile_matches_a_month_with_different_days(client):
    headers = ["Emp Code"] + [str(d) for d in range(1, 32)]
    body = {"name": "Matrix", "shape": "monthly_matrix", "headers": headers,
            "columns": {"Emp Code": "employee_code", **{str(d): "day" for d in range(1, 32)}}}
    saved = client.post("/import/profiles", json=body).json()
    assert saved["columns"] == {"Emp Code": "employee_code"}
    february = (",".join(["Emp Code"] + [str(d) for d in range(1, 29)]) + "\n" + ",".join(["1"] * 29) + "\n").encode()
    assert _analyze(client, february)["matched_profile"]["id"] == saved["id"]


def test_profile_with_unknown_field_is_rejected(client):
    assert client.post("/import/profiles", json={**PROFILE, "columns": {"Foo": "bad"}}).status_code == 400


# ---------- AI (Ollama is always mocked here) ----------
AI_BODY = {"columns": [{"name": "Karkun Number", "samples": ["0012"]}, {"name": "Aamad", "samples": ["09:02"]}],
           "already_mapped": ["name"]}


def _usage_rows():
    with engine.connect() as conn:
        return conn.execute(text("SELECT feature, ok, prompt_version FROM ai_usage")).fetchall()


def test_ai_status_when_ollama_is_off(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    body = client.get("/import/ai/status").json()
    assert body["available"] is False and "ollama.com" in body["hint"]


def test_ai_status_model_missing(client, monkeypatch):
    monkeypatch.setattr(ollama_client, "_request", lambda *a, **k: {"models": [{"name": "other:1b"}]})
    body = client.get("/import/ai/status").json()
    assert body["running"] is True and body["available"] is False and "ollama pull" in body["hint"]


def test_ai_off_gives_503_and_logs_failure(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    r = client.post("/import/ai/suggest", json=AI_BODY)
    assert r.status_code == 503 and "not changed" in r.json()["detail"]
    assert _usage_rows()[0][1] in (False, 0)


def test_ai_reply_goes_through_the_whitelist(client, monkeypatch):
    reply = {"columns": [
        {"column": "Karkun Number", "field": "employee_code", "confidence": 0.9},
        {"column": "Aamad", "field": "time_in", "confidence": 0.8},
        {"column": "Aamad", "field": "time_out", "confidence": 0.7},       # column already placed
        {"column": "Made Up Column", "field": "date", "confidence": 0.99},  # not in the file
        {"column": "Karkun Number", "field": "drop_table", "confidence": 1},  # not a field
    ]}
    monkeypatch.setattr(ollama_client, "complete", lambda *a, **k: reply)
    body = client.post("/import/ai/suggest", json=AI_BODY).json()
    assert {(s["column"], s["field"]) for s in body["suggestions"]} == {
        ("Karkun Number", "employee_code"), ("Aamad", "time_in")}
    row = _usage_rows()[0]
    assert row[0] == "import_mapping" and row[1] in (True, 1) and row[2] == smart_mapping.PROMPT_VERSION


def test_ai_cannot_take_a_field_already_used_or_low_confidence(client, monkeypatch):
    reply = {"columns": [{"column": "Karkun Number", "field": "name", "confidence": 0.95},
                         {"column": "Aamad", "field": "time_in", "confidence": 0.2}]}
    monkeypatch.setattr(ollama_client, "complete", lambda *a, **k: reply)
    assert client.post("/import/ai/suggest", json=AI_BODY).json()["suggestions"] == []


@pytest.mark.parametrize("reply", [{"columns": "oops"}, {"nothing": 1}])
def test_ai_bad_shape_gives_503(client, monkeypatch, reply):
    monkeypatch.setattr(ollama_client, "complete", lambda *a, **k: reply)
    assert client.post("/import/ai/suggest", json=AI_BODY).status_code == 503


def test_ai_prompt_sends_only_a_few_short_samples():
    long_value = "x" * 500
    column = smart_mapping.ColumnIn(name="Foo", samples=[long_value] * 10)
    body = json.loads(smart_mapping.build_messages([column], [])[1]["content"])
    assert len(body["columns"][0]["samples"]) == smart_mapping.MAX_SAMPLES
    assert all(len(s) == smart_mapping.MAX_CELL for s in body["columns"][0]["samples"])


def test_import_works_with_ai_off(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    assert _run(client, b"UID,DateTime\n1,2025-01-15 09:00\n").json()["saved"] == 1


# ---------- small units ----------
@pytest.mark.parametrize("value,expected", [
    ("2025-01-15 09:00:00.000", "2025-01-15 09:00:00"),
    ("15-Jan-25 9:05 PM", "2025-01-15 21:05:00"),
    ("45672.375", "2025-01-15 09:00:00"),
    ("2025.01.15 09:00", "2025-01-15 09:00:00"),
])
def test_date_parser_full(value, expected):
    day, clock = DateParser().parse(value)
    assert f"{day} {clock}" == expected


def test_date_parser_time_only_and_bad():
    assert DateParser().parse("0.375") == (None, DateParser().parse("09:00")[1])
    assert DateParser().parse("1899-12-30 09:00:00")[0] is None
    with pytest.raises(ValueError):
        DateParser().parse("yesterday")


@pytest.mark.parametrize("text,period", [
    ("Attendance for January 2025", "2025-01"), ("report_mar-2026.xlsx", "2026-03"),
    ("export 2025-11.csv", "2025-11"), ("nothing here", None),
])
def test_detect_period(text, period):
    assert detect_period(text) == period


def test_typo_in_header_still_matches():
    assert match_header("Employe Code")[0] == "employee_code"
    assert match_header("Department")[0] is None


def test_read_table_makes_blank_and_repeated_headers_unique():
    table = read_table(b"UID,,Name,Name\n1,x,a,b\n", "t.csv", header_row=1)
    assert table.headers == ["UID", "Column 2", "Name", "Name (2)"]
