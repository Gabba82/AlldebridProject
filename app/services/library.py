from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db import Database, utc_now
from app.models import ClassificationResult, VideoCandidate
from app.utils.filesystem import atomic_write_text
from app.utils.naming import build_strm_path, classify_media

LOGGER = logging.getLogger(__name__)


def flatten_files_tree(files: list[dict[str, Any]], parent: str = "") -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for entry in files:
        name = entry.get("n") or entry.get("name") or entry.get("filename") or "unknown"
        current = f"{parent}/{name}".strip("/")
        if "e" in entry and isinstance(entry["e"], list):
            flattened.extend(flatten_files_tree(entry["e"], current))
            continue
        flattened.append(
            {
                "path": current,
                "size": entry.get("s") or entry.get("size") or 0,
                "link": entry.get("l") or entry.get("link"),
                "group": entry,
            }
        )
    return flattened


def is_video_file(path: str, settings: Settings) -> bool:
    lower = path.lower()
    if not any(lower.endswith(ext.lower()) for ext in settings.video_extensions):
        return False
    return not any(pattern.lower() in lower for pattern in settings.file_patterns_to_ignore)


class LibraryService:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    def store_candidates(self, magnet_id: int, remote_files: list[dict[str, Any]]) -> list[VideoCandidate]:
        candidates: list[VideoCandidate] = []
        for item in remote_files:
            path = item["path"]
            if not is_video_file(path, self.settings):
                continue
            remote_file_id = str(item.get("id") or path)
            candidate = VideoCandidate(
                magnet_id=magnet_id,
                remote_file_id=remote_file_id,
                remote_path=path,
                filename=Path(path).name,
                size=int(item.get("size") or 0),
                link=item.get("link"),
            )
            candidates.append(candidate)
            self._upsert_candidate(candidate)
        return candidates

    def _upsert_candidate(self, candidate: VideoCandidate) -> None:
        now = utc_now()
        self.db.execute(
            """
            INSERT INTO magnet_files (
                magnet_id, remote_file_id, remote_path, filename, size, direct_link, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(magnet_id, remote_file_id) DO UPDATE SET
                remote_path = excluded.remote_path,
                filename = excluded.filename,
                size = excluded.size,
                direct_link = COALESCE(excluded.direct_link, magnet_files.direct_link),
                updated_at = excluded.updated_at
            """,
            (
                candidate.magnet_id,
                candidate.remote_file_id,
                candidate.remote_path,
                candidate.filename,
                candidate.size,
                candidate.link,
                now,
                now,
            ),
        )

    def classify_and_generate(self, magnet_id: int, dry_run: bool = False) -> list[ClassificationResult]:
        rows = self.db.fetch_all("SELECT * FROM magnet_files WHERE magnet_id = ?", (magnet_id,))
        results: list[ClassificationResult] = []
        for row in rows:
            result = classify_media(row["filename"])
            relative = build_strm_path(result)
            result.strm_relative_path = relative
            results.append(result)
            self.db.execute(
                """
                UPDATE magnet_files
                SET media_type = ?, title = ?, year = ?, season = ?, episode = ?, confidence = ?,
                    review_needed = ?, strm_path = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    result.media_type,
                    result.title,
                    result.year,
                    result.season,
                    result.episode,
                    result.confidence,
                    int(result.review_needed),
                    str(relative),
                    json.dumps({"reasons": result.reasons or []}, ensure_ascii=True),
                    utc_now(),
                    row["id"],
                ),
            )
            direct_link = row["direct_link"]
            if direct_link and not dry_run:
                atomic_write_text(self.settings.root_path / "library" / relative, direct_link.strip() + "\n")
            if result.review_needed:
                self.write_incident(
                    {
                        "magnet_id": magnet_id,
                        "filename": row["filename"],
                        "reason": "classification_ambiguous",
                        "target": str(relative),
                    }
                )
        return results

    def write_incident(self, incident: dict[str, Any]) -> None:
        self.settings.incidents_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.settings.incidents_path.exists()
        with self.settings.incidents_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "magnet_id", "filename", "reason", "target"])
            if not exists:
                writer.writeheader()
            writer.writerow({"timestamp": utc_now(), **incident})
