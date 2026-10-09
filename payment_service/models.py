from sqlalchemy import (
    ARRAY,
    Table,
    Column,
    Integer,
    Numeric,
    BigInteger,
    DateTime,
    Identity,
    Text,
    Boolean,
    ForeignKey,
    MetaData,
    func,
)

metadata_obj = MetaData()

# Read-only mirror of the store catalog. The payment service never migrates
# these tables (store_service Alembic owns them); it only reads prices and
# game rows for cart/checkout filtering.
games_table = Table(
    "store_games",
    metadata_obj,
    Column("appid", BigInteger, Identity(), primary_key=True),
    Column("name", Text, nullable=False),
    Column("release_date", DateTime, nullable=False),
    Column("required_age", Integer, nullable=False),
    Column("price", Numeric(10, 2), nullable=False),
    Column("discount", Integer, nullable=False),
    Column("dlc_count", Integer, nullable=False),
    Column("detailed_description", Text),
    Column("about_the_game", Text),
    Column("short_description", Text),
    Column("reviews", Text),
    Column("header_image", Text),
    Column("website", Text),
    Column("support_url", Text),
    Column("support_email", Text),
    Column("windows", Boolean),
    Column("mac", Boolean),
    Column("linux", Boolean),
    Column("metacritic_score", Integer),
    Column("metacritic_url", Text),
    Column("achievements", Integer, nullable=False),
    Column("recommendations", Integer),
    Column("notes", Text),
    Column("positive", Integer),
    Column("negative", Integer),
)

tags_table = Table(
    "store_tags",
    metadata_obj,
    Column("appid", BigInteger, ForeignKey("store_games.appid"), primary_key=True),
    Column("tags", Text, primary_key=True)
)

# Lifecycle state for one YooKassa payment, from checkout through the Kafka
# grant saga to capture/cancel. Owned by payment_service (migrated below);
# payment_consumer reads/writes the same table to report saga outcomes and
# retry failed captures/cancels without payment_service in the loop.
payments_table = Table(
    "payment_payments",
    metadata_obj,
    Column("payment_id", Text, primary_key=True),
    Column("username", Text, nullable=False),
    Column("appids", ARRAY(BigInteger), nullable=False),
    Column("idempotency_key", Text, nullable=False),
    # pending -> grant_requested -> captured | canceled
    #                            -> granted_pending_capture -> captured | capture_failed
    #                            -> cancel_failed -> canceled | cancel_failed_permanent
    Column("status", Text, nullable=False, server_default="pending"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)
