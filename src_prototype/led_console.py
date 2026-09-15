#!/usr/bin/env python3
"""Minimal LED indicator console.

Requirements this satisfies:
  1) Subscribes to a topic       -> /rover/status
  2) Publishes a command based
     on user input (button click) -> /mission/mode
  3) Paired with a simple
     publisher node               -> rover_stub.py

LED rule: red = autonomous, blue = teleop, flashing green = arrived.
Same ROS<->Qt bridge shape as src_dev/lesson_06/gps_window.py.
"""

import sys

import rclpy
from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from urc_interfaces.msg import RoverStatus

FLASH_PERIOD_MS = 400


class RosBridge(QObject):
    status_received = pyqtSignal(object)


class LedConsoleNode(Node):
    def __init__(self, bridge: RosBridge):
        super().__init__('led_console')
        self.create_subscription(
            RoverStatus, '/rover/status', lambda m: bridge.status_received.emit(m), 10)
        self.mode_pub = self.create_publisher(String, '/mission/mode', 10)


class RosThread(QThread):
    def __init__(self, node: Node):
        super().__init__()
        self.node = node
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(node)

    def run(self):
        self._executor.spin()

    def stop(self):
        self._executor.shutdown()
        self.node.destroy_node()
        self.wait()


class LedWindow(QMainWindow):
    def __init__(self, bridge: RosBridge, node: LedConsoleNode):
        super().__init__()
        self.setWindowTitle('LED indicator console')
        self._node = node
        self._mode = RoverStatus.MODE_IDLE
        self._leg_reached = False
        self._flash_on = False

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self._led = QLabel()
        self._led.setFixedSize(60, 60)
        layout.addWidget(self._led)

        buttons = QHBoxLayout()
        for label in ('TELEOP', 'AUTONOMOUS', 'ARRIVED'):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked, l=label: self._send(l))
            buttons.addWidget(btn)
        layout.addLayout(buttons)

        bridge.status_received.connect(self._on_status)

        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._tick_flash)
        self._flash_timer.start(FLASH_PERIOD_MS)

        self._render()

    def _send(self, command: str):
        msg = String()
        msg.data = command
        self._node.mode_pub.publish(msg)

    def _on_status(self, msg: RoverStatus):
        self._mode = msg.mode
        self._leg_reached = bool(msg.leg_reached)
        self._render()

    def _tick_flash(self):
        self._flash_on = not self._flash_on
        if self._leg_reached:
            self._render()

    def _render(self):
        if self._leg_reached:
            color = '#00c853' if self._flash_on else '#1b1b1b'
        elif self._mode == RoverStatus.MODE_AUTONOMOUS:
            color = '#e53935'
        elif self._mode == RoverStatus.MODE_TELEOP:
            color = '#1e88e5'
        else:
            color = '#555555'
        self._led.setStyleSheet(f'background-color: {color}; border-radius: 30px;')


def main():
    rclpy.init()
    app = QApplication(sys.argv)

    bridge = RosBridge()
    node = LedConsoleNode(bridge)
    ros_thread = RosThread(node)
    ros_thread.start()

    window = LedWindow(bridge, node)
    window.show()

    exit_code = app.exec_()

    ros_thread.stop()
    rclpy.shutdown()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
