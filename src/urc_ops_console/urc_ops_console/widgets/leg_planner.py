"""Leg planner: validated waypoint entry. The Send button stays disabled until
lat/lon are in-range, so a mistyped coordinate is caught here, not by the rover.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from urc_interfaces.msg import NavLeg

MARKER_LABELS = {
    NavLeg.MARKER_NONE: 'NONE',
    NavLeg.MARKER_ARUCO: 'ARUCO',
    NavLeg.MARKER_OBJECT: 'OBJECT',
}


class LegPlanner(QWidget):
    leg_submitted = pyqtSignal(object)  # NavLeg

    def __init__(self, parent=None):
        super().__init__(parent)
        self._next_leg_id = 1

        self._lat_edit = QLineEdit()
        self._lat_edit.setPlaceholderText('38.406400')
        self._lon_edit = QLineEdit()
        self._lon_edit.setPlaceholderText('-110.791200')

        self._marker_combo = QComboBox()
        for value, label in MARKER_LABELS.items():
            self._marker_combo.addItem(label, value)

        self._aruco_spin = QSpinBox()
        self._aruco_spin.setRange(-1, 249)
        self._aruco_spin.setValue(-1)

        self._time_limit_spin = QDoubleSpinBox()
        self._time_limit_spin.setRange(0.0, 3600.0)
        self._time_limit_spin.setValue(300.0)
        self._time_limit_spin.setSuffix(' s')

        self._send_btn = QPushButton('SEND LEG TO ROVER')
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._on_send)

        self._lat_edit.textChanged.connect(self._update_enabled)
        self._lon_edit.textChanged.connect(self._update_enabled)

        layout = QGridLayout(self)
        layout.addWidget(QLabel('LEG PLANNER'), 0, 0, 1, 2)
        layout.addWidget(QLabel('Latitude'), 1, 0)
        layout.addWidget(self._lat_edit, 1, 1)
        layout.addWidget(QLabel('Longitude'), 2, 0)
        layout.addWidget(self._lon_edit, 2, 1)
        layout.addWidget(QLabel('Marker'), 3, 0)
        layout.addWidget(self._marker_combo, 3, 1)
        layout.addWidget(QLabel('ArUco ID'), 4, 0)
        layout.addWidget(self._aruco_spin, 4, 1)
        layout.addWidget(QLabel('Time limit'), 5, 0)
        layout.addWidget(self._time_limit_spin, 5, 1)
        layout.addWidget(self._send_btn, 6, 0, 1, 2)

    def _parsed_lat_lon(self):
        try:
            lat = float(self._lat_edit.text())
            lon = float(self._lon_edit.text())
        except ValueError:
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        return lat, lon

    def _update_enabled(self) -> None:
        self._send_btn.setEnabled(self._parsed_lat_lon() is not None)

    def _on_send(self) -> None:
        coords = self._parsed_lat_lon()
        if coords is None:
            return
        lat, lon = coords

        leg = NavLeg()
        leg.leg_id = self._next_leg_id
        leg.latitude = lat
        leg.longitude = lon
        leg.marker_type = self._marker_combo.currentData()
        leg.aruco_id = self._aruco_spin.value()
        leg.time_limit_s = float(self._time_limit_spin.value())
        self._next_leg_id = (self._next_leg_id % 255) + 1

        self.leg_submitted.emit(leg)
