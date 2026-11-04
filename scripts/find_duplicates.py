#!/usr/bin/env python3
"""List duplicate punches (same employee code + same timestamp). Read-only: deletes nothing.

Usage:  python scripts/find_duplicates.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from config.database import DATABASE_URL, engine, safe_url  # noqa: E402

QUERY = text("""
    SELECT uid, punch_at, COUNT(*) AS copies, MIN(id) AS first_id
    FROM attendance_records
    WHERE punch_at IS NOT NULL
    GROUP BY uid, punch_at
    HAVING COUNT(*) > 1
    ORDER BY punch_at, uid
""")

if __name__ == "__main__":
    print(f"Database: {safe_url(DATABASE_URL)}")
    with engine.connect() as conn:
        rows = conn.execute(QUERY).fetchall()
    if not rows:
        print("No duplicate punches found.")
        sys.exit(0)
    print(f"{len(rows)} duplicate groups ({sum(r.copies - 1 for r in rows)} extra rows):")
    for r in rows:
        print(f"  UID {r.uid:<20} {r.punch_at}  x{r.copies}  (keep id {r.first_id})")
    print("\nNothing was changed. Remove extra rows only after reviewing them and taking a backup.")
