#!/usr/bin/env python3
"""Lesson 3: turning a stored goal into actual movement.

Builds on lesson_02/rover_with_commands.py. Lesson 2 could receive a goal
and switch to AUTONOMOUS mode, but nothing happened — distance_to_goal_m
stayed 0.0 forever. This adds the drive controller: the timer loop now
moves self.lat/self.lon toward self.goal each tick.

New ideas:

1. Distance and bearing between two lat/lon pairs, via a flat-earth
   approximation — fine at the ~100 m scale of one leg. See
   ../../src/urc_ops_console/urc_ops_console/geo.py for the same idea done
   properly (an ENU projection) for the GUI's map.

2. Arrival needs a tolerance, not exact equality — GPS floats essentially
   never land on the exact target.

3. leg_reached clears itself on a timer using time.monotonic(), because by
   the time it needs clearing, self.goal is already None — there's nothing
   left to re-check it against.

Still missing: the deadman heartbeat and operator overrides (abort, speed
limit) — lesson 4. Movement and safety cutoffs are different ideas.
"""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import String

from urc_interfaces.msg import NavLeg, RoverStatus

SPEED_MPS = 1.0
ARRIVAL_RADIUS_M = 2.0
LEG_REACHED_FLASH_S = 3.0


class RoverThatDrives(Node):
    """Lesson 2's node, plus a controller that actually drives to the goal."""

    def __init__(self):
        super().__init__('rover_that_drives')

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

        telemetry_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)
        command_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=10)

        self.gps_pub = self.create_publisher(NavSatFix, '/rover/gps', telemetry_qos)
        self.status_pub = self.create_publisher(RoverStatus, '/rover/status', telemetry_qos)
        self.create_subscription(NavLeg, '/mission/leg_goal', self.goal_callback, command_qos)
        self.create_subscription(String, '/mission/mode', self.mode_callback, command_qos)
        self.create_timer(1.0 / self.publish_rate_hz, self.publish_loop)

    def goal_callback(self, msg: NavLeg):
        self.goal = msg
        self.active_leg_id = int(msg.leg_id)
        self.leg_reached = False
        self.get_logger().info(f'New goal: leg {msg.leg_id} at {msg.latitude:.6f}, {msg.longitude:.6f}')

    def mode_callback(self, msg: String):
        text = msg.data.strip().upper()
        self.mode = RoverStatus.MODE_AUTONOMOUS if text == 'AUTONOMOUS' else RoverStatus.MODE_IDLE
        self.get_logger().info(f'Mode set to {text}')

    def _distance_and_bearing_to(self, lat2: float, lon2: float):
        # 111_320 m is ~1 degree of latitude everywhere; cos(lat) corrects
        # for longitude degrees shrinking away from the equator.
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
        step_m = SPEED_MPS / self.publish_rate_hz
        self.lat += (step_m * math.cos(math.radians(bearing))) / 111320.0
        self.lon += (step_m * math.sin(math.radians(bearing))) / (111320.0 * math.cos(math.radians(self.lat)))

    def publish_loop(self):
        if self.leg_reached and self.leg_reached_at is not None:
            if time.monotonic() - self.leg_reached_at >= LEG_REACHED_FLASH_S:
                self.leg_reached = False
                self.leg_reached_at = None

        if self.mode == RoverStatus.MODE_AUTONOMOUS and self.goal is not None:
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
        if self.goal is not None:
            distance, bearing = self._distance_and_bearing_to(self.goal.latitude, self.goal.longitude)
        else:
            distance, bearing = 0.0, self.heading_deg
        msg.distance_to_goal_m = distance
        msg.bearing_to_goal_deg = bearing
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RoverThatDrives()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
