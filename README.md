# Yinanping Studio

Hybrid bootstrap monorepo for the "意难平剧组" product.

## Python Backend Quick Start

The active backend lives in `src/` and is run with `uv`.

Current flow:

- Session discussion uses AutoGen multi-director streaming in `src/agents`.
- Video jobs read project/session/asset data from the database and call Seedance directly.
- The public ANet-facing gateway is exposed from `/api/gateway/*`.

1. Sync dependencies:
  - `uv sync`
2. Start the API:
  - `uv run uvicorn src.main:app --reload`
3. Optional direct checks:
  - `uv run python scripts/test_endpoints.py`
  - `uv run python -c "import asyncio; from src.agents import run_debate; print(asyncio.run(run_debate('测试剧情', style='auto')))"`

Default backend URL:

- API: `http://127.0.0.1:8000`

The old `npm run dev:api` section below is legacy documentation from the previous
Node backend and can be ignored for the current Python backend.

## Structure

- `apps/web`: Vite + D3 front-end demo.
- `apps/api`: Node API for session, discussion, and video jobs.
- `packages/contracts`: shared runtime contracts.
- `packages/agent-profiles`: shared agent definitions.

## Run

1. Install dependencies:
   - `npm install`
2. Start API:
   - `npm run dev:api`
3. Start web:
   - `npm run dev:web`

Defaults:

- API: `http://localhost:3567`
- Web: `http://localhost:5173`
- Sessions: persisted to `tmp-data/sessions.json` by default

## Environment variables

Copy `.env.example` at repo root and `apps/web/.env.example` as needed.

- `PORT`: API port (default `3567`)
- `CORS_ORIGIN`: allowed web origin (default `*` when empty)
- `SESSION_STORE_PATH`: persisted session store path
- `IOPHO_SCRIPT_PATH`: optional storyboard script path
- `DISCUSSION_ENGINE_MODE`: `template` (default) or `distilled`
- `DEMO_CLIP_SECONDS`: output mp4 clip length for demo render
- `VITE_API_BASE`: web-side API base URL (optional, defaults to current host + `:3567`)

## Optional iopho integration

Set `IOPHO_SCRIPT_PATH` to the absolute path of:

- `skills/iopho-analyzing-videos/scripts/video_to_storyboard.py`

If the script is unavailable or fails, API falls back to a placeholder artifact for demo continuity.

If `sourceVideoPath` is provided and valid, API now creates a real source-preview artifact before optional storyboard analysis.

## Demo mp4 pipeline

- API `render` stage attempts a real `ffmpeg` export to `tmp-artifacts/<jobId>/output.mp4`.
- If `ffmpeg` fails but source file is readable, API falls back to source-copy mp4 for demo continuity.
- Artifacts are exposed via `GET /api/artifacts/...`, and web result panel can play returned `publicUrl`.

## Agent Network gateway

- `GET /api/gateway/services`
- `POST /api/gateway/invoke`
- `GET /api/gateway/invocations`
- `GET /api/gateway/invocations/events`
- The gateway exposes the video-editing service externally while keeping discussion planning inside AutoGen.

- API now includes a P2P-style service gateway:
  - `GET /api/gateway/services`
  - `GET /api/gateway/capabilities`
  - `POST /api/gateway/invoke`
  - `GET /api/gateway/invocations` and `/api/gateway/invocations/events`
- Default gateway token is `agent-network-demo-token` (override with `GATEWAY_TOKEN`).
- Built-in capability services:
  - `director-brain`: `discussion.generateTimeline`
  - `video-lab`: `video.createJob`, `video.getJob`
  - `audio-lab`: `soundtrack.suggest`
  - `orchestrator-hub`: `production.plan` (cross-agent invoke demo)
  - `video-editing-api`: read project/session/assets from DB and call Seedance

## ANet full integration runbook

### 1) Start backend

1. Activate the virtual environment.
2. Start the API:
   - `uvicorn src.main:app --reload`

### 2) AutoGen discussion module

- The backend uses AutoGen in `src/agents` for multi-director discussion.
- `/api/sessions/:id/stream` streams every AutoGen message and the final synthesized markdown.
- `src/agents` does not handle video generation; video jobs remain in the API layer and call Seedance using the project database contents.

### 3) Troubleshooting

- If you want to smoke-test the agent layer directly, run:
  - `.venv\\Scripts\\python -c "import asyncio; from src.agents import run_debate; print(asyncio.run(run_debate('测试剧情', style='auto')))"`
- Invocation logging is still available at `/api/gateway/invocations` and `/api/gateway/invocations/events`.

## Distillation and smoke scripts

- Run distilled vs template evaluation:
  - `npm run distill:eval`
- Run pipeline smoke scenarios:
  - `npm run smoke:video`
  - Optional: set `SMOKE_VIDEO_PATH` to enable real-path scenarios.
- Run gateway chaos/fallback scenarios:
  - `npm run smoke:gateway`
