from datetime import datetime, timedelta, timezone
from typing import Annotated

import logging
import jwt
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncEngine
from fastapi import Depends, HTTPException, status, Header

from auth_service.engine import engine
from auth_service.models.models import users_table, token_whitelist
from auth_service.schemas.users import CreateUser, UserDB
from auth_service.schemas.token import Token
from auth_service.utils.hash_password import (
    get_password_hash,
    verify_password,
    verify_dummy, 
    SECRET_KEY,
    ALGORITHM
)
from auth_service.utils.oauth_with_cookies import OAuth2PasswordBearerWithCookie
from auth_service.utils.jwt import decode_jwt

oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="users/login")

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_MINUTES = 31 * 24 * 60

logger = logging.getLogger("auth_service")

def verify_user(user: UserDB, password: str):
    if not user:
        verify_dummy(password)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

async def delete_token_from_db(uuid: UUID):
    async with engine.begin() as conn:
        await conn.execute(token_whitelist.delete().where(token_whitelist.c.uid == uuid))
        logger.info("deleted token from whitelist table")

async def get_token_from_db(uuid: UUID):
    async with engine.begin() as conn:
        result = await conn.execute(token_whitelist.select().where(token_whitelist.c.uid == uuid))
        logger.info("got token from whitelist table")
        return result.fetchone()

async def store_token_in_db(uuid: UUID, expiration_date: datetime):
    async with engine.begin() as conn:
        logger.info("stored token in whitelist table")
        await conn.execute(token_whitelist.insert().values(uid=uuid, expiration_at=expiration_date))

def create_jwt_token(data: dict) -> str:
    to_encode = data.copy()
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_tokens(username: str, jti: str):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    access_expire = datetime.now(timezone.utc) + access_token_expires
    refresh_expire = datetime.now(timezone.utc) + refresh_token_expires
    access_token = create_jwt_token({"sub": username, "jti": str(jti), "exp": access_expire})
    refresh_token = create_jwt_token({"sub": username, "jti": str(jti), "exp": refresh_expire})
    logger.info("created tokens", extra={"username": username})
    return access_token, refresh_token, refresh_expire

async def get_user_from_jwt(token: Annotated[str, Depends(oauth2_scheme)]) -> UserDB:
    credentials_exeption = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = Token(**decode_jwt(token, SECRET_KEY, ALGORITHM))
    username = payload.sub
    if not username:
        logger.warning("missing sub claim in token")
        raise credentials_exeption
    user = await get_user(username)
    if user is None:
        logger.warning("user does not exist")
        raise credentials_exeption
    return user


async def get_user(username: str) -> UserDB:
    async with engine.begin() as conn:
        result = await conn.execute(
            users_table.select().where(users_table.c.username == username)
        )
        result = result.fetchone()
        if not result:
            return None
        return UserDB(**result._asdict())

async def insert_user(userdata: CreateUser):
    async with engine.begin() as conn:
        hashed_password = get_password_hash(userdata.password)
        await conn.execute(users_table.insert().values(
            username=userdata.username,
            email=userdata.email,
            hashed_password=hashed_password
        ))