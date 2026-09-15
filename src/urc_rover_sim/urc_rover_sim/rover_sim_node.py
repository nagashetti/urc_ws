#!/usr/bin/env python3

import math
import random
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import NavSatFix, Imu
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Point, Quaternion, Vector3
from std_msgs.msg import String, Bool, Float32, Header

from urc_interfaces.msg import RoverStatus, NavLeg, LinkStats

LEG_REACHED_FLASH_S = 3.0


class RoverSimNode(Node):
    def __init__(self):
        super().__init__('rover_sim')
        self.declare_parameters(
            namespace='',
            parameters=[
                ('publish_rate_hz', 5.0),
                ('gps_noise_m', 0.5),
                ('drop_probability', 0.0),
                ('stall_after_s', 0.0),
                ('latitude', 38.406400),
                ('longitude', -110.791200),
                ('heading_deg', 0.0),
                ('speed_mps', 0.0),
            ]
        )

        self.publish_rate_hz = self.get_parameter('publish_rate_hz').value
        self.gps_noise_m = self.get_parameter('gps_noise_m').value
        self.drop_probability = self.get_parameter('drop_probability').value
        self.stall_after_s = self.get_parameter('stall_after_s').value
        self.lat = self.get_parameter('latitude').value
        self.lon = self.get_parameter('longitude').value
        self.ref_lat = self.lat
        self.ref_lon = self.lon
        self.heading_deg = self.get_parameter('heading_deg').value
        self.speed_mps = self.get_parameter('speed_mps').value
        self.mode = RoverStatus.MODE_IDLE
        self.goal: Optional[NavLeg] = None
        self.active_leg_id = 0
        self.leg_reached = False
        self.leg_reached_at: Optional[float] = None
        self.battery_pct = 100.0
        self.aruco_visible = False
        self.aruco_id = -1
        self.state_text = 'IDLE'
        self.last_heartbeat = time.monotonic()
        self.last_time = time.monotonic()
        self.stall_started_at = None
        self._link_lost_logged = False

        qos_telemetry = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        qos_commands = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.gps_pub = self.create_publisher(NavSatFix, '/rover/gps', qos_telemetry)
        self.imu_pub = self.create_publisher(Imu, '/rover/imu', qos_telemetry)
        self.odom_pub = self.create_publisher(Odometry, '/rover/odom', qos_telemetry)
        self.status_pub = self.create_publisher(RoverStatus, '/rover/status', qos_telemetry)
        self.link_pub = self.create_publisher(LinkStats, '/rover/link', qos_telemetry)

        self.leg_goal_sub = self.create_subscription(NavLeg, '/mission/leg_goal', self.goal_callback, qos_commands)
        self.mode_sub = self.create_subscription(String, '/mission/mode', self.mode_callback, qos_commands)
        self.abort_sub = self.create_subscription(Bool, '/mission/abort', self.abort_callback, qos_commands)
        self.speed_limit_sub = self.create_subscription(Float32, '/rover/max_speed', self.speed_limit_callback, qos_commands)
        self.heartbeat_sub = self.create_subscription(Header, '/ops_console/heartbeat', self.heartbeat_callback, qos_commands)

        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self.publish_loop)

    def goal_callback(self, msg: NavLeg):
        self.goal = msg
        self.active_leg_id = int(msg.leg_id)
        self.state_text = 'NAVIGATING TO LEG'
        self.leg_reached = False
        self.get_logger().info(f'Received leg goal {msg.leg_id} at {msg.latitude:.6f}, {msg.longitude:.6f}')

    def mode_callback(self, msg: String):
        mode_text = msg.data.strip().upper()
        if mode_text == 'AUTONOMOUS':
            self.mode = RoverStatus.MODE_AUTONOMOUS
            self.state_text = 'AUTONOMOUS MODE'
        elif mode_text == 'TELEOP':
            self.mode = RoverStatus.MODE_TELEOP
            self.state_text = 'TELEOP MODE'
        else:
            self.mode = RoverStatus.MODE_IDLE
            self.state_text = 'IDLE'
        self.get_logger().info(f'Mode set to {mode_text}')

    def abort_callback(self, msg: Bool):
        if msg.data:
            self.goal = None
            self.mode = RoverStatus.MODE_IDLE
            self.leg_reached = False
            self.state_text = 'ABORTED'
            self.speed_mps = 0.0
            self.get_logger().warn('Mission aborted by operator')

    def speed_limit_callback(self, msg: Float32):
        self.speed_mps = max(0.0, float(msg.data))
        self.get_logger().info(f'Max speed set to {self.speed_mps:.2f}')

    def heartbeat_callback(self, msg: Header):
        self.last_heartbeat = time.monotonic()

    def publish_loop(self):
        now = time.monotonic()
        link_lost = False
        if self.stall_after_s > 0.0 and self.stall_started_at is None:
            self.stall_started_at = now
        if self.stall_started_at is not None and (now - self.stall_started_at) >= self.stall_after_s:
            link_lost = True
        if (now - self.last_heartbeat) > 2.0:
            link_lost = True

        if link_lost:
            self.speed_mps = 0.0
            self.state_text = 'LINK LOST — HOLDING'
            if not self._link_lost_logged:
                self.get_logger().warn('LINK LOST — HOLDING')
                self._link_lost_logged = True
        else:
            if self._link_lost_logged:
                # The link just recovered. Without this, state_text would
                # keep reporting "LINK LOST — HOLDING" forever afterward,
                # since nothing else overwrites it until the next goal or
                # mode command — a stale fault message rendered as current.
                if self.goal is not None:
                    self.state_text = 'NAVIGATING TO LEG'
                elif self.mode == RoverStatus.MODE_AUTONOMOUS:
                    self.state_text = 'AUTONOMOUS MODE'
                elif self.mode == RoverStatus.MODE_TELEOP:
                    self.state_text = 'TELEOP MODE'
                else:
                    self.state_text = 'IDLE'
            self._link_lost_logged = False

        if self.leg_reached and self.leg_reached_at is not None and (now - self.leg_reached_at) >= LEG_REACHED_FLASH_S:
            self.leg_reached = False
            self.leg_reached_at = None
            if not link_lost:
                self.state_text = 'AUTONOMOUS MODE' if self.mode == RoverStatus.MODE_AUTONOMOUS else 'IDLE'

        if not link_lost and self.goal is not None and self.mode == RoverStatus.MODE_AUTONOMOUS:
            self.drive_to_goal()

        self.publish_gps()
        self.publish_imu()
        self.publish_odom()
        self.publish_status()
        self.publish_link_stats()

    def _distance_and_bearing_to(self, lat2: float, lon2: float) -> tuple:
        dx = (lon2 - self.lon) * 111320.0 * math.cos(math.radians(self.lat))
        dy = (lat2 - self.lat) * 111320.0
        distance = math.hypot(dx, dy)
        bearing = math.degrees(math.atan2(dx, dy))
        if bearing < 0:
            bearing += 360.0
        return distance, bearing

    def drive_to_goal(self):
        if self.goal is None:
            return

        distance, bearing = self._distance_and_bearing_to(self.goal.latitude, self.goal.longitude)

        if distance < 2.0:
            self.leg_reached = True
            self.leg_reached_at = time.monotonic()
            self.state_text = 'LEG REACHED'
            self.goal = None
            self.battery_pct = max(0.0, self.battery_pct - 0.2)
            return

        self.heading_deg = bearing

        allowed_speed = max(0.0, min(self.speed_mps, 2.0))
        move_distance = allowed_speed / self.publish_rate_hz
        self.lat += (move_distance * math.cos(math.radians(bearing))) / 111320.0
        self.lon += (move_distance * math.sin(math.radians(bearing))) / (111320.0 * math.cos(math.radians(self.lat)))
        self.battery_pct = max(0.0, self.battery_pct - 0.01)
        self.aruco_visible = True
        self.aruco_id = int(self.goal.aruco_id)

    def publish_gps(self):
        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'gps'
        msg.status.status = 0
        msg.status.service = 1

        if random.random() < self.drop_probability:
            return

        noise_lat = random.uniform(-self.gps_noise_m, self.gps_noise_m) / 111320.0
        noise_lon = random.uniform(-self.gps_noise_m, self.gps_noise_m) / 111320.0
        msg.latitude = self.lat + noise_lat
        msg.longitude = self.lon + noise_lon
        msg.altitude = 0.0
        self.gps_pub.publish(msg)

    def publish_imu(self):
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'imu'
        msg.orientation = Quaternion(x=0.0, y=0.0, z=math.sin(math.radians(self.heading_deg) / 2.0), w=math.cos(math.radians(self.heading_deg) / 2.0))
        msg.angular_velocity = Vector3(x=0.0, y=0.0, z=0.0)
        msg.linear_acceleration = Vector3(x=0.0, y=0.0, z=0.0)
        self.imu_pub.publish(msg)

    def publish_odom(self):
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'odom'
        msg.child_frame_id = 'base_link'
        dx = (self.lon - self.ref_lon) * 111320.0 * math.cos(math.radians(self.ref_lat))
        dy = (self.lat - self.ref_lat) * 111320.0
        msg.pose.pose.position = Point(x=dx, y=dy, z=0.0)
        yaw = math.radians(self.heading_deg)
        msg.pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))
        msg.twist.twist.linear = Vector3(x=self.speed_mps, y=0.0, z=0.0)
        self.odom_pub.publish(msg)

    def publish_status(self):
        msg = RoverStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'rover_status'
        msg.mode = self.mode
        msg.active_leg_id = self.active_leg_id
        msg.leg_reached = self.leg_reached
        if self.goal is not None:
            distance, bearing = self._distance_and_bearing_to(self.goal.latitude, self.goal.longitude)
        else:
            distance, bearing = 0.0, self.heading_deg
        msg.distance_to_goal_m = distance
        msg.bearing_to_goal_deg = bearing
        msg.battery_pct = self.battery_pct
        msg.aruco_visible = self.aruco_visible
        msg.aruco_id = self.aruco_id
        msg.state_text = self.state_text
        self.status_pub.publish(msg)

    def publish_link_stats(self):
        msg = LinkStats()
        msg.rssi_dbm = -42.0
        msg.loss_pct = 0.0
        msg.rtt_ms = 42.0
        self.link_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RoverSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
