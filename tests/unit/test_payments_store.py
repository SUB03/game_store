"""Unit tests for payment_service's payment-lifecycle persistence (engine mocked)."""

from types import SimpleNamespace

import pytest

import payment_service.payments_store as payments_store


class _Result:
    def __init__(self, rowcount=0, row=None, rows=None):
        self.rowcount = rowcount
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, result=None):
        self.result = result if result is not None else _Result()
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return self.result


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        connection = self.connection

        class _Ctx:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


@pytest.fixture
def fake_engine(monkeypatch):
    connection = _FakeConnection()
    engine = _FakeEngine(connection)
    monkeypatch.setattr(payments_store, "engine", engine)
    return connection


async def test_create_payment_inserts_a_pending_row(fake_engine):
    await payments_store.create_payment(
        payment_id="pay-1",
        username="alice",
        appids=[1, 2],
        idempotency_key="12345678-1234-5678-1234-567812345678",
    )

    assert len(fake_engine.statements) == 1
    compiled = fake_engine.statements[0].compile()
    params = compiled.params
    assert params["payment_id"] == "pay-1"
    assert params["username"] == "alice"
    assert params["appids"] == [1, 2]
    # a retried checkout with the same idempotency key must not crash on
    # the duplicate payment_id - ON CONFLICT DO NOTHING is what makes that
    # idempotent instead of a 500.
    assert "ON CONFLICT" in str(fake_engine.statements[0])


async def test_mark_grant_requested_returns_the_trusted_row_on_success(fake_engine):
    fake_engine.result = _Result(row=SimpleNamespace(username="alice", appids=[1, 2]))

    result = await payments_store.mark_grant_requested("pay-1")

    assert result.username == "alice"
    assert result.appids == [1, 2]


async def test_mark_grant_requested_returns_none_when_not_pending(fake_engine):
    fake_engine.result = _Result(row=None)

    result = await payments_store.mark_grant_requested("pay-1")

    assert result is None


async def test_fetch_stuck_returns_matching_rows(fake_engine):
    rows = [SimpleNamespace(payment_id="pay-1", status="grant_requested", attempts=1)]
    fake_engine.result = _Result(rows=rows)

    result = await payments_store.fetch_stuck(grace_seconds=600, max_attempts=10)

    assert result == rows


async def test_bump_attempts_runs_an_update(fake_engine):
    await payments_store.bump_attempts("pay-1")

    assert len(fake_engine.statements) == 1
    assert "UPDATE payment_payments" in str(fake_engine.statements[0])


async def test_mark_granted_pending_capture_sets_status(fake_engine):
    await payments_store.mark_granted_pending_capture("pay-1")

    compiled = fake_engine.statements[0].compile()
    assert compiled.params["status"] == "granted_pending_capture"
