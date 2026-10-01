import logging
from typing import Annotated

from fastapi import HTTPException, routing, Depends, status, Request, Cookie, Header, Query, Path
from sqlalchemy import select, func

from store_service.schemas.games import Price
from store_service.engine import engine
from store_service.models.models import games_table, tags_table
from store_service.routers.store_utils import (
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
from store_service.schemas.games import PurchaseGame, CartItem, LibraryGame
from store_service.utils.jwt import decode_jwt
from store_service.schemas.token import Token
from store_service.utils.tag_groups import _TAG_TO_GROUP, TAG_GROUPS

logger = logging.getLogger("store_service")

router = routing.APIRouter(
    prefix="/store",
    tags=["store"]
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

@router.get("/tags")
async def get_tags(
    tags: str | None = Query(
        None, description="Comma-separated tags; only count games that have ALL of them"
    ),
):
    tags = [t for t in (tags or "").split(",") if t] or None
    
    async with engine.begin() as conn:
        if not tags:
            # No filter: count every tag across all games
            stmt = (
                select(
                    tags_table.c.tags.label("tag"),
                    func.count(func.distinct(tags_table.c.appid)).label("game_count"),
                )
                .group_by(tags_table.c.tags)
                .order_by(func.count(func.distinct(tags_table.c.appid)).desc())
            )
        else:
            # Find games that have ALL selected tags, then count tags within that subset
            matching_games = (
                select(tags_table.c.appid)
                .where(tags_table.c.tags.in_(tags))
                .group_by(tags_table.c.appid)
                .having(
                    func.count(func.distinct(tags_table.c.tags)) >= len(tags)
                )
                .subquery()
            )
            stmt = (
                select(
                    tags_table.c.tags.label("tag"),
                    func.count(func.distinct(tags_table.c.appid)).label("game_count"),
                )
                .where(tags_table.c.appid.in_(select(matching_games.c.appid)))
                .group_by(tags_table.c.tags)
                .order_by(func.count(func.distinct(tags_table.c.appid)).desc())
            )

        result = await conn.execute(stmt)
        rows = result.mappings().all()

    grouped: dict[str, list[dict]] = {}
    other: list[dict] = []

    for row in rows:
        group = _TAG_TO_GROUP.get(row["tag"])
        if group:
            grouped.setdefault(group, []).append(row)
        else:
            other.append(row)

    if other:
        grouped["Other"] = other

    # Preserve the order of TAG_GROUPS, drop empty groups
    ordered = {
        name: grouped[name]
        for name in [*TAG_GROUPS, "Other"]
        if name in grouped
    }
    return ordered

@router.get("/games/{appid}")
async def get_game(appid: Annotated[int, Path(title="appid of the game in db")]):
    async with engine.begin() as conn:
        result = await conn.execute(
            games_table.select().where(games_table.c.appid == appid)
        )
    return result.mappings().first()

@router.get("/games")
async def get_games(
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, description="Search by name"),
    tags: str | None = Query(
        None, description="Comma-separated tags; filter by tags (AND)"
    ),
):
    tags = [t for t in (tags or "").split(",") if t] or None
    limit = 12

    stmt = (
        select(games_table, func.array_agg(tags_table.c.tags).label("tags"))
        .join(tags_table, tags_table.c.appid == games_table.c.appid, isouter=True)
        .group_by(games_table.c.appid)
        .order_by(games_table.c.recommendations.desc(),  games_table.c.appid)
        .limit(limit + 1)  # fetch one extra to detect next page
        .offset(offset)
    )

    if search:
        stmt = stmt.where(games_table.c.name.ilike(f"%{search}%"))

    if tags:
        # Only include games that have ALL the requested tags
        stmt = stmt.having(
            func.count(func.distinct(tags_table.c.tags)).filter(
                tags_table.c.tags.in_(tags)
            ) >= len(tags)
        )
    
    async with engine.begin() as conn:
        result = await conn.execute(stmt)
        result = result.mappings().all()

    is_next_page = len(result) > limit

    return {
        "results": result[:limit],
        "is_next_page": is_next_page,
    }

@router.get("/owned_games")
async def owned_games(access_token: Annotated[str | None, Cookie()] = None):
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials"
        )
    claims = Token(**decode_jwt(access_token))

    appids = await get_owned_games(username=claims.sub)
    if not appids:
        return {"results": []}

    stmt = (
        select(games_table, func.array_agg(tags_table.c.tags).label("tags"))
        .join(tags_table, tags_table.c.appid == games_table.c.appid, isouter=True)
        .where(games_table.c.appid.in_(appids))
        .group_by(games_table.c.appid)
        .order_by(games_table.c.name)
    )

    async with engine.begin() as conn:
        result = await conn.execute(stmt)
        rows = result.mappings().all()

    return {"results": rows}


@router.get("/cart")
async def get_cart(access_token: Annotated[str | None, Cookie()] = None):
    claims = _claims_or_401(access_token)

    appids, _ = await get_user_cart(username=claims.sub)
    if not appids:
        return {"results": []}

    # Never show games the user already owns or free games (those go
    # straight to the library, they must never sit in a cart).
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
    """Start one payment covering every paid game currently in the cart.

    The cart's backend-generated checkout_key travels along as the payment's
    idempotency key, so retried checkouts can never create a second charge.
    Rows are only emptied once the games are granted (webhook / free branch);
    a failed payment leaves the cart untouched.
    """
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
            # Leftover rows can never be paid twice - strip them now.
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
            # game vanished from the catalog
            await remove_game_from_cart(username=claims.sub, appid=appid)
            continue
        if float(prices[appid]) <= 0:
            # free games never sit in a cart - grant and drop immediately
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
        "payment_id": response.payment_id,
        "confirmation_url": response.confirmation_url,
    }


@router.post("/purchase_game")
async def purchase_game(
    purchase: PurchaseGame,
    csrf: Annotated[str | None, Header(alias="CSRF")] = None,
    access_token: Annotated[str | None, Cookie()] = None,
):
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials"
        )
    claims = Token(**decode_jwt(access_token))
    if not csrf or csrf != str(claims.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials"
        )

    result = await has_game(username=claims.sub, appid=purchase.appid)
    if result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already owned by the user"
        )

    game_price = await get_price(purchase.appid)
    if not game_price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="appid is not found"
        )
    game_price = Price(**game_price._asdict())
    if game_price.price > 0:
        response = await make_payment(username=claims.sub, appid=purchase.appid, price=str(game_price.price))
        return {
            "payment_id": response.payment_id,
            "confirmation_url": response.confirmation_url,
        }
    else:
        result = await add_game(username=claims.sub, appid=purchase.appid)
        return result
    

@router.post("/notifications")
async def notifications(request: Request):
    """YooKassa webhook: grant the game when a payment succeeds.

    Always answers 200 fast (YooKassa retries on non-2xx / timeouts).
    Ownership is idempotent - re-delivered webhooks must not fail.
    """
    logger.info("YooKassa notification received")
    try:
        payload = await request.json()
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

    # Cart payments carry every covered game as "appids" ("1,2,3");
    # legacy single-game payments only carry "appid".
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

    # Strip every paid game from the cart (best effort): the buyer owns it
    # now, and GET /store/cart filters owned games anyway as a safety net.
    # Failures must never fail the webhook - YooKassa would retry forever.
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