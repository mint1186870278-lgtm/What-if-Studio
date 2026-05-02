# Yinanping Studio

Hybrid bootstrap monorepo for the "意难平剧组" product.

## Python Backend Quick Start

The active backend lives in `src/` and is run with `uv`.

Current flow:

- AutoGen in `src/agents` handles multi-director discussion and script generation.
- Core video-editing business APIs (projects/assets/sessions/jobs) are served by FastAPI.
- ANet gateway exposes backend capabilities to Agent Network callers; it does not replace AutoGen discussion.

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

- `src`: FastAPI backend.
- `web`: Vite + D3 frontend source.
- `web/dist`: frontend production build artifacts served by FastAPI.
- `storage`: runtime file storage.

## Frontend + FastAPI Integration

1. Install frontend dependencies:
   - `cd web`
   - `npm install`
2. Build frontend:
   - `npm run build`
3. Start backend from repo root:
   - `uv run uvicorn src.main:app --reload`
4. Open:
   - `http://127.0.0.1:8000`

The backend serves `web/dist` directly.  
If needed, override dist path with `FRONTEND_DIST_DIR` in `.env`.

## Environment variables

Copy `.env.example` at repo root and `web/.env.example` as needed.

- `OPENAI_API_KEY`: model provider API key required by AutoGen discussion
- `OPENAI_BASE_URL`: OpenAI-compatible endpoint base URL (default `https://api.openai.com/v1`)
- `AUTOGEN_MODEL`: model name used by AutoGen discussion (default `gpt-4o-mini`)
- `DATABASE_URL`: backend database URL (default `sqlite:///./whatif.db`)
- `FRONTEND_DIST_DIR`: frontend static dist directory (default `./web/dist`)

## Demo mp4 pipeline

- API `render` stage attempts a real `ffmpeg` export to `tmp-artifacts/<jobId>/output.mp4`.
- If `ffmpeg` fails but source file is readable, API falls back to source-copy mp4 for demo continuity.
- Artifacts are exposed via `GET /api/artifacts/...`, and web result panel can play returned `publicUrl`.

## Agent Network gateway

- `GET /api/gateway/services`
- `POST /api/gateway/invoke`
- `GET /api/gateway/invocations`
- `GET /api/gateway/invocations/events`
- Role split:
  - AutoGen: multi-director discussion (`/api/sessions/.../stream`) and script synthesis.
  - ANet gateway: external service access layer for backend capabilities.
- ANet-facing services currently include:
  - `autogen.discussion` (discussion generation)
  - `autogen.edit` (editing-plan proposal)
  - `autogen.sound` (sound design proposal)
  - `anet.video_editing` and `video-editing-api` (session/script/assets driven render workflow)
- Integration intent:
  - Keep frontend APIs as the primary product surface (create project, upload assets, start session/job, query progress).
  - Mirror equivalent capabilities through ANet for network-based invocation.

## ANet full integration runbook

### 1) Start backend

1. Activate the virtual environment.
2. Start the API:
   - `uvicorn src.main:app --reload`

### 2) AutoGen discussion module

- The backend uses AutoGen in `src/agents` for multi-director discussion.
- `/api/sessions/:id/stream` streams every AutoGen message and the final synthesized markdown.
- AutoGen discussion is a domain module, not an ANet fallback path.
- Video generation stays in API/render services and uses database-backed project/session/asset context.

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
- Run gateway scenarios:
  - `npm run smoke:gateway`
