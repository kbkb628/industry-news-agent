# React Dashboard Design

## Purpose

Add a first React + Vite management dashboard for the Industry News Agent so the
project demonstrates the Phase 2 requirement from `DEVELOPMENT_GUIDE.md`:

```text
React 管理后台展示主题、候选池、Trace、推送记录和评分。
```

This is a frontend demonstration slice. It must consume the existing backend API
contracts first and must not broaden backend capability claims.

## Current Context

The backend already provides:

- topic APIs
- monitor run APIs
- candidate and push APIs
- event timeline API
- eval quality summary API
- minimal FastAPI HTML pages
- local Docker Compose stack for backend, PostgreSQL, and Redis

The Phase 2 roadmap identifies the next recommended slice as:

```text
React + Vite dashboard -> consume existing APIs -> local Compose frontend -> README route documentation
```

## Recommended Approach

Create a standalone `frontend/` React + TypeScript + Vite application.

The frontend will use the existing backend APIs and will not require backend
schema changes for the first implementation. Existing FastAPI HTML pages remain
available until the React dashboard is verified.

## User-Facing Scope

The first dashboard version includes five views:

- Dashboard overview: summarize topic count, push count, quality metrics, and
  quick run lookup.
- Topics: list configured monitoring topics with keywords, trusted sources,
  threshold, enabled state, and schedule cron.
- Pushes: list push records as the first version of the push backend.
- Run detail: show a monitor run snapshot for a user-provided `run_id`.
- Trace timeline: show run events for a user-provided `run_id`, with event type,
  node, message, timestamp, and compact payload rendering.

The first version may use simple client-side navigation rather than a routing
library. If a routing library is added, it must be justified in the
implementation plan.

## API Contracts

The frontend must consume only these existing endpoints in the first
implementation:

- `GET /api/topics`
- `GET /api/pushes`
- `GET /api/monitor/runs/{run_id}`
- `GET /api/monitor/runs/{run_id}/events`
- `GET /api/eval/summary`

The API client should define TypeScript types that match the currently returned
JSON fields used by the UI. It should tolerate missing optional fields by
showing empty states instead of crashing.

No new backend API should be added unless implementation proves an existing
endpoint cannot support the dashboard. If a new backend API becomes necessary,
pause and write a separate backend contract plan first.

## Frontend Structure

Planned files:

- `frontend/package.json`: scripts and dependencies for Vite, React,
  TypeScript, and tests.
- `frontend/index.html`: Vite HTML entry.
- `frontend/vite.config.ts`: Vite config and backend proxy.
- `frontend/tsconfig.json`: strict TypeScript config.
- `frontend/src/main.tsx`: React app bootstrap.
- `frontend/src/App.tsx`: page layout and view composition.
- `frontend/src/api/client.ts`: typed fetch helpers.
- `frontend/src/api/types.ts`: API response types used by the UI.
- `frontend/src/components/*.tsx`: focused presentational components.
- `frontend/src/styles.css`: dashboard visual system.
- `frontend/src/*.test.tsx` or `frontend/src/**/*.test.tsx`: frontend tests.

## Visual Direction

The UI should look like an operations console for a monitored intelligence
pipeline, not a generic CRUD admin page.

Design rules:

- Use a purposeful visual direction with clear information hierarchy.
- Use CSS variables for color, spacing, and surfaces.
- Avoid default-looking purple-on-white styling.
- Show operational state clearly: loading, empty, error, degraded, and populated
  states.
- Make long run state and event payloads readable without hiding traceability.
- Keep the layout usable on desktop and mobile.

## Docker Compose Scope

Add a `frontend` service only as a local demonstration path:

- build or run from `frontend/`
- expose a local browser port, for example `5173`
- proxy API calls to the backend service
- depend on `backend`

Do not claim production deployment hardening. The Compose stack remains a local
demo stack.

## README Updates

Update `backend/README.md` or add a root README section during implementation to
document:

- frontend install command
- frontend dev command
- frontend build command
- Docker Compose usage including frontend URL
- capability boundary: React dashboard is a local management UI over existing
  APIs, not a production deployment or authentication layer

If the repository remains backend-focused, prefer adding a root README later
only if needed for clarity. The implementation plan should decide the exact doc
location after inspecting root-level files.

## Testing And Verification

Frontend tests should cover:

- API client requests use the expected endpoint paths.
- Dashboard renders populated summary data.
- Topics and pushes views render list data.
- Run detail and trace timeline show empty/error states without crashing.

Required verification before committing implementation:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\frontend
npm install
npm test -- --run
npm run build
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
docker compose config --quiet
git diff --check
```

If a different package manager is selected in the implementation plan, replace
the npm commands with the exact chosen commands and commit the corresponding
lockfile.

## Non-Goals

The first React dashboard does not include:

- authentication or authorization
- write operations such as creating topics or triggering runs
- WebSocket or realtime streaming
- provider configuration editing
- production frontend deployment
- replacement or removal of existing FastAPI HTML pages
- new backend capabilities
- new backend API contracts without a separate plan

## Acceptance Criteria

The React dashboard slice is acceptable when:

- `frontend/` builds successfully.
- Frontend tests pass.
- Backend tests still pass.
- Docker Compose config includes a local frontend service and remains valid.
- README documents how to run the dashboard and its limits.
- The UI can show topics, pushes, a quality summary, a run snapshot, and an
  event timeline using existing APIs.
- Capability claims remain aligned with implemented behavior.

## Implementation Sequence

1. Write a detailed implementation plan using
   `superpowers:writing-plans`.
2. Follow TDD for API client and rendering behavior.
3. Scaffold the minimal Vite app only after tests or plan steps define the
   expected files and behavior.
4. Verify frontend and backend together.
5. Commit and push the working dashboard slice.
