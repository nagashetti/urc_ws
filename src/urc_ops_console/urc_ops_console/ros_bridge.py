"""ROS-to-Qt bridge for the URC operator console.

The rclpy executor spins on its own QThread; subscription callbacks do exactly
one thing — emit a Qt signal carrying the message. Qt marshals the emission
onto the GUI thread automatically because the receiving widgets live there.
Publishers are called directly from GUI slots since rclpy publish is
thread-safe; this avoids coupling telemetry latency to GUI repaint, which the
common QTimer + spin_once(timeout_sec=0) pattern does not.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, pyqtSignal

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, NavSatFix
from std_msgs.msg import Bool, Float32, Header, String

from urc_interfaces.msg import LinkStats, NavLeg, RoverStatus

from .qos import COMMAND, TELEMETRY

HEARTBEAT_PERIOD_S = 0.5


class RosBridge(QObject):
    """Forwards ROS messages received on the RosThread into Qt signals."""

    gps_received = pyqtSignal(object)
    imu_received = pyqtSignal(object)
    odom_received = pyqtSignal(object)
    status_received = pyqtSignal(object)
    link_received = pyqtSignal(object)

    def __init__(self):
        super().__init__()


class OpsConsoleNode(Node):
    """The GUI's ROS node: subscribes to telemetry, publishes commands."""

    def __init__(self, bridge: RosBridge):
        super().__init__('ops_console')
        self._bridge = bridge

        self.create_subscription(NavSatFix, '/rover/gps', self._on_gps, TELEMETRY)
        self.create_subscription(Imu, '/rover/imu', self._on_imu, TELEMETRY)
        self.create_subscription(Odometry, '/rover/odom', self._on_odom, TELEMETRY)
        self.create_subscription(RoverStatus, '/rover/status', self._on_status, TELEMETRY)
        self.create_subscription(LinkStats, '/rover/link', self._on_link, TELEMETRY)

        self._leg_goal_pub = self.create_publisher(NavLeg, '/mission/leg_goal', COMMAND)
        self._mode_pub = self.create_publisher(String, '/mission/mode', COMMAND)
        self._abort_pub = self.create_publisher(Bool, '/mission/abort', COMMAND)
        self._max_speed_pub = self.create_publisher(Float32, '/rover/max_speed', COMMAND)
        self._heartbeat_pub = self.create_publisher(Header, '/ops_console/heartbeat', COMMAND)

        self.create_timer(HEARTBEAT_PERIOD_S, self._publish_heartbeat)

    def _on_gps(self, msg: NavSatFix) -> None:
        self._bridge.gps_received.emit(msg)

    def _on_imu(self, msg: Imu) -> None:
        self._bridge.imu_received.emit(msg)

    def _on_odom(self, msg: Odometry) -> None:
        self._bridge.odom_received.emit(msg)

    def _on_status(self, msg: RoverStatus) -> None:
        self._bridge.status_received.emit(msg)

    def _on_link(self, msg: LinkStats) -> None:
        self._bridge.link_received.emit(msg)

    def _publish_heartbeat(self) -> None:
        msg = Header()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = 'ops_console'
        self._heartbeat_pub.publish(msg)

    def send_leg_goal(self, leg: NavLeg) -> None:
        self._leg_goal_pub.publish(leg)

    def send_mode(self, mode: str) -> None:
        msg = String()
        msg.data = mode
        self._mode_pub.publish(msg)

    def send_abort(self) -> None:
        msg = Bool()
        msg.data = True
        self._abort_pub.publish(msg)

    def send_max_speed(self, speed_mps: float) -> None:
        msg = Float32()
        msg.data = float(speed_mps)
        self._max_speed_pub.publish(msg)


class RosThread(QThread):
    """Owns the rclpy executor. Nothing else may touch `node` off this thread
    except thread-safe rclpy calls such as publish()."""

    def __init__(self, node: Node):
        super().__init__()
        self.node = node
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(node)

    def run(self) -> None:
        try:
            self._executor.spin()
        except Exception:
            pass

    def stop(self) -> None:
        self._executor.shutdown()
        self.node.destroy_node()
        self.wait()


def init_ros(args=None) -> None:
    rclpy.init(args=args)


def shutdown_ros() -> None:
    rclpy.shutdown()
