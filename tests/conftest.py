import os

# Point the app at a dedicated test database before any backend module is imported.
# Override via WHEREISIT_TEST_DATABASE_URL when running against a different host.
os.environ["DATABASE_URL"] = os.getenv(
    "WHEREISIT_TEST_DATABASE_URL",
    "mysql+pymysql://whereisit:whereisitpw@127.0.0.1:3306/whereisit_test",
)

import pytest
import pymysql
from fastapi.testclient import TestClient


_ROOT_CONN_KWARGS = {
    "host": os.getenv("WHEREISIT_TEST_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("WHEREISIT_TEST_DB_PORT", "3306")),
    "user": os.getenv("WHEREISIT_TEST_DB_ROOT_USER", "root"),
    "password": os.getenv("WHEREISIT_TEST_DB_ROOT_PASSWORD", "rootpw"),
}
_TEST_DB = os.getenv("WHEREISIT_TEST_DB_NAME", "whereisit_test")
_APP_USER = os.getenv("WHEREISIT_TEST_DB_APP_USER", "whereisit")


def _run_root(*statements: str) -> None:
    cn = pymysql.connect(**_ROOT_CONN_KWARGS)
    try:
        with cn.cursor() as cur:
            for sql in statements:
                cur.execute(sql)
        cn.commit()
    finally:
        cn.close()


@pytest.fixture(scope="session")
def _test_database():
    _run_root(
        f"CREATE DATABASE IF NOT EXISTS `{_TEST_DB}`",
        f"GRANT ALL PRIVILEGES ON `{_TEST_DB}`.* TO '{_APP_USER}'@'%'",
        "FLUSH PRIVILEGES",
    )
    yield
    _run_root(f"DROP DATABASE IF EXISTS `{_TEST_DB}`")


@pytest.fixture(scope="session")
def client(_test_database):
    from backend.app.main import app

    with TestClient(app) as c:
        yield c
