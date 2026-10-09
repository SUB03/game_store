"""Unit tests for payment_service's payment-lifecycle persistence (engine mocked)."""

import pytest

import payment_service.payments_store as payments_store


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _FakeConnection:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(self.rowcount)


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


async def test_mark_grant_requested_returns_true_on_change(fake_engine):
    fake_engine.rowcount = 1

    result = await payments_store.mark_grant_requested("pay-1")

    assert result is True


async def test_mark_grant_requested_returns_false_when_not_pending(fake_engine):
    fake_engine.rowcount = 0

    result = await payments_store.mark_grant_requested("pay-1")

    assert result is False
