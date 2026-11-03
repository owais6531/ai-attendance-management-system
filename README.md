# AI Attendance Management System

**Open-source attendance & HR analytics in Python (FastAPI).**
Upload biometric device exports (ZKTeco and similar) or Excel/CSV sheets, validate every row, store them
safely, and query them over a REST API. Runs on SQLite with zero setup, on MySQL/PostgreSQL, on Docker, or on
cheap **cPanel shared hosting**. AI features run **100% locally and free with [Ollama](https://ollama.com)**
(no paid API keys, no data leaves your server) — see the [roadmap](#roadmap).

[![CI](https://github.com/owais6531/ai-attendance-management-system/actions/workflows/ci.yml/badge.svg)](https://github.com/owais6531/ai-attendance-management-system/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-009688)
![DB](https://img.shields.io/badge/DB-SQLite%20%7C%20MySQL%20%7C%20PostgreSQL-informational)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Why this exists

Most small and mid-size companies already own a biometric machine, but its desktop software is tied to one
brand, has fixed reports, and doesn't work across branches. Cloud HR apps charge per user per month in USD.
So HR ends up doing month-end attendance by hand in Excel.

This project takes the files you **already have**, whatever device or sheet they come from, and turns them
into clean, queryable attendance data you own, on hosting you already pay for.

## Features (v0.2)

- **Drag-and-drop upload** of `.xlsx`, `.xls`, `.csv`, including UTF-16 / tab-separated device exports
- **Per-row validation** with exact Excel row numbers and clear messages, plus **downloadable error CSV**
- **Duplicate-safe re-uploads**: the same punch (employee code + time) is never stored twice
- **Check-only (dry run)** mode to validate a file without saving
- **Day-first or month-first dates** (`03/04/2025`), chosen per upload
- **Employee codes keep leading zeros** (`0012` ≠ `12`)
- **All-or-nothing saves**: if the database fails you get an error, never a fake "success"
- **REST API** with filters by employee, batch and date range; Swagger docs at `/docs`
- **SQLite / MySQL / PostgreSQL** via one `DATABASE_URL`, with automatic **Alembic migrations**
- **cPanel shared hosting** support (Passenger WSGI), plus Docker
- Optional API-key protection, upload size limit, dark mode UI
- **Fake demo-data generator**: no real employee data anywhere in this repo

## Quick start (60 seconds, no database setup)

```bash
git clone https://github.com/owais6531/ai-attendance-management-system.git
cd ai-attendance-management-system
python -m venv venv && venv\Scripts\activate      # Windows
# source venv/bin/activate                        # macOS / Linux
pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:8000 and upload `sample_data/demo_punches_2025-01.csv` (40 fake employees, one month).
Data is stored in `data/attendance.db` (SQLite). Copy `.env.example` to `.env` to change anything.

**Docker (with PostgreSQL):**

```bash
cp .env.example .env    # set DB_PASSWORD
docker compose up --build
```

**Shared hosting (cPanel):** see [docs/deploy-shared-hosting.md](docs/deploy-shared-hosting.md).

## File format

Columns: `No, DN, UID, Name, Status, Action, APB, JobCode, DateTime` (the common biometric export layout).
Download a ready template from the app or `GET /upload/template`. Generate more fake data with:

```bash
python scripts/generate_demo_data.py --employees 120 --month 2025-03
```

> Flexible column mapping (any file, 2 to 100+ columns) is next on the roadmap.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/upload/attendance` | Upload a file (`file`, optional `date_order=DMY\|MDY`, `dry_run=true`) |
| GET | `/upload/template` | Excel template |
| GET | `/api/database/attendance/records` | Punches; filters `uid`, `batch_id`, `date_from`, `date_to`, paging |
| GET | `/api/database/attendance/records/count` | Count with the same filters |
| GET | `/api/database/attendance/records/{id}` | One punch |
| GET | `/api/database/batches` · `/batches/{id}` · `/batches/{id}/records` | Upload history |
| GET | `/health` · `/api/database/health` | Health checks |

Status codes: `400` bad file · `401` API key · `413` too large · `503` database down (nothing saved).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite `./data/attendance.db` | `mysql+pymysql://…` or `postgresql://…` |
| `AUTO_MIGRATE` | `True` | Run migrations on startup |
| `MAX_UPLOAD_MB` | `20` | Upload size limit |
| `API_KEY` | empty | If set, required as `X-API-Key` |
| `APP_NAME` | AI Attendance Management System | Shown in the UI |

## Roadmap

- [x] **v0.2** Reliable upload: validation, dedup, dry run, migrations, SQLite/MySQL/PostgreSQL, shared hosting
- [ ] **v0.3** Flexible import: any file with 2 to 100+ columns, column-mapping wizard, saved import profiles,
      monthly-matrix sheets, **direct ZKTeco device sync**
- [ ] **v0.4** Attendance engine (shifts, late, overtime, half-day, holidays, Ramadan timings), report builder,
      Excel/PDF export, dashboard, user logins & roles
- [ ] **v0.5** **Local AI with Ollama** (free, private):
  - AI column mapping for messy files
  - "Chat with your attendance": plain-language questions become reports
  - Photo/scan of a paper register into rows (local vision model)
  - **MCP server** so Claude Desktop / Cursor / other MCP clients can query attendance
  - Monthly HR summary, anomaly flags (buddy punching), warning-letter drafts with human approval
- [ ] **v1.0** Webhooks, payroll export, docs site, PyPI packages

Have an idea or need a feature? [Open an issue](https://github.com/owais6531/ai-attendance-management-system/issues).

## Development

```bash
pip install -r requirements-dev.txt
pytest -v        # uses a throwaway SQLite database
```

Project layout: `config/` (DB, auth) · `models/` · `routes/` · `services/` · `migrations/` (Alembic) ·
`scripts/` · `static/` + `templates/` (UI) · `tests/` · `sample_data/` (fake).

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Need a custom version?

I build attendance, HR, payroll and tax-automation tools for businesses: custom import formats, device
integration, reports, on-premise AI, and hosting setup.

- **Email:** [mmowaisq@gmail.com](mailto:mmowaisq@gmail.com)
- **Website:** [qbiztax.com](https://qbiztax.com)
- **GitHub:** [@owais6531](https://github.com/owais6531)

## License

MIT, see [LICENSE](LICENSE).
