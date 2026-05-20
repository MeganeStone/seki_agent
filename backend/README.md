# Seki Agent Backend

FastAPI backend for the engineering refactor of Seki Agent.

## Local Development

Create a virtual environment and install dependencies after confirmation:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For local Windows runs, make sure the root `.env` uses project-local paths,
not Docker container paths:

```env
SEKI_DATABASE_PATH="D:/seki/AI/Langchain/seki_agent/data/db/seki_agent.db"
SEKI_WORKSPACE_DIR="D:/seki/AI/Langchain/seki_agent/data/workspace"
```

If `.env` contains `/app/data/...`, it is meant for Docker and local login
will read/write a different SQLite database.

Long-running translation, SPI, and diff tasks use a configurable executor:

```bash
# default: execute during the request, useful for local debugging/tests
SEKI_TASK_EXECUTOR=sync

# MVP background execution: run tasks in a local thread pool
SEKI_TASK_EXECUTOR=thread
SEKI_TASK_EXECUTOR_MAX_WORKERS=3
```

Health check:

```text
GET http://127.0.0.1:8000/api/v1/health
```

Create or update a local user:

```bash
python scripts/create_user.py alice secret
```

The script prints the database path it wrote to. It must match the database
path used by the running backend.

## Tests

```bash
pytest
```

## Docker Compose

From the repository root:

```bash
copy .env.example .env
docker compose up --build
```

The API will be available at:

```text
http://127.0.0.1:8000/api/v1/health
```

Runtime data is stored under the repository root `data/` directory.

The container image copies only the engineered backend plus `backend/legacy`
runtime files required by migrated services. It does not copy the full old
`old/src/` prototype directory.
