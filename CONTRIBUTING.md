# Contributing

Thanks for helping! Bug reports, device export samples (with **fake** data), docs and code are all welcome.

## Ground rules
- **Never commit real employee data**, CNIC/ID numbers, salaries or phone numbers. Use
  `scripts/generate_demo_data.py` or clearly fake values.
- **No paid API keys or secrets** in code, tests or issues. AI features use local Ollama models.
- One focused change per pull request, with a test.

## Setup
```bash
python -m venv venv && venv\Scripts\activate   # or: source venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
python main.py
```

## Database changes
Change `models/db_models.py`, then add a migration in `migrations/versions/` (copy the style of
`0002_punch_at.py`). Migrations must never delete user data and must work on SQLite, MySQL and PostgreSQL.

## Good first issues
Look for the `good first issue` label, e.g. a new date format, a new device export sample, UI text, docs.
