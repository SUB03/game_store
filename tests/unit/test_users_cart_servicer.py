"""Unit tests for the users_service cart RPCs (engine is mocked)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from users_proto.users_service_pb2 import (
    AddGameToCartRequest,
    ClearCartRequest,
    GetCartRequest,
    RemoveGameFromCartRequest,
)

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


def _cart_row(appid: int) -> SimpleNamespace:
    return SimpleNamespace(username="alice", appid=appid)


# --- AddGameToCart ------------------------------------------------------------


async def test_add_to_cart_inserts_new_game(context):
    connection = FakeConnection([FakeResult(row=(42,))])  # INSERT ... RETURNING appid
    servicer = _servicer(connection)

    response = await servicer.AddGameToCart(
        AddGameToCartRequest(username="alice", appid=42), context
    )

    assert response.appid == 42
    assert response.added is True
    assert len(connection.statements) == 1
    assert "INSERT INTO users_cart" in connection.statements[0]
    assert "ON CONFLICT DO NOTHING" in connection.statements[0]
    assert "RETURNING" in connection.statements[0]


async def test_add_to_cart_is_idempotent_for_a_game_already_in_cart(context):
    connection = FakeConnection([FakeResult()])  # ON CONFLICT DO NOTHING returned no row
    servicer = _servicer(connection)

    response = await servicer.AddGameToCart(
        AddGameToCartRequest(username="alice", appid=42), context
    )

    assert response.appid == 42
    assert response.added is False
    # The (username, appid) primary key keeps the cart duplicate-free: the
    # repeat INSERT affects no row, which RETURNING reports as an empty result.
    assert len(connection.statements) == 1
    assert "ON CONFLICT DO NOTHING" in connection.statements[0]
    assert "RETURNING" in connection.statements[0]


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


async def test_get_cart_returns_appids(context):
    connection = FakeConnection(
        [FakeResult(rows=[_cart_row(appid=1), _cart_row(appid=42)])]
    )
    servicer = _servicer(connection)

    response = await servicer.GetCart(GetCartRequest(username="alice"), context)

    assert sorted(response.appids) == [1, 42]
    assert "users_cart" in connection.statements[0]


async def test_get_cart_empty_returns_no_appids(context):
    connection = FakeConnection([FakeResult(rows=[])])
    servicer = _servicer(connection)

    response = await servicer.GetCart(GetCartRequest(username="bob"), context)

    assert list(response.appids) == []


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
