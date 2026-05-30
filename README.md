# SafeSight AI

Real-time workplace safety monitoring with computer vision. SafeSight ingests video from files, webcams, or RTSP streams and continuously checks for two classes of safety violations: **missing PPE** (hardhats, high-vis vests) and **restricted-zone intrusions** (people entering operator-defined keep-out areas). Detections are tracked across frames so each person gets a persistent ID, violations are debounced per-person so a single incident produces a single event, and every event is stored with a timestamp, frame snapshot, and zone metadata in a queryable database. A FastAPI backend exposes the event stream over REST and WebSockets, and a React dashboard lets safety operators review the live feed, filter historical events, and configure zones.

> Status: fully functional. Run with `python -m src.pipeline --source YOUR_SOURCE`. Train a custom PPE model with `scripts/train.py`.

## Why this exists

In construction zones, warehouses, labs, and manufacturing floors, safety compliance is enforced by humans walking around with clipboards. Real incidents — a worker stepping into a forklift lane, someone entering a chemical area without a respirator — happen in seconds, but audits are reactive and sample only what an inspector happens to see. SafeSight runs continuously on existing camera infrastructure, surfaces violations as they happen, and produces an auditable log for compliance reviews.

This is a working prototype of the same problem that companies like Intenseye, Protex AI, and Voxel solve at industrial scale.

## Architecture

```
Video source ─▶ Frame reader ─▶ YOLO26 ─▶ ByteTrack ─▶ Rules engine ─▶ Event store ─▶ FastAPI ─▶ React
 (file/cam/RTSP)  (threaded)    (detection) (tracking)   (PPE + zones)    (SQLite)     (REST/WS)   (dashboard)
                                                              ▲
                                                              │
                                                         zones.json
                                                       (operator config)
```

Each stage is a discrete module so they can be swapped or tested independently. Key design decisions:

- **Threaded frame reader.** RTSP streams introduce variable latency. Reading frames on a background thread with a small bounded queue keeps inference running at a steady rate and drops frames gracefully when the network is slow.
- **Detection + tracking are separate.** YOLO26 detects what's in a single frame. ByteTrack assigns a persistent ID across frames using IoU + motion prediction. Without tracking, a person standing still would log a "missing hardhat" violation 30 times per second. With tracking, each person has one ID and one event per incident.
- **Rules engine consumes tracked objects, not raw detections.** The rules engine sees a stable list of people-with-IDs, each tagged with their detected PPE and bounding box. It checks two things: does this person have required PPE for the active rule set, and does their bounding box overlap any restricted zone polygon. Both checks happen per-frame, but events are only emitted when state *transitions* (no-hardhat → no-hardhat for N consecutive frames triggers; clearing the violation closes it).
- **Zones are JSON-configurable.** Operators define keep-out polygons and PPE requirements in a config file. No code changes to add a new zone.
- **SQLite + snapshot files.** Each event row stores the timestamp, person ID, violation type, zone ID, bounding box, and the path to a JPEG snapshot of the frame at the moment of detection. Snapshots make the dashboard reviewable; the database makes it queryable.

## Tech stack

| Layer            | Choice                          | Why                                          |
| ---------------- | ------------------------------- | -------------------------------------------- |
| Detection        | YOLO26 (Ultralytics)            | Edge-optimised, 43% faster CPU than YOLOv8, NMS-free, better small-object detection |
| Tracking         | ByteTrack                       | Strong on occlusion, lightweight             |
| Video I/O        | OpenCV                          | Standard, handles files/cameras/RTSP        |
| Backend          | FastAPI + Uvicorn               | Async, WebSocket support, OpenAPI for free  |
| Database         | SQLite + SQLAlchemy             | Zero-config, sufficient for single-site use  |
| Frontend         | React + Vite + TypeScript       | Component model fits a dashboard, fast HMR   |
| Realtime         | WebSocket                       | Push events as they happen, no polling       |
| Config           | JSON (zones, rules)             | Editable without rebuilding                  |

## Project structure

```
safesight-ai/
├── README.md
├── requirements.txt
├── config/
│   └── zones.json            # zone polygons and PPE rules
├── data/
│   ├── input_videos/         # sample inputs
│   ├── output_videos/        # annotated outputs
│   └── snapshots/            # per-event JPEG frames
├── logs/                     # app logs
├── models/                   # YOLO weights
├── src/
│   ├── __init__.py
│   ├── sources.py            # FileSource, WebcamSource, RTSPSource
│   ├── reader.py             # threaded frame reader
│   ├── detector.py           # YOLOv8 wrapper
│   ├── tracker.py            # ByteTrack wrapper
│   ├── rules.py              # PPE + zone intrusion logic
│   ├── events.py             # event dataclasses + debouncer
│   ├── store.py              # SQLite writer
│   ├── pipeline.py           # wires the stages together
│   └── api/
│       ├── main.py           # FastAPI app
│       └── ws.py             # WebSocket event stream
├── frontend/                 # React + Vite app
└── tests/
```

## Getting started

### Prerequisites
- Python 3.10+
- Node 18+ (for the dashboard)
- YOLO26 weights (auto-downloaded from Ultralytics on first run; PPE-specific weights go in `models/`)

### Install

```powershell
# from the project root
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Run the pipeline on a sample video

```powershell
python -m src.pipeline --source data/input_videos/sample.mp4 --config config/zones.json
```

### Run the API

```powershell
uvicorn src.api.main:app --reload --port 8000
```

API docs are auto-generated at `http://localhost:8000/docs`.

### Run the dashboard

```powershell
cd frontend
npm install
npm run dev
```

## Configuring zones

A `zones.json` file defines what counts as a violation. Example:

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

Polygons are pixel coordinates in the source frame.

## Roadmap

### Completed
- [x] Project scaffolding, README, architecture
- [x] Video source abstraction (file / webcam / RTSP / IP camera)
- [x] Threaded frame reader with bounded queue
- [x] YOLO26 inference wrapper + SAHI sliced inference for distant workers
- [x] ByteTrack integration with persistent person IDs
- [x] Rules engine: PPE checks
- [x] Rules engine: zone intrusion (point-in-polygon)
- [x] Per-ID event debouncing
- [x] SQLite event store + snapshot writer
- [x] FastAPI REST endpoints (events, zones, stats, health)
- [x] WebSocket live event stream
- [x] React dashboard: live view + event log
- [x] React dashboard: zone editor (draw polygons on frame)
- [x] Severity levels (CRITICAL / WARNING) on violations and events
- [x] Webhook alerter with exponential-backoff retry
- [x] Performance benchmarking (FPS on CPU vs GPU, model size tradeoff)
- [x] Dockerfile + docker-compose for one-command deploy
- [x] Fine-tuning infrastructure (download dataset, train, benchmark)

### Phase 1 — Authentication & Organisations
- [ ] User model: email, hashed password, role, org_id
- [ ] JWT auth endpoints: register, login, refresh
- [ ] Organisations and sites tables (one org → many sites → many cameras)
- [ ] RBAC: Safety Officer, Site Manager, Executive, Auditor
- [ ] React auth flow: login/register pages, protected routes, role-aware nav

### Phase 2 — Multi-Channel Notifications
- [ ] Email alerts via SMTP / SendGrid (HTML template with snapshot embed)
- [ ] SMS via Twilio
- [ ] Slack via Incoming Webhooks (Block Kit card)
- [ ] Microsoft Teams via Adaptive Cards
- [ ] Per-user notification preferences (channels, minimum severity, quiet hours)
- [ ] Alert deduplication (no repeat notifications for the same open event)
- [ ] Dashboard settings page for configuring channels

### Phase 3 — OSHA Rule Engine
- [ ] OSHA regulation database (config/osha_rules.json): code, description, fine range, recommendation
- [ ] Rule matcher: maps (violation_type, missing_ppe, zone_rule) → OSHA codes
- [ ] Enrich events with osha_codes, fine_estimate_usd, recommendation
- [ ] Violation detail panel: OSHA card, confidence %, annotated snapshot, plain-English explanation

### Phase 4 — Explainability & Evidence
- [ ] Confidence score propagated from detector through to API and dashboard
- [ ] Reason breakdown: structured list of why a violation was flagged
- [ ] Annotated snapshot viewer with bounding boxes per detection class
- [ ] Plain-English explanation sentence generated per event

### Phase 5 — Safety Timeline
- [ ] Chronological timeline view grouped by hour (replaces flat event list)
- [ ] Supervisor intervention notes (Site Manager role can add manual entries)
- [ ] Timeline PDF export for compliance folders
- [ ] Incident story: highlight violation runs by the same person

### Phase 6 — Analytics & Safety Score
- [ ] Analytics API: violations grouped by day/week/type/zone/worker
- [ ] Safety score algorithm: per-category compliance rates → weighted composite 0–100
- [ ] Safety score history table, recalculated nightly via background job
- [ ] Analytics dashboard page: line chart (violations/day), bar chart (by type), safety score gauge
- [ ] Trend analysis: flag week-over-week increases > 20%

### Phase 7 — Heatmaps
- [ ] Site map image upload per site (floor plan PNG/JPG)
- [ ] Violation centroid coordinates stored per event
- [ ] Server-side heatmap generation (Gaussian density overlay on site map)
- [ ] Heatmap API endpoint returning PNG
- [ ] Dashboard heatmap tab with colour key (red/yellow/green)

### Phase 8 — Multi-Site Dashboard
- [ ] Organisation overview: site cards with live violation count, safety score, status badge
- [ ] Cross-site metrics: violations per worker, per site per day, org safety score
- [ ] Site switcher in nav; all pages scope to selected site
- [ ] Weekly org safety digest email across all sites

### Phase 9 — Incident Resolution Workflow
- [ ] Incident state machine: detected → assigned → investigating → resolved → closed
- [ ] Assignment to users with Site Manager / Safety Officer role
- [ ] Activity log: every status change recorded with timestamp and user
- [ ] Resolution notes field
- [ ] Workflow filters in dashboard
- [ ] SLA tracking: configurable time-to-resolution targets per severity, overdue flags

### Phase 10 — Extended Detection Categories
- [ ] Vehicle detection: forklift, truck, excavator, scissor lift
- [ ] Forklift-pedestrian proximity alert (CRITICAL when bboxes within N pixels)
- [ ] Behaviour detection: running, climbing improperly
- [ ] Fall detection: aspect-ratio heuristic + pose model; auto-triggers SMS
- [ ] Hazard detection: open trench, unsecured ladder, scaffolding without guardrail
- [ ] OSHA rules for new categories (1926.600 vehicles, 1926.502 fall protection)
- [ ] Per-zone detection category config

### Phase 11 — Production Infrastructure
- [ ] PostgreSQL migration from SQLite (alembic migrations, asyncpg)
- [ ] Redis pub/sub replacing in-process WebSocket broadcaster
- [ ] Background job queue (arq) for nightly scores, weekly emails, heatmap generation
- [ ] GitHub Actions CI: pytest + tsc on every PR; Docker image push on merge
- [ ] Cloud deployment: separate containers for api, worker, frontend, postgres, redis
- [ ] Prometheus metrics + Grafana dashboard
- [ ] S3-compatible snapshot storage with signed URLs
- [ ] Per-organisation API keys and rate limiting

## License

MIT