import logging
import os
from contextlib import asynccontextmanager
from datetime import date

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.auth import auth_enabled
from config.database import DATABASE_URL, run_migrations, safe_url, test_connection
from routes.database_routes import router as database_router
from routes.import_routes import router as import_router
from routes.upload_routes import router as upload_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_NAME = os.getenv("APP_NAME", "AI Attendance Management System")
APP_VERSION = "0.3.0"


def _env_true(name: str, default: str = "True") -> bool:
    return os.getenv(name, default).lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s, database: %s", APP_NAME, APP_VERSION, safe_url(DATABASE_URL))
    if test_connection():
        # AUTO_CREATE_TABLES is the old name of this setting.
        if _env_true("AUTO_MIGRATE", os.getenv("AUTO_CREATE_TABLES", "True")):
            run_migrations()
    else:
        logger.warning("Database is not reachable; uploads will fail until it is. Check DATABASE_URL in .env")
    yield


app = FastAPI(
    title=APP_NAME,
    description="Open-source attendance management: upload biometric/Excel exports, validate, store and report.",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.include_router(import_router)
app.include_router(upload_router)
app.include_router(database_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse(request, "upload.html", {
        "app_name": APP_NAME,
        "auth_required": auth_enabled(),
        "year": date.today().year,
    })


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "application": APP_NAME,
        "version": APP_VERSION,
        "database": "connected" if test_connection() else "disconnected",
    }


@app.get("/info")
async def app_info():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "features": [
            "Flexible import: any Excel/CSV file, 2 to 100+ columns",
            "Three file shapes: punch log, daily sheet, monthly matrix",
            "Saved import profiles",
            "Optional local AI column mapping (Ollama)",
            "Per-row validation with downloadable errors",
            "Duplicate-safe re-uploads",
            "Dry-run (validate without saving)",
            "SQLite, MySQL or PostgreSQL",
            "REST API with date filters",
        ],
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                reload=_env_true("DEBUG", "False"), log_level="info")
