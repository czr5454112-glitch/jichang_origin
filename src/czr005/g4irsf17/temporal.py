"""Bounded online counters for the G4IRSF17 10/30/60-second features."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Sequence


DEFAULT_WINDOWS_SECONDS: tuple[int, ...] = (10, 30, 60)


def _validate_windows(windows: Sequence[int]) -> tuple[int, ...]:
    result = tuple(int(window) for window in windows)
    if not result or any(window <= 0 for window in result):
        raise ValueError("WINDOWS_MUST_BE_POSITIVE")
    if tuple(sorted(set(result))) != result:
        raise ValueError("WINDOWS_MUST_BE_STRICTLY_INCREASING")
    return result


@dataclass
class BoundedTemporalCounter:
    """Maintain exact recent event counts with bounded memory and saturation."""

    windows: tuple[int, ...] = DEFAULT_WINDOWS_SECONDS
    max_events: int = 4_096
    _timestamps: deque[float] = field(default_factory=deque, init=False, repr=False)
    _last_timestamp: float = field(default=float("-inf"), init=False, repr=False)

    def __post_init__(self) -> None:
        self.windows = _validate_windows(self.windows)
        if self.max_events <= 0:
            raise ValueError("MAX_EVENTS_MUST_BE_POSITIVE")

    def add(self, timestamp: float) -> None:
        value = float(timestamp)
        if not math.isfinite(value):
            raise ValueError("TIMESTAMP_NOT_FINITE")
        if value < self._last_timestamp:
            raise ValueError("TIMESTAMPS_MUST_BE_MONOTONIC")
        self._last_timestamp = value
        self._timestamps.append(value)
        while len(self._timestamps) > self.max_events:
            self._timestamps.popleft()

    def extend(self, timestamps: Iterable[float]) -> None:
        for timestamp in timestamps:
            self.add(timestamp)

    def snapshot(self, now: float) -> dict[int, int]:
        current = float(now)
        if not math.isfinite(current):
            raise ValueError("NOW_NOT_FINITE")
        if current < self._last_timestamp:
            raise ValueError("NOW_PRECEDES_LATEST_EVENT")
        oldest_allowed = current - self.windows[-1]
        # The window definition is inclusive: [now-window, now].
        while self._timestamps and self._timestamps[0] < oldest_allowed:
            self._timestamps.popleft()
        timestamps = tuple(self._timestamps)
        return {
            window: min(
                self.max_events,
                sum(timestamp >= current - window for timestamp in timestamps),
            )
            for window in self.windows
        }


@dataclass
class SourceTemporalCounters:
    """Release/admission counters and bounded queue-growth features."""

    windows: tuple[int, ...] = DEFAULT_WINDOWS_SECONDS
    max_events: int = 4_096
    releases: BoundedTemporalCounter = field(init=False)
    admissions: BoundedTemporalCounter = field(init=False)

    def __post_init__(self) -> None:
        self.windows = _validate_windows(self.windows)
        self.releases = BoundedTemporalCounter(self.windows, self.max_events)
        self.admissions = BoundedTemporalCounter(self.windows, self.max_events)

    def record_release(self, timestamp: float) -> None:
        self.releases.add(timestamp)

    def record_admission(self, timestamp: float) -> None:
        self.admissions.add(timestamp)

    def snapshot(self, now: float) -> dict[str, float]:
        release = self.releases.snapshot(now)
        admission = self.admissions.snapshot(now)
        output: dict[str, float] = {}
        for window in self.windows:
            output[f"release_count_{window}s"] = float(release[window])
            output[f"admission_count_{window}s"] = float(admission[window])
            output[f"queue_slope_{window}s"] = float(
                max(-self.max_events, min(self.max_events, release[window] - admission[window]))
            )
        return output


def bounded_window_counts(
    timestamps: Iterable[float],
    now: float,
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS_SECONDS,
    max_events: int = 4_096,
) -> dict[int, int]:
    """Offline convenience wrapper with the same semantics as runtime state."""

    counter = BoundedTemporalCounter(tuple(windows), max_events)
    counter.extend(sorted(float(timestamp) for timestamp in timestamps))
    return counter.snapshot(now)
