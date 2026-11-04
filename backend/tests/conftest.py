import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def db_url():
    from app.config import Settings
    url = os.environ.get("TEST_DATABASE_URL") or Settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest.fixture(scope="session")
def db_engine(db_url):
    eng = create_engine(db_url)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS gt CASCADE"))
        # Only our own tables: on Postgres <= 14 the public schema belongs to postgres, not the app role.
        c.execute(text("""DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user LOOP
                EXECUTE format('DROP TABLE %I CASCADE', r.tablename);
            END LOOP; END $$"""))
    env = {**os.environ, "DATABASE_URL": db_url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env, cwd=BACKEND)
    yield eng
    eng.dispose()
