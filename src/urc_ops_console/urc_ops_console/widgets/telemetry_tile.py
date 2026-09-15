"""A single labeled telemetry value with staleness styling.

Key principle: a stale value is never rendered as if it were fresh, and loss
of data is never rendered as a zero. Stale values turn amber and show their
age; lost values grey out, strike through, and keep showing the last known
number rather than a misleading 0.0.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

FRESH_COLOR = 'palette(text)'
STALE_COLOR = '#b8860b'
LOST_COLOR = '#b22222'


class TelemetryTile(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = QLabel(title.upper())
        self._title.setStyleSheet('font-size: 11px; color: #888; font-weight: bold;')
        self._value = QLabel('—')
        self._status = QLabel('')
        self._status.setStyleSheet('font-size: 10px;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._status)

        self._apply_value_style(FRESH_COLOR, strike=False)

    def set_fresh(self, text: str) -> None:
        self._value.setText(text)
        self._apply_value_style(FRESH_COLOR, strike=False)
        self._status.setText('')

    def set_stale(self, text: str, age_s: float) -> None:
        self._value.setText(text)
        self._apply_value_style(STALE_COLOR, strike=False)
        self._status.setText(f'⚠ {age_s:.1f}s old')
        self._status.setStyleSheet(f'font-size: 10px; color: {STALE_COLOR};')

    def set_lost(self, last_text: str) -> None:
        self._value.setText(last_text)
        self._apply_value_style(LOST_COLOR, strike=True)
        self._status.setText('SIGNAL LOST')
        self._status.setStyleSheet(f'font-size: 10px; color: {LOST_COLOR}; font-weight: bold;')

    def _apply_value_style(self, color: str, strike: bool) -> None:
        decoration = 'line-through' if strike else 'none'
        self._value.setStyleSheet(
            f'font-size: 18px; font-weight: bold; color: {color}; text-decoration: {decoration};'
        )
