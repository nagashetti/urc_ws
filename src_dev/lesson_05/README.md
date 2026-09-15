# Lesson 5 — the smallest PyQt5 window, no ROS at all

Every lesson so far has been an rclpy `Node`. This one has zero ROS in it,
on purpose: before tackling "how do ROS and Qt work together" (lesson 6),
it's worth seeing that **Qt has its own event loop that has never heard of
ROS** — the same way `rclpy.spin()` has never heard of Qt. Two independent
event loops that both want to "block and dispatch events forever" is
exactly the problem lesson 6 exists to solve.

This is also Phase 1's "hello window" acceptance check from `plan.md`: a
bare PyQt5 window opening is what proves the environment is set up
correctly, before any ROS integration is attempted.

## New ideas

**1. `QApplication` owns the event loop.** Exactly one per process, and it
has to exist before you construct any widget. `app.exec_()` blocks and
hands control to Qt: it waits for clicks, key presses, timers, and paint
requests, and dispatches each to the right widget. Nothing after that line
runs until the window closes. Compare this directly to `rclpy.spin(node)`
in every earlier lesson — same shape, different, unrelated loop.

**2. `QMainWindow` + one central widget.** A `QMainWindow` doesn't let you
drop widgets onto it directly — you give it exactly one "central widget"
and lay out everything else inside that. This is the same shape
`main_window.py` uses for the whole operator console; this lesson just
puts a label and a button in that slot instead of a map view and
telemetry tiles.

**3. Signals and slots — Qt's own, nothing to do with ROS yet.**
`button.clicked.connect(self._on_click)` wires a built-in Qt signal
(`clicked`) to a plain method. This is the exact mechanism `ros_bridge.py`
leans on in lesson 6 (`pyqtSignal(object)` + `.connect(...)`), just without
anything ROS-related crossing it yet — worth having seen once in isolation
before lesson 6 adds a second thread into the picture.

## Run it

This needs a real display — see the top-level `urc_ws` conversation about
running `ops_console` in the VM (export `DISPLAY`/`XAUTHORITY` if you're in
a remote/SSH terminal rather than a terminal opened on the desktop itself):

```bash
python3 src_dev/lesson_05/hello_window.py
```

Click the button a few times — the label updates instantly, with no ROS
node, no topics, nothing spinning anywhere. That's the whole point: this
window works standalone, and lesson 6 is entirely about what changes when
it needs to react to something happening on a *different* thread.

## What's still missing

- No ROS. No `RosBridge`, no `pyqtSignal` carrying a ROS message, no
  `QThread`. That's lesson 6.
- No layout beyond one label and one button — no map, no telemetry tiles,
  no leg planner. Those are just more widgets in the same central-widget
  slot; nothing conceptually new once lesson 6's bridge exists.
