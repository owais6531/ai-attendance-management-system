"""Turn a mapped table (any of the three file shapes) into validated attendance records."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from models.attendance_models import DB_INT_MAX, AttendanceRecord, RowError
from services.column_mapping import (
    DAILY, DAY, EXTRA, IGNORE, MATRIX, PUNCH_LOG, DateParser, day_number, full_date_header, in_out_code,
    is_day_header, required_problem,
)
from services.file_reader import Table
from services.file_upload_service import UploadError

_TIME_IN_CELL = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?")
_BLANK_MARKS = {"-", "--", "---", "n/a", "na", "nil", "null"}


@dataclass
class ImportResult:
    records: List[AttendanceRecord] = field(default_factory=list)
    errors: List[RowError] = field(default_factory=list)
    skipped_blank: int = 0
    warnings: List[str] = field(default_factory=list)


def parse_period(period: Optional[str]) -> Optional[Tuple[int, int]]:
    if not period:
        return None
    found = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", period.strip())
    if not found:
        raise UploadError("Month must look like 2025-01")
    return int(found.group(1)), int(found.group(2))


def _code(value: str) -> str:
    text = value.strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


class Transformer:
    def __init__(self, table: Table, shape: str, columns: Dict[str, str], date_order: str = "DMY",
                 period: Optional[str] = None):
        self.table, self.shape, self.date_order = table, shape, date_order
        self.parser = DateParser(date_order)
        self.period = parse_period(period)
        self.result = ImportResult()
        self.night_shifts = 0
        self.invalid_days: set = set()

        self.position = {h: i for i, h in enumerate(table.headers)}
        self.field_of: Dict[str, str] = {}
        self.day_columns: List[str] = []
        for header in table.headers:
            target = columns.get(header)
            if target is None:
                # A column the mapping does not mention is kept, never dropped.
                target = DAY if shape == MATRIX and is_day_header(header, date_order) else EXTRA
            if target == DAY:
                if shape == MATRIX:
                    self.day_columns.append(header)
                else:
                    target = EXTRA
            self.field_of[header] = target
        self._check_mapping()
        self.column_of = {t: h for h, t in self.field_of.items() if t not in (EXTRA, IGNORE, DAY)}

    def _check_mapping(self) -> None:
        used = [t for t in self.field_of.values() if t not in (EXTRA, IGNORE, DAY)]
        repeated = sorted({t for t in used if used.count(t) > 1})
        if repeated:
            raise UploadError(f"These fields are chosen for more than one column: {', '.join(repeated)}")
        problem = required_problem(self.shape, self.field_of, bool(self.day_columns))
        if problem:
            raise UploadError(problem)
        if self.shape == MATRIX and not self.period:
            if any(full_date_header(h, self.date_order) is None for h in self.day_columns):
                raise UploadError("Choose the month of this file: its day columns do not include a month and year.")

    # ---------- helpers ----------
    def _cell(self, cells: List[str], target: str) -> str:
        header = self.column_of.get(target)
        return cells[self.position[header]] if header else ""

    def _as_dict(self, cells: List[str]) -> Dict[str, Any]:
        return {h: cells[i] for h, i in self.position.items() if cells[i]}

    def _extra(self, cells: List[str]) -> Dict[str, str]:
        return {h: cells[self.position[h]] for h, t in self.field_of.items()
                if t == EXTRA and cells[self.position[h]]}

    def _optional_int(self, cells: List[str], target: str, extra: Dict[str, str]) -> Optional[int]:
        raw = self._cell(cells, target)
        if not raw:
            return None
        try:
            number = int(float(raw))
            if abs(number) <= DB_INT_MAX:
                return number
        except (ValueError, OverflowError):
            pass
        # Never lose a whole row because of an optional column: keep the original text.
        extra[self.column_of[target]] = raw
        return None

    def _status(self, cells: List[str], extra: Dict[str, str]) -> Optional[int]:
        raw = self._cell(cells, "status")
        word = in_out_code(raw) if raw else None
        return word if word is not None else self._optional_int(cells, "status", extra)

    def _record(self, cells: List[str], when: datetime, status: Optional[int] = None,
                day_status: Optional[str] = None) -> AttendanceRecord:
        extra = self._extra(cells)
        if status is None:
            status = self._status(cells, extra)
        uid = _code(self._cell(cells, "employee_code"))
        if len(uid) > 50:
            raise ValueError(f"Employee code is too long ({len(uid)} characters, maximum 50)")
        if day_status and len(day_status) > 20:
            extra["day_status_full"] = day_status
            day_status = day_status[:20]
        return AttendanceRecord(
            no=self._optional_int(cells, "record_no", extra), dn=self._optional_int(cells, "device_no", extra),
            uid=uid, name=self._cell(cells, "name")[:100], status=status,
            action=self._optional_int(cells, "action", extra), apb=self._optional_int(cells, "apb", extra),
            job_code=self._optional_int(cells, "job_code", extra), punch_at=when,
            date_time=when.strftime("%Y/%m/%d %H:%M:%S"), extra=extra, day_status=day_status,
        )

    def _is_repeated_header(self, cells: List[str]) -> bool:
        # Paged reports repeat the header row in the middle of the data.
        header = self.column_of["employee_code"]
        return cells[self.position[header]].strip().lower() == header.strip().lower()

    # ---------- shapes ----------
    def run(self) -> ImportResult:
        handler = {PUNCH_LOG: self._punch_row, DAILY: self._daily_row, MATRIX: self._matrix_row}[self.shape]
        for number, cells in self.table.rows:
            if self._is_repeated_header(cells):
                continue
            try:
                if not self._cell(cells, "employee_code"):
                    raise ValueError("Employee code is empty")
                handler(cells, number)
            except Exception as e:  # noqa: BLE001 - collect every row problem
                message = str(e).strip().splitlines()[0][:300]
                self.result.errors.append(RowError(row=number, error=message, data=self._as_dict(cells)))
        self._finish_warnings()
        return self.result

    def _finish_warnings(self) -> None:
        if self.night_shifts:
            self.result.warnings.append(
                f"{self.night_shifts} time-out values were earlier than time-in, so they were read as the next "
                "day (night shift). Check them if your office has no night shift.")
        if self.invalid_days:
            days = ", ".join(sorted(self.invalid_days))
            self.result.warnings.append(f"These day columns do not exist in the chosen month and were ignored: {days}")

    def _punch_row(self, cells: List[str], number: int) -> None:
        when = self._read_when(cells)
        day_status = self._cell(cells, "day_status") or None
        self.result.records.append(self._record(cells, when, day_status=day_status))

    def _read_when(self, cells: List[str]) -> datetime:
        raw = self._cell(cells, "punch_datetime")
        if raw:
            day, clock = self.parser.parse(raw)
            if day is None:
                if not self._cell(cells, "date"):
                    raise ValueError(f"'{raw}' has a time but no date")
                day = self._date_cell(cells)
            return datetime.combine(day, clock or time.min)
        if "punch_datetime" in self.column_of and "date" not in self.column_of:
            raise ValueError("Date and time is empty")
        day = self._date_cell(cells)
        clock_raw = self._cell(cells, "time")
        if not clock_raw:
            raise ValueError("Time is empty")
        return datetime.combine(day, self._time_of(clock_raw))

    def _date_cell(self, cells: List[str]) -> date:
        raw = self._cell(cells, "date")
        if not raw:
            raise ValueError("Date is empty")
        day = self.parser.parse(raw)[0]
        if day is None:
            raise ValueError(f"'{raw}' is not a date")
        return day

    def _time_of(self, raw: str) -> time:
        clock = self.parser.parse(raw)[1]
        if clock is None:
            raise ValueError(f"'{raw}' is not a time")
        return clock

    def _daily_row(self, cells: List[str], number: int) -> None:
        raw_in, raw_out = self._cell(cells, "time_in"), self._cell(cells, "time_out")
        day_status = self._cell(cells, "day_status") or None
        day = self._date_cell(cells)
        raw_in = "" if raw_in.lower() in _BLANK_MARKS else raw_in
        raw_out = "" if raw_out.lower() in _BLANK_MARKS else raw_out
        if not raw_in and not raw_out and not day_status:
            self.result.skipped_blank += 1
            return
        if not raw_in and not raw_out:
            when = datetime.combine(day, time.min)
            self.result.records.append(self._record(cells, when, day_status=day_status))
            return
        self._add_in_out(cells, day, [raw_in, raw_out], day_status)

    def _add_in_out(self, cells: List[str], day: date, values: List[str], day_status: Optional[str]) -> None:
        """First value is time in, last is time out; anything between keeps no in/out code."""
        # Read everything first, so one bad value adds nothing for this row.
        pending = []
        previous = None
        shifted = 0
        last = len(values) - 1
        for index, raw in enumerate(values):
            if not raw:
                continue
            read_day, clock = self.parser.parse(raw)
            if clock is None:
                raise ValueError(f"'{raw}' is not a time")
            when = datetime.combine(read_day or day, clock)
            if previous and when == previous:
                continue  # the same punch read twice
            if previous and when < previous and read_day is None:
                when += timedelta(days=1)
                shifted += 1
            previous = when
            pending.append((when, 0 if index == 0 else 1 if index == last else None))
        records = [self._record(cells, when, status=status, day_status=day_status) for when, status in pending]
        self.result.records.extend(records)
        self.night_shifts += shifted

    def _matrix_day(self, header: str) -> Optional[date]:
        exact = full_date_header(header, self.date_order)
        if exact:
            return exact
        year, month = self.period
        try:
            return date(year, month, day_number(header))
        except (ValueError, TypeError):
            return None

    def _matrix_row(self, cells: List[str], number: int) -> None:
        found_any = False
        for header in self.day_columns:
            value = cells[self.position[header]].strip()
            if not value or value.lower() in _BLANK_MARKS:
                continue
            day = self._matrix_day(header)
            if day is None:
                self.invalid_days.add(header)
                continue
            found_any = True
            try:
                times = _TIME_IN_CELL.findall(value)
                if times:
                    self._add_in_out(cells, day, times, None)
                else:
                    self.result.records.append(
                        self._record(cells, datetime.combine(day, time.min), day_status=value))
            except ValueError as e:
                self.result.errors.append(RowError(
                    row=number, error=f"Day '{header}': {str(e).splitlines()[0][:250]}", data=self._as_dict(cells)))
        if not found_any:
            self.result.skipped_blank += 1


def transform(table: Table, shape: str, columns: Dict[str, str], date_order: str = "DMY",
              period: Optional[str] = None) -> ImportResult:
    return Transformer(table, shape, columns, date_order, period).run()
