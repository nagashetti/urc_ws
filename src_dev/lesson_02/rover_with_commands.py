#!/usr/bin/env python3
"""Lesson 2: real QoS profiles, and a node that reacts to commands.

Builds directly on lesson_01/minimal_rover_node.py. Two new ideas:

1. QoS profiles. Lesson 1's publisher used a bare `10` (an implicit
   RELIABLE, keep-last-10 queue). That's the wrong default for a lossy
   ~1 km radio link: telemetry should be BEST_EFFORT/depth-1 (the latest
   fix beats a queued retransmit of a stale one), while commands must be
   RELIABLE/depth-10 (a dropped ABORT is unacceptable). Same two profiles
   as src/urc_ops_console/urc_ops_console/qos.py.

2. Subscriptions. This node now reacts instead of only emitting: a leg
   goal (urc_interfaces/NavLeg) and a mode switch (std_msgs/String). Each
   callback just updates instance state — it must never block, since
   callbacks and the publish timer share one executor thread.

Needs the custom messages built, so unlike lesson 1 this isn't standalone:
    source /opt/ros/jazzy/setup.bash
    source ~/urc_ws/install/setup.bash
    python3 src_dev/lesson_02/rover_with_commands.py
"""

"""
QoS (Quality of Service) is the set of delivery rules that a publisher and subscriber agree on for a topic — it governs how messages are delivered, not what's in them (that's the .msg file's job). ROS 2 sits on top of DDS, which was built for exactly this: real-time, unreliable-network scenarios where "just deliver everything reliably" is sometimes the wrong answer.

The two policies you're using in rover_with_commands.py:

Reliability

RELIABLE — guarantees delivery; if a message doesn't arrive, DDS retransmits it. Good for commands: a dropped ABORT is unacceptable.
BEST_EFFORT — sends once, no retry. If it's lost, it's lost. Good for telemetry on a lossy link: retrying a 3-second-old GPS fix just delays the fresh one behind it.
History

KEEP_LAST(depth=N) — hold only the last N unread messages in the queue.
(there's also KEEP_ALL, which you're not using — unbounded queue, rarely what you want)
That's why telemetry_qos is BEST_EFFORT, depth=1 (only ever care about the newest fix) and command_qos is RELIABLE, depth=10 (must arrive, and a short burst can queue).

Why it's not just a style choice: a publisher and subscriber with incompatible QoS won't talk to each other cleanly. You actually already saw this — when I ran lesson 1's node (implicit RELIABLE via that bare 10) while your real rover_sim (BEST_EFFORT) was also publishing to /rover/gps, ros2 topic echo printed:


Some, but not all, publishers are offering QoSReliabilityPolicy.RELIABLE. Falling back to QoSReliabilityPolicy.BEST_EFFORT as it will connect to all publishers
That's ROS 2 detecting the mismatch and telling you it had to compromise to make the connection work at all — a live example of why the project defines telemetry_qos/command_qos once in qos.py and has every publisher/subscriber use the same two profiles, rather than letting each one pick its own.

"""
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import String

from urc_interfaces.msg import NavLeg, RoverStatus


class RoverWithCommands(Node):
    """Publishes GPS + status; reacts to a mode switch and a leg goal."""

    def __init__(self):
        super().__init__('rover_with_commands')

        # Several parameters at once, the way the real sim node does it —
        # one declare_parameters() call rather than one per value.
        self.declare_parameters(namespace='', parameters=[
            ('publish_rate_hz', 5.0),
            ('latitude', 38.406400),
            ('longitude', -110.791200),
        ])
        self.publish_rate_hz = self.get_parameter('publish_rate_hz').value
        self.lat = self.get_parameter('latitude').value
        self.lon = self.get_parameter('longitude').value

        # State the two callbacks below mutate, and publish_status()
        # reports back out. `goal` isn't acted on yet — driving toward it
        # is lesson 3.
        self.mode = RoverStatus.MODE_IDLE
        self.goal = None
        self.active_leg_id = 0

        telemetry_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        command_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.gps_pub = self.create_publisher(NavSatFix, '/rover/gps', telemetry_qos)
        self.status_pub = self.create_publisher(RoverStatus, '/rover/status', telemetry_qos)

        self.create_subscription(NavLeg, '/mission/leg_goal', self.goal_callback, command_qos)
        self.create_subscription(String, '/mission/mode', self.mode_callback, command_qos)

        self.create_timer(1.0 / self.publish_rate_hz, self.publish_loop)

    def goal_callback(self, msg: NavLeg):
        self.goal = msg
        self.active_leg_id = int(msg.leg_id)
        self.get_logger().info(f'New goal: leg {msg.leg_id} at {msg.latitude:.6f}, {msg.longitude:.6f}')

    def mode_callback(self, msg: String):
        text = msg.data.strip().upper()
        self.mode = RoverStatus.MODE_AUTONOMOUS if text == 'AUTONOMOUS' else RoverStatus.MODE_IDLE
        self.get_logger().info(f'Mode set to {text}')

    def publish_loop(self):
        self.publish_gps()
        self.publish_status()

    def publish_gps(self):
        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'gps'
        msg.latitude = self.lat
        msg.longitude = self.lon
        msg.altitude = 0.0
        self.gps_pub.publish(msg)

    def publish_status(self):
        # Reports whatever the callbacks above have most recently set.
        # distance/bearing stay 0.0 until lesson 3's drive controller
        # actually moves the rover toward self.goal.
        msg = RoverStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.mode = self.mode
        msg.active_leg_id = self.active_leg_id
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RoverWithCommands()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
