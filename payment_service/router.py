import ipaddress
import json
import logging
import uuid
from decimal import Decimal
from typing import Annotated

from aiokafka import AIOKafkaProducer
from fastapi import HTTPException, routing, status, Request, Cookie, Header, Path
from sqlalchemy import select, func

from payment_service.schemas import Price, CartItem, LibraryGame, CheckoutRequest
from payment_service.engine import engine
from payment_service.models import games_table, tags_table
from payment_service.payment_utils import (
    get_price,
    has_game,
    add_game,
    get_owned_games,
    add_game_to_cart,
    remove_game_from_cart,
    get_user_cart,
    clear_user_cart,
    make_payment_cart,
    get_payment_settings,
)
from payment_service.payments_store import create_payment, mark_grant_requested
from payment_service.jwt_utils import decode_jwt
from payment_service.token import Token

logger = logging.getLogger("payment_service")

router = routing.APIRouter(
    prefix="/payment",
    tags=["payment"]
)

def _claims_or_401(access_token: str | None) -> Token:
    """Validate the access_token cookie exactly like purchase_game does."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials",
        )
    return Token(**decode_jwt(access_token))

def _check_csrf(claims: Token, csrf: str | None) -> None:
    if not csrf or csrf != str(claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials",
        )

@router.get("/cart")
async def get_cart(access_token: Annotated[str | None, Cookie()] = None):
    claims = _claims_or_401(access_token)

    appids = await get_user_cart(username=claims.sub)
    if not appids:
        return {"results": []}

    owned = set(await get_owned_games(username=claims.sub))
    payable = [appid for appid in appids if appid not in owned]
    if not payable:
        return {"results": []}

    stmt = (
        select(games_table, func.array_agg(tags_table.c.tags).label("tags"))
        .join(tags_table, tags_table.c.appid == games_table.c.appid, isouter=True)
        .where(
            games_table.c.appid.in_(payable),
            games_table.c.price > 0,
        )
        .group_by(games_table.c.appid)
        .order_by(games_table.c.name)
    )

    async with engine.begin() as conn:
        result = await conn.execute(stmt)
        rows = result.mappings().all()

    return {"results": rows}


@router.post("/cart")
async def add_to_cart(
    cart_item: CartItem,
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    game_price = await get_price(cart_item.appid)
    if not game_price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="appid is not found",
        )
    price = Price(**game_price._asdict())
    if price.price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="free games are added to the library directly",
        )
    if await has_game(username=claims.sub, appid=cart_item.appid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already owned by the user",
        )

    return await add_game_to_cart(username=claims.sub, appid=cart_item.appid)


@router.post("/library")
async def add_to_library(
    library_game: LibraryGame,
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    game_price = await get_price(library_game.appid)
    if not game_price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="appid is not found",
        )
    price = Price(**game_price._asdict())
    if price.price > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="paid games must be added to the cart",
        )

    if await has_game(username=claims.sub, appid=library_game.appid):
        return {"appid": library_game.appid, "added": False}

    result = await add_game(username=claims.sub, appid=library_game.appid)
    return {"appid": result.get("appid", library_game.appid), "added": True}


@router.delete("/cart/{appid}")
async def remove_from_cart(
    appid: Annotated[int, Path(title="appid to remove from the cart")],
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    return await remove_game_from_cart(username=claims.sub, appid=appid)


@router.delete("/cart")
async def clear_cart(
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    removed = await clear_user_cart(username=claims.sub)
    return {"removed": removed}


@router.post("/checkout")
async def checkout(
    checkout_request: CheckoutRequest,
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    try:
        idempotency_key = uuid.UUID(checkout_request.idempotency_key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="idempotency_key must be a valid UUID",
        )

    appids = await get_user_cart(username=claims.sub)
    if not appids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cart is empty",
        )

    owned = set(await get_owned_games(username=claims.sub))
    payable = []
    for appid in appids:
        if appid in owned:
            await remove_game_from_cart(username=claims.sub, appid=appid)
        else:
            payable.append(appid)
    if not payable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cart is empty",
        )

    stmt = select(
        games_table.c.appid, games_table.c.price
    ).where(games_table.c.appid.in_(payable))
    async with engine.begin() as conn:
        result = await conn.execute(stmt)
        prices = {row.appid: row.price for row in result.fetchall()}

    to_pay: list[int] = []
    granted: list[int] = []
    total = Decimal("0")
    for appid in payable:
        if appid not in prices:
            await remove_game_from_cart(username=claims.sub, appid=appid)
            continue
        if prices[appid] <= 0:
            await add_game(username=claims.sub, appid=appid)
            await remove_game_from_cart(username=claims.sub, appid=appid)
            granted.append(appid)
            continue
        to_pay.append(appid)
        total += prices[appid]

    if not to_pay:
        if not granted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cart is empty",
            )
        return {"message": "added the games", "appids": granted}

    response = await make_payment_cart(
        username=claims.sub,
        appids=to_pay,
        price=f"{total:.2f}",
        idempotency_key=idempotency_key,
    )
    await create_payment(
        payment_id=response["payment_id"],
        username=claims.sub,
        appids=to_pay,
        idempotency_key=checkout_request.idempotency_key,
    )
    return {
        "payment_id": response["payment_id"],
        "confirmation_url": response["confirmation_url"],
    }


def _client_ip(request: Request) -> str:
    # Caddy is the only thing that can reach payment_service directly, and it
    # sets X-Forwarded-For; fall back to the socket peer for direct access
    # (e.g. local dev without the proxy in front).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _is_from_yookassa(ip: str) -> bool:
    settings = get_payment_settings()
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(
        addr in ipaddress.ip_network(cidr)
        for cidr in settings.yookassa_notification_cidrs
    )


@router.post("/notifications")
async def notifications(request: Request):
    logger.info("YooKassa notification received")

    settings = get_payment_settings()
    if settings.verify_webhook_ip and not _is_from_yookassa(_client_ip(request)):
        logger.warning(
            "YooKassa notification ignored: unexpected source IP %s",
            _client_ip(request),
        )
        return {"status": "OK"}

    try:
        payload = await request.json()
        logger.info(f"yookassa payload: {payload}")
    except Exception:
        logger.warning(
            "YooKassa notification ignored: request body is not valid JSON",
            exc_info=True,
        )
        return {"status": "OK"}

    # capture=False means YooKassa authorizes the hold and reports
    # `payment.waiting_for_capture`; the grant saga captures (or cancels)
    # it once ownership has actually been granted.
    if payload.get("event") != "payment.waiting_for_capture":
        return {"status": "OK"}

    obj = payload.get("object")
    if not isinstance(obj, dict):
        return {"status": "OK"}

    payment_id = obj.get("id")
    if not payment_id:
        return {"status": "OK"}

    # The request body is attacker-controlled (the webhook endpoint is
    # public) - only the payment_id is used to look up what to grant.
    # username/appids always come from our own `payment_payments` row,
    # written at checkout time by the authenticated user, never from this
    # body's metadata. mark_grant_requested also dedupes a webhook YooKassa
    # redelivers: only the first delivery for a given payment_id is still
    # `pending` and gets a row back.
    payment = await mark_grant_requested(payment_id)
    if payment is None:
        return {"status": "OK"}

    message = {
        "payment_id": payment_id,
        "username": payment.username,
        "appids": list(payment.appids),
    }
    producer: AIOKafkaProducer = request.app.state.producer
    await producer.send_and_wait(
        settings.grant_requests_topic,
        json.dumps(message).encode("utf-8"),
    )

    return {"status": "OK"}

