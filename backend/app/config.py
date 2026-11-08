"""Application settings, loaded from environment variables (and `.env` if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
DEFAULT_GRID_GEOJSON = REPO_ROOT / "data" / "wny_grid.geojson"

# Load repo-root .env first, then backend/.env (neither is required).
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


def _int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


ALLOWED_MIME_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    db_pool_min: int = 1
    db_pool_max: int = 10

    gemini_api_key: str = ""
    gemini_model: str = ""

    s3_endpoint: str = ""
    s3_region: str = "ewr1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "pleiades-photos"
    s3_public_base: str = ""

    public_app_origin: str = ""

    region_tz: str = "America/New_York"
    grid_step_deg: float = 0.1
    centroid_lat: float = 42.7
    centroid_lon: float = -78.4
    forecast_hours: int = 72
    grid_geojson_path: str = str(DEFAULT_GRID_GEOJSON)

    max_upload_bytes: int = 15 * 1024 * 1024
    uploads_per_hour: int = 20
    photo_workers: int = 4
    explain_timeout_s: float = 12.0
    # Seconds between Gemini calls in `ingest explain`. 30 s keeps the free tier (5 requests/min)
    # mostly free for on-demand clicks; set 0 on a paid tier.
    explain_warm_interval_s: float = 30.0

    allowed_mime_types: dict[str, str] = field(default_factory=lambda: dict(ALLOWED_MIME_TYPES))

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key and self.s3_bucket)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=_env("DATABASE_URL"),
            db_pool_min=_int("DB_POOL_MIN", 1),
            db_pool_max=_int("DB_POOL_MAX", 10),
            gemini_api_key=_env("GEMINI_API_KEY"),
            gemini_model=_env("GEMINI_MODEL"),
            s3_endpoint=_env("VULTR_S3_ENDPOINT"),
            s3_region=_env("VULTR_S3_REGION", "ewr1"),
            s3_access_key=_env("VULTR_S3_ACCESS_KEY"),
            s3_secret_key=_env("VULTR_S3_SECRET_KEY"),
            s3_bucket=_env("VULTR_S3_BUCKET", "pleiades-photos"),
            s3_public_base=_env("VULTR_S3_PUBLIC_BASE").rstrip("/"),
            public_app_origin=_env("PUBLIC_APP_ORIGIN"),
            region_tz=_env("REGION_TZ", "America/New_York"),
            grid_step_deg=_float("GRID_STEP_DEG", 0.1),
            centroid_lat=_float("REGION_CENTROID_LAT", 42.7),
            centroid_lon=_float("REGION_CENTROID_LON", -78.4),
            forecast_hours=_int("FORECAST_HOURS", 72),
            grid_geojson_path=_env("GRID_GEOJSON_PATH") or str(DEFAULT_GRID_GEOJSON),
            max_upload_bytes=_int("MAX_UPLOAD_BYTES", 15 * 1024 * 1024),
            uploads_per_hour=_int("UPLOADS_PER_HOUR", 20),
            photo_workers=_int("PHOTO_WORKERS", 4),
            explain_timeout_s=_float("EXPLAIN_TIMEOUT_S", 12.0),
            explain_warm_interval_s=_float("EXPLAIN_WARM_INTERVAL_S", 30.0),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Process-wide settings (used by CLI jobs that run outside a Flask app)."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def current_settings() -> Settings:
    """Settings of the running Flask app, or process-wide settings outside an app context."""
    from flask import current_app, has_app_context

    if has_app_context() and "SETTINGS" in current_app.config:
        return current_app.config["SETTINGS"]
    return get_settings()
