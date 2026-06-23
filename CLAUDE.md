# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SafeSight AI is a real-time construction safety intelligence platform. It ingests video from files, webcams, or RTSP streams and detects PPE violations, restricted-zone intrusions, vehicle-pedestrian proximity hazards, near-misses, and unsafe behaviours. Every detection is tracked per-person, enriched with OSHA rule references and corrective action plans, and surfaced via a FastAPI backend and React dashboard with multi-channel alerting, predictive risk scoring, natural-language safety investigation (AI Safety Copilot), automated root-cause analysis, and a site replay system.

The goal is not to be another object-detection wrapper. SafeSight is built to answer: *"why is risk increasing, what is about to go wrong, and what should we do about it?"*

**Status: active development.** Phases 1–9 complete. Phase 10 (analytics, safety score, heatmap) in progress.

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

### Phase 1 — Authentication & Organisations ✅
- JWT auth (register, login, refresh, /me); organisations and sites tables
- RBAC: Safety Officer, Site Manager, Executive, Auditor
- React login/register pages, protected routes, role badge, sign-out

### Phase 2 — Multi-Channel Notifications
- Email (SMTP / SendGrid), SMS (Twilio), Slack (Block Kit), Teams (Adaptive Cards)
- Per-user preferences: channels, minimum severity, quiet hours; alert deduplication
- Dashboard settings page for all channels

### Phase 3 — Predictive Risk Engine
- Violation frequency trend tracker per zone / worker / type over rolling windows
- Repeat offender detection (3+ violations in configurable window)
- Zone risk scoring: violation density + time-of-day patterns + trend direction
- Rising-risk alerts when a zone's rate increases > 20% week-over-week
- Congestion monitoring in restricted areas; live risk level dashboard per zone

### Phase 4 — OSHA Rule Engine & AI Safety Consultant
- OSHA regulation database: code, description, fine range, recommendation
- Rule matcher: (violation_type, missing_ppe, zone_rule) → OSHA codes
- Enrich events with osha_codes, fine_estimate_usd, corrective action plan, estimated resolution time
- "How similar sites resolved this" context; recommended supervisor notification per violation class
- Violation detail panel: OSHA card, confidence %, annotated snapshot, plain-English explanation

### Phase 5 — AI Safety Copilot
- LLM integration (Claude API) with full event + analytics + OSHA dataset as context
- Natural language query endpoint: POST /copilot/ask → structured answer with cited evidence
- Handles: "Why did the safety score drop?", "Which workers keep violating PPE?", "What's the highest-risk zone?"
- Chat-style UI panel; role-aware responses (Executive gets summary, Safety Officer gets full evidence)

### Phase 6 — Explainability & Evidence
- Confidence score from detector propagated through to API and dashboard
- Reason breakdown: structured explanation list per event
- Annotated snapshot viewer: bounding boxes per detection class
- Evidence export: one-click PDF with snapshot, reason chain, OSHA reference, timestamp

### Phase 7 — Near-Miss Detection
- Forklift-pedestrian proximity: CRITICAL when bboxes within N pixels without contact
- Zone entry + safe exit logged as near-miss (captures unreported events)
- Trajectory-based hazard prediction: extrapolate paths to flag likely collisions
- Near-miss severity scoring; separate event type; insurance-ready export

### Phase 8 — Safety Timeline & Compliance Autopilot
- Chronological timeline grouped by hour: violations, near-misses, supervisor notes in one feed
- Supervisor intervention notes; incident story for multi-event sequences; PDF export
- Live compliance status: PPE %, zone %, overall PASS / FAIL
- Predicted compliance for tomorrow based on current trends; compliance history graph

### Phase 9 — Automated Root Cause Analysis ✅
- Time-of-day correlation: detect when violations cluster (shift changes, lunch, end of day)
- Location correlation: zone hotspot analysis with peak hours per zone
- Worker behaviour segmentation: isolated / recurring / chronic offenders with time + zone affinity
- Root cause summary auto-generated per site per week; intervention recommendations
- Note: worker-type (temp/perm/subcontractor) requires HR system integration — out of scope for vision-only detection

### Phase 10 — Analytics, Safety Score & Heatmaps
- Analytics API: violations by day / week / type / zone / worker; trend charts
- Safety score 0–100: per-category compliance rates → weighted composite; nightly recalc
- Heatmap: site map upload, Gaussian density overlay, separate layers (violations / near-misses)
- Safety score gauge, 7-day trend arrow, per-category breakdown

### Phase 11 — Multi-Site Dashboard & Incident Workflow
- Organisation overview: site cards with live count, safety score, status badge
- Cross-site metrics; site switcher; weekly org safety digest email
- Incident state machine: detected → assigned → investigating → resolved → closed
- Activity log, resolution notes, SLA tracking, overdue flags

### Phase 12 — Digital Safety Twin & Site Replay
- Site model: camera positions and fields-of-view mapped onto a floor plan
- Worker and equipment position tracking stored at 1 FPS
- Site replay: scrub to any timestamp and replay movement overlaid on the floor plan
- Hazard development visualisation; MP4 replay export; configurable retention policy

### Phase 13 — Extended Detection Categories
- Vehicle detection: forklift, truck, excavator, scissor lift (separate YOLO26 fine-tune)
- Fall detection: aspect-ratio heuristic + pose model; auto-triggers SMS
- Behaviour detection: running, climbing improperly, phone use in restricted area
- Hazard detection: open trench, unsecured ladder, scaffolding without guardrail
- OSHA rules for all new categories; per-zone detection category config

### Phase 14 — Production Infrastructure
- PostgreSQL migration (alembic, asyncpg); Redis pub/sub for horizontal WS scaling
- Background job queue (arq): nightly scores, weekly emails, heatmaps, replay rendering
- GitHub Actions CI; cloud deployment (api, worker, frontend, postgres, redis containers)
- Prometheus + Grafana; S3-compatible snapshot and replay storage; API keys + rate limiting

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
