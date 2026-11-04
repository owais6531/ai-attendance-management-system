"""Flexible import: analyse any file, map its columns, check, then save."""
import json
import logging
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.auth import verify_api_key
from config.database import get_db
from models.attendance_models import ImportResponse
from services.ai import ollama_client, provider, smart_mapping, system_check
from services.ai.errors import AiError
from services.column_mapping import (
    ALLOWED_TARGETS, DAY, FIELDS, SHAPES, detect_period, detect_shape, header_signature, is_day_header,
    suggest_columns,
)
from services.database_service import DatabaseService
from services.file_reader import read_table
from services.file_upload_service import AttendanceFileUploadService as Upload, UploadError
from services.import_transform import transform

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["import"], dependencies=[Depends(verify_api_key)])

SAMPLE_ROWS = 5
DateOrder = Literal["DMY", "MDY"]
Shape = Literal["punch_log", "daily", "monthly_matrix"]


class ImportPlan(BaseModel):
    shape: Shape
    columns: Dict[str, str]
    date_order: DateOrder = "DMY"
    period: Optional[str] = None
    sheet: Optional[str] = None
    header_row: Optional[int] = Field(None, ge=1)


class ProfileIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    shape: Shape
    columns: Dict[str, str]
    date_order: DateOrder = "DMY"
    headers: List[str] = Field(..., min_length=1)


class AiSuggestIn(BaseModel):
    columns: List[smart_mapping.ColumnIn] = Field(..., min_length=1)
    already_mapped: List[str] = []


def _check_targets(columns: Dict[str, str]) -> None:
    unknown = sorted(set(columns.values()) - ALLOWED_TARGETS)
    if unknown:
        raise HTTPException(400, f"Unknown field: {', '.join(unknown)}")


async def _read_upload(file: UploadFile) -> bytes:
    return await file.read(Upload.max_upload_bytes() + 1)


def _analyze(content: bytes, filename: str, sheet: Optional[str], header_row: Optional[int],
             date_order: str) -> dict:
    table = read_table(content, filename, sheet, header_row)
    samples = {h: [row[1][i] for row in table.rows[:SAMPLE_ROWS * 4] if row[1][i]][:SAMPLE_ROWS]
               for i, h in enumerate(table.headers)}
    suggested = suggest_columns(table.headers, samples, date_order)
    targets = {h: t for h, (t, _) in suggested.items()}
    return {
        "file_name": filename,
        "sheets": table.sheets,
        "sheet": table.sheet,
        "header_row": table.header_row,
        "row_count": len(table.rows),
        "shape": detect_shape(targets),
        "period": detect_period(table.title_text, filename),
        "columns": [{
            "name": h,
            "target": targets[h],
            "confidence": suggested[h][1],
            "samples": samples[h],
            "is_day": is_day_header(h, date_order),
        } for h in table.headers],
        "signature": header_signature(table.headers, date_order),
    }


@router.get("/fields")
def list_fields():
    """The fields a column can be mapped to, and the supported file shapes."""
    return {"fields": FIELDS, "shapes": SHAPES}


@router.post("/analyze", responses={400: {"description": "Bad file"}, 413: {"description": "File too large"}})
async def analyze_file(
    file: UploadFile = File(...),
    sheet: Optional[str] = Form(None),
    header_row: Optional[int] = Form(None, ge=1),
    date_order: DateOrder = Form("DMY"),
    db: Session = Depends(get_db),
):
    """Find the header row, suggest a mapping and a file shape. Nothing is saved."""
    content = await _read_upload(file)
    try:
        result = await run_in_threadpool(_analyze, content, file.filename, sheet, header_row, date_order)
    except UploadError as e:
        raise HTTPException(e.status_code, str(e))
    try:
        match = await run_in_threadpool(DatabaseService(db).find_profile_by_signature, result["signature"])
        result["matched_profile"] = match.to_dict() if match else None
    except SQLAlchemyError:
        # The wizard still works without saved profiles.
        logger.exception("Could not look up import profiles")
        db.rollback()
        result["matched_profile"] = None
    return result


@router.post("/run", response_model=ImportResponse, responses={
    400: {"description": "Bad file or mapping"}, 413: {"description": "File too large"},
    503: {"description": "Database unavailable; nothing was saved"}})
async def run_import(
    file: UploadFile = File(...),
    plan: str = Form(..., description="ImportPlan as JSON: shape, columns, date_order, period, sheet, header_row"),
    dry_run: bool = Form(False, description="Validate only, do not save"),
    db: Session = Depends(get_db),
):
    """Apply a confirmed mapping. Re-importing is safe: stored punches are skipped."""
    try:
        parsed = ImportPlan.model_validate(json.loads(plan))
    except (ValueError, ValidationError):
        raise HTTPException(400, "The column mapping could not be read. Please map the columns again.")
    _check_targets(parsed.columns)

    content = await _read_upload(file)

    def work():
        table = read_table(content, file.filename, parsed.sheet, parsed.header_row)
        return table, transform(table, parsed.shape, parsed.columns, parsed.date_order, parsed.period)

    try:
        table, result = await run_in_threadpool(work)
    except UploadError as e:
        raise HTTPException(e.status_code, str(e))

    total, errors, records = len(table.rows), result.errors, result.records
    saved = duplicates = 0
    batch_id = None
    if not dry_run and records:
        try:
            outcome = await run_in_threadpool(
                DatabaseService(db).save_upload, file_name=file.filename, file_size=len(content),
                total_rows=total, rows=records, failed_rows=len(errors))
        except SQLAlchemyError:
            logger.exception("Saving import %s failed", file.filename)
            raise HTTPException(503, "Database is unavailable. Nothing was saved; please try again.")
        saved, duplicates, batch_id = outcome["saved"], outcome["duplicates"], outcome["batch_id"]

    if dry_run:
        message = f"Checked {total} rows: {len(records)} records found, {len(errors)} problems (nothing saved)"
    else:
        message = f"Saved {saved} of {len(records)} records from {total} rows"
        if duplicates:
            message += f"; {duplicates} duplicates skipped"
        if errors:
            message += f"; {len(errors)} problems"

    return ImportResponse(
        message=message, file_name=file.filename, total_records=total, valid_records=len(records),
        records_found=len(records), saved=saved, duplicates_skipped=duplicates, failed_imports=len(errors),
        errors=errors[:Upload.MAX_ERRORS_RETURNED], errors_truncated=len(errors) > Upload.MAX_ERRORS_RETURNED,
        preview=records[:Upload.PREVIEW_ROWS], batch_id=batch_id, shape=parsed.shape,
        skipped_blank=result.skipped_blank, warnings=result.warnings,
    )


# ---------- profiles ----------
@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    return [p.to_dict() for p in DatabaseService(db).list_profiles()]


@router.post("/profiles")
def save_profile(body: ProfileIn, db: Session = Depends(get_db)):
    """Save the mapping under a name. Saving the same name again replaces it."""
    _check_targets(body.columns)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Profile name is empty")
    # Day columns are found again in each file, so months with 28 or 31 days both work.
    columns = {h: t for h, t in body.columns.items() if t != DAY}
    try:
        profile = DatabaseService(db).save_profile(
            name=name, shape=body.shape, columns=columns, date_order=body.date_order,
            signature=header_signature(body.headers, body.date_order))
    except SQLAlchemyError:
        logger.exception("Saving import profile failed")
        raise HTTPException(503, "Database is unavailable. The profile was not saved.")
    return profile.to_dict()


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    if not DatabaseService(db).delete_profile(profile_id):
        raise HTTPException(404, "Profile not found")
    return {"deleted": profile_id}


# ---------- AI (optional) ----------
@router.get("/ai/status")
def ai_status():
    return provider.status()


@router.get("/ai/setup")
def ai_setup():
    """What the AI options need, and whether this computer can run local AI. Installs nothing."""
    return {
        "status": provider.status(),
        "system": system_check.check(),
        "local": {
            "download_url": "https://ollama.com/download",
            "pull_command": f"ollama pull {ollama_client.text_model()}",
        },
        "api": {
            "env_example": "AI_PROVIDER=api\n"
                           "AI_API_URL=https://api.openai.com/v1\n"
                           "AI_API_KEY=your-key-here\n"
                           "AI_API_MODEL=name-of-the-model",
        },
    }


@router.post("/ai/suggest", responses={503: {"description": "AI is off or gave an unusable reply"}})
def ai_suggest(body: AiSuggestIn, db: Session = Depends(get_db)):
    """Proposals for columns the rules could not place. The person confirms them in the wizard."""
    already = [t for t in body.already_mapped if t in FIELDS]
    columns = [c for c in body.columns if c.name]
    try:
        return smart_mapping.suggest(columns, already, log=DatabaseService(db).log_ai_usage)
    except AiError as e:
        raise HTTPException(503, f"AI suggestion is not available: {e}. Your mapping was not changed.")
