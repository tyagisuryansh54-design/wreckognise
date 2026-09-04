"""Pixel -> Lat/Long georeferencing for side-scan sonar contacts.

The solve chain, in order:

    1. Row  -> ping index        -> vessel fix + heading (from telemetry)
    2. Col  -> across-track px   -> signed slant range, starboard positive
    3. Slant range + altitude    -> ground range   (r_g = sqrt(r_s^2 - h^2))
    4. Heading + side            -> true bearing   (heading +/- 90 deg)
    5. Fix + bearing + range     -> WGS-84 lat/long (direct geodetic problem)

Every intermediate value is returned in `GeoSolution` so an operator can audit
the arithmetic rather than trusting a single opaque coordinate.
"""

from __future__ import annotations

import math

from ..config import settings
from ..models.schemas import BoundingBox, GeoSolution
from ..utils.geodesy import destination_point, ground_range, normalise_bearing
from .sonar_reader import SonarSurvey

# Error budget contributions, metres (1-sigma), combined in quadrature.
GNSS_RTK_SIGMA_M = 0.20        # RTK-corrected GNSS fix
HEADING_SIGMA_DEG = 0.35       # fibre-optic gyro / dual-antenna heading
LAYBACK_SIGMA_M = 0.45         # towfish layback estimate
SOUND_SPEED_SIGMA_FRAC = 0.002  # 0.2% sound-velocity uncertainty


def solve_pixel(survey: SonarSurvey, pixel_x: float, pixel_y: float) -> GeoSolution:
    """Georeference a single pixel of the waterfall to WGS-84 lat/long."""
    ping = survey.ping_at(int(round(pixel_y)))
    nadir = survey.nadir_col
    samples_per_side = max(1, survey.samples_per_side)

    # --- 2. Across-track slant range, signed (starboard positive) -----------
    across_px = pixel_x - nadir
    metres_per_sample = ping.slant_range_m / samples_per_side
    slant_range_m = abs(across_px) * metres_per_sample
    side = 1.0 if across_px >= 0 else -1.0

    # --- 3. Slant-range (flat-seafloor) correction --------------------------
    altitude = max(0.0, ping.altitude_m)
    ground_range_m = ground_range(slant_range_m, altitude)

    # --- 4. True bearing from the towfish to the contact --------------------
    # Side-scan looks perpendicular to the track: starboard = heading + 90.
    bearing = normalise_bearing(ping.heading_deg + side * 90.0)

    # --- 5. Direct geodetic problem on the WGS-84 ellipsoid -----------------
    # The lever arm shifts the acoustic centre along-track from the GNSS antenna.
    origin_lat, origin_lon = ping.latitude, ping.longitude
    if settings.gps_antenna_offset_m:
        origin_lat, origin_lon = destination_point(
            origin_lat, origin_lon, ping.heading_deg, -settings.gps_antenna_offset_m
        )

    lat, lon = destination_point(origin_lat, origin_lon, bearing, ground_range_m)

    uncertainty = _horizontal_uncertainty(ground_range_m)
    side_name = "starboard" if side > 0 else "port"

    formula = (
        f"ping={ping.ping_number} | "
        f"across={across_px:+.1f}px x {metres_per_sample:.4f} m/sample "
        f"=> r_slant={slant_range_m:.2f} m | "
        f"r_ground=sqrt({slant_range_m:.2f}^2 - {altitude:.2f}^2)={ground_range_m:.2f} m | "
        f"bearing={ping.heading_deg:.2f}{'+' if side > 0 else '-'}90={bearing:.2f}deg ({side_name}) | "
        f"WGS-84 direct from ({origin_lat:.6f}, {origin_lon:.6f}) "
        f"=> ({lat:.6f}, {lon:.6f}) +/-{uncertainty:.2f} m"
    )

    return GeoSolution(
        pixel_x=round(pixel_x, 2),
        pixel_y=round(pixel_y, 2),
        ping_index=ping.ping_number,
        across_track_m=round(side * ground_range_m, 3),
        slant_range_m=round(slant_range_m, 3),
        altitude_m=round(altitude, 3),
        ground_range_m=round(ground_range_m, 3),
        bearing_deg=round(bearing, 3),
        vessel_latitude=round(ping.latitude, 8),
        vessel_longitude=round(ping.longitude, 8),
        latitude=round(lat, 8),
        longitude=round(lon, 8),
        horizontal_uncertainty_m=round(uncertainty, 3),
        formula=formula,
    )


def solve_bbox(survey: SonarSurvey, bbox: BoundingBox) -> GeoSolution:
    """Georeference a detection box by solving for its centroid."""
    return solve_pixel(survey, bbox.cx, bbox.cy)


def bbox_dimensions_m(survey: SonarSurvey, bbox: BoundingBox) -> tuple[float, float]:
    """Convert a pixel box into (along-track length, across-track width) metres."""
    ping = survey.ping_at(int(bbox.cy))
    metres_per_sample = ping.slant_range_m / max(1, survey.samples_per_side)

    # Along-track sample spacing = distance the fish advances between pings.
    along_spacing = _along_track_spacing_m(survey, int(bbox.cy))

    length_m = bbox.height * along_spacing
    width_m = bbox.width * metres_per_sample
    return round(length_m, 2), round(width_m, 2)


def _along_track_spacing_m(survey: SonarSurvey, row: int) -> float:
    """Metres advanced per ping, from speed over ground and the ping interval."""
    idx = max(1, min(len(survey.telemetry) - 1, row))
    prev, curr = survey.telemetry[idx - 1], survey.telemetry[idx]
    dt = (curr.timestamp - prev.timestamp).total_seconds()
    if dt <= 0:
        dt = 0.24
    return max(0.02, curr.speed_knots * 0.514444 * dt)


def _horizontal_uncertainty(ground_range_m: float) -> float:
    """Combine the independent error terms in quadrature (1-sigma, metres)."""
    heading_term = ground_range_m * math.radians(HEADING_SIGMA_DEG)
    sound_speed_term = ground_range_m * SOUND_SPEED_SIGMA_FRAC
    return math.sqrt(
        GNSS_RTK_SIGMA_M**2
        + LAYBACK_SIGMA_M**2
        + heading_term**2
        + sound_speed_term**2
    )
