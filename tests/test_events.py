import pytest
from src.events import Event, EventDebouncer
from src.rules import Violation


FPS = 15.0
MIN_DUR = 0.5   # → 8 frames at 15fps (round(15 * 0.5) = 8... actually round(7.5) = 8)
COOL_DUR = 2.0  # → 30 frames at 15fps


def make_violation(track_id: int = 1, frame_id: int = 0, v_type: str = "missing_ppe",
                   zone_id: str | None = None, missing_ppe: list[str] | None = None,
                   severity: str = "WARNING") -> Violation:
    return Violation(
        type=v_type,
        track_id=track_id,
        frame_id=frame_id,
        bbox=(0, 0, 100, 200),
        severity=severity,
        zone_id=zone_id,
        missing_ppe=missing_ppe or ["hardhat"],
    )


def feed(debouncer: EventDebouncer, violation: Violation | None, count: int,
         start_frame: int = 0) -> tuple[list[Event], list[Event]]:
    """Feed the same violation (or None) for `count` frames. Returns last frame's result."""
    opened, closed = [], []
    for i in range(count):
        v_list = [] if violation is None else [
            Violation(
                type=violation.type,
                track_id=violation.track_id,
                frame_id=start_frame + i,
                bbox=violation.bbox,
                severity=violation.severity,
                zone_id=violation.zone_id,
                missing_ppe=list(violation.missing_ppe),
            )
        ]
        opened, closed = debouncer.update(v_list, start_frame + i)
    return opened, closed


class TestMinFrames:
    def test_no_event_below_threshold(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        # Feed one fewer than required
        opened, _ = feed(d, v, d._min_frames - 1)
        assert opened == []

    def test_event_opens_at_threshold(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        opened, _ = feed(d, v, d._min_frames)
        assert len(opened) == 1
        assert opened[0].event_type == "missing_ppe"
        assert opened[0].track_id == 1
        assert opened[0].end_frame is None

    def test_no_duplicate_open_for_continuous_violation(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        all_opened = []
        for i in range(d._min_frames * 3):
            opened, _ = d.update([make_violation(frame_id=i)], i)
            all_opened.extend(opened)
        assert len(all_opened) == 1


class TestCooldown:
    def test_event_stays_open_during_cooldown(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        feed(d, v, d._min_frames)  # open event

        # Feed absence for fewer than cooldown_frames
        for i in range(d._cooldown_frames - 1):
            _, closed = d.update([], d._min_frames + i)
        assert closed == []

    def test_event_closes_after_cooldown(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        feed(d, v, d._min_frames)  # open event

        closed_all = []
        for i in range(d._cooldown_frames):
            _, closed = d.update([], d._min_frames + i)
            closed_all.extend(closed)

        assert len(closed_all) == 1
        assert closed_all[0].end_frame == d._min_frames + d._cooldown_frames - 1

    def test_pending_resets_on_absence(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        # Build up partial pending frames
        feed(d, v, d._min_frames - 1)
        # One frame absent — pending should reset
        d.update([], d._min_frames - 1)
        # Feed again from scratch — should need full min_frames again
        opened, _ = feed(d, v, d._min_frames - 1, start_frame=d._min_frames)
        assert opened == []


class TestDebounceKey:
    def test_independent_tracks(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        for i in range(d._min_frames):
            v1 = make_violation(track_id=1, frame_id=i)
            v2 = make_violation(track_id=2, frame_id=i)
            opened, _ = d.update([v1, v2], i)
        assert len(opened) == 2
        assert {e.track_id for e in opened} == {1, 2}

    def test_same_track_different_zones(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        all_opened = []
        for i in range(d._min_frames):
            v1 = make_violation(track_id=1, frame_id=i, v_type="zone_intrusion", zone_id="zone_a")
            v2 = make_violation(track_id=1, frame_id=i, v_type="zone_intrusion", zone_id="zone_b")
            opened, _ = d.update([v1, v2], i)
            all_opened.extend(opened)
        assert len(all_opened) == 2
        assert {e.zone_id for e in all_opened} == {"zone_a", "zone_b"}

    def test_same_track_different_violation_types(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        all_opened = []
        for i in range(d._min_frames):
            ppe = make_violation(track_id=1, frame_id=i, v_type="missing_ppe")
            zone = make_violation(track_id=1, frame_id=i, v_type="zone_intrusion", zone_id="z1",
                                  missing_ppe=[])
            opened, _ = d.update([ppe, zone], i)
            all_opened.extend(opened)
        assert len(all_opened) == 2
        assert {e.event_type for e in all_opened} == {"missing_ppe", "zone_intrusion"}


class TestFlush:
    def test_flush_closes_open_events(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        feed(d, v, d._min_frames)  # open one event
        flushed = d.flush(frame_id=999)
        assert len(flushed) == 1
        assert flushed[0].end_frame == 999

    def test_flush_clears_state(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        feed(d, make_violation(), d._min_frames)
        d.flush(frame_id=999)
        assert d._states == {}

    def test_flush_empty_when_no_open_events(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        flushed = d.flush(frame_id=0)
        assert flushed == []

    def test_flush_ignores_pending_not_yet_opened(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        feed(d, make_violation(), d._min_frames - 1)  # pending but not opened
        flushed = d.flush(frame_id=999)
        assert flushed == []  # pending violations are not emitted as events


class TestEventFields:
    def test_event_id_is_unique(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        feed(d, make_violation(track_id=1), d._min_frames)
        d2 = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        feed(d2, make_violation(track_id=1), d2._min_frames)
        opened1, _ = feed(d, make_violation(track_id=2), d._min_frames, start_frame=d._min_frames)
        opened2, _ = feed(d2, make_violation(track_id=2), d2._min_frames, start_frame=d2._min_frames)
        assert opened1[0].event_id != opened2[0].event_id

    def test_start_frame_is_first_violation_frame(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        opened, _ = feed(d, make_violation(), d._min_frames, start_frame=10)
        assert opened[0].start_frame == 10

    def test_missing_ppe_captured(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation(missing_ppe=["hardhat", "vest"])
        opened, _ = feed(d, v, d._min_frames)
        assert opened[0].missing_ppe == ["hardhat", "vest"]

    def test_snapshot_path_initially_none(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        opened, _ = feed(d, make_violation(), d._min_frames)
        assert opened[0].snapshot_path is None

    def test_severity_carried_from_violation(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation(v_type="zone_intrusion", zone_id="z1", severity="CRITICAL")
        opened, _ = feed(d, v, d._min_frames)
        assert opened[0].severity == "CRITICAL"

    def test_warning_severity_carried(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        opened, _ = feed(d, make_violation(severity="WARNING"), d._min_frames)
        assert opened[0].severity == "WARNING"

    def test_reopen_after_close(self):
        d = EventDebouncer(fps=FPS, min_duration=MIN_DUR, cooldown_duration=COOL_DUR)
        v = make_violation()
        frame = 0
        feed(d, v, d._min_frames, start_frame=frame)
        frame += d._min_frames

        # Let event close
        for i in range(d._cooldown_frames):
            d.update([], frame + i)
        frame += d._cooldown_frames

        # Violation returns — should open a second event
        opened, _ = feed(d, v, d._min_frames, start_frame=frame)
        assert len(opened) == 1
        assert opened[0].start_frame == frame
