# Lesson 6 — the ROS↔Qt threading bridge

Lesson 5 showed `app.exec_()` blocking its thread forever, dispatching
Qt's own events. Every ROS lesson before that showed the same thing about
`rclpy.spin(node)`. Put both calls on the same thread and whichever runs
first wins — permanently. The other never gets a turn. A real operator
console needs a live GUI *and* live ROS subscriptions running at the same
time, so one of them has to move to its own thread.

## The tempting fix that's actually wrong

Some tutorials use a `QTimer` that calls `rclpy.spin_once(timeout_sec=0)`
every ~16 ms, all on the GUI thread. It looks fine and even works most of
the time. The problem: it couples ROS message handling to the GUI's own
event loop. A slow repaint or a modal `QMessageBox` blocks `spin_once()`
right along with everything else — so telemetry silently stops being
processed exactly when the GUI is busiest, e.g. while an operator is
staring at a confirm dialog during a fault. That's the worst possible
moment to lose data. (This is called out directly in `plan.md` §5a.)

## The actual fix

Run the whole rclpy executor on its own `QThread`. A subscription callback
that fires on that thread must **never touch a widget directly** — Qt
widgets aren't thread-safe, and calling `label.setText(...)` from the
wrong thread is undefined behavior, not just bad style. Instead the
callback does exactly one thing: `bridge.gps_received.emit(msg)`.

That's the trick worth understanding, not just copying: Qt notices the
*emitting* thread isn't the *receiving* object's thread, and automatically
queues the delivery onto the GUI thread's event loop. By the time your
slot (`_on_gps`) actually runs, you're safely back on the GUI thread — no
locks, no manual queue, you get it for free from `.connect(...)`.

**Publishing doesn't have this problem.** `rclpy`'s `publish()` is
thread-safe on its own, so a button-click slot on the GUI thread can call
`node.some_publisher.publish(msg)` directly — no bridge needed in that
direction. The bridge only exists because *receiving* needs to hop threads
and Qt widgets are the fragile side of that hop.

## The four pieces, and what each one is not allowed to do

- **`RosBridge(QObject)`** — lives on the GUI thread, holds `pyqtSignal`s. Does no work itself.
- **`GpsListenerNode(Node)`** — its callback must never do slow work or touch widgets, only `emit(...)`.
- **`RosThread(QThread)`** — owns the executor; nothing outside it may call anything on `node` except thread-safe rclpy calls.
- **`GpsWindow(QMainWindow)`** — a lesson-5-shaped window; its slot is safe to touch widgets in, because the signal delivery already put it back on the GUI thread.

This is the exact shape of `src/urc_ops_console/urc_ops_console/ros_bridge.py`
and `main_window.py`, just for one topic instead of five.

## Run it

Needs something publishing `/rover/gps` to watch. Any earlier lesson's
node works — this file only subscribes, so it's safe to run alongside your
real system without remapping (it never sends anything to the topic, and
it doesn't matter that you did not `--ros-args` anything different):

```bash
# terminal 1 — anything that publishes /rover/gps
source /opt/ros/jazzy/setup.bash
python3 src_dev/lesson_01/minimal_rover_node.py

# terminal 2 — this lesson's GUI (needs a real display — see the DISPLAY
# notes from earlier in this conversation if you're in a remote terminal)
source /opt/ros/jazzy/setup.bash
python3 src_dev/lesson_06/gps_window.py
```

Watch the label update live. Then Ctrl-C the publisher in terminal 1 and
notice the label just... stops, frozen on the last value forever. Nothing
in this lesson knows that value has gone stale — that gap is exactly what
lesson 7's watchdog exists to close.

## What's still missing

- Only one topic, receive-only — the real bridge has five subscriptions
  and publishes five command topics back out.
- No staleness detection (lesson 7).
- No real layout — one label, same as lesson 5.
