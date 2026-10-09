from sqlalchemy import ARRAY, Column, DateTime, Integer, BigInteger, MetaData, Table, Text, func

metadata_obj = MetaData()

# Mirror of payment_service's table (that service owns the migrations);
# payment_consumer reads/writes it to report saga outcomes and to drive the
# capture/cancel retry sweep.
payments_table = Table(
    "payment_payments",
    metadata_obj,
    Column("payment_id", Text, primary_key=True),
    Column("username", Text, nullable=False),
    Column("appids", ARRAY(BigInteger), nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)
