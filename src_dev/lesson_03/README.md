# Lesson 3 — turning a stored goal into actual movement

Lesson 2 could *receive* a goal and switch to AUTONOMOUS mode, but nothing
happened: `distance_to_goal_m` stayed `0.0` forever, because nothing ever
computed it or moved the rover. This lesson adds the drive controller.

## New ideas

**1. Distance and bearing from two lat/lon pairs.** `_distance_and_bearing_to`
uses a flat-earth approximation — fine at the ~100 m scale of a single leg.
`111_320` is roughly meters-per-degree-of-latitude everywhere on Earth;
`cos(lat)` corrects for the fact that a degree of *longitude* covers less
ground the further you are from the equator (ignore it and MDRS-area
coordinates would drift east/west). The real GUI does the equivalent
projection properly in `src/urc_ops_console/urc_ops_console/geo.py` for
the map view.

**2. Arrival needs a tolerance, not exact equality.** Floating-point GPS
coordinates essentially never land on the exact target, so "reached" means
"within `ARRIVAL_RADIUS_M`," not "distance == 0."

**3. `leg_reached` clears itself on a timer, using wall-clock time.** Once
the goal is hit, `self.goal` is set back to `None` — so a few ticks later
there's nothing left to check "are we still at the goal?" against. Instead,
`leg_reached_at = time.monotonic()` records *when* it happened, and
`publish_loop` clears the flag once `LEG_REACHED_FLASH_S` has passed. This
is exactly the mechanism the real flashing-green LED depends on.

## Still missing (lesson 4)

- **The deadman.** Nothing stops the rover if the operator console goes
  quiet — no heartbeat subscription yet.
- **Abort.** No way to cancel a goal early.
- **Speed limit.** `SPEED_MPS` is a hardcoded constant; the real project
  makes it an operator-controlled slider over `/rover/max_speed`.

These three are grouped into one lesson because they're the same idea:
external signals that *override* the drive controller for safety, rather
than commands that give it new work.

## Run it

```bash
source /opt/ros/jazzy/setup.bash && source ~/urc_ws/install/setup.bash
python3 src_dev/lesson_03/rover_that_drives.py
```

In another terminal, watch it drive:

```bash
source /opt/ros/jazzy/setup.bash && source ~/urc_ws/install/setup.bash
ros2 topic pub /mission/mode std_msgs/msg/String "{data: 'AUTONOMOUS'}" --once
ros2 topic pub /mission/leg_goal urc_interfaces/msg/NavLeg \
  "{leg_id: 1, latitude: 38.406500, longitude: -110.791200}" --once
ros2 topic echo /rover/status
```

Watch `distance_to_goal_m` count down to `0.0`, `leg_reached` flip to
`true`, then back to `false` about three seconds later — with no further
commands sent. That timing is coming entirely from `time.monotonic()`
inside the node, not from anything you did.
