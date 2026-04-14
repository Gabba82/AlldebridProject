from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Iterable

from app.alldebrid import AllDebridClient
from app.config import Settings
from app.db import Database, utc_now
from app.services.library import LibraryService, flatten_files_tree
from app.utils.magnet import extract_magnet_hash

LOGGER = logging.getLogger(__name__)


class MagnetService:
    def __init__(self, settings: Settings, db: Database, client: AllDebridClient, library: LibraryService) -> None:
        self.settings = settings
        self.db = db
        self.client = client
        self.library = library

    def register_magnet(self, magnet_uri: str, source: str = "manual") -> int:
        magnet_uri = magnet_uri.strip()
        magnet_hash = extract_magnet_hash(magnet_uri)
        if magnet_hash:
            existing = self.db.fetch_one("SELECT id FROM magnets WHERE magnet_hash = ?", (magnet_hash,))
            if existing:
                LOGGER.info("Duplicate magnet detected by hash %s", magnet_hash)
                return int(existing["id"])
        now = utc_now()
        magnet_id = self.db.execute(
            """
            INSERT INTO magnets (magnet_uri, magnet_hash, source, status, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (magnet_uri, magnet_hash, source, now, now),
        )
        self.db.log_event("INFO", "magnet_registered", "Magnet registered", magnet_id=magnet_id, payload={"source": source})
        return magnet_id

    def register_many(self, magnets: Iterable[str], source: str) -> list[int]:
        ids: list[int] = []
        for magnet in magnets:
            magnet = magnet.strip()
            if not magnet or magnet.startswith("#"):
                continue
            ids.append(self.register_magnet(magnet, source=source))
        return ids

    def add_from_file(self, path: Path) -> list[int]:
        payload = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            parsed = json.loads(payload)
            magnets = parsed.get("magnets", []) if isinstance(parsed, dict) else parsed
            values = [item["magnet"] if isinstance(item, dict) else str(item) for item in magnets]
        else:
            values = [line.strip() for line in payload.splitlines()]
        ids = self.register_many(values, source=str(path))
        path.rename(path.with_suffix(path.suffix + ".processed"))
        return ids

    def scan_inbox(self) -> list[int]:
        processed: list[int] = []
        for path in sorted(self.settings.inbox_dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in {".txt", ".json"}:
                continue
            processed.extend(self.add_from_file(path))
        return processed

    def process_pending(self, wait: bool = True) -> dict[str, Any]:
        rows = self.db.fetch_all(
            "SELECT * FROM magnets WHERE status IN ('pending', 'submitted', 'processing', 'ready') ORDER BY created_at"
        )
        summary = {"processed": 0, "ready": 0, "errors": 0}
        for row in rows:
            summary["processed"] += 1
            try:
                self._process_single(dict(row), wait=wait)
                refreshed = self.db.fetch_one("SELECT status FROM magnets WHERE id = ?", (row["id"],))
                if refreshed and refreshed["status"] == "completed":
                    summary["ready"] += 1
            except Exception as exc:
                summary["errors"] += 1
                LOGGER.exception("Error processing magnet %s: %s", row["id"], exc)
                self.db.execute(
                    "UPDATE magnets SET status = 'error', last_error = ?, updated_at = ? WHERE id = ?",
                    (str(exc), utc_now(), row["id"]),
                )
        return summary

    def _process_single(self, row: dict[str, Any], wait: bool) -> None:
        local_id = int(row["id"])
        remote_id = row.get("remote_id")
        if not remote_id:
            upload = self.client.add_magnet(row["magnet_uri"])
            magnets = upload.get("magnets") or []
            if not magnets:
                raise RuntimeError("AllDebrid did not return any uploaded magnet")
            remote = magnets[0]
            remote_id = remote["id"]
            self.db.execute(
                """
                UPDATE magnets SET remote_id = ?, filename = ?, size = ?, status = 'submitted', updated_at = ?
                WHERE id = ?
                """,
                (remote_id, remote.get("name") or remote.get("filename"), remote.get("size"), utc_now(), local_id),
            )

        if wait:
            self._wait_until_ready(local_id, int(remote_id))
        else:
            self.refresh_remote_status(local_id, int(remote_id))

        current = self.db.fetch_one("SELECT * FROM magnets WHERE id = ?", (local_id,))
        if current and current["status"] == "ready":
            self.materialize_ready_magnet(local_id, int(remote_id))

    def refresh_remote_status(self, local_id: int, remote_id: int) -> None:
        payload = self.client.magnet_status(remote_id=remote_id)
        magnets = payload.get("magnets") or []
        if not magnets:
            raise RuntimeError(f"Magnet {remote_id} not found in remote status")
        remote = magnets[0]
        status_code = int(remote.get("statusCode") or -1)
        status = "ready" if status_code == 4 else "processing"
        if status_code >= 5:
            status = "error"
        self.db.execute(
            """
            UPDATE magnets
            SET remote_status = ?, remote_status_code = ?, filename = COALESCE(?, filename),
                size = COALESCE(?, size), status = ?, updated_at = ?, completed_at = CASE WHEN ? = 'ready' THEN COALESCE(completed_at, ?) ELSE completed_at END
            WHERE id = ?
            """,
            (
                remote.get("status"),
                status_code,
                remote.get("filename"),
                remote.get("size"),
                status,
                utc_now(),
                status,
                utc_now(),
                local_id,
            ),
        )

    def _wait_until_ready(self, local_id: int, remote_id: int) -> None:
        deadline = time.time() + self.settings.max_wait_for_magnet_seconds
        while time.time() < deadline:
            self.refresh_remote_status(local_id, remote_id)
            current = self.db.fetch_one("SELECT status, remote_status, remote_status_code FROM magnets WHERE id = ?", (local_id,))
            if current is None:
                raise RuntimeError(f"Magnet {local_id} disappeared from local state")
            if current["status"] == "ready":
                return
            if current["status"] == "error":
                raise RuntimeError(f"Magnet entered error state: {current['remote_status']} ({current['remote_status_code']})")
            time.sleep(self.settings.polling_interval_seconds)
        raise TimeoutError(f"Magnet {remote_id} did not become ready before timeout")

    def materialize_ready_magnet(self, local_id: int, remote_id: int) -> None:
        files_payload = self.client.magnet_files([remote_id])
        magnets = files_payload.get("magnets") or []
        if not magnets:
            raise RuntimeError(f"No files returned for magnet {remote_id}")
        flattened = flatten_files_tree(magnets[0].get("files") or [])
        candidates = self.library.store_candidates(local_id, flattened)
        if not candidates:
            self.db.execute(
                "UPDATE magnets SET status = 'review_needed', review_needed = 1, updated_at = ? WHERE id = ?",
                (utc_now(), local_id),
            )
            self.library.write_incident({"magnet_id": local_id, "filename": magnets[0].get("filename", ""), "reason": "no_video_candidates", "target": ""})
            return
        for candidate in candidates:
            if not candidate.link:
                continue
            direct_link = self._resolve_direct_link(candidate.link)
            self.db.execute(
                """
                UPDATE magnet_files
                SET direct_link = ?, direct_link_status = 'fresh', updated_at = ?
                WHERE magnet_id = ? AND remote_file_id = ?
                """,
                (direct_link, utc_now(), local_id, candidate.remote_file_id),
            )
        self.library.classify_and_generate(local_id, dry_run=self.settings.dry_run)
        self.db.execute("UPDATE magnets SET status = 'completed', updated_at = ? WHERE id = ?", (utc_now(), local_id))

    def _resolve_direct_link(self, source_link: str) -> str:
        unlocked = self.client.unlock_link(source_link)
        link = unlocked.get("link")
        if link:
            return str(link)
        delayed_id = unlocked.get("id")
        if delayed_id:
            delayed = self.client.delayed_link(delayed_id)
            if delayed.get("link"):
                return str(delayed["link"])
        raise RuntimeError(f"Could not resolve final link from AllDebrid for {source_link}")
