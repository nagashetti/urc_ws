#!/usr/bin/env python3
"""Lesson 5: the smallest PyQt5 window. No ROS involved at all.

Every earlier lesson was an rclpy Node. This one is pure Qt, on purpose:
before tackling how ROS and Qt cooperate (lesson 6), it's worth seeing that
Qt already has its own event loop that has never heard of ROS — the same
way rclpy.spin() has never heard of Qt.

This is also Phase 1's "hello window" acceptance check from plan.md.
"""

import sys

from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class HelloWindow(QMainWindow):
    """A QMainWindow is shaped for a real app: one dedicated slot for a
    'central widget', plus room for menus/toolbars/a status bar later —
    even though this lesson uses none of those yet.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle('URC Operator Console — hello window')
        self.resize(400, 200)
        self._click_count = 0

        # QMainWindow won't take widgets directly — you give it exactly
        # one central widget and lay out everything else inside that. This
        # is the same shape main_window.py uses for the whole console;
        # here it's just a label and a button.
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self._label = QLabel('Hello from PyQt5 — no ROS involved yet.')
        layout.addWidget(self._label)

        button = QPushButton('Click me')
        # `clicked` is a signal QPushButton already defines. Connecting it
        # to a plain method is the exact signal/slot mechanism
        # ros_bridge.py relies on in lesson 6 — just with nothing
        # ROS-related crossing it yet, and no second thread involved.
        button.clicked.connect(self._on_click)
        layout.addWidget(button)

    def _on_click(self):
        self._click_count += 1
        self._label.setText(f'Clicked {self._click_count} time(s).')


def main():
    # QApplication has to exist before any widget is constructed — it owns
    # the event loop, application-wide settings, and the connection to the
    # windowing system. Exactly one per process.
    app = QApplication(sys.argv)

    window = HelloWindow()
    window.show()  # without this the window is constructed but invisible

    # exec_() blocks here and hands control to Qt's event loop: it waits
    # for clicks, key presses, timers, and paint requests, and dispatches
    # each to the right widget's handler. Nothing after this line runs
    # until the window closes. Compare directly to rclpy.spin(node) in
    # every earlier lesson — same "block and dispatch events" shape, but a
    # completely separate loop that knows nothing about ROS. Lesson 6 is
    # about running both of these at once without one blocking the other.
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
