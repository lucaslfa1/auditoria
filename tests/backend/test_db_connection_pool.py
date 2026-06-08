import os
import sys
from threading import BoundedSemaphore

import psycopg2
import pytest
from psycopg2.pool import PoolError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import connection  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False

    def execute(self, query):
        if self.conn.fail_validation:
            raise psycopg2.OperationalError("SSL connection has been closed unexpectedly")
        self.conn.executed.append(query)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, fail_validation=False):
        self.autocommit = True
        self.closed = False
        self.executed = []
        self.fail_validation = fail_validation
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rollbacks += 1


class FakePool:
    def __init__(self, connections):
        self.connections = list(connections)
        self.put_calls = []

    def getconn(self):
        return self.connections.pop(0)

    def putconn(self, conn, close=False):
        self.put_calls.append((conn, close))

    def closeall(self):
        pass


@pytest.fixture(autouse=True)
def reset_pool_state(monkeypatch):
    connection.close_all_pools()
    monkeypatch.delenv("DB_POOL_WAIT_SECONDS", raising=False)
    monkeypatch.delenv("DB_POOL_VALIDATE_ON_CHECKOUT", raising=False)
    yield
    connection.close_all_pools()


def test_pool_checkout_waits_instead_of_immediate_pool_error(monkeypatch):
    fake_pool = FakePool([FakeConnection(), FakeConnection()])
    monkeypatch.setattr(connection, "_db_pool", fake_pool)
    monkeypatch.setattr(connection, "_pool_maxconn", 1)
    monkeypatch.setattr(connection, "_pool_semaphore", BoundedSemaphore(1))
    monkeypatch.setenv("DB_POOL_WAIT_SECONDS", "0.01")

    first = connection._create_pg_connection()
    with pytest.raises(PoolError):
        connection._create_pg_connection()

    first.close()
    second = connection._create_pg_connection()
    second.close()

    assert len(fake_pool.put_calls) == 2
    assert fake_pool.put_calls[0][1] is False
    assert fake_pool.put_calls[1][1] is False


def test_pool_discards_stale_connection_on_checkout():
    stale = FakeConnection(fail_validation=True)
    fresh = FakeConnection()
    fake_pool = FakePool([stale, fresh])
    connection._db_pool = fake_pool
    connection._pool_maxconn = 1
    connection._pool_semaphore = BoundedSemaphore(1)

    checked_out = connection._create_pg_connection()
    checked_out.close()

    assert fake_pool.put_calls[0] == (stale, True)
    assert fake_pool.put_calls[1] == (fresh, False)
    assert fresh.executed == [
        "SELECT 1",
        "SET SESSION statement_timeout = 120000",
        "SET SESSION lock_timeout = 10000",
        "SET SESSION idle_in_transaction_session_timeout = 60000",
    ]


def test_pool_initialization_sets_connect_timeout_and_application_name(monkeypatch):
    captured = {}

    class DummyPool:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

        def closeall(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@example.test:5432/auditoria")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("DB_APPLICATION_NAME", "audit-test")
    monkeypatch.setattr(connection, "ThreadedConnectionPool", DummyPool)

    connection._init_pool()

    assert captured["kwargs"]["connect_timeout"] == 7
    assert captured["kwargs"]["application_name"] == "audit-test"
    assert captured["kwargs"]["cursor_factory"] is connection.DictCursor
