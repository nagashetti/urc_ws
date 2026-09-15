"""Helpers for GNSS-to-local coordinate calculations."""

from __future__ import annotations

import math


EARTH_RADIUS_M = 6371000.0


def lat_lon_to_enu(lat_deg: float, lon_deg: float, ref_lat_deg: float, ref_lon_deg: float) -> tuple[float, float]:
    lat_rad = math.radians(lat_deg)
    lon_rad = math.radians(lon_deg)
    ref_lat_rad = math.radians(ref_lat_deg)
    ref_lon_rad = math.radians(ref_lon_deg)

    x = (lon_rad - ref_lon_rad) * math.cos(ref_lat_rad) * EARTH_RADIUS_M
    y = (lat_rad - ref_lat_rad) * EARTH_RADIUS_M
    return x, y


def distance_and_bearing_m(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> tuple[float, float]:
    x, y = lat_lon_to_enu(lat2_deg, lon2_deg, lat1_deg, lon1_deg)
    distance = math.hypot(x, y)
    bearing = math.degrees(math.atan2(x, y))
    if bearing < 0:
        bearing += 360.0
    return distance, bearing
