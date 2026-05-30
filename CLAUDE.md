# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SafeSight AI is a real-time workplace safety monitoring system for construction sites, warehouses, and manufacturing floors. It ingests video from files, webcams, or RTSP streams and detects violations: missing PPE (hardhats, vests, gloves, goggles), restricted-zone intrusions, vehicle-pedestrian proximity, fall detection, and unsafe behaviours. Detections are tracked per-person across frames, stored with snapshots and OSHA rule references in a database, and surfaced via a FastAPI backend and React dashboard with multi-channel alerting.

**Status: active development.** Core pipeline, API, dashboard, severity levels, and webhook alerting are complete. Next: authentication and organisations (Phase 1).

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Requires Python 3.10+. Node 18+ for the frontend.

## Running the code

```powershell
# Pipeline
python -m src.pipeline --source data/input_videos/sample.mp4 --config config/zones.json

# API
uvicorn src.api.main:app --reload --port 8000   # docs at localhost:8000/docs

# Dashboard
cd frontend && npm install && npm run dev

# Full stack (Docker)
docker compose up --build
```

## Architecture

```
Video source → Frame reader → YOLO26 → ByteTrack → Rules engine → Event store → FastAPI → React
(file/cam/RTSP) (threaded)  (detect)  (track IDs)  (PPE+zones)   (Postgres)  (REST/WS) (dashboard)
                                                          ▲               ↓
                                                     zones.json     Notifications
                                                                  (Email/SMS/Slack/Teams)
```

Key design decisions:

- **Threaded frame reader**: RTSP latency is absorbed by a background thread with a bounded queue so inference runs at a steady rate.
- **Detection and tracking are separate**: YOLO26 detects per-frame; ByteTrack assigns persistent IDs across frames. Without tracking, a violation would fire 30× per second per person.
- **Rules engine operates on tracked objects**: Checks PPE presence and bounding-box overlap with zone polygons per-frame, emits events only on state transitions (N consecutive frames = one event).
- **Severity**: `zone_intrusion` → CRITICAL, `missing_ppe` → WARNING. Carried through debouncer, persisted in DB, shown in dashboard.
- **OSHA rule engine**: Every violation maps to an OSHA regulation code with fine estimate and recommendation.
- **Zones are JSON-configured**: Operators define keep-out polygons and per-zone PPE requirements in `config/zones.json` with no code changes.
- **Event debouncing is per person ID**: Each person-ID tracks its own violation state independently.

## Zone configuration format

```json
{
  "required_ppe": ["hardhat", "vest"],
  "zones": [
    {
      "id": "forklift_lane",
      "name": "Forklift travel lane",
      "polygon": [[120, 400], [560, 400], [560, 480], [120, 480]],
      "rule": "no_entry"
    },
    {
      "id": "weld_area",
      "name": "Welding bay",
      "polygon": [[300, 100], [500, 100], [500, 300], [300, 300]],
      "rule": "require_ppe",
      "required_ppe": ["hardhat", "vest", "face_shield"]
    }
  ]
}
```

## Product roadmap

### Completed
- Video source abstraction (file / webcam / RTSP / IP camera)
- Threaded frame reader with bounded queue
- YOLO26 inference wrapper + SAHI sliced inference
- ByteTrack integration with persistent person IDs
- Rules engine: PPE checks + zone intrusion (point-in-polygon)
- Per-ID event debouncing
- SQLite event store + snapshot writer
- FastAPI REST endpoints (events, zones, stats, health)
- WebSocket live event stream
- React dashboard: live feed, event log, severity filters
- Zone editor (draw polygons on frame)
- Severity levels (CRITICAL / WARNING) on violations and events
- Webhook alerter with exponential-backoff retry
- Performance benchmarking
- Dockerfile + docker-compose
- Fine-tuning infrastructure (scripts/train.py, scripts/download_dataset.py)

### Phase 1 — Authentication & Organisations
- User model: email, hashed password, role, org_id
- JWT auth endpoints: register, login, refresh
- Organisations and sites tables (one org → many sites → many cameras)
- RBAC: Safety Officer, Site Manager, Executive, Auditor
- React auth flow: login/register pages, protected routes, role-aware nav

### Phase 2 — Multi-Channel Notifications
- Email alerts via SMTP / SendGrid (HTML template with snapshot embed)
- SMS via Twilio
- Slack via Incoming Webhooks (Block Kit card)
- Microsoft Teams via Adaptive Cards
- Per-user notification preferences (channels, minimum severity, quiet hours)
- Alert deduplication (no repeat notifications for the same open event)
- Dashboard settings page for configuring channels

### Phase 3 — OSHA Rule Engine
- OSHA regulation database (config/osha_rules.json): code, description, fine range, recommendation
- Rule matcher: maps (violation_type, missing_ppe, zone_rule) → OSHA codes
- Enrich events with osha_codes, fine_estimate_usd, recommendation
- Violation detail panel: OSHA card, confidence %, annotated snapshot, plain-English explanation

### Phase 4 — Explainability & Evidence
- Confidence score propagated from detector through to API and dashboard
- Reason breakdown: structured list of why a violation was flagged
- Annotated snapshot viewer with bounding boxes per detection class
- Plain-English explanation sentence generated per event

### Phase 5 — Safety Timeline
- Chronological timeline view grouped by hour (replaces flat event list)
- Supervisor intervention notes (Site Manager role can add manual entries)
- Timeline PDF export for compliance folders
- Incident story: highlight violation runs by the same person

### Phase 6 — Analytics & Safety Score
- Analytics API: violations grouped by day/week/type/zone/worker
- Safety score algorithm: per-category compliance rates → weighted composite 0–100
- Safety score history table, recalculated nightly via background job
- Analytics dashboard page: line chart (violations/day), bar chart (by type), safety score gauge
- Trend analysis: flag week-over-week increases > 20%

### Phase 7 — Heatmaps
- Site map image upload per site (floor plan PNG/JPG)
- Violation centroid coordinates stored per event
- Server-side heatmap generation (Gaussian density overlay on site map)
- Heatmap API endpoint returning PNG
- Dashboard heatmap tab with colour key (red/yellow/green)

### Phase 8 — Multi-Site Dashboard
- Organisation overview: site cards with live violation count, safety score, status badge
- Cross-site metrics: violations per worker, per site per day, org safety score
- Site switcher in nav; all pages scope to selected site
- Weekly org safety digest email across all sites

### Phase 9 — Incident Resolution Workflow
- Incident state machine: detected → assigned → investigating → resolved → closed
- Assignment to users with Site Manager / Safety Officer role
- Activity log: every status change recorded with timestamp and user
- Resolution notes field
- Workflow filters in dashboard
- SLA tracking: configurable time-to-resolution targets per severity, overdue flags

### Phase 10 — Extended Detection Categories
- Vehicle detection: forklift, truck, excavator, scissor lift
- Forklift-pedestrian proximity alert (CRITICAL when bboxes within N pixels)
- Behavior detection: running, climbing improperly
- Fall detection: aspect-ratio flip heuristic + pose model; auto-triggers SMS regardless of preferences
- Hazard detection: open trench, unsecured ladder, scaffolding without guardrail
- OSHA rules for all new categories (1926.600 vehicles, 1926.502 fall protection)
- Per-zone detection category config (operators enable/disable categories per zone)

### Phase 11 — Production Infrastructure
- PostgreSQL migration from SQLite (alembic migrations, asyncpg connection pool)
- Redis pub/sub replacing in-process WebSocket broadcaster (enables horizontal scaling)
- Background job queue (arq) for nightly scores, weekly emails, heatmap pre-generation
- GitHub Actions CI: pytest + tsc on every PR; Docker image build + push on merge to main
- Cloud deployment: separate containers for api, worker, frontend, postgres, redis
- Prometheus metrics + Grafana dashboard (request latency, pipeline FPS, queue depth)
- S3 / compatible storage for snapshots (signed URLs, MinIO for local dev)
- Per-organisation API keys and rate limiting

## Coding conventions

- Type hints on all function signatures.
- Keep individual files under 250 lines; split into submodules if a file grows beyond that.
- Prefer `@dataclass` over plain dicts for structured data (events, detections, zone config).
- All new modules go in `src/` with a corresponding test file in `tests/`.
- Use `pathlib.Path` instead of `os.path` for all file path handling.
- Log via the `logging` module, not `print()`.
- Before committing, run `python -m pytest tests/ -v`.

## Working style

- When a roadmap item is complete, check the box and commit.
- Before adding a new dependency, confirm it first.
- YOLO26 is the detector — not YOLOv8. Base weights are `yolo26s.pt` (auto-downloads from Ultralytics). PPE detection requires fine-tuned weights; zone intrusion works with the base model.
