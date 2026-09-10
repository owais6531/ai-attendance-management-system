# PostgreSQL Database Setup Script for Attendance Application
# This script creates the database and sets up the initial schema

Write-Host "PostgreSQL Database Setup for Attendance Application" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

# Database configuration - reads from environment variables (see .env.example)
$DB_HOST = if ($env:DB_HOST) { $env:DB_HOST } else { "localhost" }
$DB_PORT = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$DB_NAME = if ($env:DB_NAME) { $env:DB_NAME } else { "attendanceapp" }
$DB_USER = if ($env:DB_USER) { $env:DB_USER } else { "postgres" }
$DB_PASSWORD = $env:DB_PASSWORD

if (-not $DB_PASSWORD) {
    Write-Host "ERROR: Set the DB_PASSWORD environment variable before running this script." -ForegroundColor Red
    Write-Host "   Example: `$env:DB_PASSWORD = 'your-password'; ./scripts/setup_database.ps1" -ForegroundColor Yellow
    exit 1
}

# Function to test PostgreSQL connection
function Test-PostgreSQLConnection {
    param(
        [string]$DbHost = $DB_HOST,
        [string]$DbPort = $DB_PORT,
        [string]$DbUser = $DB_USER,
        [string]$DbPassword = $DB_PASSWORD
    )
    
    try {
        Write-Host "Testing PostgreSQL connection..." -ForegroundColor Yellow
        
        # Test connection to default 'postgres' database first
        $env:PGPASSWORD = $DbPassword
        $result = psql -h $DbHost -p $DbPort -U $DbUser -d postgres -c "SELECT 1;" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "SUCCESS: PostgreSQL connection successful!" -ForegroundColor Green
            return $true
        } else {
            Write-Host "ERROR: PostgreSQL connection failed: $result" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "ERROR: PostgreSQL connection error: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

# Function to create database
function New-AttendanceDatabase {
    param(
        [string]$DatabaseName = $DB_NAME
    )
    
    try {
        Write-Host "Creating database '$DatabaseName'..." -ForegroundColor Yellow
        
        $env:PGPASSWORD = $DB_PASSWORD
        
        # Check if database already exists
        $checkResult = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -t -c "SELECT 1 FROM pg_database WHERE datname='$DatabaseName';" 2>&1
        
        if ($checkResult -match "1") {
            Write-Host "INFO: Database '$DatabaseName' already exists." -ForegroundColor Blue
            return $true
        }
        
        # Create the database
        $createResult = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "CREATE DATABASE `"$DatabaseName`";" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "SUCCESS: Database '$DatabaseName' created successfully!" -ForegroundColor Green
            return $true
        } else {
            Write-Host "ERROR: Failed to create database: $createResult" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "ERROR: Database creation error: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

# Function to verify database setup
function Test-DatabaseSetup {
    try {
        Write-Host "Verifying database setup..." -ForegroundColor Yellow
        
        $env:PGPASSWORD = $DB_PASSWORD
        
        # Test connection to the new database
        $result = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT current_database(), current_user;" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "SUCCESS: Database verification successful!" -ForegroundColor Green
            Write-Host "Connected to: $result" -ForegroundColor Cyan
            return $true
        } else {
            Write-Host "ERROR: Database verification failed: $result" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "ERROR: Database verification error: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

# Main execution
Write-Host "Database Configuration:" -ForegroundColor Cyan
Write-Host "   Host: $DB_HOST" -ForegroundColor White
Write-Host "   Port: $DB_PORT" -ForegroundColor White
Write-Host "   Database: $DB_NAME" -ForegroundColor White
Write-Host "   User: $DB_USER" -ForegroundColor White
Write-Host ""

# Step 1: Test PostgreSQL connection
if (-not (Test-PostgreSQLConnection)) {
    Write-Host "" -ForegroundColor Red
    Write-Host "SETUP FAILED! Please check:" -ForegroundColor Red
    Write-Host "   1. PostgreSQL is installed and running" -ForegroundColor Yellow
    Write-Host "   2. PostgreSQL service is started" -ForegroundColor Yellow
    Write-Host "   3. User credentials are correct" -ForegroundColor Yellow
    Write-Host "   4. psql command is available in PATH" -ForegroundColor Yellow
    Write-Host "" -ForegroundColor Red
    Write-Host "To start PostgreSQL service, run:" -ForegroundColor Cyan
    Write-Host "   net start postgresql-x64-16" -ForegroundColor White
    Write-Host "   (or check your PostgreSQL service name)" -ForegroundColor Gray
    exit 1
}

# Step 2: Create database
if (-not (New-AttendanceDatabase)) {
    Write-Host "ERROR: Failed to create database. Setup aborted." -ForegroundColor Red
    exit 1
}

# Step 3: Verify setup
if (-not (Test-DatabaseSetup)) {
    Write-Host "ERROR: Database verification failed. Setup may be incomplete." -ForegroundColor Red
    exit 1
}

Write-Host "" -ForegroundColor Green
Write-Host "SUCCESS: Database setup completed successfully!" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "   1. Run: python scripts/create_tables.py" -ForegroundColor White
Write-Host "   2. Start the application: python main.py" -ForegroundColor White
Write-Host "" -ForegroundColor Green