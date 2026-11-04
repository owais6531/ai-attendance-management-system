#!/usr/bin/env python3
"""Write small FAKE sample files showing each layout the flexible import accepts.

Every name and code is made up. Output goes to sample_data/.

Usage:
    python scripts/generate_import_samples.py
"""
import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample_data"
STAFF = [("0001", "Ali Demo"), ("0002", "Sara Sample"), ("0003", "Usman Test")]


def write(name, rows, encoding="utf-8-sig"):
    with (OUT / name).open("w", newline="", encoding=encoding) as f:
        csv.writer(f).writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    write("import_2_columns.csv", [["Emp ID", "Punch Time"]] + [
        [code, f"2025-01-15 09:0{i}:00"] for i, (code, _) in enumerate(STAFF)])

    write("import_with_title_rows.csv", [
        ["Demo Company (Pvt) Ltd"], ["Attendance Report"], [],
        ["AC-No.", "Name", "Date/Time", "State", "Department"],
    ] + [[code, name, f"15/01/2025 09:0{i}", "C/In", "Sales"] for i, (code, name) in enumerate(STAFF)])

    write("import_daily_sheet.csv", [["Code", "Name", "Date", "Check In", "Check Out", "Department"]] + [
        [code, name, "2025-01-15", f"09:0{i}", "17:30", "Sales"] for i, (code, name) in enumerate(STAFF)])

    write("import_urdu_headers.csv", [["ملازم کوڈ", "نام", "تاریخ", "آمد", "روانگی"]] + [
        [code, name, "2025-01-15", "09:00", "17:00"] for code, name in STAFF])

    # Unusual headings the rules cannot place: this is what the AI button is for.
    write("import_messy_headers.csv", [["Karkun Number", "Ism", "Din", "Aamad", "Rawangi"]] + [
        [code, name, "2025-01-15", "09:00", "17:00"] for code, name in STAFF])

    days = [str(d) for d in range(1, 32)]
    marks = ["09:00-17:00", "P", "A", "L", "", "09:15-17:30", "P"]
    write("import_monthly_matrix.csv", [
        ["Attendance for January 2025"],
        ["Emp Code", "Name", "Department"] + days,
    ] + [[code, name, "Sales"] + [marks[(d + i) % len(marks)] for d in range(31)]
         for i, (code, name) in enumerate(STAFF)])

    print(f"Sample files written to {OUT}")


if __name__ == "__main__":
    main()
