from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import Settings
from app.db import Database
from app.models import HealthReport
from app.services.library import LibraryService
from app.utils.filesystem import atomic_write_text


class ReconcileService:
    def __init__(self, settings: Settings, db: Database, library: LibraryService) -> None:
        self.settings = settings
        self.db = db
        self.library = library

    def reconcile(self) -> HealthReport:
        incidents: list[dict[str, str]] = []
        rows = self.db.fetch_all(
            """
            SELECT mf.id, mf.magnet_id, mf.direct_link, mf.strm_path, mf.filename
            FROM magnet_files mf
            """
        )
        missing = 0
        for row in rows:
            if not row["strm_path"]:
                incidents.append({"type": "missing_strm_path", "magnet_file_id": str(row["id"]), "filename": row["filename"]})
                continue
            path = self.settings.root_path / "library" / row["strm_path"]
            if not path.exists():
                missing += 1
                incidents.append({"type": "missing_strm_file", "magnet_file_id": str(row["id"]), "path": str(path)})
                if row["direct_link"]:
                    atomic_write_text(path, str(row["direct_link"]).strip() + "\n")
        totals = {
            "magnets": self.db.fetch_one("SELECT COUNT(*) AS total FROM magnets")["total"],
            "magnet_files": self.db.fetch_one("SELECT COUNT(*) AS total FROM magnet_files")["total"],
            "missing_strm_files": missing,
            "review_needed": self.db.fetch_one("SELECT COUNT(*) AS total FROM magnet_files WHERE review_needed = 1")["total"],
        }
        report = HealthReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            totals=totals,
            incidents=incidents,
        )
        atomic_write_text(self.settings.report_path, json.dumps(report.__dict__, indent=2, ensure_ascii=False) + "\n")
        return report

    def doctor(self) -> dict[str, object]:
        return {
            "db_exists": self.settings.db_path.exists(),
            "inbox_exists": self.settings.inbox_dir.exists(),
            "movies_library_exists": self.settings.movies_library.exists(),
            "series_library_exists": self.settings.series_library.exists(),
        }
