# Implementation Plan — URC Operator Console (PyQt + ROS 2 Jazzy)

## 0. Decisions to lock before writing code

**Mission pick (recommended): Autonomous Navigation Mission.**

Reasons it beats the alternatives for this brief:
- It has a hard, explicit *rule* that forces a GUI design decision: the rover must carry a status LED — **red = autonomous, blue = teleoperated, flashing green = arrival at a leg target**. Mirroring that state panel in the GUI gives you a direct, quotable answer to "what in the rules shaped a design decision."
- Waypoints are handed to teams as decimal-degree GNSS coordinates → a natural "operator types a value and publishes it" interaction, not a toy button.
- Legs are timed and skippable → the operator needs a *decision* display (time remaining, distance/bearing to target, skip/abort), which is exactly the "tool, not demo widget" framing.
- Comms constraints (limited bandwidth, ~1 km, no field internet) give you real content for the lossy-link and topic-silence questions.

Runner-up: Science Mission (soil sensor telemetry + cache/sample control). Swapping later costs ~a day since the architecture below is mission-agnostic.

> ⚠️ Pull the **current** URC rules PDF and cite exact section numbers in your log. Don't take my summary of the LED/leg rules as authoritative — verify each one against the document you're actually building against, and screenshot the sections you cite.

**Stack choices:**
| Choice | Pick | Why |
|---|---|---|
| Qt binding | **PyQt5 via `apt install python3-pyqt5`** | Matches the Qt that ROS 2 Jazzy's own `rqt` stack uses (system Python 3.12). Avoids venv/dpkg mixing. PyQt6 via pip works but adds friction with `rosdep`/`colcon`. |
| ROS↔Qt threading | rclpy executor in a `QThread`, node emits `pyqtSignal` | Never touch widgets off the GUI thread. See §4. |
| Sim source | Custom Python rover sim node first; Gazebo Harmonic as optional Phase 7 | Gets you a working deliverable fast; Gazebo becomes an upgrade, not a blocker. |

---

## Phase 1 — Environment (½ day)

You already have `Ubuntu 24` under VirtualBox. Verify/complete inside the VM:

```bash
# 1. Confirm base
lsb_release -a                 # must be 24.04
# 2. ROS 2 Jazzy
sudo apt update && sudo apt install -y ros-jazzy-desktop
# 3. Dev tools
sudo apt install -y python3-colcon-common-extensions python3-rosdep \
                    python3-vcstool build-essential git
sudo rosdep init 2>/dev/null; rosdep update
# 4. Gazebo Harmonic + ROS bridge
sudo apt install -y ros-jazzy-ros-gz gz-harmonic
# 5. Qt
sudo apt install -y python3-pyqt5 python3-pyqt5.qtsvg
# 6. Recording
sudo apt install -y obs-studio      # or: simplescreenrecorder
echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc
```

VM gotchas to handle now, not on demo day:
- Give the VM ≥4 vCPU / 8 GB RAM, enable 3D acceleration, VBoxSVGA/VMSVGA + Guest Additions.
- Gazebo Harmonic in VirtualBox frequently fails on the Ogre2 render backend. Test early: `gz sim -v4 shapes.sdf`. If it black-screens, fall back with `gz sim --render-engine ogre` or `LIBGL_ALWAYS_SOFTWARE=1`.
- Set `export ROS_DOMAIN_ID=42` in `~/.bashrc` so a noisy network doesn't cross-talk.

**Acceptance:** `ros2 run demo_nodes_cpp talker` + `ros2 topic echo /chatter` in two terminals, and a PyQt hello-window opens.

---

## Phase 2 — Workspace & package skeleton (½ day)

```
~/urc_ws/src/
├── urc_interfaces/        # ament_cmake — msgs/srvs only
│   ├── msg/RoverStatus.msg
│   ├── msg/NavLeg.msg
│   └── msg/LinkStats.msg
├── urc_rover_sim/         # ament_python — fake rover + optional link degrader
│   └── urc_rover_sim/rover_sim_node.py
├── urc_ops_console/       # ament_python — the PyQt GUI node
│   └── urc_ops_console/
│       ├── ros_bridge.py       # QObject wrapper around rclpy Node
│       ├── qos.py              # centralised QoS profiles
│       ├── watchdog.py         # staleness tracking (pure python, unit-tested)
│       ├── geo.py              # lat/lon → local ENU, distance/bearing
│       ├── widgets/
│       │   ├── map_view.py
│       │   ├── led_panel.py
│       │   ├── telemetry_tile.py
│       │   ├── leg_planner.py
│       │   └── link_health.py
│       └── main_window.py
└── urc_bringup/           # launch + config
    └── launch/ops_console.launch.py
```

Create with:
```bash
mkdir -p ~/urc_ws/src && cd ~/urc_ws/src
ros2 pkg create urc_interfaces --build-type ament_cmake
ros2 pkg create urc_rover_sim  --build-type ament_python --dependencies rclpy sensor_msgs geometry_msgs
ros2 pkg create urc_ops_console --build-type ament_python --dependencies rclpy sensor_msgs geometry_msgs
ros2 pkg create urc_bringup --build-type ament_python
```

Add `<exec_depend>python3-pyqt5</exec_depend>` and `<depend>urc_interfaces</depend>` to `urc_ops_console/package.xml`.

**Acceptance:** `colcon build --symlink-install && source install/setup.bash` clean.

---

## Phase 3 — Interfaces & topic contract (½ day)

Write this table into the README *before* coding — it's the contract both nodes hold to.

**GUI subscribes (telemetry, BEST_EFFORT / KEEP_LAST 1):**

| Topic | Type | Rate |
|---|---|---|
| `/rover/gps` | `sensor_msgs/NavSatFix` | 5 Hz |
| `/rover/imu` | `sensor_msgs/Imu` | 20 Hz |
| `/rover/odom` | `nav_msgs/Odometry` | 10 Hz |
| `/rover/status` | `urc_interfaces/RoverStatus` | 2 Hz |
| `/rover/link` | `urc_interfaces/LinkStats` | 1 Hz |

**GUI publishes (commands, RELIABLE / KEEP_LAST 10):**

| Topic | Type | Trigger |
|---|---|---|
| `/mission/leg_goal` | `urc_interfaces/NavLeg` | "Send leg to rover" button |
| `/mission/mode` | `std_msgs/String` (`AUTONOMOUS`/`TELEOP`) | mode toggle (with confirm dialog) |
| `/mission/abort` | `std_msgs/Bool` | big red ABORT |
| `/rover/max_speed` | `std_msgs/Float32` | speed-limit slider |
| `/ops_console/heartbeat` | `std_msgs/Header` @2 Hz | automatic deadman |

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

`NavLeg.msg`: `uint8 leg_id`, `float64 latitude`, `float64 longitude`, `uint8 marker_type` (NONE/ARUCO/OBJECT), `int32 aruco_id`, `float32 time_limit_s`.

`LinkStats.msg`: `float32 rssi_dbm`, `float32 loss_pct`, `float32 rtt_ms`.

**Acceptance:** `ros2 interface show urc_interfaces/msg/RoverStatus` works.

---

## Phase 4 — The rover sim node (1 day)

`rover_sim_node.py` — a self-contained fake rover that makes the demo *legible on camera*:

1. Holds state: lat/lon (seeded at a plausible MDRS-area datum), heading, speed, mode, battery, active leg.
2. Subscribes to every command topic above. On `/mission/leg_goal` it stores the goal and, if mode is `AUTONOMOUS`, drives toward it with a simple bearing controller; publishes `leg_reached=True` for 3 s on arrival.
3. Respects `/rover/max_speed` — the slider must visibly change how fast the marker crawls across the map. **This is your "visible effect" for the screen recording.**
4. Deadman: if no `/ops_console/heartbeat` for 2 s, clamp speed to 0 and log `LINK LOST — HOLDING`. Second visible effect, and it demonstrates you thought about comms.
5. Declare ROS parameters: `publish_rate_hz`, `gps_noise_m`, `drop_probability`, `stall_after_s`. `stall_after_s` and `drop_probability` are your **fault-injection switches** — you will use `ros2 param set` live on camera to kill the GPS stream and show the GUI reacting. Do not skip these; two of the five log questions depend on being able to demo this.

**Acceptance:** `ros2 topic hz /rover/gps` shows 5 Hz; `ros2 param set /rover_sim stall_after_s 1.0` stops it.

---

## Phase 5 — The GUI (3–4 days, the bulk)

### 5a. ROS↔Qt bridge (`ros_bridge.py`)

```python
class RosBridge(QObject):
    gps_received = pyqtSignal(object)
    status_received = pyqtSignal(object)
    link_received = pyqtSignal(object)
    # ... one signal per subscription

class RosThread(QThread):
    def run(self):
        rclpy.spin(self.node)   # executor owns this thread only
```
Subscription callbacks run on the ROS thread and do exactly one thing: `self.gps_received.emit(msg)`. Qt's queued connections marshal to the GUI thread. Publishers are called directly from GUI slots (rclpy publish is thread-safe).

> Why not the common `QTimer → rclpy.spin_once(timeout_sec=0)` trick: it works, but it couples telemetry latency to GUI repaint and silently drops to ~0 Hz while a modal dialog or a slow paint blocks the event loop. Under a competition mission that's exactly when you need telemetry. Mention this tradeoff in your log — it's the kind of reasoning the prompt is fishing for.

### 5b. Layout (design it for a sunlit tent, not a demo)

```
┌──────────────────────────────────────────────────────────────┐
│ MISSION CLOCK 12:47  │ LEG 3/7 │ ● LINK OK 42 ms │ [ABORT]   │  ← always visible
├───────────────────────────────┬──────────────────────────────┤
│                               │  MODE   [ AUTO ] [ TELEOP ]  │
│        LOCAL MAP VIEW         │  ┌────────────────────────┐  │
│   (rover track, goal, ranges) │  │   LED MIRROR: ■ RED    │  │
│                               │  └────────────────────────┘  │
│                               │  DIST TO GOAL   84.2 m       │
│                               │  BEARING        071°         │
├───────────────────────────────┤  ARUCO          ID 4 ✓       │
│ LEG PLANNER                   │  BATTERY        72 %         │
│ lat [38.406___] lon [-110.79_]│  SPEED LIMIT  [──●────] 1.2  │
│ marker (ARUCO ▾) id [4]       │                              │
│        [ SEND LEG TO ROVER ]  │  STATE: SEARCHING FOR TAG    │
└───────────────────────────────┴──────────────────────────────┘
```

Design rules to hold yourself to:
- **No internet map tiles.** Custom `QWidget` with `paintEvent`, plotting a local ENU projection around the first GNSS fix. Justify it in the log: there is no field internet at URC, and tile fetches on the command network are bandwidth you don't have.
- Every number carries units and a fixed decimal count. No jitter-scrolling text.
- Colour is never the *only* channel — the LED mirror shows `■ RED — AUTONOMOUS` in text too.
- Destructive/irreversible actions (`AUTONOMOUS` engage, `ABORT`) get a confirm step or are physically separated from routine controls.
- Coordinate entry validates (`QDoubleValidator`, sane lat/lon bounds) and the Send button stays disabled until valid — an operator mistyping a longitude under time pressure should be caught by the GUI, not by the rover.

### 5c. Staleness / silent-topic handling (`watchdog.py`) — do this properly

This is one of the explicitly-graded log questions, so make it a first-class subsystem, not an afterthought:

- Each subscription records `last_rx` monotonic time and a rolling 5 s message-rate estimate.
- A 5 Hz `QTimer` evaluates every stream against thresholds: **fresh (<1 s)** → normal; **stale (1–3 s)** → tile turns amber, appends "⚠ 1.4 s old"; **lost (>3 s)** → tile turns red, the *value greys out and is struck through*, header shows `SIGNAL LOST: GPS`, and the map rover marker switches to a hollow dashed outline at its last known position.
- Key principle to state in the log: **a stale value is never rendered as if it were fresh, and loss of data is never rendered as a zero.** A frozen "0.0 m/s" that actually means "no telemetry" is how an operator drives a rover into a rock.
- Keep `watchdog.py` free of Qt imports so you can unit-test it with pytest.

### 5d. QoS (`qos.py`)
```python
TELEMETRY = QoSProfile(reliability=BEST_EFFORT, history=KEEP_LAST, depth=1)
COMMAND   = QoSProfile(reliability=RELIABLE,    history=KEEP_LAST, depth=10)
```
Telemetry is best-effort depth-1 because on a lossy link you want *the latest* fix, not a retransmitted 4-second-old one clogging the pipe. Commands are reliable because a dropped ABORT is unacceptable. Consider `TRANSIENT_LOCAL` for `/mission/mode` so a rover node that restarts inherits the current mode — but note the hazard in your log: transient-local on `/mission/abort` would replay a stale abort to a freshly-restarted node, so that one stays volatile.

**Acceptance per sub-phase:** GUI opens with sim running, values update live, killing the sim (`Ctrl-C`) turns the whole panel red within 3 s.

---

## Phase 6 — Launch, packaging, tests (1 day)

- `ops_console.launch.py` brings up `rover_sim` + `ops_console` with a shared params YAML.
- `setup.py` console_scripts entry points: `rover_sim = urc_rover_sim.rover_sim_node:main`, `ops_console = urc_ops_console.main_window:main`.
- pytest for `geo.py` (known lat/lon → distance/bearing pairs) and `watchdog.py` (fake clock → state transitions). `colcon test` must pass.
- README: architecture diagram, topic contract table, one-command run instructions, screenshots.

**Acceptance:** fresh clone → `rosdep install --from-paths src -y` → `colcon build` → `ros2 launch urc_bringup ops_console.launch.py` works on a clean VM snapshot. Actually test this on a snapshot; it's where submissions usually die.

---

## Phase 7 — Optional: swap the fake rover for Gazebo Harmonic (1–2 days)

Only after Phases 1–6 are green. Spawn a diff-drive rover in a `.sdf` world, bridge with `ros_gz_bridge` (`/model/rover/odometry`, `/cmd_vel`, and a `navsat` sensor → `NavSatFix`), and point the GUI at the bridged topics. The GUI code shouldn't change at all — if it does, your topic contract was too loosely defined. That fact is itself worth writing in the log.

---

## Phase 8 — Deliverables (½ day)

1. **Screen recording** (OBS, ~3 min), scripted so each beat is unmistakable:
   - Show `ros2 topic list` / `rqt_graph` to prove real ROS 2 pub/sub.
   - Live telemetry updating; rover moving on the map.
   - Type a waypoint → Send → rover turns and drives to it → LED mirror flashes green on arrival.
   - Drag the speed slider → visible speed change + `ros2 topic echo /rover/max_speed` in a side terminal.
   - `ros2 param set /rover_sim stall_after_s 0.5` → GPS tile goes amber then red, banner fires. **Kill the sim entirely** → full-panel degradation.
   - Press ABORT → rover halts, sim logs the abort.
2. **Public GitHub repo** — init here in `D:\GitHub\ROS2` or directly in the VM; push `urc_ws/src` at the repo root with the README.
3. **Log answers** — the plan above is deliberately built so each question already has evidence: mission/rule section (§0 + cited PDF sections), what's shown vs. omitted (§5b — omit raw camera at full rate, point clouds, per-axis IMU, covariance matrices; justify by bandwidth + operator cognitive load in a timed leg), silent-topic behaviour (§5c), rules→design (LED mirror, no internet tiles, per-leg timer), and lossy-link failure (§5d).

**Draft for "what breaks first over a lossy wireless link":** default DDS discovery is multicast-heavy and reconnects badly across a marginal WiFi link — that goes before any of your application code does. Next is reliable-QoS head-of-line blocking: retransmits of stale telemetry starve fresh data, so latency grows without bound rather than data simply dropping. Then any image topic at full rate saturates the budget. Mitigations worth naming: best-effort depth-1 telemetry (already in the design), a static discovery peer list or `rmw_zenoh_cpp` (available on Jazzy) instead of the default RMW, rate-limiting at the source rather than the sink, and the console-side heartbeat/deadman so the rover degrades safely rather than driving on a stale command.

---

## Suggested sequencing

| Day | Work |
|---|---|
| 1 | Phase 1 + 2 |
| 2 | Phase 3 + 4 |
| 3–5 | Phase 5 (bridge → layout → watchdog → QoS) |
| 6 | Phase 6 |
| 7 | Phase 8 (record, push, write log) |
| +1–2 | Phase 7 if time allows |
