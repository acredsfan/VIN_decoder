import os
from pathlib import Path
from typing import Optional, Type

import dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
dotenv.load_dotenv(SCRIPT_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class BaseConfig:
    ENV_NAME = "base"
    TESTING = False

    BASE_DIR = Path(os.getenv("VIN_DECODER_BASE_DIR") or SCRIPT_DIR).resolve()
    TEMPLATE_DIR = BASE_DIR / "templates"
    STATIC_DIR = BASE_DIR / "static"
    UPLOAD_DIR = BASE_DIR / "uploads"
    DATA_DIR = BASE_DIR / "data"
    LOG_DIR = BASE_DIR / "logs"

    DB_PATH = Path(os.getenv("VIN_DECODER_DB_PATH") or (DATA_DIR / "vin_decoder.sqlite3"))
    TEMPLATE_DOWNLOAD_FILE = STATIC_DIR / "vin_upload_template.csv"

    REQUEST_TIMEOUT_SECONDS = _env_float("VIN_DECODER_REQUEST_TIMEOUT_SECONDS", 15)
    DEFAULT_RATE_LIMIT = os.getenv("VIN_DECODER_DEFAULT_RATE_LIMIT", "500 per minute")
    RATE_LIMIT_STORAGE_URI = os.getenv("VIN_DECODER_RATE_LIMIT_STORAGE_URI", "memory://")

    CACHE_TTL_HOURS = _env_int("VIN_DECODER_CACHE_TTL_HOURS", 168)
    CLEANUP_TTL_HOURS = _env_int("VIN_DECODER_CLEANUP_TTL_HOURS", 24)
    JOB_POLL_INTERVAL_MS = _env_int("VIN_DECODER_JOB_POLL_INTERVAL_MS", 3000)
    MAX_CONTENT_LENGTH = _env_int("VIN_DECODER_MAX_CONTENT_LENGTH_MB", 16) * 1024 * 1024
    MAX_RECENT_JOBS = _env_int("VIN_DECODER_MAX_RECENT_JOBS", 8)
    LOG_LEVEL = os.getenv("VIN_DECODER_LOG_LEVEL", "INFO").upper()


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    DEFAULT_RATE_LIMIT = "1000 per minute"
    CLEANUP_TTL_HOURS = 1


ConfigType = Type[BaseConfig]


def get_config_class(env_name: Optional[str] = None) -> ConfigType:
    env = (
        env_name
        or os.getenv("VIN_DECODER_ENV")
        or ("development" if os.name == "nt" else "production")
    ).lower()

    mapping = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }
    return mapping.get(env, DevelopmentConfig)
