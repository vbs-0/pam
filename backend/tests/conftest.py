import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest.fixture(scope="session")
def db_engine(db_url):
    eng = create_engine(db_url)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS gt CASCADE"))
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    env = {**os.environ, "DATABASE_URL": db_url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env, cwd=BACKEND)
    yield eng
    eng.dispose()
