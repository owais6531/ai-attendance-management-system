"""Field registry, rule-based column matching and file-shape detection.

Rules run first; AI (optional) is only asked about columns the rules could not place.
"""
import hashlib
import re
import unicodedata
from datetime import date, datetime, time
from difflib import SequenceMatcher, get_close_matches
from typing import Dict, List, Optional, Tuple

PUNCH_LOG, DAILY, MATRIX = "punch_log", "daily", "monthly_matrix"
SHAPES = (PUNCH_LOG, DAILY, MATRIX)
EXTRA, IGNORE, DAY = "extra", "ignore", "day"

FIELDS: Dict[str, str] = {
    "employee_code": "Employee code",
    "name": "Employee name",
    "punch_datetime": "Date and time (one column)",
    "date": "Date",
    "time": "Time",
    "time_in": "Time in",
    "time_out": "Time out",
    "day_status": "Day status (P, A, Leave...)",
    "status": "In/Out state",
    "record_no": "Record number",
    "device_no": "Device number",
    "action": "Action code",
    "apb": "APB code",
    "job_code": "Job code",
}
ALLOWED_TARGETS = set(FIELDS) | {EXTRA, IGNORE, DAY}

# Normalised header -> field. Generic words get less confidence, so a clearer column wins.
_SYNONYMS: Dict[str, List[str]] = {
    "employee_code": [
        "uid", "user id", "userid", "emp id", "empid", "emp code", "empcode", "employee id", "employeeid",
        "employee code", "employee no", "employee number", "emp no", "empno", "ac no", "acno", "account no",
        "enroll no", "enrollno", "enroll id", "enrollment no", "enroll number", "badge", "badge no",
        "badgenumber", "badge number", "card no", "card number", "cardno", "person id", "personnel id",
        "staff id", "staff no", "staff code", "worker id", "ecode", "user code", "ملازم کوڈ", "ملازم نمبر",
        "کوڈ", "آئی ڈی", "id", "code", "pin",
    ],
    "name": ["name", "employee name", "emp name", "empname", "full name", "staff name", "person name",
             "user name", "username", "نام", "ملازم کا نام"],
    "punch_datetime": ["datetime", "date time", "date and time", "date & time", "punch time", "punchtime",
                       "punch", "punch date time", "check time", "checktime", "log time", "logtime", "timestamp",
                       "time stamp", "clock time", "att time", "attendance time", "record time", "verify time",
                       "تاریخ و وقت"],
    "date": ["date", "att date", "attendance date", "work date", "workdate", "log date", "punch date", "day date",
             "تاریخ"],
    "time": ["time", "وقت"],
    "time_in": ["in", "time in", "timein", "in time", "intime", "check in", "checkin", "clock in", "clockin",
                "first in", "first punch", "on duty", "onduty", "c in", "punch in", "آمد", "وقت آمد"],
    "time_out": ["out", "time out", "timeout", "out time", "outtime", "check out", "checkout", "clock out",
                 "clockout", "last out", "last punch", "off duty", "offduty", "c out", "punch out", "روانگی",
                 "وقت روانگی"],
    "day_status": ["attendance", "att status", "attendance status", "day status", "present", "p a", "حاضری"],
    "status": ["status", "state", "check type", "checktype", "punch state", "in out", "io mode", "in out mode",
               "stat"],
    "record_no": ["no", "sr", "sr no", "srno", "sno", "s no", "serial", "serial no", "record no", "log id",
                  "نمبر شمار"],
    "device_no": ["dn", "device", "device no", "device id", "deviceid", "machine", "machine no", "machine id",
                  "terminal", "terminal id", "terminal no"],
    "action": ["action"],
    "apb": ["apb", "anti pass back"],
    "job_code": ["jobcode", "job code", "job"],
}
_WEAK = {"id", "code", "pin", "no", "sr", "s no", "state", "stat", "job", "in", "out", "device", "machine", "present"}
_LOOKUP = {syn: field for field, syns in _SYNONYMS.items() for syn in syns}

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH_RE = "|".join(_MONTHS)
_DAY_NAME_RE = "mon|tue|wed|thu|fri|sat|sun"


def normalize(header: str) -> str:
    text = unicodedata.normalize("NFKC", str(header)).lower()
    text = re.sub(r"[._\-/#:()\[\]\\]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_header(header: str) -> Tuple[Optional[str], float]:
    """Return (field, confidence) from the synonym list, or (None, 0)."""
    key = normalize(header)
    if key in _LOOKUP:
        return _LOOKUP[key], 0.7 if key in _WEAK else 1.0
    if len(key) >= 5 and key.isascii():
        close = get_close_matches(key, [s for s in _LOOKUP if s.isascii()], n=1, cutoff=0.86)
        if close:
            return _LOOKUP[close[0]], round(SequenceMatcher(None, key, close[0]).ratio() * 0.9, 2)
    return None, 0.0


def header_hit_count(cells: List[str]) -> int:
    return sum(1 for c in cells if match_header(c)[0])


class DateParser:
    """Reads date/time text in the formats exports actually use. Remembers the last format that worked."""

    _TIMES = (" %H:%M:%S", " %H:%M", " %I:%M:%S %p", " %I:%M %p", "T%H:%M:%S", "T%H:%M")
    _COMMON = ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %b %y", "%d/%b/%Y",
               "%b %d, %Y", "%d-%B-%Y", "%d %B %Y", "%B %d, %Y")
    _DMY = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y")
    _MDY = ("%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y", "%m/%d/%y", "%m-%d-%y", "%m.%d.%y")
    _TIME_ONLY = ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I %p")

    def __init__(self, date_order: str = "DMY"):
        dates = self._COMMON + (self._MDY if str(date_order).upper() == "MDY" else self._DMY)
        self._formats = [d + t for d in dates for t in self._TIMES] + list(dates)
        self._last_full: Optional[str] = None
        self._last_time: Optional[str] = None

    def parse(self, value: str) -> Tuple[Optional[date], Optional[time]]:
        """Return (date, time); either part may be None. Raises ValueError if unreadable."""
        text = re.sub(r"\s+", " ", str(value).strip())
        number = self._as_number(text)
        if number is not None:
            return self._from_excel_number(number, value)
        if ":" in text:  # fractions of a second: 09:00:00.000
            text = re.sub(r"\.\d+$", "", text)

        for fmt in filter(None, (self._last_time, *self._TIME_ONLY)):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            self._last_time = fmt
            return None, parsed.time()

        for fmt in filter(None, (self._last_full, *self._formats)):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            self._last_full = fmt
            return self._split(parsed, "%H" in fmt or "%I" in fmt)
        raise ValueError(f"Could not read date/time '{value}'")

    @staticmethod
    def _split(parsed: datetime, has_time: bool):
        # Excel stores a bare time as an 1899/1900 date.
        if parsed.year <= 1900:
            return None, parsed.time()
        return parsed.date(), parsed.time() if has_time else None

    @staticmethod
    def _as_number(text: str) -> Optional[float]:
        return float(text) if re.fullmatch(r"\d+\.\d+|\d{5}", text) else None

    @staticmethod
    def _from_excel_number(number: float, original):
        whole = int(number)
        seconds = round((number - whole) * 86400)
        clock = time(seconds // 3600 % 24, seconds % 3600 // 60, seconds % 60)
        if whole == 0:
            return None, clock
        if 20000 <= whole <= 80000:  # Excel serial date (1954-2119)
            day = date.fromordinal(date(1899, 12, 30).toordinal() + whole)
            return day, clock if seconds else None
        raise ValueError(f"Could not read date/time '{original}'")


def _kind(value: str, parser: DateParser) -> Optional[str]:
    try:
        day, clock = parser.parse(value)
    except ValueError:
        return None
    if day and clock:
        return "datetime"
    return "date" if day else "time"


def looks_like_data(cell: str) -> bool:
    """True when a cell looks like a value (number or date) rather than a header word."""
    text = cell.strip()
    if re.fullmatch(r"[\d\s.,:/\-]+", text):
        return True
    if not re.search(r"\d", text):
        return False
    return _kind(text, DateParser()) is not None


def day_number(header: str) -> Optional[int]:
    """Day of month if the header is a matrix day column (1, 01, D5, Mon 3, 3-Jan...)."""
    key = normalize(re.sub(r"\.0$", "", str(header).strip()))
    patterns = (r"(\d{1,2})", r"(?:day|d) ?(\d{1,2})", rf"(?:{_DAY_NAME_RE})[a-z]* ?(\d{{1,2}})",
                rf"(\d{{1,2}}) ?(?:{_DAY_NAME_RE})[a-z]*", rf"(\d{{1,2}}) ?(?:{_MONTH_RE})[a-z]*(?: \d{{2,4}})?",
                rf"(?:{_MONTH_RE})[a-z]* ?(\d{{1,2}})")
    for pattern in patterns:
        found = re.fullmatch(pattern, key)
        if found and 1 <= int(found.group(1)) <= 31:
            return int(found.group(1))
    return None


def full_date_header(header: str, date_order: str = "DMY") -> Optional[date]:
    """The exact date in a header such as 2025-01-05, or None."""
    if not re.search(r"\d{4}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2}", str(header)):
        return None
    try:
        return DateParser(date_order).parse(header)[0]
    except ValueError:
        return None


def is_day_header(header: str, date_order: str = "DMY") -> bool:
    return day_number(header) is not None or full_date_header(header, date_order) is not None


def day_run_length(cells: List[str]) -> int:
    return sum(1 for c in cells if is_day_header(c))


def detect_period(*texts: str) -> Optional[str]:
    """Find a month such as 'January 2025' or '2025-01' in titles or a file name. Returns YYYY-MM."""
    for text in texts:
        low = str(text or "").lower()
        # Not \b: an underscore counts as a word character, and file names use them.
        found = re.search(rf"(?<![a-z])({_MONTH_RE})[a-z]*[\s\-_,']*(20\d{{2}})(?!\d)", low)
        if found:
            return f"{found.group(2)}-{_MONTHS.index(found.group(1)) + 1:02d}"
        found = re.search(r"(?<!\d)(20\d{2})[\-_/.](0[1-9]|1[0-2])(?!\d)", low)
        if found:
            return f"{found.group(1)}-{found.group(2)}"
    return None


def suggest_columns(headers: List[str], samples: Dict[str, List[str]], date_order: str = "DMY"
                    ) -> Dict[str, Tuple[str, float]]:
    """Map each header to (target, confidence). Each field is used once; the rest stay as extra data."""
    matrix = sum(1 for h in headers if is_day_header(h, date_order)) >= 7
    result: Dict[str, Tuple[str, float]] = {}
    candidates = []
    for header in headers:
        if matrix and is_day_header(header, date_order):
            result[header] = (DAY, 1.0)
            continue
        field, confidence = match_header(header)
        if field:
            candidates.append((header, _refine_by_values(field, samples.get(header, []), date_order), confidence))
        else:
            result[header] = (EXTRA, 0.0)

    taken = set()
    for header, field, confidence in sorted(candidates, key=lambda c: -c[2]):
        if field in taken:
            result[header] = (EXTRA, 0.0)
        else:
            taken.add(field)
            result[header] = (field, confidence)

    # A daily sheet's date column may hold full timestamps; it is still the day of that row.
    if taken & {"time_in", "time_out"} and "punch_datetime" in taken and "date" not in taken:
        for header, (field, confidence) in result.items():
            if field == "punch_datetime":
                result[header] = ("date", confidence)
    return {h: result[h] for h in headers}


def _refine_by_values(field: str, samples: List[str], date_order: str) -> str:
    """The header can mislead: a 'Date' column may hold full timestamps, a 'Status' column P/A marks."""
    values = [s for s in samples if s]
    if not values:
        return field
    if field in ("punch_datetime", "date", "time"):
        parser = DateParser(date_order)
        kinds = {_kind(v, parser) for v in values}
        if kinds == {"datetime"}:
            return "punch_datetime"
        if kinds == {"date"}:
            return "date"
        if kinds == {"time"}:
            return "time"
    if field == "status" and not all(_is_in_out(v) for v in values):
        return "day_status"
    return field


_IN_WORDS = {"in", "i", "c in", "check in", "checkin", "clock in", "on duty", "duty on"}
_OUT_WORDS = {"out", "o", "c out", "check out", "checkout", "clock out", "off duty", "duty off"}


def _is_in_out(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.0)?", value.strip())) or normalize(value) in _IN_WORDS | _OUT_WORDS


def in_out_code(value: str) -> Optional[int]:
    """0 = in, 1 = out, matching the device convention. None when it is not an in/out word."""
    key = normalize(value)
    if key in _IN_WORDS:
        return 0
    if key in _OUT_WORDS:
        return 1
    return None


def detect_shape(targets: Dict[str, str]) -> str:
    used = set(targets.values())
    if DAY in used:
        return MATRIX
    if used & {"time_in", "time_out"} or ("date" in used and "day_status" in used and "time" not in used):
        return DAILY
    return PUNCH_LOG


def required_problem(shape: str, targets: Dict[str, str], has_day_columns: bool) -> Optional[str]:
    """What is missing for this shape, in plain words, or None."""
    used = set(targets.values())
    if "employee_code" not in used:
        return "Choose which column is the Employee code."
    if shape == PUNCH_LOG:
        if "punch_datetime" not in used and not {"date", "time"} <= used:
            return "Choose the Date and time column (or one Date column and one Time column)."
    elif shape == DAILY:
        if "date" not in used:
            return "Choose the Date column."
        if not used & {"time_in", "time_out", "day_status"}:
            return "Choose at least one of Time in, Time out or Day status."
    elif shape == MATRIX and not has_day_columns:
        return "No day columns (1, 2, 3...) were found in this file."
    return None


def header_signature(headers: List[str], date_order: str = "DMY") -> str:
    """Identifies a file layout; day columns are left out so February matches March."""
    names = sorted({normalize(h) for h in headers if not is_day_header(h, date_order)})
    return hashlib.sha1("|".join(names).encode("utf-8")).hexdigest()
