# Topics in ROS 2

A **topic** in ROS 2 is a named, typed channel that nodes use to exchange messages asynchronously — publishers send messages on a topic without knowing who (if anyone) is listening, and subscribers receive them without knowing who sent them. It's ROS 2's core pub/sub mechanism (built on DDS), as opposed to services (synchronous request/response) or actions (long-running goals with feedback).

Your lessons build this concept up incrementally:

## Lesson 1 — the minimal publisher
[minimal_rover_node.py](../lesson_01/minimal_rover_node.py#L52) creates one topic, `/rover/gps`, typed as `sensor_msgs/NavSatFix`, and a timer fires [publish_gps()](../lesson_01/minimal_rover_node.py#L63-L71) 5×/sec to publish on it. No subscriber exists yet — that's fine, a topic doesn't need a listener to be valid. This lesson also introduces the message-type contract: [RoverStatus.msg](../lesson_01/msg/RoverStatus.msg) defines the exact fields (`mode`, `battery_pct`, `state_text`, etc.) that any publisher/subscriber pair on `/rover/status` must agree on.

## Lesson 2 — subscriptions and QoS
[rover_with_commands.py](../lesson_02/rover_with_commands.py) adds a second publisher (`/rover/status`) and two subscriptions: `/mission/leg_goal` ([goal_callback](../lesson_02/rover_with_commands.py#L98-L101)) and `/mission/mode` ([mode_callback](../lesson_02/rover_with_commands.py#L103-L106)). This is where topics become two-way: the node now reacts to messages arriving instead of only emitting them. It also shows that a topic has a QoS contract, not just a type — telemetry topics use `BEST_EFFORT`/depth-1 (drop stale GPS fixes rather than queue them), command topics use `RELIABLE`/depth-10 (an ABORT can't be lost). See the file's docstring for the real mismatch warning ROS printed when lesson 1's implicit-RELIABLE publisher connected to a BEST_EFFORT one.

## Lesson 3 — topics driving behavior
[rover_that_drives.py](../lesson_03/rover_that_drives.py) doesn't add new topics — it shows that subscribed data (`self.goal`, set by [goal_callback](../lesson_03/rover_that_drives.py#L76-L80)) can drive actual computation each tick ([drive_to_goal()](../lesson_03/rover_that_drives.py#L96-L106)), and the results (distance/bearing) flow back out over `/rover/status`. Topics here are the full loop: command in → state change → telemetry out.

## Lesson 4 — more topics, including "absence as signal"
[rover_with_deadman.py](../lesson_04/rover_with_deadman.py) adds three more subscriptions: `/mission/abort` (`std_msgs/Bool`), `/rover/max_speed` (`std_msgs/Float32`), and `/ops_console/heartbeat` (`std_msgs/Header`). The heartbeat topic is the interesting case: its [callback](../lesson_04/rover_with_deadman.py#L101-L102) just records a timestamp — the actual logic ("has it been too long since the last message?") lives in the timer, because a topic subscription can only react to messages that *do* arrive, never to ones that stop.

## Lesson 5 — the non-example
[hello_window.py](../lesson_05/hello_window.py) deliberately has **no topics at all** — it's plain PyQt5. It's there to contrast Qt's event loop (`app.exec_()`) with ROS 2's spin loop (`rclpy.spin(node)`), setting up lesson 6 where the two get combined. Worth noting since topics only exist inside the ROS graph — a pure-Qt file has nothing to publish or subscribe to.

**In short:** across lessons 1–4, the project accumulates these topics:

| Topic | Type | QoS |
|---|---|---|
| `/rover/gps` | `sensor_msgs/NavSatFix` | telemetry (BEST_EFFORT) |
| `/rover/status` | `urc_interfaces/RoverStatus` | telemetry (BEST_EFFORT) |
| `/mission/leg_goal` | `urc_interfaces/NavLeg` | command (RELIABLE) |
| `/mission/mode` | `std_msgs/String` | command (RELIABLE) |
| `/mission/abort` | `std_msgs/Bool` | command (RELIABLE) |
| `/rover/max_speed` | `std_msgs/Float32` | command (RELIABLE) |
| `/ops_console/heartbeat` | `std_msgs/Header` | command (RELIABLE) |

## DDS — the middleware underneath topics

DDS (Data Distribution Service) is the communication middleware that ROS 2 uses under the hood for message passing between nodes — it's what actually carries the topics, services, and actions your nodes publish/subscribe to.

Key points relevant to your workspace:

- **Pub/sub middleware standard**: DDS is an OMG (Object Management Group) industry standard for real-time, decentralized data exchange, originally used in things like aerospace/defense systems before ROS 2 adopted it.
- **No central master**: Unlike ROS 1 (which needed a `roscore` master node), DDS uses automatic peer discovery — nodes find each other on the network directly via multicast, so there's no single point of failure.
- **Pluggable implementations**: ROS 2 doesn't implement DDS itself; it sits on top of a vendor implementation via the `rmw` (ROS middleware) abstraction layer. Common ones: Fast DDS (eProsima, the default), Cyclone DDS (Eclipse), and Connext DDS (RTI). You can switch via the `RMW_IMPLEMENTATION` env var.
- **QoS (Quality of Service)**: DDS is where ROS 2's QoS settings come from — reliability (best-effort vs. reliable), durability, history depth, deadlines, etc. This matters for your `.msg` files: when you define a message like [RoverStatus.msg](../lesson_01/msg/RoverStatus.msg), the `.msg` definition gets compiled into type support that DDS serializes and ships over the wire, and the publisher/subscriber nodes negotiate QoS to actually connect.
- **Why it matters for a rover**: for a URC (University Rover Challenge) style robot, DDS's discovery and QoS knobs are relevant for things like intermittent/lossy radio links — e.g., using best-effort QoS for high-rate sensor data vs. reliable QoS for commands.
