from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_VIDEO_EXTENSIONS = [".mkv", ".mp4", ".avi", ".mov", ".wmv", ".ts"]
DEFAULT_IGNORE_PATTERNS = [
    "sample",
    "trailer",
    "behind the scenes",
    ".nfo",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".srt",
    ".sub",
    ".ass",
    ".ssa",
]


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(value: str | list[str] | None, default: list[str]) -> list[str]:
    if value is None:
        return default.copy()
    if isinstance(value, list):
        return [str(item) for item in value]
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_scalar(value: str) -> Any:
    text = value.strip().strip('"').strip("'")
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_simple_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key:
            data.setdefault(current_list_key, []).append(_parse_scalar(stripped[2:]))
            continue
        current_list_key = None
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            current_list_key = key
            continue
        data[key] = _parse_scalar(value)
    return data


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _load_structured_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() in {".yaml", ".yml"}:
        return _parse_simple_yaml(path)
    raise ValueError(f"Unsupported config format: {path}")


@dataclass(slots=True)
class Settings:
    alldebrid_api_key: str = ""
    alldebrid_agent: str = "alldebrid-emby/1.0"
    root_path: Path = Path("/mnt/16G/alldebrid-emby")
    library_movies_path: Path | None = None
    library_series_path: Path | None = None
    log_level: str = "INFO"
    request_timeout: float = 20.0
    retry_count: int = 3
    retry_delay: float = 3.0
    dry_run: bool = False
    use_docker: bool = False
    polling_interval_seconds: int = 60
    max_wait_for_magnet_seconds: int = 7200
    worker_refresh_interval_cycles: int = 10
    validate_links_timeout: float = 15.0
    video_extensions: list[str] = field(default_factory=lambda: DEFAULT_VIDEO_EXTENSIONS.copy())
    file_patterns_to_ignore: list[str] = field(default_factory=lambda: DEFAULT_IGNORE_PATTERNS.copy())
    config_path: Path = Path("config/config.yaml")

    @property
    def config_dir(self) -> Path:
        return self.root_path / "config"

    @property
    def data_dir(self) -> Path:
        return self.root_path / "data"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def db_path(self) -> Path:
        return self.state_dir / "alldebrid_emby.sqlite3"

    @property
    def incidents_path(self) -> Path:
        return self.state_dir / "incidents.csv"

    @property
    def report_path(self) -> Path:
        return self.state_dir / "health-report.json"

    @property
    def movies_library(self) -> Path:
        return self.library_movies_path or (self.root_path / "library" / "Peliculas")

    @property
    def series_library(self) -> Path:
        return self.library_series_path or (self.root_path / "library" / "Series")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file(Path(".env"))
    config_path = Path(os.environ.get("CONFIG_PATH", "config/config.yaml"))
    payload = _load_structured_config(config_path)
    return Settings(
        alldebrid_api_key=os.environ.get("ALLDEBRID_API_KEY", str(payload.get("alldebrid_api_key", payload.get("ALLDEBRID_API_KEY", "")))),
        alldebrid_agent=os.environ.get("ALLDEBRID_AGENT", str(payload.get("alldebrid_agent", "alldebrid-emby/1.0"))),
        root_path=Path(os.environ.get("ROOT_PATH", str(payload.get("root_path", "/mnt/16G/alldebrid-emby")))),
        library_movies_path=Path(os.environ["LIBRARY_MOVIES_PATH"]) if os.environ.get("LIBRARY_MOVIES_PATH") else (Path(str(payload["library_movies_path"])) if payload.get("library_movies_path") else None),
        library_series_path=Path(os.environ["LIBRARY_SERIES_PATH"]) if os.environ.get("LIBRARY_SERIES_PATH") else (Path(str(payload["library_series_path"])) if payload.get("library_series_path") else None),
        log_level=os.environ.get("LOG_LEVEL", str(payload.get("log_level", "INFO"))),
        request_timeout=float(os.environ.get("REQUEST_TIMEOUT", payload.get("request_timeout", 20.0))),
        retry_count=int(os.environ.get("RETRY_COUNT", payload.get("retry_count", 3))),
        retry_delay=float(os.environ.get("RETRY_DELAY", payload.get("retry_delay", 3.0))),
        dry_run=_parse_bool(os.environ.get("DRY_RUN", payload.get("dry_run")), False),
        use_docker=_parse_bool(os.environ.get("USE_DOCKER", payload.get("use_docker")), False),
        polling_interval_seconds=int(os.environ.get("POLLING_INTERVAL_SECONDS", payload.get("polling_interval_seconds", 60))),
        max_wait_for_magnet_seconds=int(os.environ.get("MAX_WAIT_FOR_MAGNET_SECONDS", payload.get("max_wait_for_magnet_seconds", 7200))),
        worker_refresh_interval_cycles=int(os.environ.get("WORKER_REFRESH_INTERVAL_CYCLES", payload.get("worker_refresh_interval_cycles", 10))),
        validate_links_timeout=float(os.environ.get("VALIDATE_LINKS_TIMEOUT", payload.get("validate_links_timeout", 15.0))),
        video_extensions=_parse_list(os.environ.get("VIDEO_EXTENSIONS"), payload.get("video_extensions", DEFAULT_VIDEO_EXTENSIONS)),
        file_patterns_to_ignore=_parse_list(os.environ.get("FILE_PATTERNS_TO_IGNORE"), payload.get("file_patterns_to_ignore", DEFAULT_IGNORE_PATTERNS)),
        config_path=config_path,
    )
