"""Read any Excel/CSV file into plain rows and find the real header row.

Exports often start with title rows ("Attendance Report", company name, dates)
and contain blank rows and columns. Everything is read as text, so employee codes
such as "0012" keep their leading zeros.
"""
import csv
import io
import logging
from dataclasses import dataclass, field
from statistics import median
from typing import List, Optional, Tuple

import pandas as pd

from services.column_mapping import day_run_length, header_hit_count, looks_like_data
from services.file_upload_service import AttendanceFileUploadService as Upload, UploadError

logger = logging.getLogger(__name__)
HEADER_SEARCH_ROWS = 25


@dataclass
class Table:
    headers: List[str]
    rows: List[Tuple[int, List[str]]]  # (row number as seen in Excel, cells)
    sheets: List[str] = field(default_factory=list)
    sheet: Optional[str] = None
    header_row: int = 1  # 1-based
    title_text: str = ""


def check_upload(content: bytes, filename: Optional[str]) -> None:
    if not Upload.is_allowed_filename(filename):
        raise UploadError("Invalid file type. Supported formats: Excel (.xlsx, .xls) and CSV (.csv)")
    if len(content) > Upload.max_upload_bytes():
        raise UploadError(f"File is too large. Maximum size is {Upload.max_upload_bytes() // (1024 * 1024)} MB", 413)
    if not content:
        raise UploadError("The file is empty")


def _decode(content: bytes) -> str:
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return content.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadError("Could not decode the CSV file")


def _read_csv(content: bytes) -> List[List[str]]:
    try:
        text = _decode(content)
    except UnicodeError:
        raise UploadError("Could not decode the CSV file")
    lines = [line for line in text.splitlines()[:50] if line.strip()]
    if not lines:
        raise UploadError("The file is empty")
    # The widest typical line wins; title rows have no delimiters and the median ignores them.
    delimiter = max("\t,;|", key=lambda d: median(len(line.split(d)) for line in lines) * 1000
                    + max(len(line.split(d)) for line in lines))
    try:
        return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    except csv.Error as e:
        logger.info("CSV parse failed: %s", e)
        raise UploadError("Could not read the CSV file")


def _read_excel(content: bytes, sheet: Optional[str]) -> Tuple[List[List[str]], List[str], str]:
    try:
        book = pd.ExcelFile(io.BytesIO(content))
        names = [str(n) for n in book.sheet_names]
        if sheet and sheet not in names:
            raise UploadError(f"Sheet '{sheet}' was not found in this file")
        for name in ([sheet] if sheet else names):
            frame = book.parse(name, header=None, dtype=str).fillna("")
            if not frame.empty:
                return [[str(c).strip() for c in row] for row in frame.values.tolist()], names, name
    except UploadError:
        raise
    except Exception as e:  # noqa: BLE001 - any parser failure is a bad file
        logger.info("Excel parse failed: %s", e)
        raise UploadError("Could not read the file. Make sure it is a valid Excel or CSV file.")
    raise UploadError("The file has no data")


def detect_header_row(grid: List[List[str]]) -> int:
    """Return the 0-based index of the most header-like row among the first rows."""
    best, best_score = None, 0
    for index, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
        cells = [c for c in row if c]
        if len(cells) < 2:
            continue
        text_cells = sum(1 for c in cells if not looks_like_data(c))
        run = day_run_length(cells)
        score = header_hit_count(cells) * 3 + text_cells + (run * 2 if run >= 5 else 0)
        if score > best_score:
            best, best_score = index, score
    if best is not None:
        return best
    # Nothing looks like a header: use the first non-blank row.
    return next((i for i, row in enumerate(grid) if any(row)), 0)


def _unique_headers(cells: List[str]) -> List[str]:
    seen, headers = {}, []
    for position, cell in enumerate(cells, start=1):
        name = cell or f"Column {position}"
        seen[name] = seen.get(name, 0) + 1
        headers.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return headers


def read_table(content: bytes, filename: str, sheet: Optional[str] = None,
               header_row: Optional[int] = None) -> Table:
    """Read the file. ``header_row`` (1-based) overrides automatic detection."""
    check_upload(content, filename)
    if filename.lower().endswith(".csv"):
        grid, sheets, chosen = _read_csv(content), [], None
    else:
        grid, sheets, chosen = _read_excel(content, sheet)
    if not any(any(row) for row in grid):
        raise UploadError("The file has no data")

    width = max(len(row) for row in grid)
    grid = [row + [""] * (width - len(row)) for row in grid]
    keep = [i for i in range(width) if any(row[i] for row in grid)]
    grid = [[row[i] for i in keep] for row in grid]

    if header_row is not None:
        if not 1 <= header_row <= len(grid):
            raise UploadError(f"Header row must be between 1 and {len(grid)}")
        index = header_row - 1
    else:
        index = detect_header_row(grid)

    title = " ".join(c for row in grid[:index] for c in row if c)
    rows = [(number, row) for number, row in enumerate(grid[index + 1:], start=index + 2) if any(row)]
    return Table(_unique_headers(grid[index]), rows, sheets, chosen, index + 1, title)
