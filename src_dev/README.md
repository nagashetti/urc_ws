# src_dev — learn `src` by rebuilding it, 100 lines at a time

This is not a ROS package and isn't built by colcon. It's a lesson series:
each `lesson_NN/` folder is roughly the next 100 lines of code you'd write
if you were building the real `src/` project from nothing, in the order
the ideas actually depend on each other (not the order the files happen to
sit in `src/`).

Read a lesson's own README first, then its code — every line has a comment
explaining *why* it's there, not just what it does.

## Lessons so far

| Lesson | Teaches | Maps to |
|---|---|---|
| [lesson_01](lesson_01/) | The topic contract; a minimal rclpy Node with one publisher and one timer | `urc_interfaces/msg/*`, the skeleton of `urc_rover_sim/rover_sim_node.py` |
| [lesson_02](lesson_02/) | Real QoS profiles (BEST_EFFORT vs RELIABLE); subscriptions and callback-driven state | `urc_ops_console/qos.py`, the subscription block of `rover_sim_node.py` |
| [lesson_03](lesson_03/) | The drive controller — distance/bearing math, moving toward a goal each tick, arrival with a tolerance, and a self-clearing flash timer | the `drive_to_goal`/`_distance_and_bearing_to` part of `rover_sim_node.py` |
| [lesson_04](lesson_04/) | The deadman heartbeat (reacting to a message's *absence*), abort, and a live speed-limit override | the rest of `rover_sim_node.py`. **Found and fixed a real bug** in the real file while testing this lesson — see lesson_04's README. |
| [lesson_05](lesson_05/) | The smallest PyQt5 window — `QApplication`, `QMainWindow` + one central widget, and Qt's own signal/slot mechanism. Zero ROS. | Phase 1's "hello window" check, and the shape of `main_window.py` |
| [lesson_06](lesson_06/) | The ROS↔Qt threading bridge — why `rclpy.spin()` and `app.exec_()` can't share a thread, and the `QThread` + `pyqtSignal` pattern that lets a subscription callback safely reach a widget | `ros_bridge.py` |
| [lesson_07](lesson_07/) | Watching a value go stale — a pure-Python staleness classifier, kept free of Qt and ROS on purpose, unit-tested with a fake clock instead of real `sleep()` calls | `watchdog.py` |

## That's the roadmap — architecturally, you've now rebuilt `src/`

Messages and QoS (1–2), a drive controller and safety overrides (3–4), a
GUI and the thread bridge that makes it safe (5–6), and staleness
detection (7) — every core idea in the real project, each introduced in
isolation and actually run, not just read. Lesson 4 also caught a real bug
in the real project along the way (see its README).

What's left in `src/` from here is packaging and glue, not new
architecture: the full multi-widget layout wiring all seven ideas
together (`main_window.py`), the launch file, and `colcon test` running
`geo.py`/`watchdog.py` under pytest as part of the build (`plan.md` Phase
6). None of that needs its own lesson — if you want to go further, ask for
it directly rather than as "the next lesson."

## A gotcha you'll hit if you test these against the real system

Every lesson node uses the *same* topic names as the real project
(`/rover/gps`, `/mission/mode`, ...). If your real `rover_sim`/`ops_console`
launch is running at the same time, a lesson node's publishers/subscribers
will freely mix with the real ones — `ros2 topic pub /mission/mode ...`
would command *both*, and `ros2 topic echo /rover/status` might show you
the real node's messages instead of the lesson's. Either stop the real
launch first, or remap the lesson node's topics so it can't collide:

```bash
python3 src_dev/lesson_03/rover_that_drives.py --ros-args \
  -r /rover/gps:=/lesson3/gps -r /rover/status:=/lesson3/status \
  -r /mission/mode:=/lesson3/mode -r /mission/leg_goal:=/lesson3/leg_goal
```

then point `ros2 topic pub`/`echo` at the `/lesson3/...` names instead.

Each lesson is meant to run on its own where possible, so you can see it do
something before moving to the next one.
