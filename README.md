# SafeSight AI

Real-time construction safety intelligence. SafeSight ingests video from files, webcams, or RTSP streams and detects PPE violations, restricted-zone intrusions, vehicle-pedestrian proximity hazards, near-misses, and unsafe behaviours. Every detection is tracked per-person, stored with a snapshot and OSHA rule reference, and surfaced through a FastAPI backend and React dashboard with multi-channel alerting, predictive risk scoring, natural-language safety investigation, automated root-cause analysis, and a site replay system.

> Status: active development. Phase 1 (auth, organisations, RBAC) complete. Run with `python -m src.pipeline --source YOUR_SOURCE`. Train a custom PPE model with `scripts/train.py`.

## Why this exists

Most CCTV safety platforms answer one question: *did a violation happen?* SafeSight is built to answer harder questions: *why is risk increasing, what is about to go wrong, and what should we do about it?*

Construction safety compliance is currently enforced by humans with clipboards. Audits are reactive and sample only what an inspector happens to see. SafeSight runs continuously on existing camera infrastructure, surfaces violations the moment they occur, predicts where risk is building before an incident happens, and produces the auditable, explainable evidence that compliance reviews and insurance carriers require.

The goal is not to be another object-detection wrapper. The goal is to be the safety intelligence platform that construction firms, insurers, and regulators actually rely on — the system that answers *"are we currently compliant, and what happens tomorrow if we don't change anything?"*

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
- [x] Rules engine: PPE checks + zone intrusion (point-in-polygon)
- [x] Per-ID event debouncing
- [x] SQLite event store + snapshot writer
- [x] FastAPI REST endpoints (events, zones, stats, health)
- [x] WebSocket live event stream
- [x] React dashboard: live view, event log, severity filters
- [x] Zone editor (draw polygons on frame)
- [x] Severity levels (CRITICAL / WARNING) on violations and events
- [x] Webhook alerter with exponential-backoff retry
- [x] Performance benchmarking (FPS on CPU vs GPU, model size tradeoff)
- [x] Dockerfile + docker-compose for one-command deploy
- [x] Fine-tuning infrastructure (download dataset, train, benchmark)
- [x] **Phase 1 — Authentication & Organisations**
  - [x] JWT auth (register, login, refresh, /me)
  - [x] Organisations and sites tables
  - [x] RBAC: Safety Officer, Site Manager, Executive, Auditor
  - [x] React login/register pages, protected routes, role badge, sign-out

---

### Phase 2 — Multi-Channel Notifications
*Extend the existing webhook alerter to reach operators wherever they are.*
- [ ] Email alerts via SMTP / SendGrid — HTML template with snapshot embed, OSHA reference, severity badge
- [ ] SMS via Twilio — short critical-only message for CRITICAL events
- [ ] Slack via Incoming Webhooks — Block Kit card with snapshot, zone, severity, quick-link to dashboard
- [ ] Microsoft Teams via Adaptive Cards — same data as Slack, formatted for Teams
- [ ] Per-user notification preferences: channels enabled, minimum severity threshold, quiet hours
- [ ] Alert deduplication: no repeat notifications for the same open event
- [ ] Dashboard settings page for configuring all channels per user

---

### Phase 3 — Predictive Risk Engine
*Move from detection → prediction. Most competitors can't do this.*
- [ ] Violation frequency trend tracker: count violations per zone/worker/type over rolling time windows
- [ ] Repeat offender detection: flag workers with 3+ violations in a configurable window
- [ ] Zone risk scoring: zones ranked by violation density, time-of-day patterns, and recent trend direction
- [ ] Rising-risk alerts: notify Safety Officer when a zone's violation rate increases >20% week-over-week
- [ ] Congestion monitoring: flag when person density in a restricted area crosses a threshold
- [ ] Risk dashboard: live risk level per zone (ELEVATED / HIGH / CRITICAL) with trend arrows
- [ ] Risk history table for trend charting and insurance reporting

---

### Phase 4 — OSHA Rule Engine & AI Safety Consultant
*Every violation becomes actionable, not just logged.*
- [ ] OSHA regulation database (`config/osha_rules.json`): code, title, description, fine range, severity
- [ ] Rule matcher: maps `(violation_type, missing_ppe, zone_rule)` → matching OSHA codes
- [ ] Enrich events: `osha_codes`, `fine_estimate_usd`, `recommendation`, `estimated_resolution_time`
- [ ] Corrective action plans: step-by-step remediation generated per violation type
- [ ] "How similar sites resolved this" context pulled from anonymised resolution history
- [ ] Violation detail panel: OSHA card, confidence %, annotated snapshot, plain-English explanation
- [ ] Recommended supervisor notification surfaced automatically per violation class

---

### Phase 5 — AI Safety Copilot
*Natural language safety investigation. ChatGPT for your construction site.*
- [ ] LLM integration (Claude API) with the full event + analytics + OSHA dataset as context
- [ ] Natural language query endpoint: `POST /copilot/ask` → structured answer with evidence
- [ ] Example queries the system can answer:
  - "Why did the safety score drop this week?"
  - "Show me every ladder violation near the west scaffold between 6 AM and 9 AM"
  - "Which workers have the most repeated PPE violations?"
  - "What is the highest-risk zone right now and why?"
  - "Summarise this week's incidents for a board report"
- [ ] Chat-style UI panel in the dashboard
- [ ] Source citations: every answer links back to the specific events it reasoned over
- [ ] Role-aware responses: Executive gets a summary, Safety Officer gets full evidence

---

### Phase 6 — Explainability & Evidence
*Companies don't trust "AI said so." Show them exactly why.*
- [ ] Confidence score propagated from detector through violations → events → API → dashboard
- [ ] Reason breakdown: structured list explaining every flag ("Person detected", "Hardhat class not found within bounding box", "OSHA 1926.100 triggered")
- [ ] Annotated snapshot viewer: bounding boxes rendered per detection class in the detail panel
- [ ] Plain-English explanation sentence auto-generated per event
- [ ] Evidence export: one-click PDF of the event with snapshot, reason chain, OSHA reference, timestamp

---

### Phase 7 — Near-Miss Detection
*Detect the incidents that never get reported. Insurance companies care deeply about these.*
- [ ] Forklift-pedestrian proximity: CRITICAL when bounding boxes come within N pixels without contact
- [ ] Zone entry + safe exit logging: person enters restricted zone and leaves without incident — logged as near-miss
- [ ] Trajectory-based hazard prediction: extrapolate paths of person + vehicle to flag likely collision courses
- [ ] Near-miss severity scoring: distance, speed, zone type → LOW / MEDIUM / HIGH near-miss rating
- [ ] Separate near-miss event type in DB, dashboard, and notifications
- [ ] Near-miss trend reporting: "14 near-misses this week, up from 6 last week"
- [ ] Insurance-ready near-miss export with full evidence chain

---

### Phase 8 — Safety Timeline & Compliance Autopilot
*Turn raw detections into a story. Show real-time compliance status at a glance.*

**Safety Timeline**
- [ ] Chronological timeline view grouped by hour — violations, near-misses, supervisor interventions in one feed
- [ ] Supervisor intervention notes: Site Manager can manually annotate the timeline
- [ ] Incident story: highlight multi-event sequences involving the same worker
- [ ] Timeline PDF export for compliance folders and audits

**Compliance Autopilot**
- [ ] Live compliance status panel: PPE compliance %, zone compliance %, overall PASS / FAIL
- [ ] Predicted compliance for tomorrow based on current trends
- [ ] Compliance history graph: daily PASS/FAIL status over rolling 30 days
- [ ] Instant compliance snapshot exportable for regulator visits

---

### Phase 9 — Automated Root Cause Analysis
*Tell management where to intervene, not just what went wrong.*
- [ ] Time-of-day correlation: detect when violations cluster (shift changes, lunch, end of day)
- [ ] Location correlation: identify which areas produce the most violations relative to foot traffic
- [ ] Worker-type correlation: temporary vs. permanent staff, subcontractor crew breakdowns
- [ ] Root cause summary auto-generated per site per week ("68% of violations occurred during shift changes")
- [ ] Intervention recommendations: suggested policy changes based on root cause patterns
- [ ] Root cause dashboard: bar charts of violation breakdown by time / location / worker type

---

### Phase 10 — Analytics, Safety Score & Heatmaps
*Give management the numbers they need to prove improvement over time.*

**Analytics**
- [ ] Analytics API: violations grouped by day / week / type / zone / worker
- [ ] Most common violations, trend analysis, week-over-week comparison
- [ ] Violations per worker, violations per site per day

**Safety Score**
- [ ] Score algorithm: per-category compliance rates → weighted composite 0–100
- [ ] Score history table, recalculated nightly via background job
- [ ] Safety score gauge, 7-day trend arrow, per-category breakdown (Helmet 97%, Vest 92%, Zones 100%)

**Heatmaps**
- [ ] Site map image upload per site (floor plan PNG/JPG)
- [ ] Violation centroid coordinates stored per event
- [ ] Server-side heatmap generation (Gaussian density overlay on site map)
- [ ] Separate layers: violations / near-misses / highest-risk periods
- [ ] Dashboard heatmap tab with colour key (red / yellow / green)

---

### Phase 11 — Multi-Site Dashboard & Incident Workflow
*Sell to companies, not individual sites.*

**Multi-Site Dashboard**
- [ ] Organisation overview: site cards with live violation count, safety score, status badge (green / amber / red)
- [ ] Cross-site metrics: violations per worker, per site per day, org-wide safety score
- [ ] Site switcher in nav; all pages scope to selected site
- [ ] Weekly org safety digest email summarising all sites

**Incident Resolution Workflow**
- [ ] Incident state machine: detected → assigned → investigating → resolved → closed
- [ ] Assignment to Site Manager / Safety Officer
- [ ] Activity log: every status change recorded with timestamp and user
- [ ] Resolution notes, corrective action taken
- [ ] Workflow filters in dashboard
- [ ] SLA tracking: configurable time-to-resolution targets per severity, overdue flags surfaced to Executive

---

### Phase 12 — Digital Safety Twin & Site Replay
*The feature no competitor is close to having.*
- [ ] Site model: map camera positions and fields-of-view onto a site floor plan
- [ ] Worker position tracking: store anonymised centroid positions per tracked person per frame (1 FPS)
- [ ] Equipment position tracking: vehicles and machinery tracked on the same model
- [ ] Site replay: scrub back to any timestamp and replay worker + vehicle movement overlaid on the floor plan
- [ ] "Show me what happened at 2:47 PM yesterday" — query by timestamp, replay from that point
- [ ] Hazard development visualisation: watch how a near-miss developed over the preceding 30 seconds
- [ ] Replay export: MP4 render of the site model replay for incident reports and insurance claims
- [ ] Retention policy: configurable days of position history kept per site

---

### Phase 13 — Extended Detection Categories
*The wider the safety coverage, the stronger the moat.*
- [ ] Vehicle detection: forklift, truck, excavator, scissor lift (separate YOLO26 fine-tune)
- [ ] Fall detection: aspect-ratio flip heuristic + pose model; auto-triggers SMS regardless of preferences
- [ ] Behaviour detection: running, climbing improperly, phone use in restricted area
- [ ] Hazard detection: open trench, unsecured ladder, scaffolding without guardrail
- [ ] OSHA rules for all new categories (1926.600 vehicles, 1926.502 fall protection)
- [ ] Per-zone detection category config: operators enable / disable categories per zone

---

### Phase 14 — Production Infrastructure
*Make it ready for 500 sites running simultaneously.*
- [ ] PostgreSQL migration from SQLite (alembic migrations, asyncpg connection pool)
- [ ] Redis pub/sub replacing in-process WebSocket broadcaster — enables horizontal API scaling
- [ ] Background job queue (arq) for nightly safety scores, weekly digest emails, heatmap pre-generation, site replay rendering
- [ ] GitHub Actions CI: pytest + tsc on every PR; Docker image build and push on merge to main
- [ ] Cloud deployment: separate containers for api, worker, frontend, postgres, redis
- [ ] Prometheus metrics + Grafana dashboard: request latency, pipeline FPS, WS connections, queue depth
- [ ] S3-compatible snapshot and replay storage with signed URLs; MinIO for local dev
- [ ] Per-organisation API keys and rate limiting (slowapi)

## License

MIT