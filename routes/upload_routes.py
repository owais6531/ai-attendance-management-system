import io
import logging
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.auth import verify_api_key
from config.database import get_db
from models.attendance_models import UploadResponse
from services.database_service import DatabaseService
from services.file_upload_service import AttendanceFileUploadService as Upload, UploadError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/attendance", response_model=UploadResponse, dependencies=[Depends(verify_api_key)],
             responses={400: {"description": "Bad file"}, 413: {"description": "File too large"},
                        503: {"description": "Database unavailable; nothing was saved"}})
async def upload_attendance_file(
    file: UploadFile = File(...),
    date_order: Literal["DMY", "MDY"] = Form("DMY", description="How to read dates like 03/04/2025"),
    dry_run: bool = Form(False, description="Validate only, do not save"),
    db: Session = Depends(get_db),
):
    """Upload an Excel/CSV attendance file, validate every row and save the valid ones.

    Re-uploading the same file is safe: punches already stored (same employee code
    and timestamp) are skipped and counted in ``duplicates_skipped``.
    """
    if not Upload.is_allowed_filename(file.filename):
        raise HTTPException(400, "Invalid file type. Supported formats: Excel (.xlsx, .xls) and CSV (.csv)")

    limit = Upload.max_upload_bytes()
    content = await file.read(limit + 1)
    try:
        df, records, errors = await run_in_threadpool(Upload.parse_and_validate, content,
                                                      file.filename, date_order)
    except UploadError as e:
        raise HTTPException(e.status_code, str(e))

    saved = duplicates = 0
    batch_id = None
    if not dry_run and records:
        try:
            result = await run_in_threadpool(
                DatabaseService(db).save_upload, file_name=file.filename, file_size=len(content),
                total_rows=len(df), rows=records, failed_rows=len(errors))
        except SQLAlchemyError:
            logger.exception("Saving upload %s failed", file.filename)
            raise HTTPException(503, "Database is unavailable. Nothing was saved; please try again.")
        saved, duplicates, batch_id = result["saved"], result["duplicates"], result["batch_id"]

    if dry_run:
        message = f"Checked {len(df)} rows: {len(records)} valid, {len(errors)} with errors (nothing saved)"
    else:
        message = f"Saved {saved} of {len(df)} rows"
        if duplicates:
            message += f"; {duplicates} duplicates skipped"
        if errors:
            message += f"; {len(errors)} rows have errors"

    return UploadResponse(
        message=message,
        file_name=file.filename,
        total_records=len(df),
        valid_records=len(records),
        saved=saved,
        duplicates_skipped=duplicates,
        failed_imports=len(errors),
        errors=errors[:Upload.MAX_ERRORS_RETURNED],
        errors_truncated=len(errors) > Upload.MAX_ERRORS_RETURNED,
        preview=records[:Upload.PREVIEW_ROWS],
        batch_id=batch_id,
    )


@router.get("/template")
async def download_template():
    """Download an Excel template with the expected columns and fake sample rows."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        Upload.generate_template().to_excel(writer, sheet_name='Attendance Template', index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": "attachment; filename=attendance_template.xlsx"},
    )


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "attendance_upload"}
