from sqlalchemy import (
    Table,
    Column,
    MetaData,
    Integer,
    BigInteger,
    ForeignKey,
    Identity,
    Text,
)

metadata = MetaData()

# reference
games = Table(
    "store_games",
    metadata,
    Column("appid", BigInteger, Identity(), primary_key=True),
    extend_existing=True
)

users_table = Table(
    "auth_users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", Text, nullable=False, unique=True),
    extend_existing=True
)

games_ownership = Table(
    "users_game_ownership",
    metadata,
    Column("username", Text, ForeignKey("auth_users.username"), primary_key=True),
    Column("appid", BigInteger, ForeignKey("store_games.appid"), primary_key=True),
)

users_cart = Table(
    "users_cart",
    metadata,
    Column("username", Text, ForeignKey("auth_users.username"), primary_key=True),
    Column("appid", BigInteger, ForeignKey("store_games.appid"), primary_key=True),
)