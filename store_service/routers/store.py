import logging

from fastapi import HTTPException, routing, status, Cookie, Query, Path
from sqlalchemy import select, func
from typing import Annotated

from store_service.engine import engine
from store_service.models.models import games_table, tags_table
from store_service.routers.store_utils import (
    get_price,
    get_owned_games,
)
from store_service.utils.jwt import decode_jwt
from store_service.schemas.token import Token
from store_service.utils.tag_groups import _TAG_TO_GROUP, TAG_GROUPS

logger = logging.getLogger("store_service")

router = routing.APIRouter(
    prefix="/store",
    tags=["store"]
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
