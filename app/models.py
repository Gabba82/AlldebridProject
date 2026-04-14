from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class VideoCandidate:
    magnet_id: int
    remote_file_id: str
    remote_path: str
    filename: str
    size: int
    link: str | None = None
    mime_type: str | None = None


@dataclass(slots=True)
class ClassificationResult:
    media_type: str
    title: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    strm_relative_path: Path | None = None
    confidence: float = 0.0
    review_needed: bool = False
    reasons: list[str] | None = None


@dataclass(slots=True)
class LinkValidationResult:
    ok: bool
    status_code: int | None
    method: str
    checked_at: datetime
    detail: str | None = None


@dataclass(slots=True)
class HealthReport:
    generated_at: str
    totals: dict[str, Any]
    incidents: list[dict[str, Any]]
