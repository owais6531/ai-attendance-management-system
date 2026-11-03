"""Entry point for cPanel "Setup Python App" (Phusion Passenger, WSGI).

Passenger speaks WSGI while FastAPI is ASGI; a2wsgi bridges the two.
Set the application startup file to ``passenger_wsgi.py`` and the entry point to ``application``.
See docs/deploy-shared-hosting.md.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # so static/ and templates/ resolve

from a2wsgi import ASGIMiddleware  # noqa: E402

from config.database import run_migrations, test_connection  # noqa: E402
from main import app  # noqa: E402

# Passenger does not run ASGI lifespan events, so migrate here once per process start.
if os.getenv("AUTO_MIGRATE", "True").lower() == "true" and test_connection():
    run_migrations()

application = ASGIMiddleware(app)
