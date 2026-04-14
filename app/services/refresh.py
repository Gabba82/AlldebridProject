from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from app.alldebrid import AllDebridClient
from app.config import Settings
from app.db import Database, utc_now
from app.utils.filesystem import atomic_write_text

LOGGER = logging.getLogger(__name__)


class RefreshService:
    def __init__(self, settings: Settings, db: Database, client: AllDebridClient) -> None:
        self.settings = settings
        self.db = db
        self.client = client

    def validate_link(self, url: str) -> tuple[bool, int | None, str, str | None]:
        try:
            response = requests.head(url, allow_redirects=True, timeout=self.settings.validate_links_timeout)
            if response.status_code < 400:
                return True, response.status_code, "HEAD", None
            if response.status_code in {403, 405}:
                response = requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=self.settings.validate_links_timeout)
                return response.status_code < 400, response.status_code, "GET_RANGE", None
            return False, response.status_code, "HEAD", response.reason
        except requests.RequestException as exc:
            return False, None, "HEAD", str(exc)

    def refresh_links(self) -> dict[str, int]:
        rows = self.db.fetch_all(
            """
            SELECT mf.id, mf.magnet_id, mf.remote_file_id, mf.remote_path, mf.direct_link, mf.strm_path
            FROM magnet_files mf
            JOIN magnets m ON m.id = mf.magnet_id
            WHERE m.remote_id IS NOT NULL
            """
        )
        summary = {"checked": 0, "refreshed": 0, "stale": 0}
        for row in rows:
            summary["checked"] += 1
            if not row["direct_link"]:
                self._refresh_row(row)
                summary["refreshed"] += 1
                continue
            ok, status_code, method, detail = self.validate_link(row["direct_link"])
            self.db.execute(
                """
                UPDATE magnet_files SET direct_link_status = ?, direct_link_checked_at = ?, updated_at = ?
                WHERE id = ?
                """,
                ("fresh" if ok else "stale", utc_now(), utc_now(), row["id"]),
            )
            if ok:
                continue
            summary["stale"] += 1
            LOGGER.info("Refreshing stale link for magnet_file=%s via %s status=%s detail=%s", row["id"], method, status_code, detail)
            self._refresh_row(row)
            summary["refreshed"] += 1
        return summary

    def _refresh_row(self, row) -> None:
        magnet = self.db.fetch_one("SELECT remote_id FROM magnets WHERE id = ?", (row["magnet_id"],))
        if not magnet:
            raise RuntimeError(f"Missing magnet {row['magnet_id']} for refresh")
        files_payload = self.client.magnet_files([int(magnet["remote_id"])])
        remote_files = files_payload.get("magnets", [{}])[0].get("files") or []
        target = self._find_link_by_path(remote_files, row["remote_path"])
        if not target:
            raise RuntimeError(f"Could not find remote path {row['remote_path']} for refresh")
        final_link = self.client.unlock_link(target).get("link")
        if not final_link:
            raise RuntimeError(f"Could not unlock refreshed link for {row['remote_path']}")
        self.db.execute(
            """
            UPDATE magnet_files
            SET direct_link = ?, direct_link_status = 'fresh', direct_link_checked_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (final_link, datetime.now(timezone.utc).isoformat(), utc_now(), row["id"]),
        )
        if row["strm_path"]:
            atomic_write_text(self.settings.root_path / "library" / row["strm_path"], str(final_link).strip() + "\n")

    def _find_link_by_path(self, entries, expected_path: str, parent: str = "") -> str | None:
        for entry in entries:
            name = entry.get("n") or entry.get("name") or entry.get("filename") or "unknown"
            current = f"{parent}/{name}".strip("/")
            if "e" in entry and isinstance(entry["e"], list):
                nested = self._find_link_by_path(entry["e"], expected_path, current)
                if nested:
                    return nested
                continue
            if current == expected_path:
                return entry.get("l") or entry.get("link")
        return None
