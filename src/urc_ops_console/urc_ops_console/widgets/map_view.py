"""Local ENU map view. No internet map tiles: there is no field internet at
URC, and tile fetches would spend bandwidth the command link doesn't have.
Instead this projects GNSS fixes onto a flat local plane around the first fix.
"""

from __future__ import annotations

from collections import deque

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from ..geo import lat_lon_to_enu

TRAIL_MAXLEN = 500
MARGIN_PX = 24.0


class MapView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self._ref = None
        self._trail: deque = deque(maxlen=TRAIL_MAXLEN)
        self._rover_xy = None
        self._rover_fresh = True
        self._goal_xy = None

    def update_rover(self, lat: float, lon: float, fresh: bool = True) -> None:
        if self._ref is None:
            self._ref = (lat, lon)
        xy = lat_lon_to_enu(lat, lon, self._ref[0], self._ref[1])
        self._rover_xy = xy
        self._rover_fresh = fresh
        if fresh:
            self._trail.append(xy)
        self.update()

    def set_rover_fresh(self, fresh: bool) -> None:
        self._rover_fresh = fresh
        self.update()

    def set_goal(self, lat: float, lon: float) -> None:
        if self._ref is None:
            self._ref = (lat, lon)
        self._goal_xy = lat_lon_to_enu(lat, lon, self._ref[0], self._ref[1])
        self.update()

    def clear_goal(self) -> None:
        self._goal_xy = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#1b1b1b'))

        if self._ref is None:
            painter.setPen(QColor('#999999'))
            painter.drawText(self.rect(), Qt.AlignCenter, 'WAITING FOR GPS FIX')
            painter.end()
            return

        cx, cy = self.width() / 2.0, self.height() / 2.0
        scale = self._compute_scale()

        self._draw_crosshair(painter, cx, cy)
        self._draw_trail(painter, cx, cy, scale)
        self._draw_goal(painter, cx, cy, scale)
        self._draw_rover(painter, cx, cy, scale)
        painter.end()

    def _compute_scale(self) -> float:
        points = list(self._trail)
        if self._goal_xy is not None:
            points.append(self._goal_xy)
        if self._rover_xy is not None:
            points.append(self._rover_xy)
        max_extent = 5.0
        for x, y in points:
            max_extent = max(max_extent, abs(x), abs(y))
        available = max(40.0, min(self.width(), self.height()) / 2.0 - MARGIN_PX)
        return available / max_extent

    def _to_screen(self, point, cx: float, cy: float, scale: float) -> QPointF:
        x, y = point
        return QPointF(cx + x * scale, cy - y * scale)

    def _draw_crosshair(self, painter: QPainter, cx: float, cy: float) -> None:
        painter.setPen(QPen(QColor('#333333'), 1))
        painter.drawLine(0, int(cy), self.width(), int(cy))
        painter.drawLine(int(cx), 0, int(cx), self.height())

    def _draw_trail(self, painter: QPainter, cx: float, cy: float, scale: float) -> None:
        if len(self._trail) < 2:
            return
        path = QPainterPath()
        points = list(self._trail)
        path.moveTo(self._to_screen(points[0], cx, cy, scale))
        for point in points[1:]:
            path.lineTo(self._to_screen(point, cx, cy, scale))
        painter.setPen(QPen(QColor('#4fa3d1'), 2))
        painter.drawPath(path)

    def _draw_goal(self, painter: QPainter, cx: float, cy: float, scale: float) -> None:
        if self._goal_xy is None:
            return
        gx, gy = self._to_screen(self._goal_xy, cx, cy, scale).x(), self._to_screen(self._goal_xy, cx, cy, scale).y()
        painter.setPen(QPen(QColor('#e0a030'), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(gx - 8, gy), QPointF(gx + 8, gy))
        painter.drawLine(QPointF(gx, gy - 8), QPointF(gx, gy + 8))
        painter.drawEllipse(QPointF(gx, gy), 10, 10)

    def _draw_rover(self, painter: QPainter, cx: float, cy: float, scale: float) -> None:
        if self._rover_xy is None:
            return
        pos = self._to_screen(self._rover_xy, cx, cy, scale)
        if self._rover_fresh:
            painter.setPen(QPen(QColor('#e8e8e8'), 2))
            painter.setBrush(QBrush(QColor('#5fc35f')))
            painter.drawEllipse(pos, 7, 7)
        else:
            painter.setPen(QPen(QColor('#999999'), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(pos, 9, 9)
