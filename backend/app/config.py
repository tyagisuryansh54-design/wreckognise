"""Runtime configuration for the Wreckognise backend."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment-driven settings. Override with a `.env` file or real env vars."""

    app_name: str = "Wreckognise"
    app_version: str = "1.0.0"
    debug: bool = True

    # --- storage ---
    storage_dir: Path = BASE_DIR / "storage"
    upload_dir: Path = BASE_DIR / "storage" / "uploads"
    processed_dir: Path = BASE_DIR / "storage" / "processed"
    report_dir: Path = BASE_DIR / "storage" / "reports"

    # --- ingestion limits ---
    max_upload_mb: int = 512
    allowed_extensions: tuple[str, ...] = (".xtf", ".jsf", ".sgy", ".segy")

    # --- preprocessing defaults ---
    denoise_method: str = "nlm"          # "nlm" | "bilateral" | "none"
    nlm_h: float = 10.0                  # filter strength for Non-Local Means
    nlm_template_window: int = 7
    nlm_search_window: int = 21
    bilateral_diameter: int = 9
    bilateral_sigma_color: float = 75.0
    bilateral_sigma_space: float = 75.0
    clahe_clip_limit: float = 2.5
    clahe_tile_grid: int = 8

    # --- detection defaults ---
    model_weights: str = "yolov8n-sonar.pt"
    confidence_threshold: float = 0.35
    iou_threshold: float = 0.45
    max_detections: int = 100

    # --- georeferencing ---
    # WGS-84 ellipsoid constants used by the pixel -> lat/long solver.
    wgs84_a: float = 6_378_137.0
    wgs84_f: float = 1 / 298.257223563
    gps_antenna_offset_m: float = 0.0    # lever-arm correction, bow-positive

    # --- CORS ---
    # Comma-separated, not a tuple: pydantic-settings parses complex types as
    # JSON, so a tuple field would reject the plain
    # "https://a.app,https://b.app" that every hosting dashboard hands you.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    )
    # Optional regex, for platforms that mint a new origin per preview deploy
    # (e.g. r"https://.*\.vercel\.app").
    cors_origin_regex: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        env_prefix = "WRECKOGNISE_"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for directory in (
        settings.storage_dir,
        settings.upload_dir,
        settings.processed_dir,
        settings.report_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
