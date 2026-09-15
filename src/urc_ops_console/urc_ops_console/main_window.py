#!/usr/bin/env python3
"""URC Operator Console — main window.

Ties the ROS<->Qt bridge, the staleness watchdog, and the widgets together.
Designed for a sunlit tent, not a demo: every number carries units, colour is
never the only channel, and a stale value is never rendered as if it were
fresh.
"""

import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .ros_bridge import OpsConsoleNode, RosBridge, RosThread, init_ros, shutdown_ros
from .watchdog import Watchdog
from .widgets.led_panel import LedPanel
from .widgets.leg_planner import LegPlanner
from .widgets.link_health import LinkHealth
from .widgets.map_view import MapView
from .widgets.telemetry_tile import TelemetryTile

STREAM_NAMES = ['gps', 'imu', 'odom', 'status', 'link']
STREAM_LABELS = {'gps': 'GPS', 'imu': 'IMU', 'odom': 'ODOM', 'status': 'STATUS', 'link': 'LINK'}
STREAM_COLORS = {'fresh': '#2e7d32', 'stale': '#b8860b', 'lost': '#b22222'}

WATCHDOG_POLL_MS = 200  # 5 Hz
CLOCK_POLL_MS = 1000


class _StreamDot(QWidget):
    """One "● NAME" indicator in the per-stream health strip."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._dot = QLabel('●')
        self._text = QLabel(label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 10, 0)
        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        self.set_status('lost')

    def set_status(self, status: str) -> None:
        self._dot.setStyleSheet(f'color: {STREAM_COLORS[status]}; font-size: 12px;')


class MainWindow(QMainWindow):
    def __init__(self, bridge: RosBridge, node: OpsConsoleNode, parent=None):
        super().__init__(parent)
        self._node = node
        self._watchdog = Watchdog(STREAM_NAMES)
        self._latest_status = None
        self._latest_link = None
        self._status_texts = None
        self._legs_sent = 0

        self.setWindowTitle('URC Operator Console')
        self.resize(1200, 800)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addLayout(self._build_header())
        root.addWidget(self._build_stream_row())
        self._banner = QLabel('')
        self._banner.setStyleSheet('background-color: #b22222; color: white; font-weight: bold; padding: 4px;')
        self._banner.hide()
        root.addWidget(self._banner)
        root.addLayout(self._build_body(), 1)

        bridge.gps_received.connect(self._on_gps)
        bridge.imu_received.connect(self._on_imu)
        bridge.odom_received.connect(self._on_odom)
        bridge.status_received.connect(self._on_status)
        bridge.link_received.connect(self._on_link)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(CLOCK_POLL_MS)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._elapsed_s = 0

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(WATCHDOG_POLL_MS)
        self._watchdog_timer.timeout.connect(self._refresh_watchdog)
        self._watchdog_timer.start()

    # -- layout builders ------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._clock_label = QLabel('MISSION CLOCK 00:00')
        self._clock_label.setStyleSheet('font-weight: bold;')
        self._leg_label = QLabel('LEG —')
        self._leg_label.setStyleSheet('font-weight: bold;')
        self._link_health = LinkHealth()
        abort_btn = QPushButton('ABORT')
        abort_btn.setStyleSheet('background-color: #b22222; color: white; font-weight: bold; padding: 6px 18px;')
        abort_btn.clicked.connect(self._on_abort)

        row.addWidget(self._clock_label)
        row.addWidget(self._leg_label)
        row.addWidget(self._link_health)
        row.addStretch(1)
        row.addWidget(abort_btn)
        return row

    def _build_stream_row(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        self._stream_dots = {}
        for name in STREAM_NAMES:
            dot = _StreamDot(STREAM_LABELS[name])
            self._stream_dots[name] = dot
            row.addWidget(dot)
        row.addStretch(1)
        return container

    def _build_body(self) -> QHBoxLayout:
        body = QHBoxLayout()

        left = QVBoxLayout()
        self._map_view = MapView()
        left.addWidget(self._map_view, 1)
        self._leg_planner = LegPlanner()
        self._leg_planner.leg_submitted.connect(self._on_leg_submitted)
        left.addWidget(self._leg_planner)
        body.addLayout(left, 2)

        right = QVBoxLayout()
        right.addLayout(self._build_mode_row())
        self._led_panel = LedPanel()
        right.addWidget(self._led_panel)

        tiles = QGridLayout()
        self._dist_tile = TelemetryTile('Dist to goal')
        self._bearing_tile = TelemetryTile('Bearing')
        self._aruco_tile = TelemetryTile('ArUco')
        self._battery_tile = TelemetryTile('Battery')
        tiles.addWidget(self._dist_tile, 0, 0)
        tiles.addWidget(self._bearing_tile, 0, 1)
        tiles.addWidget(self._aruco_tile, 1, 0)
        tiles.addWidget(self._battery_tile, 1, 1)
        right.addLayout(tiles)

        right.addLayout(self._build_speed_row())

        self._state_tile = TelemetryTile('State')
        right.addWidget(self._state_tile)
        right.addStretch(1)

        body.addLayout(right, 1)
        return body

    def _build_mode_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel('MODE'))
        auto_btn = QPushButton('AUTO')
        auto_btn.clicked.connect(lambda: self._on_mode_clicked('AUTONOMOUS'))
        teleop_btn = QPushButton('TELEOP')
        teleop_btn.clicked.connect(lambda: self._on_mode_clicked('TELEOP'))
        row.addWidget(auto_btn)
        row.addWidget(teleop_btn)
        row.addStretch(1)
        return row

    def _build_speed_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel('SPEED LIMIT'))
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(0, 20)
        self._speed_label = QLabel('0.0 m/s')
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        self._speed_slider.setValue(10)
        row.addWidget(self._speed_slider, 1)
        row.addWidget(self._speed_label)
        return row

    # -- user actions -----------------------------------------------------

    def _on_leg_submitted(self, leg) -> None:
        self._node.send_leg_goal(leg)
        self._map_view.set_goal(leg.latitude, leg.longitude)
        self._legs_sent += 1

    def _on_mode_clicked(self, mode: str) -> None:
        if mode == 'AUTONOMOUS':
            reply = QMessageBox.question(
                self,
                'Confirm mode change',
                'Engage AUTONOMOUS mode? The rover will drive itself toward the active leg.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._node.send_mode(mode)

    def _on_abort(self) -> None:
        reply = QMessageBox.warning(
            self,
            'Confirm ABORT',
            'Abort the mission? This immediately halts the rover.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._node.send_abort()

    def _on_speed_changed(self, value: int) -> None:
        speed_mps = value / 10.0
        self._speed_label.setText(f'{speed_mps:.1f} m/s')
        self._node.send_max_speed(speed_mps)

    # -- ROS message handlers (run on the GUI thread via queued signals) --

    def _on_gps(self, msg) -> None:
        self._watchdog.mark_received('gps')
        self._map_view.update_rover(msg.latitude, msg.longitude, fresh=True)

    def _on_imu(self, _msg) -> None:
        self._watchdog.mark_received('imu')

    def _on_odom(self, _msg) -> None:
        self._watchdog.mark_received('odom')

    def _on_status(self, msg) -> None:
        self._watchdog.mark_received('status')
        self._latest_status = msg
        self._status_texts = {
            'dist': f'{msg.distance_to_goal_m:.1f} m',
            'bearing': f'{msg.bearing_to_goal_deg:03.0f}°',
            'aruco': f'ID {msg.aruco_id}' if msg.aruco_visible else 'NOT VISIBLE',
            'battery': f'{msg.battery_pct:.0f} %',
            'state': msg.state_text,
        }
        leg_text = f'LEG {msg.active_leg_id}' if msg.active_leg_id else 'LEG —'
        self._leg_label.setText(f'{leg_text} ({self._legs_sent} sent)')
        self._apply_status_tiles()
        self._led_panel.set_mode(msg.mode, msg.leg_reached)

    def _on_link(self, msg) -> None:
        self._watchdog.mark_received('link')
        self._latest_link = msg

    # -- periodic refresh ---------------------------------------------------

    def _update_clock(self) -> None:
        self._elapsed_s += 1
        minutes, seconds = divmod(self._elapsed_s, 60)
        self._clock_label.setText(f'MISSION CLOCK {minutes:02d}:{seconds:02d}')

    def _refresh_watchdog(self) -> None:
        lost_labels = []
        for name in STREAM_NAMES:
            status = self._watchdog.status(name)
            self._stream_dots[name].set_status(status)
            if status == 'lost':
                lost_labels.append(STREAM_LABELS[name])

        if lost_labels:
            self._banner.setText('SIGNAL LOST: ' + ', '.join(lost_labels))
            self._banner.show()
        else:
            self._banner.hide()

        self._apply_status_tiles()

        gps_status = self._watchdog.status('gps')
        self._map_view.set_rover_fresh(gps_status == 'fresh')
        if gps_status == 'lost':
            self._led_panel.set_no_data()

        link_status = self._watchdog.status('link')
        if link_status == 'lost':
            self._link_health.set_lost()
        elif self._latest_link is not None:
            self._link_health.update_stats(self._latest_link.rtt_ms, self._latest_link.loss_pct)

    def _apply_status_tiles(self) -> None:
        if self._status_texts is None:
            return
        status = self._watchdog.status('status')
        age = self._watchdog.age('status')
        tiles = {
            'dist': self._dist_tile,
            'bearing': self._bearing_tile,
            'aruco': self._aruco_tile,
            'battery': self._battery_tile,
            'state': self._state_tile,
        }
        for key, tile in tiles.items():
            text = self._status_texts[key]
            if status == 'fresh':
                tile.set_fresh(text)
            elif status == 'stale':
                tile.set_stale(text, age)
            else:
                tile.set_lost(text)
        if status == 'lost' and self._latest_status is not None:
            self._led_panel.set_no_data()


def main(args=None):
    init_ros(args)
    app = QApplication(sys.argv)

    bridge = RosBridge()
    node = OpsConsoleNode(bridge)
    ros_thread = RosThread(node)
    ros_thread.start()

    window = MainWindow(bridge, node)
    window.show()

    exit_code = app.exec_()

    ros_thread.stop()
    shutdown_ros()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
