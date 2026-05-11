# IS601 Module 12 – Calculations API

A FastAPI REST service with JWT authentication and PostgreSQL persistence.
Users can register, log in, and perform full BREAD operations on arithmetic calculations (addition, subtraction, multiplication, division).

---

## Table of Contents

1. [Quick Start (Docker Compose)](#1-quick-start-docker-compose)
2. [Local Development (no Docker)](#2-local-development-no-docker)
3. [Environment Variables](#3-environment-variables)
4. [Running Integration Tests](#4-running-integration-tests)
5. [Manual Testing via OpenAPI (Swagger UI)](#5-manual-testing-via-openapi-swagger-ui)
6. [API Reference](#6-api-reference)
7. [CI/CD Pipeline](#7-cicd-pipeline)

---

## 1. Quick Start (Docker Compose)

> Requires Docker Desktop (or Docker Engine + Compose plugin).

```bash
# Clone the repo
git clone <your-repo-url>
cd module12_is601

# Start the full stack (API + PostgreSQL + pgAdmin)
docker compose up --build

# API is now available at:
#   http://localhost:8000
# Swagger UI (interactive docs):
#   http://localhost:8000/docs
# pgAdmin (DB browser):
#   http://localhost:5050  (login: admin@admin.com / admin)
```

Stop everything:

```bash
docker compose down
```

Tear down including database volumes:

```bash
docker compose down -v
```

---

## 2. Local Development (no Docker)

### Prerequisites

- Python 3.10+
- A running PostgreSQL instance

### Setup

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and edit the environment file
cp .env.example .env              # or create .env manually (see section 3)
```

### Start the server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`.

---

## 3. Environment Variables

Create a `.env` file in the project root (same directory as `requirements.txt`):

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_db

# JWT – change these secrets before deploying to production
JWT_SECRET_KEY=your-super-secret-key-change-this
JWT_REFRESH_SECRET_KEY=your-refresh-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Security
BCRYPT_ROUNDS=12

# Optional – leave blank to disable token blacklisting
REDIS_URL=
```

---

## 4. Running Integration Tests

### With Docker Compose (recommended)

```bash
# Start only the database service
docker compose up -d db

# Wait a few seconds, then run the full test suite
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_db \
JWT_SECRET_KEY=test-secret \
JWT_REFRESH_SECRET_KEY=test-refresh-secret \
REDIS_URL="" \
pytest tests/unit/ tests/integration/ -v
```

### Without Docker (local Postgres)

```bash
source venv/bin/activate

# Export required variables (or put them in .env)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_test
export JWT_SECRET_KEY=test-secret
export JWT_REFRESH_SECRET_KEY=test-refresh-secret
export REDIS_URL=

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests (unit + model + API endpoint tests)
pytest tests/integration/ -v

# Run everything except E2E (which requires a running browser)
pytest tests/unit/ tests/integration/ -v

# Run with coverage report
pytest tests/unit/ tests/integration/ --cov=app --cov-report=html
# Open htmlcov/index.html in your browser to inspect coverage
```

### Preserve the test database between runs

```bash
pytest tests/integration/ --preserve-db
```

### Run slow tests (bulk operations, etc.)

```bash
pytest tests/integration/ --run-slow
```

---

## 5. Manual Testing via OpenAPI (Swagger UI)

With the server running, open **http://127.0.0.1:8000/docs** in your browser.

### Step-by-step walkthrough

**1. Register a user**

Expand `POST /users/register` → click **Try it out** → fill in the example body → **Execute**.

```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "username": "janedoe",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!"
}
```

You will receive a `201 Created` response containing the user object (no password in the response).

**2. Log in and get a token**

Expand `POST /users/login` → **Try it out** → supply your username and password → **Execute**.

Copy the `access_token` value from the response.

**3. Authorize the Swagger UI**

Click the **Authorize** button (lock icon, top right of Swagger UI) → paste your token into the `Value` field → **Authorize** → **Close**.

All subsequent requests will automatically include the bearer token.

**4. Create a calculation**

Expand `POST /calculations` → **Try it out** → send:

```json
{
  "type": "addition",
  "inputs": [10.5, 3, 2]
}
```

Response includes `id`, `result` (15.5), `user_id`, and timestamps.

**5. List your calculations**

`GET /calculations` → **Try it out** → **Execute** – returns an array of all your calculations.

**6. Update a calculation**

`PUT /calculations/{calc_id}` → paste the `id` from step 4 → send new inputs:

```json
{ "inputs": [100, 4] }
```

The result is recomputed automatically (104.0 for addition).

**7. Delete a calculation**

`DELETE /calculations/{calc_id}` → paste the `id` → **Execute** → `204 No Content`.

---

## 6. API Reference

### Users

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/users/register` | No | Register a new user |
| POST | `/users/login` | No | Login, receive JWT tokens |

### Calculations (all require Bearer token)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/calculations` | Add – create and persist a calculation |
| GET | `/calculations` | Browse – list your calculations |
| GET | `/calculations/{id}` | Read – retrieve one calculation |
| PUT | `/calculations/{id}` | Edit – update inputs, recompute result |
| DELETE | `/calculations/{id}` | Delete – remove permanently |

### Supported calculation types

| Type | Operation |
|------|-----------|
| `addition` | sum of all inputs |
| `subtraction` | first input minus all subsequent inputs |
| `multiplication` | product of all inputs |
| `division` | first input divided by all subsequent inputs |

All calculations require **at least 2 inputs**. Division by zero returns `400 Bad Request`.

---

## 7. CI/CD Pipeline

Every push / pull request to `main` triggers the GitHub Actions workflow (`.github/workflows/test.yml`):

1. **Test** – spins up a PostgreSQL 17 service, installs dependencies, and runs:
   - `tests/unit/` – arithmetic operation unit tests
   - `tests/integration/` – model, schema, database, auth, and API endpoint tests
   - `tests/e2e/` – end-to-end browser tests via Playwright
2. **Security** – builds the Docker image and scans it with [Trivy](https://github.com/aquasecurity/trivy) for CRITICAL/HIGH CVEs.
3. **Deploy** – on `main` only, builds a multi-arch (`linux/amd64`, `linux/arm64`) Docker image and pushes it to Docker Hub using `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets.

### Required GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `DOCKERHUB_USERNAME` | Docker Hub account username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |

The Docker image is published as:
```
<DOCKERHUB_USERNAME>/is601_module12:latest
<DOCKERHUB_USERNAME>/is601_module12:<git-sha>
```
