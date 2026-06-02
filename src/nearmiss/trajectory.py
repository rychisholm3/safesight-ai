"""
Trajectory tracking and collision prediction for near-miss detection.

TrajectoryTracker maintains a rolling window of centre-point positions per
track_id and extrapolates each track's path forward to predict whether two
tracks will converge within a configurable distance threshold.
"""
import math
from collections import deque

# How many past positions to keep per track (about 10 frames = ~0.3 s at 30 fps)
_HISTORY_LEN = 15


class TrajectoryTracker:
    """
    Stateful position-history store with linear-velocity extrapolation.

    Call :meth:`update` once per frame for every tracked person.
    Call :meth:`time_to_convergence` to check if two tracks are predicted
    to collide within *frames_ahead* frames.
    """

    def __init__(self, history_len: int = _HISTORY_LEN) -> None:
        self._history_len = history_len
        # track_id → deque of (cx, cy) positions
        self._positions: dict[int, deque[tuple[float, float]]] = {}

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, track_id: int, bbox: tuple[int, int, int, int]) -> None:
        """Record the centre-point of *bbox* for *track_id*."""
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        if track_id not in self._positions:
            self._positions[track_id] = deque(maxlen=self._history_len)
        self._positions[track_id].append((cx, cy))

    def evict_stale(self, active_track_ids: set[int]) -> None:
        """Remove history for tracks that are no longer being tracked."""
        stale = [tid for tid in self._positions if tid not in active_track_ids]
        for tid in stale:
            del self._positions[tid]

    # ── Prediction ────────────────────────────────────────────────────────────

    def _velocity(self, track_id: int) -> tuple[float, float] | None:
        """Return average (vx, vy) pixels/frame from recent history, or None."""
        hist = self._positions.get(track_id)
        if hist is None or len(hist) < 2:
            return None
        # Use last min(5, len) positions for a smoother velocity estimate
        recent = list(hist)[-5:]
        n = len(recent)
        if n < 2:
            return None
        vx = (recent[-1][0] - recent[0][0]) / (n - 1)
        vy = (recent[-1][1] - recent[0][1]) / (n - 1)
        return vx, vy

    def predict_position(
        self, track_id: int, frames_ahead: int
    ) -> tuple[float, float] | None:
        """
        Extrapolate where *track_id* will be in *frames_ahead* frames.
        Returns None if there is insufficient history.
        """
        hist = self._positions.get(track_id)
        if hist is None or len(hist) < 2:
            return None
        vel = self._velocity(track_id)
        if vel is None:
            return None
        cx, cy = hist[-1]
        return cx + vel[0] * frames_ahead, cy + vel[1] * frames_ahead

    def time_to_convergence(
        self,
        id_a: int,
        id_b: int,
        threshold_px: float,
        frames_ahead: int,
        min_history: int = 3,
    ) -> int | None:
        """
        Return the earliest future frame (1…frames_ahead) at which the two
        tracks are predicted to be within *threshold_px* of each other,
        or None if no convergence is predicted in that window.

        Both tracks must have at least *min_history* positions recorded.
        """
        hist_a = self._positions.get(id_a)
        hist_b = self._positions.get(id_b)
        if (hist_a is None or len(hist_a) < min_history or
                hist_b is None or len(hist_b) < min_history):
            return None

        vel_a = self._velocity(id_a)
        vel_b = self._velocity(id_b)
        if vel_a is None or vel_b is None:
            return None

        cx_a, cy_a = hist_a[-1]
        cx_b, cy_b = hist_b[-1]

        for t in range(1, frames_ahead + 1):
            px_a = cx_a + vel_a[0] * t
            py_a = cy_a + vel_a[1] * t
            px_b = cx_b + vel_b[0] * t
            py_b = cy_b + vel_b[1] * t
            dist = math.sqrt((px_a - px_b) ** 2 + (py_a - py_b) ** 2)
            if dist < threshold_px:
                return t

        return None

    def history_length(self, track_id: int) -> int:
        """Number of recorded positions for *track_id*."""
        hist = self._positions.get(track_id)
        return len(hist) if hist else 0
