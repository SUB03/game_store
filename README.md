## Learning Project: Online Game Distribution Platform

**Work in progress**

This is a learning project where I am building an online game distribution platform.

## Running on Linux

### 1. Generate a secret key

Create a `.env` file entry for the JWT secret key:

```bash
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env
```

### 2. Add the database URL

Add the following line to your generated `.env` file:

```env
SQLALCHEMY_URL=postgresql+psycopg://postgres:postgres@postgres:5432/learning
```

### 3. Optional: initialize the database with games

If you want to populate the database with games:

1. Download the dataset from [Kaggle](https://www.kaggle.com/datasets/artermiloff/steam-games-dataset).
2. Place it in the `datasets` folder.
3. Run the dataset filter script:

```bash
python filter_dataset.py
```

### 4. Create the database tables

Run the Alembic migrations:

```bash
alembic -c store_service/alembic.ini upgrade head
alembic -c auth_service/alembic.ini upgrade head
alembic -c users_service/alembic.ini upgrade head
```

If the dataset is available, the tables will also be populated.

### 5. Start the project

Run the project with Docker Compose:

```bash
docker-compose up -d
```

## Local development

For local development, you may also want to install the protobuf packages:

```bash
cd shared
pip install -e ./protobufs
```

## Tests

Install the dev dependencies (pytest + pytest-asyncio + pytest-cov) into your virtualenv:

```bash
pip install -r requirements-dev.txt
```

Run everything:

```bash
pytest
```

- **Unit tests** (`tests/unit`) need no database and no Docker:

  ```bash
  pytest tests/unit
  ```

- **Integration tests** (`tests/integration`) start a throwaway
  `postgres:18` container on `127.0.0.1:5433`, apply all three services'
  Alembic migrations to it, run the tests and remove the container again.
  Requires a working Docker daemon. To use an existing database instead,
  point the suite at it:

  ```bash
  TEST_SQLALCHEMY_URL=postgresql+psycopg://user:pass@host:5432/dbname pytest tests/integration
  ```

  The tables used by the tests (`auth_users`, `auth_token_whitelist`,
  `store_games`, `store_tags`, `users_game_ownership`, `users_cart`) are
  truncated around every test.

## Coverage

`pytest-cov` is part of `requirements-dev.txt`, and `pytest.ini` always passes
the `--cov-*` flags, so every `pytest` run prints a per-file coverage table and
writes `coverage.xml` plus an HTML report into `htmlcov/`:

```bash
pytest
xdg-open htmlcov/index.html   # or: python -m http.server -d htmlcov 8000
```

Coverage is report-only — there is no threshold that can fail the run.
Alembic migrations run as subprocesses and are intentionally not measured.

## CI/CD

`.github/workflows/tests.yml` runs on every push to `master` (or manually via
*Actions -> Tests -> Run workflow*):

1. **tests** job (GitHub-hosted `ubuntu-latest`, Docker available): installs
   dependencies, runs the unit suite, then the integration suite (test data is
   appended so a single `coverage.xml` covers both suites).
2. **deploy** job (`needs: tests`, self-hosted label `laptop`): starts **only
   after the tests are green** and then:

   - recreates `.env` from the `DEPLOY_ENV` repository secret (the file is
     gitignored and `actions/checkout` removes untracked files every run),
   - starts PostgreSQL and waits until it accepts connections,
   - runs `alembic upgrade head` for `auth_service`, `store_service` and
     `users_service` in one-off containers,
   - deploys the stack:

   ```bash
   docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d --build
   ```

   **Required secret:** add `DEPLOY_ENV` under *Settings -> Secrets and
   variables -> Actions* with the full contents of your `.env` file.