#!/usr/bin/env python3
"""Generate FAKE attendance files for demos and testing.

Every name and code is randomly generated; no real person or company data is used.
Output goes to sample_data/ in the device-export format the app accepts.

Usage:
    python scripts/generate_demo_data.py                     # 40 employees, 1 month
    python scripts/generate_demo_data.py --employees 120 --month 2025-03 --seed 7
"""
import argparse
import calendar
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

FIRST = ["Ali", "Sara", "Usman", "Ayesha", "Hamza", "Fatima", "Kashif", "Zainab", "Omar", "Hira",
         "Saad", "Mariam", "Fahad", "Noor", "Imran", "Sana", "Talha", "Iqra", "Danish", "Amna"]
LAST = ["Demo", "Sample", "Test", "Example", "Placeholder"]  # obviously fake surnames
HEADER = ["No", "DN", "UID", "Name", "Status", "Action", "APB", "JobCode", "DateTime"]


def build_rows(employees: int, year: int, month: int, rng: random.Random):
    staff = [(f"{i:04d}", f"{rng.choice(FIRST)} {rng.choice(LAST)} {i}") for i in range(1, employees + 1)]
    # Each fake employee gets a personality: punctual, often late, or sometimes absent.
    profile = {code: rng.choices(["punctual", "late", "absent"], [70, 20, 10])[0] for code, _ in staff}
    rows, n = [], 0
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        date = datetime(year, month, day)
        if date.weekday() == 6:  # Sunday off
            continue
        for code, name in staff:
            p = profile[code]
            if (p == "absent" and rng.random() < 0.25) or rng.random() < 0.03:
                continue
            late = rng.randint(10, 75) if p == "late" and rng.random() < 0.5 else rng.randint(-15, 8)
            check_in = date.replace(hour=9) + timedelta(minutes=late, seconds=rng.randint(0, 59))
            check_out = date.replace(hour=17) + timedelta(minutes=rng.randint(-20, 90), seconds=rng.randint(0, 59))
            punches = [(check_in, 0), (check_out, 1)]
            if rng.random() < 0.04:  # forgot to punch out
                punches = punches[:1]
            for when, status in punches:
                n += 1
                rows.append([n, rng.choice([1, 1, 2]), code, name, status, 1, 0, 0,
                             when.strftime("%Y/%m/%d %H:%M:%S")])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--employees", type=int, default=40)
    parser.add_argument("--month", default="2025-01", help="YYYY-MM")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="sample_data")
    args = parser.parse_args()

    year, month = map(int, args.month.split("-"))
    rows = build_rows(args.employees, year, month, random.Random(args.seed))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / f"demo_punches_{args.month}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)

    # A tab-separated UTF-16 copy, like many biometric devices export.
    device_path = out / f"demo_device_export_{args.month}_utf16.csv"
    with device_path.open("w", newline="", encoding="utf-16") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(HEADER)
        writer.writerows(rows)

    print(f"{len(rows)} fake punches for {args.employees} fake employees:\n  {csv_path}\n  {device_path}")


if __name__ == "__main__":
    main()
