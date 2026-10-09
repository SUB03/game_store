import json
import logging
import uuid
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
    total = 0.0
    for appid in payable:
        if appid not in prices:
            await remove_game_from_cart(username=claims.sub, appid=appid)
            continue
        if float(prices[appid]) <= 0:
            await add_game(username=claims.sub, appid=appid)
            await remove_game_from_cart(username=claims.sub, appid=appid)
            granted.append(appid)
            continue
        to_pay.append(appid)
        total += float(prices[appid])

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


@router.post("/notifications")
async def notifications(request: Request):
    logger.info("YooKassa notification received")
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
    metadata = obj.get("metadata") or {}
    username = metadata.get("username")
    appids_raw = metadata.get("appids")

    if not username or not appids_raw:
        return {"status": "OK"}

    appids: list[int] = []
    for raw_appid in appids_raw.split(","):
        try:
            appids.append(int(raw_appid))
        except ValueError:
            continue
    if not appids:
        return {"status": "OK"}

    # Dedupe a webhook YooKassa redelivers: only the first delivery for a
    # given payment_id is still `pending` and gets to publish a grant request.
    if not await mark_grant_requested(payment_id):
        return {"status": "OK"}

    message = {"payment_id": payment_id, "username": username, "appids": appids}
    producer: AIOKafkaProducer = request.app.state.producer
    await producer.send_and_wait(
        get_payment_settings().grant_requests_topic,
        json.dumps(message).encode("utf-8"),
    )

    return {"status": "OK"}

