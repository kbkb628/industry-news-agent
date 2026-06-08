# Industry News Agent Backend

This directory contains the backend skeleton for the MVP of the
industry-news structured push agent.

Current scope for Task 1:

- provide the backend project contract via `pyproject.toml`
- expose a minimal `GET /health` endpoint
- keep later MVP work out of this task

Out of scope in this step:

- database models or migrations
- topics CRUD APIs
- monitoring workflow execution
- HTML pages or template rendering

## Setup

```bash
cd backend
py -3.12 -m pip install -e ".[dev]"
```

## Run

```bash
cd backend
py -3.12 -m uvicorn app.main:app --reload
```

## Verify

```bash
cd backend
py -3.12 -m pytest tests/test_health_api.py::test_health_endpoint_exists -v
```
