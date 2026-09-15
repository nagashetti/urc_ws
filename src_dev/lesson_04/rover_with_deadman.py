#!/usr/bin/env python3
"""Lesson 4: the deadman heartbeat, abort, and a live speed limit.

Builds on lesson_03/rover_that_drives.py. Replaces the hardcoded SPEED_MPS
with three operator-controlled overrides:

1. Deadman heartbeat. Every other callback in this project reacts to a
   message arriving; this one reacts to a message NOT arriving.
   heartbeat_callback only records a timestamp — the actual safety check
   (has too much time passed since the last one?) has to live in the timer
   callback, publish_loop, since a callback that never fires can't run any
   code of its own.

2. Abort. Clears self.goal immediately. Since drive_to_goal() only ever
   runs when self.goal is not None, clearing it is enough to stop movement
   on the very next tick — no separate "stop" flag needed.

3. Speed limit. SPEED_MPS the constant becomes self.max_speed_mps the
   state, starting at 0.0 (the rover doesn't move until told a speed) and
   changed only by max_speed_callback.

Needs the custom messages built, and collides with the real project's
topic names — see the top-level src_dev README's remap example.
"""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Bool, Float32, Header, String

from urc_interfaces.msg import NavLeg, RoverStatus

ARRIVAL_RADIUS_M = 2.0
LEG_REACHED_FLASH_S = 3.0
HEARTBEAT_TIMEOUT_S = 2.0


class RoverWithDeadman(Node):
    """Lesson 3's driving node, plus heartbeat/abort/speed-limit overrides."""

    def __init__(self):
        super().__init__('rover_with_deadman')

        self.declare_parameters(namespace='', parameters=[
            ('publish_rate_hz', 5.0),
            ('latitude', 38.406400),
            ('longitude', -110.791200),
        ])
        self.publish_rate_hz = self.get_parameter('publish_rate_hz').value
        self.lat = self.get_parameter('latitude').value
        self.lon = self.get_parameter('longitude').value

        self.mode = RoverStatus.MODE_IDLE
        self.goal = None
        self.active_leg_id = 0
        self.heading_deg = 0.0
        self.leg_reached = False
        self.leg_reached_at = None
        self.max_speed_mps = 0.0
        self.last_heartbeat = time.monotonic()
        self.state_text = 'IDLE'
        self._link_lost_logged = False

        telemetry_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)
        command_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=10)

        self.gps_pub = self.create_publisher(NavSatFix, '/rover/gps', telemetry_qos)
        self.status_pub = self.create_publisher(RoverStatus, '/rover/status', telemetry_qos)
        self.create_subscription(NavLeg, '/mission/leg_goal', self.goal_callback, command_qos)
        self.create_subscription(String, '/mission/mode', self.mode_callback, command_qos)
        self.create_subscription(Bool, '/mission/abort', self.abort_callback, command_qos)
        self.create_subscription(Float32, '/rover/max_speed', self.max_speed_callback, command_qos)
        self.create_subscription(Header, '/ops_console/heartbeat', self.heartbeat_callback, command_qos)
        self.create_timer(1.0 / self.publish_rate_hz, self.publish_loop)

    def goal_callback(self, msg: NavLeg):
        self.goal = msg
        self.active_leg_id = int(msg.leg_id)
        self.leg_reached = False

    def mode_callback(self, msg: String):
        text = msg.data.strip().upper()
        self.mode = RoverStatus.MODE_AUTONOMOUS if text == 'AUTONOMOUS' else RoverStatus.MODE_IDLE

    def abort_callback(self, msg: Bool):
        if msg.data:
            self.goal = None
            self.leg_reached = False
            self.state_text = 'ABORTED'
            self.get_logger().warn('Mission aborted by operator')

    def max_speed_callback(self, msg: Float32):
        self.max_speed_mps = max(0.0, float(msg.data))

    def heartbeat_callback(self, _msg: Header):
        self.last_heartbeat = time.monotonic()

    def _distance_and_bearing_to(self, lat2: float, lon2: float):
        dx = (lon2 - self.lon) * 111320.0 * math.cos(math.radians(self.lat))
        dy = (lat2 - self.lat) * 111320.0
        distance = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dx, dy)) % 360.0
        return distance, bearing

    def drive_to_goal(self):
        distance, bearing = self._distance_and_bearing_to(self.goal.latitude, self.goal.longitude)
        if distance < ARRIVAL_RADIUS_M:
            self.leg_reached = True
            self.leg_reached_at = time.monotonic()
            self.goal = None
            return
        self.heading_deg = bearing
        step_m = self.max_speed_mps / self.publish_rate_hz
        self.lat += (step_m * math.cos(math.radians(bearing))) / 111320.0
        self.lon += (step_m * math.sin(math.radians(bearing))) / (111320.0 * math.cos(math.radians(self.lat)))

    def publish_loop(self):
        now = time.monotonic()
        link_lost = (now - self.last_heartbeat) > HEARTBEAT_TIMEOUT_S
        if link_lost:
            self.state_text = 'LINK LOST — HOLDING'
            if not self._link_lost_logged:
                self.get_logger().warn('LINK LOST — HOLDING')
                self._link_lost_logged = True
        else:
            if self._link_lost_logged:
                # The link just came back. Without this, state_text would
                # keep reporting "LINK LOST" forever after recovery, since
                # nothing else ever overwrites it — a stale fault message
                # rendered as if it were still current. Same bug existed
                # in src/urc_rover_sim/urc_rover_sim/rover_sim_node.py.
                self.state_text = 'NAVIGATING TO LEG' if self.goal is not None else (
                    'AUTONOMOUS MODE' if self.mode == RoverStatus.MODE_AUTONOMOUS else 'IDLE')
            self._link_lost_logged = False

        if self.leg_reached and self.leg_reached_at is not None:
            if now - self.leg_reached_at >= LEG_REACHED_FLASH_S:
                self.leg_reached = False
                self.leg_reached_at = None

        if not link_lost and self.mode == RoverStatus.MODE_AUTONOMOUS and self.goal is not None:
            self.drive_to_goal()

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
        msg = RoverStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.mode = self.mode
        msg.active_leg_id = self.active_leg_id
        msg.leg_reached = self.leg_reached
        msg.state_text = self.state_text
        if self.goal is not None:
            distance, bearing = self._distance_and_bearing_to(self.goal.latitude, self.goal.longitude)
        else:
            distance, bearing = 0.0, self.heading_deg
        msg.distance_to_goal_m = distance
        msg.bearing_to_goal_deg = bearing
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RoverWithDeadman()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
