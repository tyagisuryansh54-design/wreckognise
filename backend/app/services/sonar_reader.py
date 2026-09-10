"""Raw side-scan sonar ingestion.

Decodes `.xtf` (eXtended Triton Format) via `pyxtf` and `.jsf` (EdgeTech JSF)
via a self-contained header walker. When a file cannot be decoded -- or when the
demo runs without hardware captures on disk -- the module falls back to a
physically-modelled synthetic swath so the whole pipeline stays exercisable.

The synthetic model is not decorative: it reproduces TVG roll-off, Rayleigh
speckle, a nadir water column, sand-ripple bedforms, and target highlight +
acoustic shadow pairs, which is exactly the signal structure the OpenCV stage
and the detector are tuned against.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..models.schemas import ChannelInfo, GeoBounds, PingTelemetry, SonarMetadata
from ..utils.geodesy import destination_point

logger = logging.getLogger("wreckognise.sonar")

try:  # pragma: no cover - optional dependency
    import pyxtf

    PYXTF_AVAILABLE = True
except ImportError:  # pragma: no cover
    pyxtf = None
    PYXTF_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #
@dataclass
class PlantedTarget:
    """Ground truth for a synthetic contact, consumed by the detector."""

    row: int
    col: int
    height_px: int
    width_px: int
    shadow_px: int
    label: str
    intensity: float


@dataclass
class SonarSurvey:
    """Everything decoded from one sonar line, held in memory for the session."""

    survey_id: str
    metadata: SonarMetadata
    telemetry: list[PingTelemetry]
    waterfall: np.ndarray  # uint8, shape (pings, samples)
    # `filtered` is the operator-facing image (CLAHE applied); `detect_input`
    # is the same swath before equalisation, which is what the network sees.
    filtered: np.ndarray | None = None
    detect_input: np.ndarray | None = None
    targets: list[PlantedTarget] = field(default_factory=list)
    detections: list = field(default_factory=list)
    preprocess_stats: object | None = None
    inference_metrics: object | None = None

    @property
    def nadir_col(self) -> int:
        return self.waterfall.shape[1] // 2

    @property
    def samples_per_side(self) -> int:
        return self.waterfall.shape[1] // 2

    def ping_at(self, row: int) -> PingTelemetry:
        idx = max(0, min(len(self.telemetry) - 1, int(row)))
        return self.telemetry[idx]


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def read_sonar_file(path: Path, survey_id: str) -> SonarSurvey:
    """Decode a sonar file into a `SonarSurvey`, whatever the format.

    The `reason` strings below are operator-facing: they appear in the
    dashboard's Parser field and in exported reports. They must stay short and
    must never carry a server filesystem path or a raw exception -- the full
    detail is logged instead.
    """
    suffix = path.suffix.lower()

    if not path.is_file():
        return _synthesise(path, survey_id, reason="modelled swath, no capture file")

    if suffix == ".xtf" and PYXTF_AVAILABLE:
        try:
            return _read_xtf(path, survey_id)
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the upload
            logger.warning("XTF decode failed for %s: %s", path.name, exc)
            return _synthesise(path, survey_id, reason="XTF undecodable, modelled swath")

    if suffix == ".jsf":
        try:
            return _read_jsf(path, survey_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("JSF decode failed for %s: %s", path.name, exc)
            return _synthesise(path, survey_id, reason="JSF undecodable, modelled swath")

    if suffix == ".xtf" and not PYXTF_AVAILABLE:
        return _synthesise(path, survey_id, reason="pyxtf not installed, modelled swath")

    return _synthesise(path, survey_id, reason=f"no decoder for {suffix}, modelled swath")


# --------------------------------------------------------------------------- #
# XTF via pyxtf
# --------------------------------------------------------------------------- #
def _read_xtf(path: Path, survey_id: str) -> SonarSurvey:
    """Decode an XTF file's sonar packets and navigation into a survey."""
    _, packets = pyxtf.xtf_read(str(path))
    sonar_packets = packets.get(pyxtf.XTFHeaderType.sonar, [])
    if not sonar_packets:
        raise ValueError("XTF file contains no sonar packets")

    port_rows: list[np.ndarray] = []
    starboard_rows: list[np.ndarray] = []
    telemetry: list[PingTelemetry] = []

    for idx, ping in enumerate(sonar_packets):
        channels = ping.data
        if len(channels) < 2:
            continue
        port_rows.append(np.asarray(channels[0], dtype=np.float32))
        starboard_rows.append(np.asarray(channels[1], dtype=np.float32))

        chan_info = ping.ping_chan_headers[0]
        slant = float(getattr(chan_info, "SlantRange", 0.0) or 75.0)
        telemetry.append(
            PingTelemetry(
                ping_number=idx,
                timestamp=_packet_datetime(ping),
                latitude=float(ping.SensorYcoordinate),
                longitude=float(ping.SensorXcoordinate),
                heading_deg=float(ping.SensorHeading) % 360,
                speed_knots=abs(float(getattr(ping, "SensorSpeed", 0.0))),
                sensor_depth_m=abs(float(getattr(ping, "SensorDepth", 0.0))),
                altitude_m=abs(float(getattr(ping, "SensorPrimaryAltitude", 0.0))) or 12.0,
                slant_range_m=slant,
            )
        )

    if not port_rows:
        raise ValueError("XTF sonar packets carried no dual-channel data")

    width = min(min(r.size for r in port_rows), min(r.size for r in starboard_rows))
    # Port channel is stored outward-from-nadir; mirror it so nadir sits centre-frame.
    port = np.stack([r[:width][::-1] for r in port_rows])
    starboard = np.stack([r[:width] for r in starboard_rows])
    waterfall = _to_uint8(np.hstack([port, starboard]))

    metadata = _build_metadata(
        survey_id=survey_id,
        path=path,
        fmt="xtf",
        telemetry=telemetry,
        waterfall=waterfall,
        parser="pyxtf",
        frequency_khz=(455.0, 455.0),
    )
    return SonarSurvey(survey_id, metadata, telemetry, waterfall)


def _packet_datetime(ping) -> datetime:
    try:
        return datetime(
            int(ping.Year),
            int(ping.Month),
            int(ping.Day),
            int(ping.Hour),
            int(ping.Minute),
            int(ping.Second),
            tzinfo=timezone.utc,
        )
    except (ValueError, AttributeError, TypeError):
        return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# JSF (EdgeTech) -- minimal message walker
# --------------------------------------------------------------------------- #
JSF_START_MARKER = 0x1601
JSF_SONAR_DATA = 80
JSF_HEADER_STRUCT = "<HBBHBBBBHI"  # marker, ver, session, type, cmd, sub, chan, seq, res, size


def _read_jsf(path: Path, survey_id: str) -> SonarSurvey:
    """Walk EdgeTech JSF message headers and pull type-80 sonar data records.

    A JSF file is a flat stream of 16-byte message headers, each carrying a
    start marker, a message type, and the byte count of the payload that
    follows. Type 80 is the sonar data record; its first 240 payload bytes are
    the record header and the remainder is int16 sample data.
    """
    raw = path.read_bytes()
    offset = 0
    rows: list[np.ndarray] = []
    channels: list[int] = []

    while offset + 16 <= len(raw):
        marker, _ver, _sess, msg_type, _cmd, _sub, chan, _seq, _res, size = struct.unpack_from(
            JSF_HEADER_STRUCT, raw, offset
        )
        if marker != JSF_START_MARKER:
            offset += 1  # resynchronise on a corrupt stream
            continue
        payload = raw[offset + 16 : offset + 16 + size]
        if msg_type == JSF_SONAR_DATA and len(payload) > 240:
            samples = np.frombuffer(payload[240:], dtype="<i2").astype(np.float32)
            if samples.size:
                rows.append(samples)
                channels.append(chan)
        offset += 16 + size

    if len(rows) < 8:
        raise ValueError("JSF stream yielded too few sonar records")

    width = min(r.size for r in rows)
    port_rows = [r[:width][::-1] for r, c in zip(rows, channels) if c == 0]
    stbd_rows = [r[:width] for r, c in zip(rows, channels) if c == 1]
    if not port_rows or not stbd_rows:
        raise ValueError("JSF stream is missing one of the two sonar channels")

    n = min(len(port_rows), len(stbd_rows))
    waterfall = _to_uint8(np.hstack([np.stack(port_rows[:n]), np.stack(stbd_rows[:n])]))

    telemetry = _synthetic_track(n, seed=_seed_of(path))
    metadata = _build_metadata(
        survey_id=survey_id,
        path=path,
        fmt="jsf",
        telemetry=telemetry,
        waterfall=waterfall,
        parser="wreckognise.jsf",
        frequency_khz=(120.0, 410.0),
    )
    return SonarSurvey(survey_id, metadata, telemetry, waterfall)


# --------------------------------------------------------------------------- #
# Synthetic swath model
# --------------------------------------------------------------------------- #
TARGET_LIBRARY: list[tuple[str, int, int, int, float]] = [
    # label,         along-px, across-px, shadow-px, intensity
    ("shipwreck", 74, 30, 96, 1.85),
    ("shipwreck", 58, 22, 72, 1.70),
    ("debris_field", 40, 46, 26, 1.35),
    ("container", 30, 16, 40, 1.62),
    ("boulder", 18, 18, 30, 1.48),
    ("pipeline", 150, 7, 12, 1.30),
    ("uxo", 14, 10, 24, 1.55),
]


def _synthesise(
    path: Path,
    survey_id: str,
    reason: str,
    pings: int = 900,
    samples_per_side: int = 512,
) -> SonarSurvey:
    """Build a deterministic, physically-plausible side-scan swath."""
    rng = np.random.default_rng(_seed_of(path))
    telemetry = _synthetic_track(pings, seed=_seed_of(path))
    width = samples_per_side * 2
    nadir = samples_per_side

    # Across-track distance from nadir, in samples, for every column.
    col = np.arange(width)
    r_px = np.abs(col - nadir).astype(np.float32)
    r_norm = np.clip(r_px / samples_per_side, 1e-3, 1.0)

    # 1. Time-varied-gain roll-off: backscatter falls away with range.
    base = np.tile(0.85 / (r_norm**0.55), (pings, 1))

    # 2. Sand ripples / bedform texture -- low frequency on both axes.
    yy, xx = np.mgrid[0:pings, 0:width].astype(np.float32)
    ripple = (
        0.11 * np.sin(xx / 17.0 + yy / 240.0)
        + 0.07 * np.sin(xx / 41.0 - yy / 95.0)
        + 0.05 * np.sin(yy / 33.0)
    )
    base = base * (1.0 + ripple)

    # 3. Rayleigh speckle -- the dominant noise term in coherent sonar imagery.
    speckle = rng.rayleigh(scale=0.55, size=(pings, width)).astype(np.float32)
    swath = base * (0.55 + 0.45 * speckle)

    # 4. Nadir water column: near-zero return either side of the fish track.
    swath *= 1.0 - 0.93 * np.exp(-(r_px**2) / (2 * 21.0**2))

    # 5. Plant highlight + acoustic-shadow target pairs.
    targets = _plant_targets(swath, rng, nadir, samples_per_side, pings)

    # 6. Additive sensor / electronic noise floor.
    swath += rng.normal(0.0, 0.045, size=swath.shape).astype(np.float32)

    waterfall = _to_uint8(swath)
    metadata = _build_metadata(
        survey_id=survey_id,
        path=path,
        fmt="synthetic",
        telemetry=telemetry,
        waterfall=waterfall,
        parser=f"wreckognise.synthetic ({reason})",
        frequency_khz=(455.0, 455.0),
    )
    return SonarSurvey(survey_id, metadata, telemetry, waterfall, targets=targets)


def _plant_targets(
    swath: np.ndarray,
    rng: np.random.Generator,
    nadir: int,
    samples_per_side: int,
    pings: int,
) -> list[PlantedTarget]:
    """Stamp highlight/shadow target pairs into the swath and return ground truth."""
    planted: list[PlantedTarget] = []
    count = int(rng.integers(5, 9))

    for k in range(count):
        label, h_px, w_px, shadow_px, intensity = TARGET_LIBRARY[
            int(rng.integers(0, len(TARGET_LIBRARY)))
        ]

        # Keep contacts clear of the nadir gap and of the far-range edge.
        side = 1 if k % 2 == 0 else -1
        offset = int(rng.integers(int(0.22 * samples_per_side), int(0.80 * samples_per_side)))
        cx = nadir + side * offset
        cy = int(rng.integers(70, max(71, pings - 70)))

        y0, y1 = max(0, cy - h_px // 2), min(pings, cy + h_px // 2)
        x0, x1 = max(0, cx - w_px // 2), min(swath.shape[1], cx + w_px // 2)
        if y1 - y0 < 4 or x1 - x0 < 4:
            continue

        # Highlight: an elliptical bright return on the near-range face.
        gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        ellipse = ((gy - cy) / (h_px / 2 + 1e-6)) ** 2 + ((gx - cx) / (w_px / 2 + 1e-6)) ** 2
        mask = np.clip(1.0 - ellipse, 0.0, 1.0) ** 0.6
        swath[y0:y1, x0:x1] += intensity * mask * (0.8 + 0.4 * rng.random())

        # Shadow: an acoustic void extending away from nadir behind the target.
        s_start = cx + side * (w_px // 2)
        s_end = s_start + side * shadow_px
        lo, hi = sorted((s_start, s_end))
        lo, hi = max(0, lo), min(swath.shape[1], hi)
        if hi - lo > 2:
            # Shadow is darkest right behind the target and recovers with range.
            taper = np.linspace(0.08, 0.92, hi - lo, dtype=np.float32)
            if side < 0:
                taper = taper[::-1]
            profile = np.clip(
                1.0 - np.abs(np.linspace(-1, 1, y1 - y0, dtype=np.float32)) ** 2, 0.0, 1.0
            )
            attenuation = 1.0 - np.outer(profile, 1.0 - taper)
            swath[y0:y1, lo:hi] *= attenuation

        planted.append(
            PlantedTarget(
                row=cy,
                col=cx,
                height_px=h_px,
                width_px=w_px,
                shadow_px=shadow_px,
                label=label,
                intensity=float(intensity),
            )
        )

    return planted


# Demo survey origin: open water in the Gulf of Mannar, ~25 km off the
# Thoothukudi coast. Verified against GEBCO 2020 bathymetry -- every point in a
# +/-0.03 deg box around it is sea, 27-169 m deep, which brackets the towfish
# depth this model assumes. The previous origin (8.9260, 78.1560) sat at +10 m
# elevation: contacts were being plotted in a field.
DEMO_ORIGIN_LAT = 8.60
DEMO_ORIGIN_LON = 78.40
DEMO_ORIGIN_JITTER_DEG = 0.012  # ~1.3 km, well inside the verified water box


def _synthetic_track(
    pings: int,
    seed: int,
    origin: tuple[float, float] | None = None,
) -> list[PingTelemetry]:
    """A survey line with realistic drift, yaw and heave.

    `origin` pins the line to a specific place. Without it every line would
    start from the same demo point, so a chart showing several surveys would
    stack them on top of each other and look broken.
    """
    rng = np.random.default_rng(seed + 7)
    base_lat, base_lon = origin if origin else (DEMO_ORIGIN_LAT, DEMO_ORIGIN_LON)
    lat = base_lat + float(rng.normal(0, DEMO_ORIGIN_JITTER_DEG))
    lon = base_lon + float(rng.normal(0, DEMO_ORIGIN_JITTER_DEG))
    base_heading = float(rng.uniform(0, 360))
    speed_knots = float(rng.uniform(3.4, 4.6))
    slant = float(rng.choice([50.0, 75.0, 100.0, 150.0]))
    ping_interval_s = 0.24
    metres_per_ping = speed_knots * 0.514444 * ping_interval_s
    start = datetime.now(timezone.utc) - timedelta(seconds=pings * ping_interval_s)

    telemetry: list[PingTelemetry] = []
    for i in range(pings):
        # A towed line is never straight: slow course change plus yaw noise.
        heading = base_heading + 6.0 * math.sin(i / 320.0) + float(rng.normal(0, 0.35))
        lat, lon = destination_point(lat, lon, heading % 360, metres_per_ping)
        altitude = 12.0 + 2.4 * math.sin(i / 110.0) + float(rng.normal(0, 0.18))
        depth = 34.0 + 5.0 * math.sin(i / 260.0) + float(rng.normal(0, 0.12))

        telemetry.append(
            PingTelemetry(
                ping_number=i,
                timestamp=start + timedelta(seconds=i * ping_interval_s),
                latitude=lat,
                longitude=lon,
                heading_deg=heading % 360,
                speed_knots=max(0.0, speed_knots + float(rng.normal(0, 0.06))),
                sensor_depth_m=max(0.0, depth),
                altitude_m=max(3.0, altitude),
                slant_range_m=slant,
            )
        )
    return telemetry


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _to_uint8(arr: np.ndarray) -> np.ndarray:
    """Percentile-stretch an arbitrary float swath into 8-bit display space."""
    finite = np.nan_to_num(arr.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = np.percentile(finite, (1.0, 99.5))
    if hi - lo < 1e-6:
        hi = lo + 1.0
    return np.clip((finite - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def _seed_of(path: Path) -> int:
    """Stable per-file seed so a given upload always renders identically."""
    return int(hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:8], 16)


def _build_metadata(
    survey_id: str,
    path: Path,
    fmt: str,
    telemetry: list[PingTelemetry],
    waterfall: np.ndarray,
    parser: str,
    frequency_khz: tuple[float, float],
) -> SonarMetadata:
    lats = [t.latitude for t in telemetry]
    lons = [t.longitude for t in telemetry]
    slant = telemetry[0].slant_range_m
    samples_per_side = waterfall.shape[1] // 2

    line_length = 0.0
    for a, b in zip(telemetry, telemetry[1:]):
        line_length += math.dist((a.latitude, a.longitude), (b.latitude, b.longitude)) * 111_320

    duration = (telemetry[-1].timestamp - telemetry[0].timestamp).total_seconds()

    return SonarMetadata(
        survey_id=survey_id,
        filename=path.name,
        file_format=fmt,  # type: ignore[arg-type]
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        ping_count=len(telemetry),
        channels=[
            ChannelInfo(
                channel_id=0,
                name="Port",
                frequency_khz=frequency_khz[0],
                samples_per_ping=samples_per_side,
                slant_range_m=slant,
            ),
            ChannelInfo(
                channel_id=1,
                name="Starboard",
                frequency_khz=frequency_khz[1],
                samples_per_ping=samples_per_side,
                slant_range_m=slant,
            ),
        ],
        duration_seconds=round(duration, 2),
        line_length_m=round(line_length, 2),
        swath_width_m=slant * 2,
        mean_altitude_m=round(sum(t.altitude_m for t in telemetry) / len(telemetry), 2),
        start_time=telemetry[0].timestamp,
        bounds=GeoBounds(north=max(lats), south=min(lats), east=max(lons), west=min(lons)),
        parser=parser,
    )

# --------------------------------------------------------------------------- #
# Real sonar image samples
# --------------------------------------------------------------------------- #
SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"


def list_samples() -> list[dict]:
    """Bundled real sonar images, from the detector's held-out split."""
    manifest = SAMPLES_DIR / "manifest.json"
    if not manifest.is_file():
        return []
    try:
        import json

        return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def read_image_sample(filename: str, survey_id: str) -> SonarSurvey:
    """Load a real sonar image as a survey the rest of the pipeline can process.

    A bare sonar image carries no navigation, so a plausible track is attached
    to keep georeferencing, the chart and reporting exercisable. The positions
    that come out are therefore ILLUSTRATIVE, not survey-grade -- the metadata
    says so explicitly, and the dashboard surfaces it, because a coordinate
    derived from invented navigation must never be mistaken for a real fix.
    """
    import cv2

    path = SAMPLES_DIR / Path(filename).name
    if not path.is_file():
        raise FileNotFoundError(f"no bundled sample named '{filename}'")

    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"could not decode sample '{filename}'")

    pings = image.shape[0]
    origin = None
    for entry in list_samples():
        if entry.get("file") == path.name and entry.get("origin"):
            origin = (entry["origin"]["lat"], entry["origin"]["lon"])
            break
    telemetry = _synthetic_track(pings, seed=_seed_of(path), origin=origin)
    metadata = _build_metadata(
        survey_id=survey_id,
        path=path,
        fmt="image",
        telemetry=telemetry,
        waterfall=image,
        parser="real sonar image (SCTD) — navigation simulated",
        frequency_khz=(455.0, 455.0),
    )
    return SonarSurvey(survey_id, metadata, telemetry, image)
