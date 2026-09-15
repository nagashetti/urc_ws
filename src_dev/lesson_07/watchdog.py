"""Lesson 7: watching a value go stale — no Qt, no ROS, just a clock.

Lesson 6 ended with a live GPS label that just stopped, frozen on its last
value forever, the moment the publisher died. Nothing noticed. This file
is the piece that notices: a pure-Python staleness classifier, kept free
of Qt AND rclpy on purpose, so it can be unit-tested with a fake clock
instead of real sleep() calls and a running ROS graph.

Key principle (plan.md Phase 5c): a stale value is never rendered as if it
were fresh, and loss of data is never rendered as a zero. This file only
answers "how old is this?" — deciding what to DO about a stale value
(grey it out, strike it through) is the GUI's job, not this one's.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

FRESH_S = 1.0  # newer than this: trust it completely
STALE_S = 3.0  # older than this: treat it as gone, not just old


def evaluate_stream(last_rx: float, now: float | None = None) -> str:
    """'fresh', 'stale', or 'lost' — purely a function of elapsed time.

    `now` defaults to the real clock, but every test in test_watchdog.py
    passes an explicit value instead. That one parameter is what makes
    this testable in microseconds instead of needing real time.sleep(3)
    calls: a test doesn't wait for 3 seconds to pass, it asserts what the
    answer would be if 3 seconds HAD passed.
    """
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

    def update(self, now: float | None = None) -> None:
        self.last_rx = monotonic() if now is None else now


class Watchdog:
    """One StreamState per named topic — a real console watches
    gps/imu/odom/status/link all at once, each aging independently.
    """

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
