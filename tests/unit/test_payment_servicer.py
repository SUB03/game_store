"""Unit tests for the payment_service gRPC servicer (YooKassa is mocked)."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from payment_proto.payment_service_pb2 import MakePaymentRequest

import payment_service.main as payment_main
from payment_service.main import PaymentServiceServicer, Settings


class FakeYooKassaClient:
    """Stands in for async_yookassa.YooKassaClient."""

    created_requests = []
    idempotency_keys = []
    payment_id = "yk-payment-1"
    confirmation_url = "https://yookassa.example/confirm/1"

    def __init__(self, account_id=None, secret_key=None):
        self.account_id = account_id
        self.secret_key = secret_key
        self.payment = SimpleNamespace(create=self._create)

    async def _create(self, request, idempotency_key=None):
        FakeYooKassaClient.created_requests.append(request)
        FakeYooKassaClient.idempotency_keys.append(idempotency_key)
        return SimpleNamespace(
            id=FakeYooKassaClient.payment_id,
            confirmation=SimpleNamespace(
                confirmation_url=FakeYooKassaClient.confirmation_url
            ),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def fake_yookassa(monkeypatch):
    FakeYooKassaClient.created_requests.clear()
    FakeYooKassaClient.idempotency_keys.clear()
    monkeypatch.setattr(payment_main, "YooKassaClient", FakeYooKassaClient)
    return FakeYooKassaClient


@pytest.fixture
def servicer():
    return PaymentServiceServicer(Settings())


@pytest.fixture
def context():
    return MagicMock()


async def test_make_payment_returns_payment_id_and_confirmation_url(
    servicer, context
):
    response = await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="9.99"), context
    )
    assert response.payment_id == "yk-payment-1"
    assert response.confirmation_url == "https://yookassa.example/confirm/1"


async def test_make_payment_builds_amount_in_rub_and_redirect_confirmation(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="123.45"), context
    )

    assert len(fake_yookassa.created_requests) == 1
    request = fake_yookassa.created_requests[0]

    assert request.amount.value == "123.45"
    assert request.amount.currency == "RUB"
    assert request.confirmation.type == "redirect"


async def test_make_payment_uses_configured_shop_credentials(servicer, context):
    await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="1.00"), context
    )
    # Settings() reads SHOPID / UKASS_API_KEY from the environment
    assert servicer.settings.shopid
    assert servicer.settings.ukass_api_key


async def test_make_payment_attaches_metadata_for_webhook(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="9.99"), context
    )
    request = fake_yookassa.created_requests[0]
    # The store_service webhook reads these to grant ownership.
    assert request.metadata == {
        "username": "alice",
        "appid": "42",
        "appids": "42",
    }
    assert "42" in request.description


async def test_make_payment_return_url_points_at_profile(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="9.99"), context
    )
    request = fake_yookassa.created_requests[0]
    assert (
        request.confirmation.return_url
        == f"{servicer.settings.frontend_url}/app/42"
    )


# --- cart checkout payments ---------------------------------------------------


async def test_cart_payment_describes_all_games_and_returns_to_profile(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(
            username="alice",
            appid=1,
            price="14.99",
            appids=[1, 2],
        ),
        context,
    )

    request = fake_yookassa.created_requests[0]
    assert request.description == "Purchase of 2 games by alice"
    assert request.metadata == {
        "username": "alice",
        "appid": "1",
        "appids": "1,2",
    }
    assert request.confirmation.return_url == f"{servicer.settings.frontend_url}/profile"
    assert request.amount.value == "14.99"


async def test_cart_payment_forwards_the_cart_idempotency_key(
    servicer, context, fake_yookassa
):
    key = uuid.UUID("12345678-1234-5678-1234-567812345678")
    await servicer.MakePayment(
        MakePaymentRequest(
            username="alice",
            appid=1,
            price="14.99",
            appids=[1, 2],
            idempotency_key=str(key),
        ),
        context,
    )

    # a retried checkout of the same cart must reuse the same YooKassa
    # Idempotence-Key so it can never create a second charge
    assert fake_yookassa.idempotency_keys == [key]


async def test_single_game_payment_uses_legacy_appid_return_url(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="9.99"),
        context,
    )
    request = fake_yookassa.created_requests[0]
    assert request.confirmation.return_url == f"{servicer.settings.frontend_url}/app/42"
    assert request.description == "Purchase of app 42 by alice"


async def test_malformed_idempotency_key_falls_back_to_a_random_one(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(
            username="alice",
            appid=1,
            price="9.99",
            appids=[1],
            idempotency_key="not-a-uuid",
        ),
        context,
    )

    # None lets the library generate its own key instead of failing
    assert fake_yookassa.idempotency_keys == [None]


async def test_payment_without_idempotency_key_passes_none(
    servicer, context, fake_yookassa
):
    await servicer.MakePayment(
        MakePaymentRequest(username="alice", appid=42, price="9.99"), context
    )
    assert fake_yookassa.idempotency_keys == [None]