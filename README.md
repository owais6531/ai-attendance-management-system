# AI Attendance Management System

**Open-source attendance & HR analytics in Python (FastAPI).**
Import **any** biometric export (ZKTeco and similar) or Excel/CSV sheet, from 2 columns to 100+. Match the columns
once, validate every row, store it safely, and query it over a REST API. Runs on SQLite with zero setup, on MySQL/PostgreSQL, on Docker, or on
cheap **cPanel shared hosting**. AI is optional: run it **free and locally with [Ollama](https://ollama.com)**, or use your own API key.
The app works fully without either.

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

## Features (v0.3)

- **Flexible import wizard**: any file with 2 to 100+ columns. Only employee code and date/time are required;
  every other column is kept as extra data, so nothing is lost
- **Three file layouts**: punch log, daily sheet (in/out columns), monthly sheet (one column per day)
- **Finds the real heading row**, skipping company names and title rows; handles several sheets in one workbook
- **English and Urdu headings** matched automatically, including common typos
- **Saved mappings**: a file with the same columns next month is recognised and mapped for you
- **Optional AI suggestions** for headings the rules cannot place: local Ollama or your own API key. AI only suggests, you confirm
- **Specs check** in the app tells you whether a computer can run local AI
- **Drag-and-drop** `.xlsx`, `.xls`, `.csv`, including UTF-16 / tab-separated device exports
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

## File layouts

| Layout | Looks like | Minimum columns |
|---|---|---|
| **Punch log** | One row per punch | Employee code + date-time (or date and time separately) |
| **Daily sheet** | One row per employee per day | Employee code + date + time in, time out or a day status |
| **Monthly sheet** | One row per employee, one column per day | Employee code + day columns (`1`…`31`, `Mon 3`, `3-Jan`, `2025-01-03`) |

Monthly cells can hold times (`09:00-17:00`, `9:00 AM 5:30 PM`) or marks (`P`, `A`, `Leave`). Marks are stored as a
day status with no clock time. A time-out earlier than the time-in is read as the next day (night shift), and the
result tells you how many rows this affected.

Try it with the fake files in [`sample_data/`](sample_data), or make more:

```bash
python scripts/generate_import_samples.py                         # one small file per layout
python scripts/generate_demo_data.py --employees 120 --month 2025-03
```

## AI (optional)

The app works fully without AI. Open **AI options** on the import page to see whether your computer can run it.

**Option 1: free, on your own computer.** Needs about 8 GB RAM, 6 GB free disk and 4 CPU cores. Install
[Ollama](https://ollama.com), then run `ollama pull llama3.2:3b`. **Suggest with AI** turns on by itself.

**Option 2: your own API key**, for computers below the minimum. Any OpenAI-compatible service works. Add to `.env`
and restart:

```env
AI_PROVIDER=api
AI_API_URL=https://api.openai.com/v1
AI_API_KEY=your-key-here
AI_API_MODEL=name-of-the-model
```

**What the AI sees:** only the headings the rules could not place, with up to three short sample values each. With
option 2 this goes to your provider, and the page says so. This project ships no key, and your `.env` is never
committed.

**What the AI can do:** only suggest. Its reply is checked against your file's columns and the app's field list, it
cannot overwrite a column already matched, and nothing is imported until you confirm. Every call is logged in the
`ai_usage` table.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/import/analyze` | Find headings, suggest a mapping and layout; saves nothing |
| POST | `/import/run` | Import with a confirmed mapping (`file`, `plan` JSON, `dry_run=true`) |
| GET · POST | `/import/profiles` | List or save mappings |
| DELETE | `/import/profiles/{id}` | Delete a saved mapping |
| GET | `/import/ai/status` · `/import/ai/setup` | AI status, specs check and setup details |
| POST | `/import/ai/suggest` | AI suggestions for unmatched columns |
| POST | `/upload/attendance` | Fixed 9-column upload, for existing integrations (`file`, optional `date_order=DMY\|MDY`, `dry_run=true`) |
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
| `AI_PROVIDER` | `ollama` | `ollama`, `api` or `off` |
| `OLLAMA_URL` | `http://localhost:11434` | Local AI server (optional) |
| `OLLAMA_TEXT_MODEL` | `llama3.2:3b` | Model for AI suggestions |
| `OLLAMA_TIMEOUT` | `120` | Seconds to wait for a suggestion |
| `AI_API_URL` · `AI_API_KEY` · `AI_API_MODEL` | empty | Your own OpenAI-compatible API (`https` required) |
| `AI_API_TIMEOUT` | `60` | Seconds to wait for the API |

## Roadmap

- [x] **v0.2** Reliable upload: validation, dedup, dry run, migrations, SQLite/MySQL/PostgreSQL, shared hosting
- [x] **v0.3** Flexible import: any file with 2 to 100+ columns, column-mapping wizard, saved mappings,
      monthly sheets, AI column suggestions (local Ollama or your own API key)
- [ ] **v0.3.x** **Direct ZKTeco device sync**
- [ ] **v0.4** Attendance engine (shifts, late, overtime, half-day, holidays, Ramadan timings), report builder,
      Excel/PDF export, dashboard, user logins & roles
- [ ] **v0.5** **More AI**, local or with your own key:
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
