"""Write a valid XTF survey line from a real sonar image.

Why this exists
---------------
The dashboard has two ingest paths and they are not equivalent. A .jpg carries
no navigation, so the pipeline attaches a modelled track and every coordinate
it produces is illustrative -- the UI says so, and hides the position column.
Only an XTF carries a real GPS fix per ping, which is what makes slant-range
correction, georeferencing and the chart mean anything.

Demonstrating that second path needs an XTF, and the public corpora ship
images. This builds one: real acoustic data from an SCTD frame, wrapped in a
genuine XTF container with a plausible Gulf of Mannar track, written through
pyxtf's own ctypes structures rather than hand-packed bytes so the layout is
the library's definition of the format and not my reading of the spec.

The returns are real. The navigation is synthetic and the file says so in its
NoteString, because a coordinate derived from an invented track must never be
mistaken for a survey-grade fix.
"""

from __future__ import annotations

import ctypes
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from pyxtf import xtf_ctypes as X

# Gulf of Mannar outer shelf -- the origin the bundled samples already use.
ORIGIN_LAT, ORIGIN_LON = 8.6000, 78.4000
HEADING_DEG = 101.7
SPEED_KNOTS = 3.10
# 40 m range at 10 Hz. The ping rate is bounded by the two-way travel time,
# 2 * 40 / 1500 = 53 ms, so 100 ms is comfortably legal rather than merely
# convenient -- a file that pings faster than sound returns is a file any
# surveyor on the panel will spot.
SLANT_RANGE_M = 40.0
SENSOR_DEPTH_M = 38.5
ALTITUDE_M = 8.0
PING_INTERVAL_S = 0.10
FREQUENCY_KHZ = 455.0

MAGIC = 0xFACE
SONAR = 0  # XTFHeaderType.sonar
METRES_PER_DEG_LAT = 111_320.0


def _file_header(name: str, samples: int) -> X.XTFFileHeader:
    fh = X.XTFFileHeader()
    fh.FileFormat = 123
    fh.SystemType = 1
    fh.RecordingProgramName = b"WRECKOGN"
    fh.RecordingProgramVersion = b"1.0.0"
    fh.SonarName = b"Klein 3000"
    fh.SonarType = 4
    fh.NoteString = b"Synthetic navigation; acoustic returns from SCTD 1.0"
    fh.ThisFileName = name.encode()[:63]
    fh.NavUnits = 3          # 3 = latitude/longitude in degrees
    fh.NumberOfSonarChannels = 2
    fh.ReferencePointHeight = 0.0

    for i, (label, kind) in enumerate(((b"PORT", 1), (b"STBD", 2))):
        ci = fh.ChanInfo[i]
        ci.TypeOfChannel = kind
        ci.SubChannelNumber = i
        ci.CorrectionFlags = 1      # slant range, uncorrected
        ci.UniPolar = 1
        ci.BytesPerSample = 2
        ci.Reserved = samples       # SamplesPerChannel in the XTF spec
        ci.ChannelName = label
        ci.VoltScale = 5.0
        ci.Frequency = FREQUENCY_KHZ * 1000.0
        ci.HorizBeamAngle = 0.5
        ci.TiltAngle = 20.0
        ci.BeamWidth = 50.0
    return fh


def _ping_header(index: int, when: datetime, lat: float, lon: float, samples: int) -> X.XTFPingHeader:
    ph = X.XTFPingHeader()
    ph.MagicNumber = MAGIC
    ph.HeaderType = SONAR
    ph.SubChannelNumber = 0
    ph.NumChansToFollow = 2
    ph.NumBytesThisRecord = (
        ctypes.sizeof(X.XTFPingHeader)
        + 2 * (ctypes.sizeof(X.XTFPingChanHeader) + samples * 2)
    )
    ph.Year, ph.Month, ph.Day = when.year, when.month, when.day
    ph.Hour, ph.Minute, ph.Second = when.hour, when.minute, when.second
    ph.HSeconds = when.microsecond // 10_000
    ph.JulianDay = when.timetuple().tm_yday
    ph.PingNumber = index
    ph.EventNumber = 0
    ph.SoundVelocity = 750.0        # XTF stores half the two-way velocity
    ph.ComputedSoundVelocity = 1500.0

    # Towfish and vessel are colocated here; a real survey would offset by the
    # layback, which is why both pairs exist in the format at all.
    ph.SensorYcoordinate = lat
    ph.SensorXcoordinate = lon
    ph.ShipYcoordinate = lat
    ph.ShipXcoordinate = lon
    ph.SensorHeading = HEADING_DEG + 1.5 * math.sin(index / 45.0)
    ph.ShipGyro = ph.SensorHeading
    ph.SensorSpeed = SPEED_KNOTS
    ph.ShipSpeed = SPEED_KNOTS
    ph.SensorDepth = SENSOR_DEPTH_M + 0.4 * math.sin(index / 30.0)
    ph.SensorPrimaryAltitude = ALTITUDE_M + 0.6 * math.sin(index / 21.0)
    ph.SensorPitch = 0.3 * math.sin(index / 17.0)
    ph.SensorRoll = 0.6 * math.sin(index / 13.0)
    ph.Heave = 0.05 * math.sin(index / 11.0)
    ph.FixTimeHour, ph.FixTimeMinute, ph.FixTimeSecond = when.hour, when.minute, when.second
    return ph


def _chan_header(channel: int, samples: int) -> X.XTFPingChanHeader:
    ch = X.XTFPingChanHeader()
    ch.ChannelNumber = channel
    ch.SlantRange = SLANT_RANGE_M
    ch.GroundRange = math.sqrt(max(SLANT_RANGE_M**2 - ALTITUDE_M**2, 0.0))
    ch.TimeDuration = SLANT_RANGE_M / 750.0
    ch.SecondsPerPing = PING_INTERVAL_S
    ch.Frequency = int(FREQUENCY_KHZ)
    ch.NumSamples = samples
    ch.Weight = 0
    return ch


def _compose(sources: list[Path], width: int) -> np.ndarray:
    """Stack frames into one continuous line, seabed between contacts.

    One SCTD frame is a crop around a single target, so a line built from one
    frame is a few hundred pings long and renders as a thin strip. A real line
    runs for minutes and passes several things. Stacking frames -- resampled to
    a common swath width, with a stretch of that frame's own target-free seabed
    between them -- gives a line of the right proportions carrying several
    contacts, with every pixel still a real return.
    """
    import cv2

    blocks: list[np.ndarray] = []
    for i, src in enumerate(sources):
        frame = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
        if frame is None:
            raise SystemExit(f"could not read {src}")
        h = max(1, round(frame.shape[0] * width / frame.shape[1]))
        frame = cv2.resize(frame, (width, h), interpolation=cv2.INTER_AREA)
        if i:
            # Run-in seabed, taken from this frame's own outer columns where
            # the ground truth box does not reach.
            quiet = frame[:, int(width * 0.65) :]
            reps = width // quiet.shape[1] + 1
            blocks.append(np.tile(quiet, (1, reps))[:, :width][:140])
        blocks.append(frame)
    return np.vstack(blocks)


def build(sources: list[Path] | Path, destination: Path, width: int = 972) -> Path:
    if isinstance(sources, Path):
        sources = [sources]
    image = _compose(sources, width)
    pings, samples = image.shape

    # The target goes on ONE channel, not astride the centre.
    #
    # Splitting a frame down the middle puts the object at nadir -- directly
    # beneath the towfish, where slant range is barely above altitude and
    # sqrt(slant^2 - alt^2) collapses to zero. Nadir is the blind band of a
    # side-scan line; nothing is ever detected there. Built that way the file
    # decodes fine and then reports a 155 m contact at ground range 0.0 m.
    #
    # So starboard carries the real frames, and port carries seabed from the
    # same data -- columns beyond x=0.65, which no ground truth box reaches --
    # tiled to width. Both channels are genuine returns; the port side simply
    # has no target on it, which is what the quiet side of a line looks like.
    seabed = image[:, int(samples * 0.65) :]
    reps = samples // seabed.shape[1] + 1
    port = np.tile(seabed, (1, reps))[:, :samples][:, ::-1]
    starboard = image

    # 12-bit-ish range, which is what a real 16-bit unipolar channel looks
    # like; leaving it at 0-255 would make the TVG stage see a dead signal.
    scale = 16
    port16 = port.astype(np.uint16) * scale
    stbd16 = starboard.astype(np.uint16) * scale

    start = datetime(2026, 3, 14, 6, 12, 0, tzinfo=timezone.utc)
    step_m = SPEED_KNOTS * 0.514444 * PING_INTERVAL_S
    bearing = math.radians(HEADING_DEG)

    out = bytearray()
    out += bytes(_file_header(destination.name, samples))

    for i in range(pings):
        along = step_m * i
        lat = ORIGIN_LAT + (along * math.cos(bearing)) / METRES_PER_DEG_LAT
        lon = ORIGIN_LON + (along * math.sin(bearing)) / (
            METRES_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
        )
        when = start + timedelta(seconds=PING_INTERVAL_S * i)

        out += bytes(_ping_header(i, when, lat, lon, samples))
        for channel, row in ((0, port16[i]), (1, stbd16[i])):
            out += bytes(_chan_header(channel, samples))
            out += row.astype("<u2").tobytes()

    destination.write_bytes(out)
    return destination


if __name__ == "__main__":
    import sys

    *srcs, dst_arg = sys.argv[1:]
    dst = Path(dst_arg)
    path = build([Path(x) for x in srcs], dst)
    size = path.stat().st_size
    print(f"wrote {path}  ({size / 1024:.0f} KB)")
