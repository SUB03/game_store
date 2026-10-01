"""Unit tests for the users_service cart RPCs (engine is mocked)."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from users_proto.users_service_pb2 import (
    AddGameToCartRequest,
    ClearCartRequest,
    GetCartRequest,
    RemoveGameFromCartRequest,
)

import users_service.main as users_main
from users_service.main import Settings, UsersServiceServicer


class FakeResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows if rows is not None else ([] if row is None else [row])
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        return self.results.pop(0)


class FakeEngine:
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


def _servicer(connection) -> UsersServiceServicer:
    servicer = UsersServiceServicer(
        Settings(SQLALCHEMY_URL="postgresql+psycopg://user:pw@localhost/db")
    )
    servicer.engine = FakeEngine(connection)
    return servicer


@pytest.fixture
def context():
    return MagicMock()  # the servicer never uses the ServicerContext


def _cart_row(appid: int, checkout_key: str = "cart-key") -> SimpleNamespace:
    return SimpleNamespace(username="alice", appid=appid, checkout_key=checkout_key)


# --- AddGameToCart ------------------------------------------------------------


async def test_add_to_cart_generates_checkout_key_for_empty_cart(
    context, monkeypatch
):
    generated = []

    def fake_uuid4():
        key = uuid.UUID("12345678-1234-5678-1234-567812345678")
        generated.append(key)
        return key

    monkeypatch.setattr(users_main.uuid, "uuid4", fake_uuid4)

    connection = FakeConnection(
        [
            FakeResult(rows=[]),  # select existing cart rows
            FakeResult(row=(42,)),  # INSERT ... RETURNING appid
        ]
    )
    servicer = _servicer(connection)

    response = await servicer.AddGameToCart(
        AddGameToCartRequest(username="alice", appid=42), context
    )

    assert response.appid == 42
    assert response.added is True
    assert generated == [uuid.UUID("12345678-1234-5678-1234-567812345678")]
    assert len(connection.statements) == 2
    assert "users_cart" in connection.statements[0]
    assert "INSERT INTO users_cart" in connection.statements[1]
    assert "ON CONFLICT DO NOTHING" in connection.statements[1]
    assert "RETURNING" in connection.statements[1]


async def test_add_to_cart_reuses_key_of_populated_cart(context, monkeypatch):
    def explode():
        raise AssertionError("uuid4 must not be called for a non-empty cart")

    monkeypatch.setattr(users_main.uuid, "uuid4", explode)

    connection = FakeConnection(
        [
            FakeResult(row=_cart_row(appid=1, checkout_key="existing-key")),
            FakeResult(row=(42,)),
        ]
    )
    servicer = _servicer(connection)

    response = await servicer.AddGameToCart(
        AddGameToCartRequest(username="alice", appid=42), context
    )

    assert response.appid == 42
    assert response.added is True
    assert len(connection.statements) == 2
    assert "ON CONFLICT DO NOTHING" in connection.statements[1]


async def test_add_to_cart_is_idempotent_for_a_game_already_in_cart(
    context, monkeypatch
):
    def explode():
        raise AssertionError("uuid4 must not be called when the add is a no-op")

    monkeypatch.setattr(users_main.uuid, "uuid4", explode)

    connection = FakeConnection(
        [
            FakeResult(row=_cart_row(appid=42, checkout_key="existing-key")),
            FakeResult(),  # ON CONFLICT DO NOTHING returned no row
        ]
    )
    servicer = _servicer(connection)

    response = await servicer.AddGameToCart(
        AddGameToCartRequest(username="alice", appid=42), context
    )

    assert response.appid == 42
    assert response.added is False
    # The (username, appid) primary key keeps the cart duplicate-free: the
    # repeat INSERT affects no row, which RETURNING reports as an empty result,
    # and the cart's checkout_key is left untouched.
    assert len(connection.statements) == 2
    assert "ON CONFLICT DO NOTHING" in connection.statements[1]
    assert "RETURNING" in connection.statements[1]


# --- RemoveGameFromCart -------------------------------------------------------


async def test_remove_from_cart_reports_removed_row(context):
    connection = FakeConnection([FakeResult(rowcount=1)])
    servicer = _servicer(connection)

    response = await servicer.RemoveGameFromCart(
        RemoveGameFromCartRequest(username="alice", appid=42), context
    )

    assert response.appid == 42
    assert response.removed is True
    assert "DELETE FROM users_cart" in connection.statements[0]


async def test_remove_from_cart_reports_missing_row(context):
    connection = FakeConnection([FakeResult(rowcount=0)])
    servicer = _servicer(connection)

    response = await servicer.RemoveGameFromCart(
        RemoveGameFromCartRequest(username="alice", appid=42), context
    )

    assert response.removed is False


# --- GetCart ------------------------------------------------------------------


async def test_get_cart_returns_appids_and_checkout_key(context):
    connection = FakeConnection(
        [
            FakeResult(
                rows=[
                    _cart_row(appid=1, checkout_key="key-1"),
                    _cart_row(appid=42, checkout_key="key-1"),
                ]
            )
        ]
    )
    servicer = _servicer(connection)

    response = await servicer.GetCart(GetCartRequest(username="alice"), context)

    assert sorted(response.appids) == [1, 42]
    assert response.checkout_key == "key-1"
    assert "users_cart" in connection.statements[0]


async def test_get_cart_empty_returns_empty_key(context):
    connection = FakeConnection([FakeResult(rows=[])])
    servicer = _servicer(connection)

    response = await servicer.GetCart(GetCartRequest(username="bob"), context)

    assert list(response.appids) == []
    assert response.checkout_key == ""


# --- ClearCart ----------------------------------------------------------------


async def test_clear_cart_counts_removed_rows(context):
    connection = FakeConnection([FakeResult(rowcount=3)])
    servicer = _servicer(connection)

    response = await servicer.ClearCart(ClearCartRequest(username="alice"), context)

    assert response.removed == 3
    assert "DELETE FROM users_cart" in connection.statements[0]


async def test_clear_cart_on_empty_cart_removes_nothing(context):
    connection = FakeConnection([FakeResult(rowcount=0)])
    servicer = _servicer(connection)

    response = await servicer.ClearCart(ClearCartRequest(username="bob"), context)

    assert response.removed == 0
