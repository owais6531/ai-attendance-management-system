from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from routes.upload_routes import router as upload_router
from routes.database_routes import router as database_router
from config.database import test_connection, create_tables
import os
import uvicorn
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events"""
    logger.info("🚀 Starting Bilal Attendance System...")

    logger.info("🔍 Testing database connection...")
    if test_connection():
        logger.info("✅ Database connection successful")
        if os.getenv("AUTO_CREATE_TABLES", "True").lower() == "true":
            create_tables()
    else:
        logger.warning("⚠️  Database connection failed - some features may not work")
        logger.info("💡 Check your DB_* environment variables in .env")

    yield


# Create FastAPI application
app = FastAPI(
    title="Bilal Attendance System",
    description="Employee attendance management system with Excel/CSV upload functionality",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(upload_router)
app.include_router(database_router)

# Root endpoint - serve upload page
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main upload page"""
    return templates.TemplateResponse(request, "upload.html")

# Favicon endpoint to prevent 404 errors
@app.get("/favicon.ico")
async def favicon():
    """Return empty response for favicon to prevent 404 errors"""
    return {"message": "No favicon configured"}

# Health check endpoint
@app.get("/health")
async def health_check():
    """Application health check"""
    # Test database connection
    db_status = "connected" if test_connection() else "disconnected"
    
    return {
        "status": "healthy",
        "application": "Bilal Attendance System",
        "version": "1.0.0",
        "database": db_status
    }

# API info endpoint
@app.get("/info")
async def app_info():
    """Application information"""
    return {
        "name": "Bilal Attendance System",
        "version": "1.0.0",
        "description": "Employee attendance management with Excel/CSV upload",
        "features": [
            "Excel/CSV file upload",
            "Data validation",
            "Error reporting",
            "Template download",
            "Real-time processing"
        ]
    }

if __name__ == "__main__":
    print("Starting Bilal Attendance System...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )