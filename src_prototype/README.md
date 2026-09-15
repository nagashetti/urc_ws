# src_prototype — LED indicator console

Two files, minimum code to satisfy the brief:

- `rover_stub.py` — a simple publisher node. Publishes `/rover/status`
  and reacts to `/mission/mode` (`std_msgs/String`: `TELEOP` |
  `AUTONOMOUS` | `ARRIVED`).
- `led_console.py` — the GUI. Subscribes to `/rover/status` and renders
  the required LED rule (red = autonomous, blue = teleop, flashing
  green = arrived at target). Three buttons publish `/mission/mode`
  based on operator input.

## Run

```bash
source /opt/ros/jazzy/setup.bash
source /home/rohan/urc_ws/install/setup.bash

# terminal 1
python3 src_prototype/rover_stub.py

# terminal 2
python3 src_prototype/led_console.py
```

Click TELEOP / AUTONOMOUS / ARRIVED in the GUI and watch the LED swatch
change (ARRIVED flashes green for 4s then reverts to whatever mode was
last set).

See `LOG.md` for the design write-up.
