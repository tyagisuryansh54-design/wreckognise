"""Runtime configuration for the Wreckognise backend."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment-driven settings. Override with a `.env` file or real env vars."""

    app_name: str = "Wreckognise"
    app_version: str = "1.0.0"
    # Defaults to off. A debug flag that defaults ON ships verbose logging and
    # framework internals to production the moment someone forgets an env var,
    # and nothing in development is harmed by having to opt in.
    debug: bool = False
    # Empty means "work it out from the platform". An explicit value always
    # wins, so WRECKOGNISE_ENVIRONMENT=development still forces the dev posture
    # on a hosted instance when something needs debugging.
    environment: str = ""

    @property
    def is_production(self) -> bool:
        """Hardened unless this is demonstrably a developer's machine.

        The first cut of this defaulted to "development", which meant HSTS, the
        CSP and the /docs lockdown were opt-in -- and the opt-in was an
        environment variable in a dashboard. It shipped to production without
        one, ran unhardened, and nothing said so: every response looked fine.
        That is the same failure this file already fixed once for `debug`, so
        it should not have been reintroduced two fields below it.

        Render exports RENDER=true into every service, so the platform can
        answer the question itself and the safe state needs no human step.
        """
        declared = self.environment.strip().lower()
        if declared:
            return declared in {"production", "prod", "staging"}
        return os.environ.get("RENDER", "").lower() in {"true", "1"}

    # --- security ---
    # Non-upload routes carry a survey id and a few flags. A megabyte is three
    # orders of magnitude of headroom.
    max_json_body_bytes: int = 1_048_576

    # Two throttle tiers. "heavy" covers decode/denoise/inference, which cost
    # 8-40 s of CPU each on a 0.5 vCPU instance; "light" covers the rest.
    rate_limit_heavy: int = 12
    rate_limit_heavy_window_s: int = 300
    rate_limit_light: int = 120
    rate_limit_light_window_s: int = 60

    # Serve the interactive API docs only outside production. They are a
    # complete map of the attack surface and pull scripts from a CDN, which no
    # strict CSP should have to accommodate.
    expose_docs_in_production: bool = False

    # --- authentication ---
    # Off unless an account is configured. A deployment that quietly starts with
    # a default account is worse than one with no login at all, so the presence
    # of credentials IS the switch.
    auth_username: str = ""
    auth_password: str = ""
    # When true, the API refuses unauthenticated calls to the protected routes.
    # Default false so enabling auth does not silently break a running
    # deployment the moment the first account is seeded -- sign in, confirm it
    # works, then turn this on.
    require_auth: bool = False
    # HMAC key for artefact URLs. Generated per-process when unset, which means
    # existing links stop verifying after a restart -- acceptable, since the
    # files they point at live on an ephemeral disk and do not survive one
    # either. Set it once the storage does persist.
    secret_key: str = ""
    # Matched to the session lifetime rather than an arbitrary hour: an
    # operator who ingests a line and works through it for a morning should
    # not find the waterfall gone from under them halfway down the page.
    artefact_url_ttl_seconds: int = 43_200

    session_cookie_name: str = "wreckognise_session"
    session_ttl_seconds: int = 43_200          # 12 h
    min_password_length: int = 12

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_username and self.auth_password)

    # Origins the browser may load subresources from. Leaflet basemap tiles come
    # from Esri, fonts from Google, waterfall PNGs from the API itself.
    csp_img_src: str = "https://server.arcgisonline.com"
    csp_connect_src: str = ""

    @property
    def csp_header(self) -> str:
        """Content-Security-Policy for API-origin responses.

        style-src carries 'unsafe-inline' and that is not an oversight: Leaflet
        positions every tile by writing element.style, and CSP governs inline
        style attributes. Dropping it does not harden anything meaningful here
        -- these responses are JSON and PNG, not HTML -- and it silently breaks
        the chart. Stated plainly rather than left for someone to rediscover.
        """
        img = " ".join(x for x in ("'self'", "data:", "blob:", self.csp_img_src) if x)
        connect = " ".join(x for x in ("'self'", self.csp_connect_src) if x)
        return "; ".join(
            (
                "default-src 'self'",
                "base-uri 'self'",
                "frame-ancestors 'none'",
                "object-src 'none'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                "font-src 'self' https://fonts.gstatic.com",
                f"img-src {img}",
                f"connect-src {connect}",
                "form-action 'self'",
                "upgrade-insecure-requests",
            )
        )

    # --- storage ---
    storage_dir: Path = BASE_DIR / "storage"
    upload_dir: Path = BASE_DIR / "storage" / "uploads"
    processed_dir: Path = BASE_DIR / "storage" / "processed"
    report_dir: Path = BASE_DIR / "storage" / "reports"

    # --- ingestion limits ---
    max_upload_mb: int = 512
    allowed_extensions: tuple[str, ...] = (
        ".xtf", ".jsf", ".sgy", ".segy",          # raw sonar, navigation included
        ".jpg", ".jpeg", ".png", ".tif", ".tiff",  # exported waterfall images
    )

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
