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

For local Windows runs, the usual development setup is:

1. Start PostgreSQL and Redis with Docker Compose from the repository root.
2. Run FastAPI directly from this virtual environment.

```bash
docker compose up -d postgres redis
```

Make sure the root `.env` uses project-local paths and host ports:

```env
SEKI_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/seki_agent"
SEKI_CELERY_BROKER_URL="redis://127.0.0.1:6379/0"
SEKI_WORKSPACE_DIR="D:/seki/cc/seki_agent/data/workspace"
```

If `.env` contains `postgres:5432`, it is meant for processes running inside
Docker Compose. A backend running directly on Windows should use
`127.0.0.1:5432` unless you changed the host port mapping.

Legacy RAG reads its knowledge-base directories from plain (non-`SEKI_`)
environment variables; the data lives under `data/`:

```env
TBOX_DOCS_DIR="C:/seki/seki_agent/seki_agent/data/tbox_docs"
PARENT_STORE_DIR="C:/seki/seki_agent/seki_agent/data/parent_store"
VECTOR_DB_DIR="C:/seki/seki_agent/seki_agent/data/tbox_vector_db"
```

Long-running translation, SPI, and diff tasks use a configurable executor:

```bash
# default: execute during the request, useful for local debugging/tests
SEKI_TASK_EXECUTOR=sync

# MVP background execution: run tasks in a local thread pool
SEKI_TASK_EXECUTOR=thread
SEKI_TASK_EXECUTOR_MAX_WORKERS=3

# production-like compose path: send tasks to Redis/Celery worker
SEKI_TASK_EXECUTOR=celery
SEKI_CELERY_BROKER_URL=redis://127.0.0.1:6379/0
```

Each conversation also has a token budget:

```env
SEKI_MAX_CONVERSATION_TOKENS=200000
```

When the total reaches the current budget, the backend returns 409 and the
frontend asks the user whether to continue. Each confirmation increases the
budget by one base unit.

Code agent command execution is policy driven:

```env
# Direct execution, no frontend confirmation.
SEKI_CODE_AGENT_ALLOWED_COMMAND_PREFIXES='["ruff check","npm test"]'

# The agent can request these commands, but the user must confirm first.
SEKI_CODE_AGENT_CONFIRMED_COMMAND_PREFIXES='["python --version"]'
```

Unknown commands that do not match either list become pending operations, but
will not execute after confirmation until a matching confirmed prefix is
configured. Dangerous commands and shell control operators are still rejected.
The code agent can delete files and directories under the current user's
workspace. Project root and shared skills paths are readable/executable but not
deletable. Overwriting an existing file produces a unified-diff preview and a
pending operation that the user must confirm in the frontend; files the agent
created in the current run can be overwritten directly.

Every code agent tool execution (succeeded, failed, rejected, or pending
confirmation) is persisted to the `code_audit_records` table. Audit details do
not include file contents. Query the current user's records via
`GET /api/v1/code-operations/audit`.

The runtime Agent path is LangGraph, where the main agent decides handoff
through tools instead of backend keyword guesses. `RuleBasedAgentRunner` is
kept only for unit tests and narrow local debugging by explicit injection.

Web search uses the old Volc/Feedcoop-compatible provider when a key is
available:

```env
SEKI_WEB_SEARCH_API_KEY=your-volc-key
SEKI_WEB_SEARCH_API_URL=https://open.feedcoopapi.com/search_api/web_search
```

API keys are configured in backend environment variables; the frontend does
not collect per-request temporary keys.

LangSmith tracing should use the native LangChain/LangGraph environment
variables so tool/model/graph spans are captured without custom wrappers:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=seki-agent-local
```

The project also has a built-in trace store in PostgreSQL. Each chat turn
creates an `agent_trace_runs` row; model usage and tool calls are stored in
`agent_trace_events` and can be viewed from the frontend Trace page.

## Logging

Logs are written to `SEKI_LOG_DIR` (default `data/logs/`), isolated by
business domain with size-based rotation (50MB per file, 10 backups):

```text
logs/
├── access.log      ← HTTP request logs (seki.request)
├── app.log         ← Main business logs (agent, task, auth, admin, etc.)
├── audit.log       ← Security audit logs (code agent ops, user management)
├── trace.log       ← Agent trace logs (seki.trace)
└── error.log       ← Copy of all ERROR-level logs (quick issue triage)
```

All log records automatically include the current user's username (extracted
from the Authorization header) for multi-user scenarios.

Configure format and level via environment variables:

```env
SEKI_LOG_FORMAT=json      # json (single-line JSON) or console (human-readable)
SEKI_LOG_LEVEL=INFO       # standard Python log level
SEKI_LOG_DIR=/app/data/logs
```

Health check:

```text
GET http://127.0.0.1:8000/api/v1/health
```

Create or update a local user:

```bash
python scripts/create_user.py alice secret
```

The script prints the database URL it wrote to. It must match the database URL
used by the running backend.

## Tests

```bash
pytest
```

Tests require PostgreSQL on `127.0.0.1:5432` by default. Start dependencies
first:

```bash
docker compose up -d postgres redis
```

Use `SEKI_TEST_DATABASE_URL` if your test database is on another port.

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
