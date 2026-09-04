"""WGS-84 geodesy helpers used by the georeferencing solver.

Everything here is pure math with no third-party dependencies so the
pixel -> Lat/Long chain stays auditable and unit-testable.
"""

from __future__ import annotations

import math

WGS84_A = 6_378_137.0                 # semi-major axis (m)
WGS84_F = 1 / 298.257223563           # flattening
WGS84_B = WGS84_A * (1 - WGS84_F)     # semi-minor axis (m)
WGS84_E2 = WGS84_F * (2 - WGS84_F)    # first eccentricity squared


def meridian_radius(lat_deg: float) -> float:
    """Radius of curvature in the meridian (north-south) at a given latitude."""
    lat = math.radians(lat_deg)
    return WGS84_A * (1 - WGS84_E2) / (1 - WGS84_E2 * math.sin(lat) ** 2) ** 1.5


def normal_radius(lat_deg: float) -> float:
    """Radius of curvature in the prime vertical (east-west) at a given latitude."""
    lat = math.radians(lat_deg)
    return WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)


def destination_point(
    lat_deg: float, lon_deg: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    """Direct geodetic problem, solved on the local ellipsoidal tangent plane.

    For side-scan swaths (< 500 m) this is accurate to well under a centimetre,
    which is an order of magnitude tighter than the GNSS/heading error budget.
    """
    bearing = math.radians(bearing_deg)
    d_north = distance_m * math.cos(bearing)
    d_east = distance_m * math.sin(bearing)

    m_rad = meridian_radius(lat_deg)
    n_rad = normal_radius(lat_deg)

    d_lat = math.degrees(d_north / m_rad)
    d_lon = math.degrees(d_east / (n_rad * math.cos(math.radians(lat_deg))))

    return _clamp_lat(lat_deg + d_lat), _wrap_lon(lon_deg + d_lon)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    r = 6_371_008.8  # mean Earth radius
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = p2 - p1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Forward azimuth from point 1 to point 2, degrees true."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def ground_range(slant_range_m: float, altitude_m: float) -> float:
    """Flat-seafloor slant-range correction: r_ground = sqrt(r_slant^2 - h^2)."""
    if slant_range_m <= altitude_m:
        return 0.0
    return math.sqrt(slant_range_m**2 - altitude_m**2)


def shadow_height(shadow_length_m: float, ground_range_m: float, altitude_m: float) -> float:
    """Target height from acoustic shadow geometry: h = (L_s * H) / (R_g + L_s)."""
    denominator = ground_range_m + shadow_length_m
    if denominator <= 0:
        return 0.0
    return (shadow_length_m * altitude_m) / denominator


def _clamp_lat(lat: float) -> float:
    return max(-90.0, min(90.0, lat))


def _wrap_lon(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def normalise_bearing(bearing_deg: float) -> float:
    return (bearing_deg + 360) % 360
