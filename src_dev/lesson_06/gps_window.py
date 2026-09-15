#!/usr/bin/env python3
"""Lesson 6: the ROS<->Qt threading bridge.

Lesson 5 showed app.exec_() blocking its thread forever, dispatching Qt's
own events. Every ROS lesson before that showed rclpy.spin(node) doing the
same thing. Put both on one thread and whichever runs first wins forever —
the other never runs. A real console needs both alive at once, so one of
them moves to its own thread.

The tempting-but-wrong fix: a QTimer calling rclpy.spin_once(timeout_sec=0)
on the GUI thread. It couples ROS handling to the GUI's own event loop — a
slow repaint or a modal dialog blocks spin_once() too, so telemetry stops
processing exactly when the GUI is busiest.

The actual fix: run the executor on its own QThread. Its subscription
callback must never touch a widget directly (Qt widgets aren't
thread-safe) — it only does bridge.gps_received.emit(msg). Qt notices the
emitting thread isn't the receiving object's thread and automatically
queues delivery onto the GUI thread's event loop, so the slot runs safely
back on the GUI thread. Publishing has no such problem: rclpy's publish()
is thread-safe on its own, so a GUI slot can call publish() directly.

Needs a live /rover/gps publisher to watch — any earlier lesson's node.
Read-only, so it's safe to run alongside a real system unremapped.
"""

import sys

import rclpy
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix


class RosBridge(QObject):
    """Lives on the GUI thread. Holds signals; does no work of its own."""

    gps_received = pyqtSignal(object)


class GpsListenerNode(Node):
    """The callback's only job is to hand the message off and return —
    no widget code, no slow work, ever, since it runs on the ROS thread.
    """

    def __init__(self, bridge: RosBridge):
        super().__init__('gps_listener')
        self._bridge = bridge
        self.create_subscription(NavSatFix, '/rover/gps', self._on_gps, 10)

    def _on_gps(self, msg: NavSatFix):
        self._bridge.gps_received.emit(msg)


class RosThread(QThread):
    """Owns the rclpy executor. Nothing outside this thread may call
    anything on `node` except thread-safe rclpy calls like publish().
    """

    def __init__(self, node: Node):
        super().__init__()
        self.node = node
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(node)

    def run(self):
        self._executor.spin()  # blocks THIS thread, never the GUI thread

    def stop(self):
        self._executor.shutdown()
        self.node.destroy_node()
        self.wait()


class GpsWindow(QMainWindow):
    """Same shape as lesson 5's window, but the label now updates from
    live ROS data instead of a button click.
    """

    def __init__(self, bridge: RosBridge):
        super().__init__()
        self.setWindowTitle('Lesson 6 — live GPS via the ROS<->Qt bridge')
        self.resize(420, 160)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self._label = QLabel('Waiting for /rover/gps ...')
        layout.addWidget(self._label)

        # This slot runs on the GUI thread even though gps_received was
        # emitted from the ROS thread — that's the entire point.
        bridge.gps_received.connect(self._on_gps)

    def _on_gps(self, msg: NavSatFix):
        self._label.setText(f'lat={msg.latitude:.6f}  lon={msg.longitude:.6f}')


def main():
    rclpy.init()
    app = QApplication(sys.argv)

    bridge = RosBridge()
    node = GpsListenerNode(bridge)
    ros_thread = RosThread(node)
    ros_thread.start()

    window = GpsWindow(bridge)
    window.show()

    # This blocks the GUI thread; ROS keeps spinning on ros_thread the
    # whole time, feeding messages in through the signal.
    exit_code = app.exec_()

    ros_thread.stop()
    rclpy.shutdown()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
