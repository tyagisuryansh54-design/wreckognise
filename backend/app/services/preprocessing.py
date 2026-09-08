"""OpenCV preprocessing chain for side-scan sonar waterfalls.

Raw sonar imagery is dominated by multiplicative Rayleigh speckle, and range
roll-off makes far-range contacts far dimmer than near-range ones. This stage
runs, in order:

    1. TVG normalisation   -- flatten the across-track intensity gradient
    2. Denoise             -- Non-Local Means or Bilateral (edge-preserving)
    3. CLAHE               -- local contrast so faint shadows survive
    4. Slant-range flag    -- geometric correction is applied at solve time

Both the input and the output are scored (SNR, speckle index, contrast) so the
UI can prove the filter earned its place rather than just asserting it.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from ..config import settings
from ..models.schemas import PreprocessStats


def preprocess(
    waterfall: np.ndarray,
    method: str | None = None,
    apply_tvg: bool = True,
    apply_clahe: bool = True,
) -> tuple[np.ndarray, PreprocessStats]:
    """Denoise a raw waterfall and report before/after image-quality metrics."""
    method = (method or settings.denoise_method).lower()
    started = time.perf_counter()

    raw = waterfall if waterfall.dtype == np.uint8 else _to_uint8(waterfall)
    working = _normalise_tvg(raw) if apply_tvg else raw.copy()

    # Score the denoiser against its own input. TVG normalisation deliberately
    # lifts far-range returns -- and the noise riding on them -- so measuring
    # from the pre-TVG raw image would credit the filter for a gain it never
    # made, or penalise it for one the gain stage caused.
    before_metrics = _quality(working)

    if method == "nlm":
        # Non-Local Means: best speckle suppression, keeps wreck edges intact.
        filtered = cv2.fastNlMeansDenoising(
            working,
            None,
            h=settings.nlm_h,
            templateWindowSize=settings.nlm_template_window,
            searchWindowSize=settings.nlm_search_window,
        )
        kernel = (
            f"NLM h={settings.nlm_h} "
            f"template={settings.nlm_template_window} "
            f"search={settings.nlm_search_window}"
        )
    elif method == "bilateral":
        # Bilateral: ~8x faster, preferred for real-time deck-side review.
        filtered = cv2.bilateralFilter(
            working,
            d=settings.bilateral_diameter,
            sigmaColor=settings.bilateral_sigma_color,
            sigmaSpace=settings.bilateral_sigma_space,
        )
        kernel = (
            f"Bilateral d={settings.bilateral_diameter} "
            f"sigmaColor={settings.bilateral_sigma_color} "
            f"sigmaSpace={settings.bilateral_sigma_space}"
        )
    else:
        filtered = working
        kernel = "identity (denoise disabled)"

    # Score the denoiser on its own output. CLAHE is a contrast stage, not a
    # noise stage -- it deliberately re-amplifies local detail, so folding it
    # into the SNR figure would understate what the filter actually achieved.
    denoise_metrics = _quality(filtered)

    if apply_clahe:
        clahe = cv2.createCLAHE(
            clipLimit=settings.clahe_clip_limit,
            tileGridSize=(settings.clahe_tile_grid, settings.clahe_tile_grid),
        )
        filtered = clahe.apply(filtered)
        kernel += (
            f" + CLAHE clip={settings.clahe_clip_limit} "
            f"tiles={settings.clahe_tile_grid}x{settings.clahe_tile_grid}"
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    # Contrast is scored on the final image, since that is what the operator
    # and the detector actually see.
    final_metrics = _quality(filtered)
    after_metrics = {**denoise_metrics, "contrast": final_metrics["contrast"]}

    stats = PreprocessStats(
        method=method,
        kernel=kernel,
        input_snr_db=before_metrics["snr_db"],
        output_snr_db=after_metrics["snr_db"],
        snr_gain_db=round(after_metrics["snr_db"] - before_metrics["snr_db"], 2),
        speckle_index_before=before_metrics["speckle_index"],
        speckle_index_after=after_metrics["speckle_index"],
        contrast_ratio=round(
            after_metrics["contrast"] / max(before_metrics["contrast"], 1e-6), 3
        ),
        elapsed_ms=round(elapsed_ms, 2),
        tvg_applied=apply_tvg,
        slant_range_corrected=True,
    )
    return filtered, stats


def _normalise_tvg(image: np.ndarray) -> np.ndarray:
    """Flatten across-track range roll-off (empirical gain normalisation).

    Each column is divided by a smoothed profile of its own mean intensity, so
    far-range returns are lifted to the same working level as near-range ones
    without amplifying the nadir water column into noise.
    """
    column_mean = image.astype(np.float32).mean(axis=0)
    # Smooth the profile so real along-track features are not divided away.
    smoothed = cv2.GaussianBlur(column_mean.reshape(1, -1), (0, 0), sigmaX=15.0).ravel()
    smoothed = np.maximum(smoothed, 1.0)
    gain = smoothed.mean() / smoothed
    # Bound the gain so the near-zero nadir column cannot explode.
    gain = np.clip(gain, 0.5, 3.0)
    return np.clip(image.astype(np.float32) * gain[None, :], 0, 255).astype(np.uint8)


def _quality(image: np.ndarray) -> dict[str, float]:
    """Image-quality triplet used to score the filter's effect."""
    arr = image.astype(np.float32)
    mean = float(arr.mean())
    std = float(arr.std())

    # Speckle index (sigma / mu) -- the standard multiplicative-noise measure.
    speckle_index = std / max(mean, 1e-6)

    # SNR estimated against a heavily smoothed "signal" reference. Both powers
    # are floored: a degenerate swath (a constant-value ping block, or a file
    # whose samples all decode to zero) would otherwise take log10(0) and yield
    # -inf, which is not JSON-serialisable and 500s the ingest endpoint.
    signal = cv2.GaussianBlur(arr, (0, 0), sigmaX=3.0)
    noise = arr - signal
    noise_power = max(float((noise**2).mean()), 1e-9)
    signal_power = max(float((signal**2).mean()), 1e-9)
    snr_db = float(np.clip(10.0 * np.log10(signal_power / noise_power), -100.0, 100.0))

    # Michelson contrast across the 5th-95th percentile band.
    p5, p95 = np.percentile(arr, (5, 95))
    contrast = float((p95 - p5) / max(p95 + p5, 1e-6))

    return {
        "snr_db": round(float(snr_db), 2),
        "speckle_index": round(speckle_index, 4),
        "contrast": round(contrast, 4),
    }


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(arr, (1.0, 99.5))
    if hi - lo < 1e-6:
        hi = lo + 1.0
    return np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_waterfall(image: np.ndarray, path, colormap: str = "bone") -> None:
    """Write a waterfall to disk as a PNG using a sonar-appropriate colormap."""
    colormaps = {
        "bone": cv2.COLORMAP_BONE,
        "ocean": cv2.COLORMAP_OCEAN,
        "viridis": cv2.COLORMAP_VIRIDIS,
        "hot": cv2.COLORMAP_HOT,
        "gray": None,
    }
    cmap = colormaps.get(colormap, cv2.COLORMAP_BONE)
    bgr = image if cmap is None else cv2.applyColorMap(image, cmap)
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(path), bgr)


def render_annotated(image: np.ndarray, detections: list, path) -> None:
    """Draw YOLOv8-style bounding boxes, labels and confidences onto a waterfall."""
    canvas = cv2.applyColorMap(image, cv2.COLORMAP_BONE)

    # BGR palette matching the Wreckognise accent tokens.
    palette = {
        "critical": (107, 107, 255),   # coral blush #FF6B6B
        "high": (0, 122, 255),         # sunset orange #FF7A00
        "medium": (3, 183, 255),       # golden amber #FFB703
        "low": (216, 180, 0),          # aqua #00B4D8
    }

    for det in detections:
        severity = getattr(det.severity, "value", str(det.severity))
        colour = palette.get(severity, (216, 180, 0))
        x, y, w, h = det.bbox.x, det.bbox.y, det.bbox.width, det.bbox.height
        cv2.rectangle(canvas, (x, y), (x + w, y + h), colour, 2)

        label = getattr(det.label, "value", str(det.label))
        caption = f"{label} {det.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(canvas, (x, max(0, y - th - 7)), (x + tw + 6, y), colour, -1)
        cv2.putText(
            canvas,
            caption,
            (x + 3, max(10, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (15, 25, 47),  # deep navy #0A192F
            1,
            cv2.LINE_AA,
        )

    cv2.imwrite(str(path), canvas)
