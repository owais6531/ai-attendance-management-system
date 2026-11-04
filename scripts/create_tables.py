#!/usr/bin/env python3
"""Create or upgrade the database schema (runs Alembic migrations).

The app also does this automatically on startup unless AUTO_MIGRATE=False.

Usage:  python scripts/create_tables.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import DATABASE_URL, run_migrations, safe_url, test_connection  # noqa: E402

if __name__ == "__main__":
    print(f"Database: {safe_url(DATABASE_URL)}")
    if not test_connection():
        print("Cannot connect. Check DATABASE_URL (or DB_* variables) in .env")
        sys.exit(1)
    run_migrations()
    print("Schema is up to date. Start the app with: python main.py")
