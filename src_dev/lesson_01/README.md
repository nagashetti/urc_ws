# Lesson 1 — the topic contract, and the smallest node that does something

Before writing any real logic, the real project locked in *what messages
cross the wire* (see `plan.md` Phase 3 — "write this table into the README
before coding, it's the contract both nodes hold to"). That's not a detour;
it's the first thing you write because every subscriber, publisher, and GUI
widget downstream is typed against it.

So lesson 1 is two pieces, in the order you'd actually type them:

1. **`msg/*.msg`** — the three custom message shapes the whole project is
   built on. These are copied verbatim from `src/urc_interfaces/msg/`, not
   simplified, because there's nothing to simplify — a message definition
   *is* already the minimal statement of "what data flows on this topic."

2. **`minimal_rover_node.py`** — a deliberately gutted version of
   `src/urc_rover_sim/urc_rover_sim/rover_sim_node.py`. The real node has
   ~270 lines: parameters, five publishers, five subscribers, a drive
   controller, a deadman timer, fault injection. This version keeps only
   enough to be a real, runnable ROS 2 node: **one Node subclass, one
   parameter, one publisher, one timer.** Every later lesson adds one more
   capability on top of this exact shape.

## Why start with GPS specifically

`/rover/gps` is the simplest topic in the contract (`sensor_msgs/NavSatFix`,
a message ROS already ships — no custom message needed to publish it), and
it's the one the GUI's map view ultimately depends on. Starting here means
lesson 1 doesn't need `urc_interfaces` built at all.

## Run it

No colcon build needed — this only uses a stock ROS message type:

```bash
source /opt/ros/jazzy/setup.bash
python3 src_dev/lesson_01/minimal_rover_node.py
```

In another terminal:

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic echo /rover/gps
ros2 topic hz /rover/gps
ros2 node list
ros2 param get /minimal_rover publish_rate_hz
```

You should see the same fixed lat/lon repeat at ~5 Hz. That's the entire
node — no movement, no commands accepted, nothing else published yet.

## What's deliberately missing (and which lesson adds it back)

- No `latitude`/`longitude` ROS parameters (hardcoded instead) — added when
  lesson 2 introduces `declare_parameters(namespace=..., parameters=[...])`
  for a whole batch at once.
- No noise, no movement, no other topics — lesson 2.
- No subscriptions, so nothing the node does can be changed from outside —
  lesson 2 adds `create_subscription` and a callback.
- The custom messages (`RoverStatus`, `NavLeg`, `LinkStats`) aren't used by
  the node yet, only defined — lesson 2 publishes `RoverStatus` and
  subscribes to `NavLeg`.
