# Yinanping Studio

Hybrid bootstrap monorepo for the "意难平剧组" product.

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
- `CORS_ORIGIN`: allowed web origin (set explicitly in non-demo environments)
- `SESSION_STORE_PATH`: persisted session store path
- `IOPHO_SCRIPT_PATH`: optional storyboard script path
- `DISCUSSION_ENGINE_MODE`: `template` (default) or `distilled`
- `DEMO_CLIP_SECONDS`: output mp4 clip length for demo render
- `VITE_API_BASE`: optional web-side API origin (e.g. `http://localhost:3567`); leave empty to use same-origin `/api` (Vite dev proxy / production reverse proxy)

Local dev defaults:

- `npm run dev:web` proxies `/api/*` to `http://localhost:3567`
- Set `VITE_API_BASE` only when web and API are intentionally cross-origin

## Optional iopho integration

Set `IOPHO_SCRIPT_PATH` to the absolute path of:

- `skills/iopho-analyzing-videos/scripts/video_to_storyboard.py`

If the script is unavailable or fails, API falls back to a placeholder artifact for demo continuity.

If `sourceVideoPath` is provided and valid, API now creates a real source-preview artifact before optional storyboard analysis.

## Demo mp4 pipeline

- API `render` stage attempts a real `ffmpeg` export to `tmp-artifacts/<jobId>/output.mp4`.
- If `ffmpeg` fails but source file is readable, API falls back to source-copy mp4 for demo continuity.
- Artifacts are exposed via `GET /api/artifacts/...`, and web result panel can play returned `publicUrl`.
- Web now supports browser file upload (`POST /api/uploads`) and then binds uploaded media to `/api/video-jobs` via `sourceVideoUploadId`.

## Agent Network gateway

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

## ANet full integration runbook

### 1) Prepare daemon and Python environment

1. Install and start daemon:
   - `anet --version`
   - `anet daemon`
   - `anet whoami`
2. Install Python dependencies:
   - `cd anet-services`
   - `pip install -r requirements.txt`
3. Start agent services (Windows):
   - `powershell -ExecutionPolicy Bypass -File .\\start_agents.ps1`
4. Optional helper scripts (Windows):
   - `powershell -ExecutionPolicy Bypass -File .\\setup_windows.ps1`
   - `powershell -ExecutionPolicy Bypass -File .\\run_local_demo.ps1`

### 2) Register services to daemon

- `cd anet-services`
- `python register_agents.py`
- Optional smoke:
  - `python test_call.py`

Expected: 4 services (`yinanping-composer/editor/director/collector`) are discoverable.

### 3) Start API and web

1. Back to repo root and set env:
   - `ANET_BASE=http://127.0.0.1:3998`
2. Start backend:
   - `npm run dev:api`
3. Start frontend:
   - `npm run dev:web`

When ANet discover/call is healthy:
- `/api/sessions/:id/discussion/stream` dispatches calls to `director/composer/editor/collector`.
- API emits invocation events (`calling` / `ok` / `failed`) into `/api/gateway/invocations/events`.
- Web D3 graph flashes links for each cross-node invocation.

### 4) Troubleshooting

- `discover` returns empty:
  - Ensure all 4 Python services are alive (`/health` endpoints).
  - Re-run `python register_agents.py`.
- API cannot reach daemon:
  - Check `ANET_BASE` and `curl http://127.0.0.1:3998/api/status`.
- Invocation stream is degraded:
  - Verify API is running and browser can reach `/api/gateway/invocations/events`.
  - ANet failures are auto-fallbacked to local gateway capabilities for demo continuity.

## Distillation and smoke scripts

- Run distilled vs template evaluation:
  - `npm run distill:eval`
- Run pipeline smoke scenarios:
  - `npm run smoke:video`
  - Optional: set `SMOKE_VIDEO_PATH` to enable real-path scenarios.
- Run gateway chaos/fallback scenarios:
  - `npm run smoke:gateway`
