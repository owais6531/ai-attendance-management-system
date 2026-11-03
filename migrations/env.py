import os
import sys

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import Base, engine as app_engine  # noqa: E402
import models.db_models  # noqa: E402,F401  (registers tables on Base)

target_metadata = Base.metadata


def run_migrations_online():
    engine = context.config.attributes.get("engine", app_engine)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
