# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SafeSight AI is a real-time workplace safety monitoring system. It ingests video from files, webcams, or RTSP streams and detects two violation classes: **missing PPE** (hardhats, high-vis vests) and **restricted-zone intrusions**. Detections are tracked per-person across frames and stored with snapshots in SQLite, then surfaced via a FastAPI backend and React dashboard.

**Status: early development.** Only project scaffolding and the README exist. No pipeline modules have been implemented yet. The roadmap in `README.md` is the source of truth for what's next.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Requires Python 3.10+. Node 18+ needed when building the frontend (not yet started).

## Running the code

When `src/pipeline.py` exists, the intended entry point will be:

```powershell
python -m src.pipeline --source data/input_videos/sample.mp4 --config config/zones.json
```

Planned API and frontend commands (modules not yet built):

```powershell
uvicorn src.api.main:app --reload --port 8000   # API docs at localhost:8000/docs
cd frontend && npm install && npm run dev         # React dashboard
```

## Architecture

The pipeline is a linear chain of discrete modules, each independently testable:

```
Video source → Frame reader → YOLOv8 → ByteTrack → Rules engine → Event store → FastAPI → React
(file/cam/RTSP) (threaded)  (detect)  (track IDs)  (PPE+zones)   (SQLite)    (REST/WS) (dashboard)
                                                          ▲
                                                     zones.json
```

**Key design decisions:**

- **Threaded frame reader** (`src/reader.py`, not yet built): RTSP latency is absorbed by a background thread with a bounded queue so inference runs at a steady rate.
- **Detection and tracking are separate**: `src/detector.py` wraps YOLOv8 for per-frame detection; `src/tracker.py` (not yet built) wraps ByteTrack to assign persistent person IDs across frames. Without tracking, a violation would fire 30 times/second per person.
- **Rules engine operates on tracked objects, not raw detections**: After tracking assigns stable IDs, the rules engine (`src/rules.py`, not yet built) checks PPE presence and bounding-box overlap with zone polygons per-frame, but emits events only on state *transitions* (N consecutive frames in violation = one event).
- **Zones are JSON-configured**: Operators define keep-out polygons and per-zone PPE requirements in `config/zones.json` — no code changes to add a zone. Polygons are pixel coordinates in the source frame.
- **Event debouncing is per person ID**: Each person-ID tracks its own violation state so simultaneous violations from multiple people are independent.

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

## Implementation status

Nothing beyond project scaffolding (`README.md`, `requirements.txt`, directory structure, `src/__init__.py`) has been built. All pipeline modules are unstarted. See the roadmap in `README.md` for the intended build order.

## Coding conventions

- Type hints on all function signatures.
- Keep individual files under 250 lines; split into submodules if a file grows beyond that.
- Prefer `@dataclass` over plain dicts for structured data (events, detections, zone config).
- All new modules go in `src/` with a corresponding test file in `tests/`.
- Use `pathlib.Path` instead of `os.path` for all file path handling.
- Log via the `logging` module, not `print()`.
- Before committing, run any tests that exist: `python -m pytest tests/ -v` (the venv python is on PATH when activated).

## Working style

- Before writing code for a new module, propose the interface (function signatures, classes, types) and wait for approval.
- When a roadmap item from `README.md` is complete, check the box in `README.md` and prompt to commit.
- Before adding a new dependency, mention it and wait for a decision.
