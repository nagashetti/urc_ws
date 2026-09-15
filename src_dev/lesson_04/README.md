# Lesson 4 — the deadman heartbeat, abort, and a live speed limit

Lesson 3's rover drives at a hardcoded `SPEED_MPS = 1.0` forever, and
nothing can make it stop early. This lesson replaces that constant with
three things an operator actually controls at runtime, all grouped
together because they're the same idea: **external signals that override
the drive controller for safety**, rather than commands that give it new
work (that was lesson 2's job).

## 1. The deadman heartbeat — reacting to *absence*

Every other callback in this project reacts to a message *arriving*. The
deadman is the opposite: the operator console publishes a heartbeat at
2 Hz, and `heartbeat_callback` does nothing but record *when* the last one
showed up:

```python
def heartbeat_callback(self, msg):
    self.last_heartbeat = time.monotonic()
```

The actual safety logic lives in `publish_loop`, which checks the *gap*
since that timestamp on every tick:

```python
link_lost = (time.monotonic() - self.last_heartbeat) > HEARTBEAT_TIMEOUT_S
```

If the console (or the network) dies, no message ever arrives to "tell" the
rover — so the rover has to notice the silence itself. This is why the
timeout check has to live in the timer callback, not in `heartbeat_callback`:
a callback that never fires can't run any code.

## 2. Abort — an explicit override, not a new goal

`abort_callback` doesn't schedule anything or wait for the next tick; it
clears `self.goal` immediately. Since `drive_to_goal()` is only ever called
when `self.goal is not None`, clearing it is enough to stop movement on the
very next publish, no separate "stop" flag needed.

## 3. Speed limit — a constant becomes a live topic

`SPEED_MPS` is gone. In its place, `self.max_speed_mps` starts at `0.0`
(matching the real sim's default — the rover doesn't move until told a
speed) and is only ever changed by `max_speed_callback`. This is the
"visible effect" the plan calls out for the demo recording: drag a slider
in the real GUI, watch the rover's speed change in real time.

## Run it

Same remap caveat as lesson 3 — see the top-level README's gotcha section.

```bash
source /opt/ros/jazzy/setup.bash && source ~/urc_ws/install/setup.bash
python3 src_dev/lesson_04/rover_with_deadman.py --ros-args \
  -r /rover/gps:=/lesson4/gps -r /rover/status:=/lesson4/status \
  -r /mission/mode:=/lesson4/mode -r /mission/leg_goal:=/lesson4/leg_goal \
  -r /mission/abort:=/lesson4/abort -r /rover/max_speed:=/lesson4/max_speed \
  -r /ops_console/heartbeat:=/lesson4/heartbeat
```

Try it **without** ever publishing a heartbeat:

```bash
ros2 topic pub /lesson4/mode std_msgs/msg/String "{data: 'AUTONOMOUS'}" --once
ros2 topic pub /lesson4/leg_goal urc_interfaces/msg/NavLeg "{leg_id: 1, latitude: 38.4070, longitude: -110.7912}" --once
ros2 topic pub /lesson4/max_speed std_msgs/msg/Float32 "{data: 2.0}" --once
ros2 topic echo /lesson4/status
```

`distance_to_goal_m` never moves — link is "lost" from the moment the node
starts, since no heartbeat has ever arrived (`self.last_heartbeat` is
seeded at construction time, so an idle console looks identical to a dead
one). Now start a heartbeat in another terminal and watch it start driving:

```bash
ros2 topic pub /lesson4/heartbeat std_msgs/msg/Header -r 5
```

Kill that heartbeat publisher (Ctrl-C) mid-drive and watch `state_text`
switch to `LINK LOST — HOLDING` within ~2 seconds, and distance stop
changing. Then try `/lesson4/abort` with `{data: true}` while it's driving
— the goal clears immediately, no waiting for arrival.

## A real bug this lesson surfaced

Building this exposed a genuine bug — not just in the lesson, but in
`src/urc_rover_sim/urc_rover_sim/rover_sim_node.py` too, since it used the
same pattern: `state_text` was set to `'LINK LOST — HOLDING'` while the
link was down, but nothing ever set it back once the heartbeat resumed.
Telemetry would resume updating normally (distance counting down, GPS
moving) while `state_text` kept reporting a fault that was no longer true —
a stale fault message rendered as current, the mirror image of the "never
render a stale value as fresh" rule from the watchdog design (Phase 5c).
Both files now reset `state_text` to the right thing the moment
`link_lost` flips back to `false`. Worth remembering: a value that's only
ever *set* on the way into a bad state, and never *unset* on the way out,
is a recurring shape of bug — the same thing to watch for in lesson 7's
watchdog.

## What's still missing

Everything from `rover_sim_node.py` is now covered except fault injection
(`gps_noise_m`, `drop_probability`, `stall_after_s`) — those exist so you
can *demo* signal loss without physically unplugging anything, which isn't
a new architectural idea, just parameters feeding into logic you've already
built. Worth a quick look at the real file, not necessarily its own lesson.

From here the remaining lessons move to the GUI side: a bare PyQt5 window
(lesson 5), the ROS↔Qt threading bridge (lesson 6), and the staleness
watchdog (lesson 7).
