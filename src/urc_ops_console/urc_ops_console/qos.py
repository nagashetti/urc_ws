"""Centralized QoS definitions for URC telemetry and command topics."""

from dataclasses import dataclass

from rclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    HistoryPolicy,
)


@dataclass(frozen=True)
class QoSProfileConfig:
    reliability: ReliabilityPolicy
    history: HistoryPolicy
    depth: int = 1


TELEMETRY = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

COMMAND = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
