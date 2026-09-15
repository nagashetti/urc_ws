# Lesson 7 — watching a value go stale, with a fake clock

Lesson 6 ended on a cliffhanger: kill the GPS publisher, and the label in
`gps_window.py` just stops — frozen on its last value forever, looking
exactly as "fresh" as it did a second before the publisher died. Nothing
in that lesson could tell the difference. This lesson is the piece that
can.

## Why this file has no Qt and no rclpy imports, on purpose

Deciding "is this data too old to trust?" has nothing to do with widgets
or topics — it's pure arithmetic on timestamps. Keeping it free of both
dependencies means it can be unit-tested directly with `pytest`, no
`QApplication`, no ROS node, no running graph. That's not a style
preference; it's what makes `test_watchdog.py` in this same folder run in
milliseconds instead of needing real `time.sleep()` calls.

## The trick: inject the clock instead of calling it internally

```python
def evaluate_stream(last_rx: float, now: float | None = None) -> str:
    current = monotonic() if now is None else now
    ...
```

`now` defaults to the real clock so production code can call
`evaluate_stream(last_rx)` and get a real answer. But every test passes an
explicit `now` instead. A test never waits 3 real seconds to check "is
this stale after 3 seconds?" — it just asserts what the answer *would be*
if 3 seconds had passed, by handing in `now = last_rx + 3.0` directly. This
pattern (accept the dependency as a parameter, default it to the real
thing) is worth remembering well beyond this project — it's the general
fix for "my code is hard to test because it calls `time.monotonic()` /
reads a file / hits the network internally."

## The three states, and the principle behind the thresholds

- **fresh** (`< FRESH_S`, 1.0 s) — render it normally, trust it completely.
- **stale** (`FRESH_S`–`STALE_S`, 1–3 s) — still shown, but visibly flagged.
- **lost** (`> STALE_S`, past 3 s) — treated as gone, not just old.

The rule this exists to enforce (`plan.md` §5c): **a stale value is never
rendered as if it were fresh, and loss of data is never rendered as a
zero.** A frozen "0.0 m/s" that actually means "no telemetry at all" is
how an operator drives a rover into a rock. Notice `evaluate_stream` never
decides *what to do* about staleness (grey it out? strike it through?) —
that's a rendering decision, and rendering decisions belong in the GUI,
not in this file. Keeping the two separated is exactly why this file can
stay Qt-free.

## `Watchdog` — because a real console tracks five streams, not one

`gps_window.py` only ever watched one topic. The real console watches
`gps`/`imu`/`odom`/`status`/`link` simultaneously, each aging
independently. `Watchdog` is just a `dict` of `StreamState`, keyed by
name, so `wd.status('gps')` and `wd.status('link')` can disagree at the
same instant — one fresh, one lost.

## What the real `watchdog.py` adds that this lesson skips

`src/urc_ops_console/urc_ops_console/watchdog.py` also tracks a rolling
5-second message-rate estimate per stream (`rate_estimate_hz`) — useful
for showing "GPS: 4.8 Hz" in a diagnostics view, but it's bookkeeping on
top of the same idea, not a new concept, so it's left out here to keep
this lesson focused on staleness classification.

## Run the tests

```bash
python3 -m pytest src_dev/lesson_07/test_watchdog.py -v
# or, with no pytest installed:
python3 src_dev/lesson_07/test_watchdog.py
```

## How this plugs into a real GUI (conceptually — not rewritten here)

`main_window.py`'s `_refresh_watchdog` does exactly what you'd expect
after lesson 6 and this lesson combined: a `QTimer` at 5 Hz calls
`watchdog.status(name)` for each stream and restyles the matching tile —
grey/strike-through text on `'lost'`, an amber "⚠ 1.4s old" on `'stale'`.
No new architectural idea, just lesson 6's bridge and this lesson's
classifier used together on a timer.

## You've now rebuilt every core idea in `src/`

Messages and QoS (1–2), a drive controller and safety overrides (3–4), a
GUI and the thread bridge that makes it safe (5–6), and now staleness
(7). What's left in the real project from here is packaging and glue —
launch files, `colcon test`, the full multi-widget layout — not new
concepts. Worth doing if you want the full picture, but the "one new idea
per 100 lines" pace has covered the architecture.
