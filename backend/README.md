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

Health check:

```text
GET http://127.0.0.1:8000/api/v1/health
```

Create or update a local user:

```bash
python scripts/create_user.py alice secret
```

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
`src/` prototype directory.
