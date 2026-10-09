"""Root test configuration.

Everything in this module runs *before* any test module is imported, which is
required because the services read environment variables at import time
(e.g. ``auth_service.utils.hash_password`` asserts ``SECRET_KEY`` is set, and
``store_service.engine`` builds its engine from ``SQLALCHEMY_URL``).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for extra in (
    ROOT,  # `auth_service`, `store_service`, `payment_service`, `users_service` packages
    ROOT / "users_service",  # users_service/main.py does `from models import ...`
    ROOT / "shared" / "protobufs" / "src",  # `users_proto`
):
    path = str(extra)
    if path not in sys.path:
        sys.path.insert(0, path)

# Fixed test database URL. Integration tests start a Docker Postgres published
# on 127.0.0.1:5433; unit tests never connect (SQLAlchemy connects lazily).
DEFAULT_TEST_DB_URL = (
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/learning_test"
)
TEST_DB_URL = os.environ.get("TEST_SQLALCHEMY_URL", DEFAULT_TEST_DB_URL)

# Force every service onto the test database, never the dev/prod one.
os.environ["SQLALCHEMY_URL"] = TEST_DB_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("DEVELOPMENT", "true")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3001")
# payment_service settings (only used when constructing its Settings)
os.environ.setdefault("SHOPID", "1")
os.environ.setdefault("UKASS_API_KEY", "test-api-key")
# tests never run from a YooKassa IP; the webhook IP allowlist is tested
# separately via explicit settings overrides.
os.environ.setdefault("VERIFY_WEBHOOK_IP", "false")