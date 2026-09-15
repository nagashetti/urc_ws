# Lesson 2 — real QoS, and reacting to commands

Lesson 1's node only ever spoke; it never listened, and its publisher used
a bare `10` (an implicit RELIABLE queue). Two new ideas here, both promised
in lesson 1's comments:

## 1. QoS profiles

A bare integer like `create_publisher(NavSatFix, '/rover/gps', 10)` is
shorthand for "RELIABLE, keep the last 10." That's the wrong default for a
lossy ~1 km radio link: RELIABLE means a dropped message gets
*retransmitted*, so on a bad link you'd rather lose an old GPS fix than
have it queue up and delay the next one. Commands are the opposite — a
dropped ABORT is unacceptable. So this lesson uses two named profiles:

```python
telemetry_qos = QoSProfile(reliability=BEST_EFFORT, history=KEEP_LAST, depth=1)
command_qos   = QoSProfile(reliability=RELIABLE,    history=KEEP_LAST, depth=10)
```

This is the exact pair defined once and reused everywhere in the real
project at `src/urc_ops_console/urc_ops_console/qos.py` — GPS/status get
`telemetry_qos`, leg goals/mode/abort get `command_qos`.

## 2. Subscriptions

`rover_with_commands.py` now has two `create_subscription(...)` calls. A
subscription callback's only job is to update instance state quickly —
`goal_callback` stores an incoming `NavLeg`, `mode_callback` flips
`self.mode`. Neither does slow work, because callbacks and the publish
timer all run on the same single-threaded executor: one slow callback
delays everything else, including your own telemetry.

The timer-driven `publish_loop()` is unchanged in spirit from lesson 1 — it
just now publishes two messages instead of one, reporting back whatever
the callbacks have most recently set.

## What's deliberately still missing

- **No movement.** `RoverStatus.distance_to_goal_m`/`bearing_to_goal_deg`
  are hardcoded to 0.0 — the node stores a goal but never drives toward
  it. That's lesson 3.
- **No deadman.** A real console publishes a heartbeat and the rover
  clamps to a stop if it goes quiet; not here yet.
- **No fault injection.** `gps_noise_m`, `drop_probability`,
  `stall_after_s` are still absent.

## Run it

This one needs the custom messages built, so it isn't fully standalone
like lesson 1:

```bash
source /opt/ros/jazzy/setup.bash
source ~/urc_ws/install/setup.bash   # provides urc_interfaces
python3 src_dev/lesson_02/rover_with_commands.py
```

In another terminal, watch it react:

```bash
source /opt/ros/jazzy/setup.bash && source ~/urc_ws/install/setup.bash
ros2 topic echo /rover/status
```

And in a third, send it commands:

```bash
ros2 topic pub /mission/mode std_msgs/msg/String "{data: 'AUTONOMOUS'}" --once
ros2 topic pub /mission/leg_goal urc_interfaces/msg/NavLeg \
  "{leg_id: 1, latitude: 38.4065, longitude: -110.7912}" --once
```

Watch the `/rover/status` echo: `mode` flips to `2` (MODE_AUTONOMOUS) and
`active_leg_id` becomes `1` — but `distance_to_goal_m` stays `0.0` no
matter what coordinates you send, since nothing computes it yet.
