# SafeSight AI

Real-time workplace safety monitoring with computer vision. SafeSight ingests video from files, webcams, or RTSP streams and continuously checks for two classes of safety violations: **missing PPE** (hardhats, high-vis vests) and **restricted-zone intrusions** (people entering operator-defined keep-out areas). Detections are tracked across frames so each person gets a persistent ID, violations are debounced per-person so a single incident produces a single event, and every event is stored with a timestamp, frame snapshot, and zone metadata in a queryable database. A FastAPI backend exposes the event stream over REST and WebSockets, and a React dashboard lets safety operators review the live feed, filter historical events, and configure zones.

> Status: in development. Currently building the inference pipeline. See the roadmap at the bottom.

## Why this exists

In construction zones, warehouses, labs, and manufacturing floors, safety compliance is enforced by humans walking around with clipboards. Real incidents — a worker stepping into a forklift lane, someone entering a chemical area without a respirator — happen in seconds, but audits are reactive and sample only what an inspector happens to see. SafeSight runs continuously on existing camera infrastructure, surfaces violations as they happen, and produces an auditable log for compliance reviews.

This is a working prototype of the same problem that companies like Intenseye, Protex AI, and Voxel solve at industrial scale.

## Architecture

```
Video source ─▶ Frame reader ─▶ YOLOv8 ─▶ ByteTrack ─▶ Rules engine ─▶ Event store ─▶ FastAPI ─▶ React
 (file/cam/RTSP)  (threaded)    (detection) (tracking)   (PPE + zones)    (SQLite)     (REST/WS)   (dashboard)
                                                              ▲
                                                              │
                                                         zones.json
                                                       (operator config)
```

Each stage is a discrete module so they can be swapped or tested independently. Key design decisions:

- **Threaded frame reader.** RTSP streams introduce variable latency. Reading frames on a background thread with a small bounded queue keeps inference running at a steady rate and drops frames gracefully when the network is slow.
- **Detection + tracking are separate.** YOLOv8 detects what's in a single frame. ByteTrack assigns a persistent ID across frames using IoU + motion prediction. Without tracking, a person standing still would log a "missing hardhat" violation 30 times per second. With tracking, each person has one ID and one event per incident.
- **Rules engine consumes tracked objects, not raw detections.** The rules engine sees a stable list of people-with-IDs, each tagged with their detected PPE and bounding box. It checks two things: does this person have required PPE for the active rule set, and does their bounding box overlap any restricted zone polygon. Both checks happen per-frame, but events are only emitted when state *transitions* (no-hardhat → no-hardhat for N consecutive frames triggers; clearing the violation closes it).
- **Zones are JSON-configurable.** Operators define keep-out polygons and PPE requirements in a config file. No code changes to add a new zone.
- **SQLite + snapshot files.** Each event row stores the timestamp, person ID, violation type, zone ID, bounding box, and the path to a JPEG snapshot of the frame at the moment of detection. Snapshots make the dashboard reviewable; the database makes it queryable.

## Tech stack

| Layer            | Choice                          | Why                                          |
| ---------------- | ------------------------------- | -------------------------------------------- |
| Detection        | YOLOv8 (Ultralytics)            | State of the art, fast, good Python tooling  |
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
- A YOLO weights file (the app downloads `yolov8n.pt` on first run; PPE-specific weights go in `models/`)

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

- [x] Project scaffolding, README, architecture
- [x] Video source abstraction (file / webcam / RTSP)
- [x] Threaded frame reader with bounded queue
- [ ] YOLOv8 inference wrapper
- [ ] ByteTrack integration with persistent IDs
- [ ] Rules engine: PPE checks
- [ ] Rules engine: zone intrusion (point-in-polygon)
- [ ] Per-ID event debouncing
- [ ] SQLite event store + snapshot writer
- [ ] FastAPI REST endpoints (events, zones, stats)
- [ ] WebSocket live event stream
- [ ] React dashboard: live view + event log
- [ ] React dashboard: zone editor (draw polygons on frame)
- [ ] Performance benchmarking (FPS on CPU vs GPU, model size tradeoff)
- [ ] Dockerfile for one-command deploy

## License

MIT