"""Staleness tracking helpers for incoming telemetry streams.

Kept free of Qt imports so it can be unit-tested with pytest and a fake clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

FRESH_S = 1.0
STALE_S = 3.0
RATE_WINDOW_S = 5.0


def evaluate_stream(last_rx: float, now: float | None = None) -> str:
    current = monotonic() if now is None else now
    age_s = current - last_rx
    if age_s < FRESH_S:
        return 'fresh'
    if age_s < STALE_S:
        return 'stale'
    return 'lost'


@dataclass
class StreamState:
    last_rx: float
    rx_times: list = field(default_factory=list)
    rate_estimate_hz: float = 0.0

    def update(self, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        self.last_rx = current
        self.rx_times.append(current)
        cutoff = current - RATE_WINDOW_S
        self.rx_times = [t for t in self.rx_times if t >= cutoff]
        window = self.rx_times[-1] - self.rx_times[0] if len(self.rx_times) > 1 else 0.0
        self.rate_estimate_hz = (len(self.rx_times) - 1) / window if window > 0 else 0.0


class Watchdog:
    """Tracks last-received time and staleness state for named telemetry streams."""

    def __init__(self, stream_names: list[str]):
        now = monotonic()
        self._streams = {name: StreamState(last_rx=now) for name in stream_names}

    def mark_received(self, name: str, now: float | None = None) -> None:
        self._streams[name].update(now)

    def status(self, name: str, now: float | None = None) -> str:
        return evaluate_stream(self._streams[name].last_rx, now)

    def age(self, name: str, now: float | None = None) -> float:
        current = monotonic() if now is None else now
        return current - self._streams[name].last_rx

    def rate_hz(self, name: str) -> float:
        return self._streams[name].rate_estimate_hz
