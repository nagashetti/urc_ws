# QoS: reliability, durability, and the other delivery knobs

[topic.md](topic.md) introduced QoS as "a topic has a contract, not just a type" and covered the two policies your project actually uses — **reliability** and **history**. This file goes one level deeper: the full policy set DDS exposes, which ones you're using vs. which ones plan.md flags as worth *considering*, and the compatibility rule that explains why a mismatch degrades instead of erroring.

Every policy below is set the same way — as a field on a `QoSProfile` passed to `create_publisher`/`create_subscription`:

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

TELEMETRY = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
```

## 1. Reliability — retry, or don't

```python
ReliabilityPolicy.RELIABLE       # DDS retransmits until delivered (or the subscriber gives up)
ReliabilityPolicy.BEST_EFFORT    # sent once; lost means lost
```

**When to use:** `RELIABLE` for anything that must arrive — commands, one-shot events. `BEST_EFFORT` for anything where a stale retry is worse than a dropped sample — high-rate telemetry on a lossy link.
**Why:** this is the policy that actually changes wire behavior under packet loss, which is the failure mode plan.md's Phase 8 "what breaks first over a lossy link" question is built around — a `RELIABLE` publisher under real loss doesn't just retry quietly, it head-of-line-blocks: a retransmitted 4-second-old GPS fix clogs the queue in front of the fresh one behind it. That's *why* telemetry is `BEST_EFFORT` here — not "loss is fine," but "retrying is worse than loss."
**Pairs with:** `depth` (see §2) — a `RELIABLE` publisher with a deep queue is exactly the head-of-line-blocking scenario above; `BEST_EFFORT` with `depth=1` is the deliberate opposite choice.
**In this project:** [qos.py:19-27](../../src/urc_ops_console/urc_ops_console/qos.py#L19-L27) defines exactly two profiles, `TELEMETRY` (`BEST_EFFORT`) and `COMMAND` (`RELIABLE`), and every publisher/subscriber across [rover_sim_node.py:62-83](../../src/urc_rover_sim/urc_rover_sim/rover_sim_node.py#L62-L83) and [ros_bridge.py](../../src/urc_ops_console/urc_ops_console/ros_bridge.py) uses one of the two — never a bespoke profile per topic. You've already seen the mismatch failure mode live: lesson 1's implicit-`RELIABLE` publisher (bare `10`) connected to your real `BEST_EFFORT` sim on `/rover/gps` and ROS printed a fallback warning — see [topic.md](topic.md)'s Lesson 2 section for the exact message.

## 2. History + depth — how much backlog to hold

```python
HistoryPolicy.KEEP_LAST   # hold the newest `depth` unread messages
HistoryPolicy.KEEP_ALL    # unbounded queue (rarely what you want)
```

**When to use:** `KEEP_LAST` essentially always; `depth` is the real tuning knob — `1` when only the newest value matters, higher when a short burst of distinct messages must all survive.
**Why:** depth is what turns "recover from a burst" into "queue of stale data" — too shallow drops real commands, too deep (combined with `RELIABLE`) is the head-of-line-blocking trap from §1.
**Pairs with:** reliability (§1) — the two are chosen as a pair in this project, never independently.
**In this project:** `TELEMETRY` is `depth=1` (only the latest GPS/IMU/odom fix is ever useful — see [qos.py:19-23](../../src/urc_ops_console/urc_ops_console/qos.py#L19-L23)), `COMMAND` is `depth=10` (a short burst of button presses — leg goal, mode switch, abort — must all queue and arrive, per [qos.py:25-28](../../src/urc_ops_console/urc_ops_console/qos.py#L25-L28)).

## 3. Durability — does a late-joining subscriber get history, or only what's published after it connects?

```python
DurabilityPolicy.VOLATILE          # default — late subscribers get nothing until the next publish
DurabilityPolicy.TRANSIENT_LOCAL   # publisher retains the last `depth` messages for late joiners
```

**When to use:** `TRANSIENT_LOCAL` for state a freshly-connecting/restarting node needs *immediately*, without waiting for the next periodic publish — typically low-rate, "current setting" style topics. `VOLATILE` (the default) for everything else, and *especially* for anything where a replayed old value would be actively dangerous.
**Why:** this is the policy that matters most for restart behavior, not steady-state behavior — `VOLATILE` is invisible while everything's already running, and only shows up as "why did the newly-launched node start with no idea what mode we're in?"
**Pairs with:** reliability — both publisher and subscriber must match (or be compatible; see §5) for the connection to form at the requested durability.
**In this project:** not implemented yet — both `TELEMETRY` and `COMMAND` in [qos.py](../../src/urc_ops_console/urc_ops_console/qos.py) are implicitly `VOLATILE` (rclpy's default). But plan.md §5d names a specific, concrete plan for it: consider `TRANSIENT_LOCAL` for `/mission/mode` so a rover node that restarts mid-mission inherits the current mode instead of defaulting to idle/teleop. **The hazard plan.md flags in the same breath**: don't do the same thing to `/mission/abort` — a `TRANSIENT_LOCAL` abort topic would replay a stale "ABORT" to a freshly-restarted rover node forever, which is exactly the kind of "old command executes on reconnect" bug durability exists to let you opt into *carefully*, per-topic, not globally. If you implement this, it's the one topic in the whole contract that should differ from the shared `TELEMETRY`/`COMMAND` profiles rather than reusing them.

## 4. Deadline — "I expect a message at least this often"

```python
from rclpy.duration import Duration
QoSProfile(..., deadline=Duration(seconds=0.5))
```

**When to use:** when you want DDS itself (not your own timer logic) to notice a publisher going silent, via an `on_offered_deadline_missed` / `on_requested_deadline_missed` event callback.
**Why:** it's a built-in "this stream should never go quiet for longer than X" contract, enforced by the middleware instead of application code.
**Pairs with:** conceptually competes with your own watchdog logic.
**In this project:** not used — and deliberately superseded. [rover_with_deadman.py](../lesson_04/rover_with_deadman.py) and plan.md §5c's `watchdog.py` design implement the exact same "has it been too long since the last message?" question in application code instead, with three graded states (fresh/stale/lost) and specific GUI behavior (amber tile, red tile, greyed-and-struck-through value) — richer than a QoS deadline-missed event can express on its own. Worth knowing this policy exists, but this project's staleness handling is intentionally the pure-Python `watchdog.py` from [event_loop.md](event_loop.md), not `deadline`.

## 5. Liveliness — "is the publisher process even still alive?"

```python
from rclpy.qos import LivelinessPolicy
QoSProfile(..., liveliness=LivelinessPolicy.AUTOMATIC, liveliness_lease_duration=Duration(seconds=2.0))
```

**When to use:** distinguishing "the publisher process died" from "the publisher is alive but hasn't published in a while" — matters when a node might legitimately go quiet on purpose.
**Why:** deadline (§4) fires whenever the *topic* goes quiet, whether the node is alive or not; liveliness is specifically about the node's own heartbeat to DDS, independent of whether it publishes.
**Pairs with:** deadline — the two are commonly confused because both detect "silence," but at different layers.
**In this project:** not used, and the deadman heartbeat already solves the problem this would solve, just built at the application layer instead: `/ops_console/heartbeat` in [rover_with_deadman.py:79](../lesson_04/rover_with_deadman.py#L79) is a hand-rolled liveliness signal (2 Hz, per [ros_bridge.py:27](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L27)) that the rover checks against `HEARTBEAT_TIMEOUT_S` — functionally the same question DDS liveliness answers, but visible as an ordinary topic you can `ros2 topic echo`, rather than a QoS-layer event.

## 6. Lifespan — how long a message stays valid in the queue

```python
QoSProfile(..., lifespan=Duration(seconds=1.0))
```

**When to use:** expiring a queued-but-undelivered message after some age, so a slow subscriber never receives data that's already too old to act on.
**Why:** complements `depth` — depth bounds queue *size*, lifespan bounds queue *age*.
**In this project:** not used — `depth=1` on telemetry already makes this moot (there's nothing to expire in a 1-deep queue; the next publish just overwrites it).

## Why a mismatch degrades instead of failing

Reliability, durability, and liveliness are each split into what a **publisher offers** and what a **subscriber requests** — DDS connects them only if the subscriber's request is *equal to or weaker than* the publisher's offer (`RELIABLE` offered satisfies a `BEST_EFFORT` request; the reverse doesn't connect at all). This is exactly what you saw in lesson 2: lesson 1's node offered `RELIABLE` (via the bare `10`), your `BEST_EFFORT` sim was already running, and rather than refusing to connect, ROS 2 logged a fallback warning and connected at the weaker `BEST_EFFORT`. That's why plan.md §5d's advice is to define `TELEMETRY`/`COMMAND` **once**, centrally, and have every publisher/subscriber import the same two objects ([qos.py](../../src/urc_ops_console/urc_ops_console/qos.py)) rather than letting each call site pick its own profile — a silent downgrade is a much easier bug to introduce than to notice.

## Quick map: policy → status in this project

| Policy | Used? | Where / plan |
|---|---|---|
| Reliability | Yes | `TELEMETRY`=BEST_EFFORT, `COMMAND`=RELIABLE — [qos.py](../../src/urc_ops_console/urc_ops_console/qos.py) |
| History + depth | Yes | depth=1 telemetry, depth=10 command — same file |
| Durability | Not yet | planned for `/mission/mode` only, explicitly *not* `/mission/abort` — plan.md §5d |
| Deadline | No | superseded by `watchdog.py`'s fresh/stale/lost logic — §5c |
| Liveliness | No | superseded by the `/ops_console/heartbeat` topic + deadman timer — [event_loop.md](event_loop.md) §4 |
| Lifespan | No | moot at depth=1 |
