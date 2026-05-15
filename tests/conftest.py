import os
from pathlib import Path

# Point the app at a dedicated test database before any backend module is imported.
# Override via WHEREISIT_TEST_DATABASE_URL when running against a different host.
os.environ["DATABASE_URL"] = os.getenv(
    "WHEREISIT_TEST_DATABASE_URL",
    "mysql+pymysql://whereisit:whereisitpw@127.0.0.1:3306/whereisit_test",
)

import pytest
import pymysql
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


_ROOT_CONN_KWARGS = {
    "host": os.getenv("WHEREISIT_TEST_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("WHEREISIT_TEST_DB_PORT", "3306")),
    "user": os.getenv("WHEREISIT_TEST_DB_ROOT_USER", "root"),
    "password": os.getenv("WHEREISIT_TEST_DB_ROOT_PASSWORD", "rootpw"),
}
_TEST_DB = os.getenv("WHEREISIT_TEST_DB_NAME", "whereisit_test")
_APP_USER = os.getenv("WHEREISIT_TEST_DB_APP_USER", "whereisit")
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_root(*statements: str) -> None:
    cn = pymysql.connect(**_ROOT_CONN_KWARGS)
    try:
        with cn.cursor() as cur:
            for sql in statements:
                cur.execute(sql)
        cn.commit()
    finally:
        cn.close()


def _apply_migrations() -> None:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def _test_database():
    _run_root(
        f"CREATE DATABASE IF NOT EXISTS `{_TEST_DB}`",
        f"GRANT ALL PRIVILEGES ON `{_TEST_DB}`.* TO '{_APP_USER}'@'%'",
        "FLUSH PRIVILEGES",
    )
    _apply_migrations()
    yield
    _run_root(f"DROP DATABASE IF EXISTS `{_TEST_DB}`")


@pytest.fixture(scope="session")
def client(_test_database):
    from backend.app.main import app

    with TestClient(app) as c:
        yield c
