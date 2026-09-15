#!/usr/bin/env python3
"""Minimal paired publisher for led_console.py (there's nothing to
subscribe to without it). Publishes /rover/status and reacts to one
command topic, /mission/mode (std_msgs/String): "TELEOP" | "AUTONOMOUS" |
"ARRIVED".
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from urc_interfaces.msg import RoverStatus

ARRIVAL_FLASH_S = 4.0


class RoverStub(Node):
    def __init__(self):
        super().__init__('rover_stub')
        self.mode = RoverStatus.MODE_IDLE
        self.leg_reached = False
        self._arrived_at = None

        self.status_pub = self.create_publisher(RoverStatus, '/rover/status', 10)
        self.create_subscription(String, '/mission/mode', self._on_command, 10)
        self.create_timer(0.5, self._publish_status)

    def _on_command(self, msg: String):
        cmd = msg.data.strip().upper()
        if cmd == 'TELEOP':
            self.mode = RoverStatus.MODE_TELEOP
        elif cmd == 'AUTONOMOUS':
            self.mode = RoverStatus.MODE_AUTONOMOUS
        elif cmd == 'ARRIVED':
            self.leg_reached = True
            self._arrived_at = self.get_clock().now()

    def _publish_status(self):
        if self.leg_reached and self._arrived_at is not None:
            elapsed_s = (self.get_clock().now() - self._arrived_at).nanoseconds / 1e9
            if elapsed_s >= ARRIVAL_FLASH_S:
                self.leg_reached = False
                self._arrived_at = None

        msg = RoverStatus()
        msg.mode = self.mode
        msg.leg_reached = self.leg_reached
        self.status_pub.publish(msg)


def main():
    rclpy.init()
    node = RoverStub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
