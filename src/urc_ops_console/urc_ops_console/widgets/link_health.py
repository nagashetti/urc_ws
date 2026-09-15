"""Compact link-health indicator for the always-visible header bar."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

OK = '#2e7d32'
DEGRADED = '#b8860b'
LOST = '#b22222'

DEGRADED_LOSS_PCT = 20.0
DEGRADED_RTT_MS = 500.0


class LinkHealth(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot = QLabel('●')
        self._text = QLabel('LINK: NO DATA')
        self._text.setStyleSheet('font-weight: bold;')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._dot)
        layout.addWidget(self._text)

        self._set(LOST, 'LINK: NO DATA')

    def update_stats(self, rtt_ms: float, loss_pct: float) -> None:
        if loss_pct >= DEGRADED_LOSS_PCT or rtt_ms >= DEGRADED_RTT_MS:
            self._set(DEGRADED, f'LINK DEGRADED  {rtt_ms:.0f} ms  {loss_pct:.0f}% loss')
        else:
            self._set(OK, f'LINK OK  {rtt_ms:.0f} ms')

    def set_lost(self) -> None:
        self._set(LOST, 'LINK LOST')

    def _set(self, color: str, text: str) -> None:
        self._dot.setStyleSheet(f'color: {color}; font-size: 14px;')
        self._text.setText(text)
