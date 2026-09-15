"""LED mirror: reflects the rover's physical status LED per the URC rule —
red = autonomous, blue = teleop, flashing green = arrived at leg target.
Colour is never the only channel: the state is always spelled out in text too.
"""

from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from urc_interfaces.msg import RoverStatus

RED = '#c62828'
BLUE = '#1565c0'
GREEN = '#2e7d32'
GREY = '#757575'
FLASH_PERIOD_MS = 300


class LedPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot = QLabel('■')
        self._dot.setStyleSheet(f'color: {GREY}; font-size: 22px;')
        self._text = QLabel('LED MIRROR: NO DATA')
        self._text.setStyleSheet('font-weight: bold;')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        layout.addStretch(1)

        self._flashing = False
        self._flash_on = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(FLASH_PERIOD_MS)
        self._flash_timer.timeout.connect(self._on_flash_tick)

    def set_mode(self, mode: int, leg_reached: bool) -> None:
        if leg_reached:
            self._start_flash()
            return
        self._stop_flash()
        if mode == RoverStatus.MODE_AUTONOMOUS:
            self._set(RED, 'RED — AUTONOMOUS')
        elif mode == RoverStatus.MODE_TELEOP:
            self._set(BLUE, 'BLUE — TELEOP')
        else:
            self._set(GREY, 'OFF — IDLE')

    def set_no_data(self) -> None:
        self._stop_flash()
        self._set(GREY, 'NO DATA — SIGNAL LOST')

    def _start_flash(self) -> None:
        if not self._flashing:
            self._flashing = True
            self._flash_timer.start()

    def _stop_flash(self) -> None:
        if self._flashing:
            self._flashing = False
            self._flash_timer.stop()

    def _on_flash_tick(self) -> None:
        self._flash_on = not self._flash_on
        self._set(GREEN if self._flash_on else GREY, 'FLASHING GREEN — LEG REACHED')

    def _set(self, color: str, text: str) -> None:
        self._dot.setStyleSheet(f'color: {color}; font-size: 22px;')
        self._text.setText(f'LED MIRROR: {text}')
