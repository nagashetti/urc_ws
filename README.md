# URC Operator Console

PyQt5 + ROS 2 Jazzy ground station for the URC Autonomous Navigation Mission.

## Packages

| Package | Type | Purpose |
|---|---|---|
| `urc_interfaces` | ament_cmake | Custom msgs (`RoverStatus`, `NavLeg`, `LinkStats`) |
| `urc_rover_sim` | ament_python | Fake rover node for development/demo without hardware |
| `urc_ops_console` | ament_python | PyQt5 GUI node (the operator console) |
| `urc_bringup` | ament_python | Launch files + shared params |

## Topic contract

This is the interface both `urc_rover_sim` and `urc_ops_console` are built against. Either side may be swapped (e.g. real rover hardware, Gazebo bridge) without changing the other, as long as this contract holds.

**GUI subscribes (telemetry, `BEST_EFFORT` / `KEEP_LAST` depth 1):**

| Topic | Type | Rate |
|---|---|---|
| `/rover/gps` | `sensor_msgs/NavSatFix` | 5 Hz |
| `/rover/imu` | `sensor_msgs/Imu` | 20 Hz |
| `/rover/odom` | `nav_msgs/Odometry` | 10 Hz |
| `/rover/status` | `urc_interfaces/RoverStatus` | 2 Hz |
| `/rover/link` | `urc_interfaces/LinkStats` | 1 Hz |

**GUI publishes (commands, `RELIABLE` / `KEEP_LAST` depth 10):**

| Topic | Type | Trigger |
|---|---|---|
| `/mission/leg_goal` | `urc_interfaces/NavLeg` | "Send leg to rover" button |
| `/mission/mode` | `std_msgs/String` (`AUTONOMOUS` / `TELEOP`) | mode toggle (with confirm dialog) |
| `/mission/abort` | `std_msgs/Bool` | big red ABORT |
| `/rover/max_speed` | `std_msgs/Float32` | speed-limit slider |
| `/ops_console/heartbeat` | `std_msgs/Header` @ 2 Hz | automatic deadman |

QoS rationale: telemetry is best-effort/depth-1 because on a lossy link the latest fix matters more than a retransmitted stale one; commands are reliable because a dropped ABORT is unacceptable. `/mission/abort` intentionally stays volatile (not transient-local) so a freshly restarted node never replays a stale abort.

## Message definitions

`RoverStatus.msg`:
```
uint8 MODE_IDLE=0
uint8 MODE_TELEOP=1
uint8 MODE_AUTONOMOUS=2
std_msgs/Header header
uint8 mode
uint8 active_leg_id
bool  leg_reached          # drives flashing-green LED
float32 distance_to_goal_m
float32 bearing_to_goal_deg
float32 battery_pct
bool    aruco_visible
int32   aruco_id
string  state_text         # e.g. "SEARCHING FOR TAG"
```

`NavLeg.msg`:
```
uint8 MARKER_NONE=0
uint8 MARKER_ARUCO=1
uint8 MARKER_OBJECT=2

uint8 leg_id
float64 latitude
float64 longitude
uint8 marker_type
int32 aruco_id
float32 time_limit_s
```

`LinkStats.msg`:
```
float32 rssi_dbm
float32 loss_pct
float32 rtt_ms
```

## Build

```bash
cd ~/urc_ws
rosdep install --from-paths src -y --ignore-src
colcon build --symlink-install
source install/setup.bash
```

## Verify the interfaces

```bash
ros2 interface show urc_interfaces/msg/RoverStatus
ros2 interface show urc_interfaces/msg/NavLeg
ros2 interface show urc_interfaces/msg/LinkStats
```
