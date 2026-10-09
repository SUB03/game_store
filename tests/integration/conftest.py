"""Fixtures for integration tests: ephemeral PostgreSQL (Docker) + Alembic.

The test database URL is fixed by ``tests/conftest.py`` (127.0.0.1:5433) so
that service engines created at *import time* already point at it; this
fixture just makes sure a server is actually listening there and has the
schema applied. Set ``TEST_SQLALCHEMY_URL`` to reuse an existing database
instead of starting Docker.
"""

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
CONTAINER_NAME = "game_store_test_postgres"
DB_NAME = "learning_test"
PORT = 5433
DEFAULT_URL = f"postgresql+psycopg://postgres:postgres@127.0.0.1:{PORT}/{DB_NAME}"

TABLES = [
    "users_game_ownership",
    "users_cart",
    "auth_token_whitelist",
    "auth_users",
    "store_tags",
    "store_games",
    "payment_payments",
]


def _docker_usable() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "version"], capture_output=True).returncode == 0


def _wait_for_postgres(url: str, timeout: float = 90.0) -> None:
    from sqlalchemy import create_engine

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            engine = create_engine(url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return
        except Exception as exc:  # noqa: BLE001 - retry any connection error
            last_exc = exc
            time.sleep(0.5)
    raise RuntimeError(f"PostgreSQL did not become ready in time: {last_exc}")


@pytest.fixture(scope="session")
def pg_url():
    url = os.environ["SQLALCHEMY_URL"]

    if os.environ.get("TEST_SQLALCHEMY_URL"):
        # caller provides the database
        yield url
        return

    if not _docker_usable():
        pytest.skip("Docker is not available and TEST_SQLALCHEMY_URL is not set")

    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
    proc = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "--name", CONTAINER_NAME,
            "-e", "POSTGRES_USER=postgres",
            "-e", "POSTGRES_PASSWORD=postgres",
            "-e", f"POSTGRES_DB={DB_NAME}",
            "-p", f"127.0.0.1:{PORT}:5432",
            "postgres:18",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"could not start PostgreSQL container: {proc.stderr.strip()}")

    try:
        _wait_for_postgres(url)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)


def _alembic(args: list[str], cwd: Path, env: dict) -> None:
    alembic_bin = Path(sys.executable).with_name("alembic")
    cmd = [str(alembic_bin), *args] if alembic_bin.exists() else [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {' '.join(args)} failed in {cwd}:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def db(pg_url):
    """Test database with the schema of all four services migrated."""
    env = {
        **os.environ,
        "SQLALCHEMY_URL": pg_url,
        "PYTHONPATH": os.pathsep.join(
            [
                str(ROOT),
                str(ROOT / "users_service"),
                str(ROOT / "shared" / "protobufs" / "src"),
            ]
        ),
    }
    _alembic(["-c", "auth_service/alembic.ini", "upgrade", "head"], ROOT, env)
    _alembic(["-c", "store_service/alembic.ini", "upgrade", "head"], ROOT, env)
    _alembic(["-c", "alembic.ini", "upgrade", "head"], ROOT / "users_service", env)
    _alembic(["-c", "alembic.ini", "upgrade", "head"], ROOT / "payment_service", env)

    yield create_async_engine(pg_url)


@pytest.fixture(scope="session")
def auth_db(db):
    """Point auth_service's module-level engine (hardcoded to the docker host
    name) at the test database."""
    import auth_service.engine as auth_engine_module
    import auth_service.routers.users.users as users_router
    import auth_service.routers.users.users_utils as users_utils

    modules = (auth_engine_module, users_utils, users_router)
    originals = [(module, getattr(module, "engine", None)) for module in modules]
    for module, _ in originals:
        module.engine = db
    yield db
    for module, original in originals:
        module.engine = original


@pytest.fixture(autouse=True)
async def _clean_tables(db):
    """Empty every table the tests touch before and after each test."""
    truncate = text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
    async with db.begin() as conn:
        await conn.execute(truncate)
    yield
    async with db.begin() as conn:
        await conn.execute(truncate)


# --- seed helpers ------------------------------------------------------------

@pytest.fixture
def seed_user(auth_db):
    from auth_service.utils.hash_password import get_password_hash

    async def _seed(username: str = "alice", password: str = "s3cret-pw", email: str | None = None):
        email = email or f"{username}@example.com"
        async with auth_db.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO auth_users (username, hashed_password, email) "
                    "VALUES (:username, :password, :email)"
                ),
                {"username": username, "password": get_password_hash(password), "email": email},
            )
        return username

    return _seed


@pytest.fixture
def seed_game(db):
    async def _seed(
        name: str = "Test Game",
        price: str = "9.99",
        recommendations: int = 100,
        tags: tuple[str, ...] = (),
    ) -> int:
        async with db.begin() as conn:
            result = await conn.execute(
                text(
                    "INSERT INTO store_games "
                    "(name, release_date, required_age, price, discount, dlc_count, "
                    " achievements, recommendations) "
                    "VALUES (:name, :release_date, 0, :price, 0, 0, 0, :recommendations) "
                    "RETURNING appid"
                ),
                {
                    "name": name,
                    "release_date": datetime(2020, 1, 1),
                    "price": price,
                    "recommendations": recommendations,
                },
            )
            appid = result.scalar_one()
            for tag in tags:
                await conn.execute(
                    text("INSERT INTO store_tags (appid, tags) VALUES (:appid, :tag)"),
                    {"appid": appid, "tag": tag},
                )
        return appid

    return _seed