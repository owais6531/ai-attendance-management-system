#!/usr/bin/env python3
"""
Database table creation script for Attendance Application

This script creates all necessary database tables for the attendance system.
Run this script after setting up PostgreSQL database and before starting the application.

Usage:
    python scripts/create_tables.py
"""

import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import engine, Base, test_connection, create_tables, DatabaseConfig
from models.db_models import AttendanceRecord, UploadBatch
from sqlalchemy import text

def main():
    """Main function to create database tables"""
    print("🚀 Starting database setup...")
    print(f"📊 Database: {DatabaseConfig.DB_NAME}")
    print(f"🔗 Host: {DatabaseConfig.DB_HOST}:{DatabaseConfig.DB_PORT}")
    print(f"👤 User: {DatabaseConfig.DB_USER}")
    print("-" * 50)
    
    # Test database connection
    print("🔍 Testing database connection...")
    if not test_connection():
        print("❌ Database connection failed. Please check your PostgreSQL setup.")
        print("\n📋 Troubleshooting steps:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check database credentials in config/database.py")
        print("3. Verify database 'attendanceApp' exists")
        print("4. Confirm user has proper permissions")
        return False
    
    # Create tables
    print("\n🏗️  Creating database tables...")
    try:
        # Import models to ensure they're registered with Base
        print("📝 Registering models...")
        print(f"   - AttendanceRecord: {AttendanceRecord.__tablename__}")
        print(f"   - UploadBatch: {UploadBatch.__tablename__}")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✅ All tables created successfully!")
        
        # Verify tables were created
        print("\n🔍 Verifying table creation...")
        with engine.connect() as connection:
            # Check if tables exist
            result = connection.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """))
            
            tables = [row[0] for row in result]
            print(f"📋 Created tables: {', '.join(tables)}")
            
            if 'attendance_records' in tables and 'upload_batches' in tables:
                print("✅ All required tables verified!")
                return True
            else:
                print("⚠️  Some tables may be missing")
                return False
                
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        return False

def check_database_status():
    """Check current database status"""
    print("\n📊 Database Status Check")
    print("-" * 30)
    
    try:
        with engine.connect() as connection:
            # Check existing tables
            result = connection.execute(text("""
                SELECT table_name, 
                       (SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = t.table_name AND table_schema = 'public') as column_count
                FROM information_schema.tables t
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """))
            
            tables = list(result)
            if tables:
                print("📋 Existing tables:")
                for table_name, column_count in tables:
                    print(f"   - {table_name} ({column_count} columns)")
            else:
                print("📋 No tables found in database")
                
            # Check attendance_records table structure if it exists
            if any(table[0] == 'attendance_records' for table in tables):
                print("\n📝 attendance_records table structure:")
                result = connection.execute(text("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = 'attendance_records' 
                    AND table_schema = 'public'
                    ORDER BY ordinal_position;
                """))
                
                for column_name, data_type, is_nullable, column_default in result:
                    nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
                    default = f" DEFAULT {column_default}" if column_default else ""
                    print(f"   - {column_name}: {data_type} {nullable}{default}")
                    
    except Exception as e:
        print(f"❌ Failed to check database status: {e}")

if __name__ == "__main__":
    print("🎯 Attendance App - Database Setup")
    print("=" * 40)
    
    # Check current status first
    check_database_status()
    
    # Ask user if they want to proceed
    print("\n❓ Do you want to create/recreate the database tables? (y/N): ", end="")
    response = input().strip().lower()
    
    if response in ['y', 'yes']:
        success = main()
        if success:
            print("\n🎉 Database setup completed successfully!")
            print("\n🚀 You can now start the application with: python main.py")
        else:
            print("\n❌ Database setup failed. Please check the errors above.")
            sys.exit(1)
    else:
        print("\n⏹️  Database setup cancelled.")
        check_database_status()