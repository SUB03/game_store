import logging
from typing import Annotated

from fastapi import HTTPException, routing, status, Request, Cookie, Header, Path
from sqlalchemy import select, func

from payment_service.schemas import Price, PurchaseGame, CartItem, LibraryGame
from payment_service.engine import engine
from payment_service.models import games_table, tags_table
from payment_service.payment_utils import (
    get_price,
    has_game,
    make_payment,
    add_game,
    get_owned_games,
    add_game_to_cart,
    remove_game_from_cart,
    get_user_cart,
    clear_user_cart,
    make_payment_cart,
)
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

@router.post("/purchase_game")
async def purchase_game(
    purchase: PurchaseGame,
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    if await has_game(username=claims.sub, appid=purchase.appid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already owned by the user",
        )

    game_price = await get_price(purchase.appid)
    if game_price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="appid is not found",
        )

    price = Price(**game_price._asdict())
    if price.price <= 0:
        result = await add_game(username=claims.sub, appid=purchase.appid)
        return {"message": result.get("message", "added the game"), "appid": purchase.appid}

    response = await make_payment(
        username=claims.sub,
        appid=purchase.appid,
        price=str(game_price.price),
    )
    return {
        "payment_id": response["payment_id"],
        "confirmation_url": response["confirmation_url"],
    }


@router.get("/cart")
async def get_cart(access_token: Annotated[str | None, Cookie()] = None):
    claims = _claims_or_401(access_token)

    appids, _ = await get_user_cart(username=claims.sub)
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
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    claims = _claims_or_401(access_token)
    _check_csrf(claims, csrf)

    appids, checkout_key = await get_user_cart(username=claims.sub)
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
        checkout_key=checkout_key,
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

    if not isinstance(payload, dict):
        logger.warning(
            "YooKassa notification ignored: JSON payload is not an object",
            extra={"payload_type": type(payload).__name__},
        )
        return {"status": "OK"}

    event = payload.get("event")
    obj = payload.get("object")
    payment_id = obj.get("id") if isinstance(obj, dict) else None
    log_context = {
        "event": event,
        "payment_id": payment_id,
    }

    if event != "payment.succeeded":
        logger.info(
            "YooKassa notification ignored: event is not payment.succeeded",
            extra=log_context,
        )
        return {"status": "OK"}

    metadata = obj.get("metadata") if isinstance(obj, dict) else None
    metadata = metadata if isinstance(metadata, dict) else {}
    username = metadata.get("username")
    raw_appids = metadata.get("appids")

    appids: list[int] = []
    if raw_appids:
        try:
            appids = [int(part) for part in str(raw_appids).split(",") if part.strip()]
        except (TypeError, ValueError):
            appids = []

    if not appids:
        raw_appid = metadata.get("appid")
        try:
            appids = [int(raw_appid)] if raw_appid is not None else []
        except (TypeError, ValueError):
            appids = []

    if not username or not appids:
        logger.warning(
            "Succeeded payment ignored: username or appid metadata is missing",
            extra={
                **log_context,
                "username": username,
                "raw_appids": repr(raw_appids)[:200],
            },
        )
        return {"status": "OK"}

    for appid in appids:
        ownership_context = {**log_context, "username": username, "appid": appid}
        logger.info("Checking ownership for succeeded payment", extra=ownership_context)
        try:
            already_owned = await has_game(username=username, appid=appid)
        except Exception as exc:
            logger.exception(
                "Failed to check ownership for succeeded payment",
                extra={**ownership_context, "error_type": type(exc).__name__},
            )
            raise

        if already_owned:
            logger.info(
                "Game is already owned; skipping grant for succeeded payment",
                extra={**ownership_context, "already_owned": True},
            )
            continue

        try:
            result = await add_game(username=username, appid=appid)
        except Exception as exc:
            logger.exception(
                "Failed to add game for succeeded payment",
                extra={**ownership_context, "error_type": type(exc).__name__},
            )
            raise

        logger.info(
            "Successfully added game for succeeded payment",
            extra={
                **ownership_context,
                "result_appid": result.get("appid") if isinstance(result, dict) else None,
            },
        )

    for appid in appids:
        try:
            await remove_game_from_cart(username=username, appid=appid)
        except Exception:
            logger.warning(
                "Failed to remove purchased game from cart",
                extra={**log_context, "username": username, "appid": appid},
                exc_info=True,
            )

    return {"status": "OK"}

