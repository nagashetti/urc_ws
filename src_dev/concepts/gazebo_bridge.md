# Gazebo topic bridging (`ros_gz_bridge`)

This is Phase 7 in [plan.md](../../plan.md#L239-L241) — explicitly optional, and explicitly *last*: "Only after Phases 1–6 are green." Nothing in this file is built yet. It exists so the concept is written down before you need it, the same way [qos.md](qos.md) documented durability before Phase 5d needed it.

## The problem this solves

Gazebo (Harmonic, the version pinned in [plan.md:22,40](../../plan.md#L22) and installed via `ros-jazzy-ros-gz gz-harmonic` in [plan.md:40](../../plan.md#L40)) is its own simulator with its own transport layer, **gz-transport** — not ROS 2, not DDS. A simulated rover in Gazebo publishes odometry, sensor data, etc. as gz-transport messages that no `rclpy` node can subscribe to directly. `ros_gz_bridge` is the translator: a process that subscribes on one side (gz-transport or ROS 2) and republishes on the other, converting message types as it goes.

## Why this project needs it at all

Phase 4's `rover_sim_node.py` is a hand-written Python node that *already speaks ROS 2 natively* — no bridge needed, because you wrote the publishers yourself. Phase 7 replaces that fake rover with an actual physics simulation (a diff-drive rover in a `.sdf` world), and physics sim ≠ ROS 2 node. The bridge is what makes a Gazebo-simulated rover indistinguishable, from the GUI's point of view, from Phase 4's hand-rolled one.

**When to use:** any time a simulator (Gazebo, or generally anything outside the ROS graph) needs to appear on ROS 2 topics, or vice versa.
**Why:** it's strictly a transport + type translator — it does no logic of its own. It's the same "keep the boundary thin" idea as [ros_bridge.py](../../src/urc_ops_console/urc_ops_console/ros_bridge.py)'s ROS↔Qt bridge in [event_loop.md](event_loop.md) §9: one side's messages get relayed to the other side's format, and nothing else happens in between.
**Pairs with:** the topic contract from [plan.md Phase 3](../../plan.md#L99-L144) — the bridge's whole job is to make Gazebo's native topics *become* `/rover/gps`, `/rover/odom`, etc., matching the exact types your GUI already subscribes to.

## The core mechanism: a type-mapped topic pair

Each bridged topic needs four things: the gz-transport topic name + type, the ROS 2 topic name + type, and a direction. Configured either per-topic on the command line, or in bulk via a YAML file passed to the bridge node.

**Command line, one topic:**
```bash
ros2 run ros_gz_bridge parameter_bridge \
  /model/rover/odometry@nav_msgs/msg/Odometry@gz.msgs.Odometry
```
The `@`-separated triple is `<ros_topic>@<ros_type>@<gz_type>`. This form defaults to bidirectional.

**YAML, the form you'd actually check into `urc_bringup`:**
```yaml
- ros_topic_name: "/rover/odom"
  gz_topic_name: "/model/rover/odometry"
  ros_type_name: "nav_msgs/msg/Odometry"
  gz_type_name: "gz.msgs.Odometry"
  direction: GZ_TO_ROS

- ros_topic_name: "/cmd_vel"
  gz_topic_name: "/model/rover/cmd_vel"
  ros_type_name: "geometry_msgs/msg/Twist"
  gz_type_name: "gz.msgs.Twist"
  direction: ROS_TO_GZ

- ros_topic_name: "/rover/gps"
  gz_topic_name: "/model/rover/navsat"
  ros_type_name: "sensor_msgs/msg/NavSatFix"
  gz_type_name: "gz.msgs.NavSat"
  direction: GZ_TO_ROS
```
**Direction matters and isn't symmetric with your topic contract**: telemetry (`odometry`, `navsat`) flows `GZ_TO_ROS` — Gazebo is the source of truth, the GUI only ever reads it. Velocity commands flow `ROS_TO_GZ` — something (your GUI, or a driving node subscribed to `/mission/leg_goal`) has to publish `Twist` messages for Gazebo's diff-drive plugin to actually move the model. Note this is a *new* topic your Phase 1–6 command set doesn't have: `/mission/leg_goal` → `Twist` translation is logic (a bearing controller), and the bridge does no logic — something still needs to be the node computing `cmd_vel` from a goal, the same job [rover_with_deadman.py](../lesson_04/rover_with_deadman.py)'s `drive_to_goal()` does today in pure Python.

## What plan.md specifies exactly

Per [plan.md:241](../../plan.md#L241), Phase 7 bridges:

| Gazebo topic | Purpose | ROS-side type |
|---|---|---|
| `/model/rover/odometry` | ground-truth pose/velocity from the sim | `nav_msgs/msg/Odometry` — matches `/rover/odom` from Phase 3's contract exactly |
| `/cmd_vel` | drive command into the diff-drive plugin | `geometry_msgs/msg/Twist` |
| a `navsat` sensor | simulated GPS | `sensor_msgs/msg/NavSatFix` — matches `/rover/gps` |

## The acceptance test plan.md actually cares about

> "The GUI code shouldn't change at all — if it does, your topic contract was too loosely defined."

This is the real point of Phase 7, more than Gazebo itself: it's a test of Phase 3. If [ros_bridge.py](../../src/urc_ops_console/urc_ops_console/ros_bridge.py)'s `OpsConsoleNode` needs *any* edit to work against a Gazebo-backed rover instead of [rover_sim_node.py](../../src/urc_rover_sim/urc_rover_sim/rover_sim_node.py), that's a sign the GUI was coupled to something about the fake rover's implementation rather than to the topic contract table in [plan.md Phase 3](../../plan.md#L99-L144) — worth writing into the log either way, per plan.md's own note.

## QoS across the bridge

`ros_gz_bridge` publishes/subscribes on the ROS side using default QoS unless told otherwise (some bridge versions expose a `qos` override per-topic in the YAML). This matters directly for this project: your `TELEMETRY`/`COMMAND` profiles from [qos.py](../../src/urc_ops_console/urc_ops_console/qos.py) assume `BEST_EFFORT`/depth-1 on telemetry topics. If the bridge's default is `RELIABLE`, that's a repeat of the exact mismatch lesson 2 already demonstrated on `/rover/gps` (see [qos.md](qos.md) §1 and [topic.md](topic.md)) — worth explicitly checking, not assuming, once Phase 7 is underway.

## Launch integration

Phase 6 already builds `urc_bringup/launch/ops_console.launch.py` to bring up `rover_sim` + `ops_console` together ([plan.md:230](../../plan.md#L230)). Phase 7 adds a third process to that same launch file — `ros_gz_bridge`'s `parameter_bridge` node, pointed at the YAML above — as an alternative to (not alongside) `rover_sim`. Nothing here has been written yet; when it is, it belongs in `urc_bringup`, not a new package, since it's bringup configuration rather than application code.

## Status in this project

Not implemented — Phase 7 is gated behind Phases 1–6 being green, per plan.md's own sequencing table. No `.sdf`/`.world` file, no bridge YAML, and no `ros_gz_bridge` invocation exist in the workspace yet. This file is written ahead of that work so the mechanism (type-mapped topic pairs, direction, the YAML shape) doesn't need to be re-derived from scratch when Phase 7 starts.
