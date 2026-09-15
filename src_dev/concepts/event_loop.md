# rclpy event generation: subscriptions, timers, and the spin loop

Everything a ROS 2 node *does* after `__init__()` happens because something triggered a callback. This file is a reference for the rclpy primitives that generate those triggers ("events"), what actually drives them (the spin loop / executor), and where each one shows up — or would show up — across your lessons and the real `src/` packages.

Every event source below needs two things to actually fire: something that creates it (`create_subscription`, `create_timer`, ...) and something that pumps the loop (`rclpy.spin`, an executor). No amount of `create_subscription()` calls will run a single callback if nothing is spinning — that's the recurring bug lessons 5–6 are built around.

## 1. The init → spin → shutdown skeleton

```python
rclpy.init(args=args)
node = MyNode()
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    rclpy.shutdown()
```

**When to use:** every standalone rclpy program, full stop — this is the outermost frame everything else lives inside.
**Why:** `rclpy.init()` stands up the ROS context (must happen before any Node is constructed); `spin()` is what actually pumps callbacks; `shutdown()` releases the context cleanly. Skipping any step either crashes on construction or leaks the context on exit.
**Pairs with:** every event source below — none of them fire without something spinning.
**In this project:** identical, unchanged, in [minimal_rover_node.py:74-86](../lesson_01/minimal_rover_node.py#L74-L86), [rover_with_commands.py:132-141](../lesson_02/rover_with_commands.py#L132-L141), and [rover_with_deadman.py:178-187](../lesson_04/rover_with_deadman.py#L178-L187). Lesson 1's docstring calls this out directly: "you'll see this exact block, unchanged, at the bottom of the real sim node" ([rover_sim_node.py](../../src/urc_rover_sim/urc_rover_sim/rover_sim_node.py)).

## 2. Subscriptions — event: a message arrived

```python
self.create_subscription(NavLeg, '/mission/leg_goal', self.goal_callback, command_qos)
```

**When to use:** whenever your node needs to react to data another node publishes, and doesn't need to talk back synchronously.
**Why:** it's ROS 2's core async pub/sub event source — decoupled, many-to-many, no blocking. The callback fires whenever a message lands in the queue and the executor gets a turn to run it.
**Pairs with:** a matching QoS profile on both ends (mismatched reliability silently degrades — see [topic.md](topic.md) §Lesson 2), and usually a timer or another subscription that *acts on* the state the callback just set, since callbacks themselves should stay cheap.
**In this project:** [rover_with_deadman.py:75-79](../lesson_04/rover_with_deadman.py#L75-L79) has five of these — `leg_goal`, `mode`, `abort`, `max_speed`, `heartbeat`. Each callback ([goal_callback](../lesson_04/rover_with_deadman.py#L82-L85), [abort_callback](../lesson_04/rover_with_deadman.py#L91-L96), etc.) does nothing but mutate `self.*` state — the actual driving/safety logic runs later, in the timer. The GUI side mirrors this exactly in [ros_bridge.py:50-54](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L50-L54), except each callback re-emits a Qt signal instead of setting an attribute.

## 3. Publishers — the other half of the pair, not an event source itself

```python
self.gps_pub = self.create_publisher(NavSatFix, '/rover/gps', telemetry_qos)
self.gps_pub.publish(msg)
```

**When to use:** whenever your node needs to emit data or a command onto the graph.
**Why:** included here only because it's the thing every subscription above is listening for — but note `publish()` doesn't *generate* an event in your own node; it's fire-and-forget and returns immediately. It generates an event in whoever is subscribed.
**Pairs with:** almost always a timer (poll-and-publish) or a subscription callback (react-and-republish, like `heartbeat_callback` → nothing, vs. `goal_callback` → state that a later publish reports).
**In this project:** `gps_pub` / `status_pub` in every lesson from [minimal_rover_node.py:52](../lesson_01/minimal_rover_node.py#L52) onward; `publish()` is called thread-safely straight from GUI slots in [ros_bridge.py:85-101](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L85-L101) — the one rclpy call lesson 6's docstring notes is safe to call off the ROS thread.

## 4. Timers — event: periodic tick

```python
self.create_timer(1.0 / self.publish_rate_hz, self.publish_loop)
```

**When to use:** anything that needs to happen on a schedule rather than in response to a specific message — polling, publishing telemetry, or checking "has too much time passed since X?"
**Why:** it's the only event source that fires even when *nothing else happens* — which is exactly what makes it the right (only) place to detect absence, as opposed to a subscription, which can only react to messages that arrive.
**Pairs with:** publishers (the overwhelmingly common case in this project) and, less obviously, subscription callbacks that only record a timestamp — the timer is what actually checks that timestamp later.
**In this project:** [minimal_rover_node.py:61](../lesson_01/minimal_rover_node.py#L61) is the minimal case — 5 Hz, publish only. [rover_with_deadman.py:80](../lesson_04/rover_with_deadman.py#L80) is the interesting one: `publish_loop` is where the deadman check actually lives — `heartbeat_callback` ([line 101-102](../lesson_04/rover_with_deadman.py#L101-L102)) just stamps `self.last_heartbeat`, and the timer ([line 124-125](../lesson_04/rover_with_deadman.py#L124-L125)) computes `now - self.last_heartbeat > HEARTBEAT_TIMEOUT_S` every tick. The lesson 4 docstring states the principle directly: "a callback that never fires can't run any code of its own."

## 5. Services — event: a request arrived, response expected synchronously

```python
self.srv = self.create_service(AddTwoInts, 'add_two_ints', self.srv_callback)

def srv_callback(self, request, response):
    response.sum = request.a + request.b
    return response
```

**When to use:** request/response, one-shot, caller needs the answer before moving on — "reset the odometry origin," "recalibrate the IMU," "are you ready?"
**Why:** unlike a topic, the caller gets a typed reply tied to their specific request instead of just broadcasting and hoping something acts on it.
**Pairs with:** a client (`create_client` + `call_async` + `spin_until_future_complete`, or an async await in a callback) on the other node.
**In this project:** not used anywhere yet — every command in this project (`mode`, `abort`, `max_speed`, `leg_goal`) is deliberately a topic, not a service, because the operator console never needs to block waiting for a synchronous reply from the rover over a lossy radio link (see [topic.md](topic.md)'s QoS discussion — the same lossy-link reasoning that pushes commands to RELIABLE topics is why they aren't services). If you added something like "recenter GPS origin," a service would be the right shape for it since the console genuinely wants to know it happened before proceeding — it just hasn't come up in [plan.md](../../plan.md)'s phases.

## 6. Actions — event: goal accepted, then a stream of feedback, then a result

```python
self.action_server = ActionServer(self, DriveToWaypoint, 'drive_to_waypoint', self.execute_callback)
self.action_client = ActionClient(self, DriveToWaypoint, 'drive_to_waypoint')
send_goal_future = self.action_client.send_goal_async(goal_msg, feedback_callback=self.fb_cb)
```

**When to use:** long-running, preemptible work where the caller also wants progress updates along the way — a multi-second-to-minutes task, not a millisecond request.
**Why:** it's the only rclpy primitive that natively bundles goal/feedback/result/cancel into one event sequence, instead of you hand-rolling that with a topic pair.
**Pairs with:** typically layered *on top of* topics, not replacing them — feedback often mirrors what a status topic already reports.
**In this project:** also unused, and arguably deliberately avoided — `/mission/leg_goal` + `/rover/status` in [rover_with_deadman.py:75,150-151](../lesson_04/rover_with_deadman.py#L75) already gives the console goal-in / continuous-feedback-out / reached-flag without the bookkeeping overhead of a real action server. `drive_to_goal()` ([line 111-121](../lesson_04/rover_with_deadman.py#L111-L121)) is functionally "the execute callback" of an action, just expressed as a timer tick reading `self.goal` instead. Worth reaching for if a future phase needs cancel-mid-goal semantics beyond what `/mission/abort` already gives you.

## 7. Parameter-change callback — event: a param was set live

```python
self.add_on_set_parameters_callback(self.param_callback)

def param_callback(self, params):
    for p in params:
        ...
    return SetParametersResult(successful=True)
```

**When to use:** when a live `ros2 param set` needs to trigger real reaction (validation, or re-deriving something) instead of just silently updating a stored value.
**Why:** without it, `declare_parameter` values are read once (or read fresh each access) but nothing *notices* a change — this is the event source for that.
**Pairs with:** `declare_parameter`/`declare_parameters`, which this project already uses.
**In this project:** [minimal_rover_node.py:40-41](../lesson_01/minimal_rover_node.py#L40-L41) and [rover_with_commands.py:63-70](../lesson_02/rover_with_commands.py#L63-L70) declare `publish_rate_hz`, `latitude`, `longitude` — but only read them once at startup via `self.get_parameter(...).value`. There's no `add_on_set_parameters_callback`, so a live `ros2 param set` on this node currently does nothing to its running behavior. Lesson 1's comment flags this as future work: "this one habit is what makes the real sim's fault injection possible later (`drop_probability`, `stall_after_s`)" — that's exactly the kind of param where you'd want the change to take effect immediately, which needs this callback.

## 8. Spinning — what actually pumps every event above

```python
rclpy.spin(node)                                 # blocks, runs callbacks forever
rclpy.spin_once(node, timeout_sec=1.0)            # runs at most one
rclpy.spin_until_future_complete(node, future)    # blocks until a Future (e.g. a service call) resolves
```

**When to use:** `spin()` for the common case — a node with nothing else to do but process ROS events. `spin_once`/timed variants only when something *else* also needs the thread.
**Why:** rclpy callbacks never run on their own — they only run while something is inside a spin call. `spin()` is the simple, correct default; `spin_once` shows up in tutorials as a way to interleave ROS with another loop, but it couples ROS responsiveness to whatever else is sharing that call site.
**Pairs with:** an `Executor` under the hood (`spin()` is really "construct a default `SingleThreadedExecutor`, add this node, spin it").
**In this project:** `rclpy.spin(node)` is the pattern in every standalone lesson node ([minimal_rover_node.py:81](../lesson_01/minimal_rover_node.py#L81), etc). `spin_once` is explicitly called out and rejected: lesson 6's docstring names "a `QTimer` calling `rclpy.spin_once(timeout_sec=0)`" as "the tempting-but-wrong fix" ([gps_window.py:10-13](../lesson_06/gps_window.py#L10-L13)) — because a slow repaint or modal dialog on the GUI thread would block `spin_once()` right when telemetry matters most. `ros_bridge.py`'s docstring repeats the same warning ([ros_bridge.py:6-8](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L6-L8)).

## 9. Executors — what `spin()` is secretly doing, made explicit

```python
executor = SingleThreadedExecutor()
executor.add_node(node)
executor.spin()   # blocks THIS thread
```

**When to use:** any time you need to control *which thread* ROS callbacks run on, or spin more than one node together.
**Why:** `rclpy.spin(node)` hides this by creating a default executor for you — fine for a single standalone node, but wrong the moment ROS has to share a process with something else that also wants to own a thread (a GUI event loop, here).
**Pairs with:** `QThread` (in this project) — the executor owns the ROS-side thread, Qt signals carry data across to the GUI thread.
**In this project:** this is the actual fix lesson 6 builds toward. [gps_window.py:57-74](../lesson_06/gps_window.py#L57-L74)'s `RosThread` wraps a `SingleThreadedExecutor`, calls `executor.spin()` inside `QThread.run()`, and the subscription callback only ever does `self._bridge.gps_received.emit(msg)` — never touches a widget directly, since Qt widgets aren't thread-safe. The real console does the identical thing in [ros_bridge.py:104-123](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L104-L123). `MultiThreadedExecutor` doesn't appear anywhere in this project — there's only ever one node per process here, so there's nothing to parallelize across.

## 10. Callback groups — controlling concurrency *within* one node's callbacks

```python
from rclpy.callback_groups import ReentrantCallbackGroup
cbg = ReentrantCallbackGroup()
self.create_subscription(String, 'topic', self.cb, 10, callback_group=cbg)
```

**When to use:** when two callbacks on the same node need to run concurrently (e.g. a slow service call shouldn't block a timer) — otherwise a `MultiThreadedExecutor` alone still runs same-group callbacks one at a time.
**Why:** by default every callback on a node is `MutuallyExclusiveCallbackGroup` — safe, but serial. This is the knob for relaxing that.
**Pairs with:** `MultiThreadedExecutor` — a callback group is meaningless under a single-threaded one.
**In this project:** not used, and there's no `MultiThreadedExecutor` in the codebase to pair it with. Every node here (`RoverWithDeadman`, `OpsConsoleNode`) has a handful of cheap, non-blocking callbacks under one `SingleThreadedExecutor`, so there's no contention this would solve yet — it'd become relevant only if a future node needed a slow blocking call (e.g. a synchronous service client call) to not stall the timer alongside it.

## 11. Guard conditions — manually-triggered events

```python
guard = node.create_guard_condition(callback=self.guard_cb)
guard.trigger()
```

**When to use:** rare — injecting a wake-up into the executor from outside the normal ROS message flow (e.g. another thread wants to force a spin cycle immediately).
**Why:** every other event source in this file is driven by ROS itself (a message, a timer tick); a guard condition is the escape hatch for triggering the executor from your own code instead.
**Pairs with:** cross-thread signaling, as an alternative to what Qt signals already do in this project.
**In this project:** unused — [gps_window.py](../lesson_06/gps_window.py) and [ros_bridge.py](../../src/urc_ops_console/urc_ops_console/ros_bridge.py) already solve cross-thread signaling with `pyqtSignal`, which is the more natural tool once Qt is in the picture anyway. This would only matter in a pure-rclpy (no Qt) multi-thread setup.

## 12. Rate — an older, less composable alternative to timers

```python
rate = node.create_rate(2)  # 2 Hz
rate.sleep()
```

**When to use:** almost never in new code — prefer `create_timer` (§4).
**Why:** `rate.sleep()` blocks the calling thread until the next tick, which only behaves correctly if something *else* is spinning the node concurrently (usually a separate thread) — easy to misuse into a deadlock (the classic bug: calling `rate.sleep()` from the same thread/callback that's supposed to be spinning). A timer callback is driven by the executor instead, so it can't deadlock itself this way.
**Pairs with:** a separate spin thread, if used at all.
**In this project:** not used anywhere — every periodic need (`publish_gps`, `publish_loop`, `_publish_heartbeat`) is a `create_timer` instead, consistent with this being the modern-rclpy default.

---

## Quick map: event source → where it lives in this project

| Event source | Used here? | Where |
|---|---|---|
| Subscription | Yes | [rover_with_deadman.py:75-79](../lesson_04/rover_with_deadman.py#L75-L79), [ros_bridge.py:50-54](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L50-L54) |
| Timer | Yes | [minimal_rover_node.py:61](../lesson_01/minimal_rover_node.py#L61), [rover_with_deadman.py:80](../lesson_04/rover_with_deadman.py#L80) |
| `rclpy.spin()` | Yes | every standalone lesson's `main()` |
| Executor (`SingleThreadedExecutor`) | Yes | [gps_window.py:57-74](../lesson_06/gps_window.py#L57-L74), [ros_bridge.py:104-123](../../src/urc_ops_console/urc_ops_console/ros_bridge.py#L104-L123) |
| Service | No | topics chosen instead — see §5 |
| Action | No | topic pair (`leg_goal` + `status`) chosen instead — see §6 |
| Param-change callback | No | params are read once at startup, not watched — see §7 |
| `MultiThreadedExecutor` / callback groups | No | one node per process, nothing to parallelize yet |
| Guard condition | No | Qt signals cover cross-thread signaling instead |
| `create_rate` | No | timers used exclusively |
