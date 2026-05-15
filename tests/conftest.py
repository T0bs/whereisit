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
from sqlalchemy import event
from sqlalchemy.orm import Session


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


@pytest.fixture(autouse=True)
def _isolated_db(_test_database):
    """Wrap each test in a transaction that's rolled back at the end.

    All sessions handed to the FastAPI app via `get_db` are bound to the same
    test-scoped connection. Handler commits land on a SAVEPOINT that's restarted
    after each commit, so the outer transaction stays open for the rollback.
    """
    from backend.app import database as db_module
    from backend.app.main import app

    connection = db_module.engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, autoflush=False, autocommit=False, future=True)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[db_module.get_db] = _override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(db_module.get_db, None)
        session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
