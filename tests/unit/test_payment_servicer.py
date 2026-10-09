"""Unit tests for the payment_service YooKassa helpers (YooKassa is mocked)."""

import uuid
from types import SimpleNamespace

import pytest

import payment_service.payment_utils as payment_utils
from payment_service.main_settings import Settings


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
    monkeypatch.setattr(payment_utils, "YooKassaClient", FakeYooKassaClient)
    return FakeYooKassaClient


@pytest.fixture
def settings():
    return Settings()


# --- cart checkout payments ---------------------------------------------------


async def test_cart_payment_describes_all_games_and_returns_to_profile(
    settings, fake_yookassa
):
    await payment_utils.make_payment_cart(
        username="alice", appids=[1, 2], price="14.99", idempotency_key=None
    )

    request = fake_yookassa.created_requests[0]
    assert request.description == "Purchase of 2 games by alice"
    assert request.metadata == {
        "username": "alice",
        "appids": "1,2",
    }
    assert request.confirmation.return_url == f"{settings.frontend_url}/profile"
    assert request.amount.value == "14.99"


async def test_cart_payment_forwards_the_client_idempotency_key(
    settings, fake_yookassa
):
    key = uuid.UUID("12345678-1234-5678-1234-567812345678")
    await payment_utils.make_payment_cart(
        username="alice", appids=[1, 2], price="14.99", idempotency_key=key
    )

    # a retried checkout of the same cart must reuse the same client-supplied
    # key so it can never create a second charge
    assert fake_yookassa.idempotency_keys == [key]