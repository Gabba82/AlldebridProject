from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.alldebrid import AllDebridClient
from app.config import get_settings
from app.db import Database
from app.logging_utils import setup_logging
from app.services.library import LibraryService
from app.services.magnets import MagnetService
from app.services.reconcile import ReconcileService
from app.services.refresh import RefreshService
from app.services.worker import WorkerService
from app.utils.filesystem import ensure_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AllDebrid to Emby STRM bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("test-auth")
    add = sub.add_parser("add-magnet")
    add.add_argument("magnet")
    add_file = sub.add_parser("add-magnets-file")
    add_file.add_argument("path")
    sub.add_parser("scan-inbox")
    process = sub.add_parser("process-pending")
    process.add_argument("--no-wait", action="store_true")
    sub.add_parser("refresh-links")
    sub.add_parser("reconcile")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("worker")
    return parser


def bootstrap() -> tuple[argparse.Namespace, Database, MagnetService, RefreshService, ReconcileService, WorkerService]:
    settings = get_settings()
    setup_logging(settings)
    db = Database(settings.db_path)
    db.init()
    ensure_dirs(
        [
            settings.root_path,
            settings.config_dir,
            settings.data_dir,
            settings.inbox_dir,
            settings.cache_dir,
            settings.state_dir,
            settings.logs_dir,
            settings.root_path / "library",
            settings.movies_library,
            settings.series_library,
        ]
    )
    client = AllDebridClient(settings)
    library = LibraryService(settings, db)
    magnet_service = MagnetService(settings, db, client, library)
    refresh_service = RefreshService(settings, db, client)
    reconcile_service = ReconcileService(settings, db, library)
    worker = WorkerService(
        magnet_service=magnet_service,
        refresh_service=refresh_service,
        reconcile_service=reconcile_service,
        polling_interval_seconds=settings.polling_interval_seconds,
        refresh_every_cycles=settings.worker_refresh_interval_cycles,
    )
    args = build_parser().parse_args()
    return args, db, magnet_service, refresh_service, reconcile_service, worker


def main() -> None:
    args, db, magnet_service, refresh_service, reconcile_service, worker = bootstrap()
    settings = get_settings()
    if args.command == "init":
        print(f"Initialized project structure under {settings.root_path}")
        return
    if args.command == "test-auth":
        print(json.dumps(magnet_service.client.test_auth(), indent=2))
        return
    if args.command == "add-magnet":
        print(f"Registered magnet with local id {magnet_service.register_magnet(args.magnet)}")
        return
    if args.command == "add-magnets-file":
        print(json.dumps({"added": magnet_service.add_from_file(Path(args.path))}, indent=2))
        return
    if args.command == "scan-inbox":
        print(json.dumps({"added": magnet_service.scan_inbox()}, indent=2))
        return
    if args.command == "process-pending":
        print(json.dumps(magnet_service.process_pending(wait=not args.no_wait), indent=2))
        return
    if args.command == "refresh-links":
        print(json.dumps(refresh_service.refresh_links(), indent=2))
        return
    if args.command == "reconcile":
        print(json.dumps(reconcile_service.reconcile().__dict__, indent=2))
        return
    if args.command == "status":
        payload = {
            "magnets": [dict(row) for row in db.fetch_all("SELECT * FROM magnets ORDER BY created_at DESC LIMIT 25")],
            "magnet_files": [dict(row) for row in db.fetch_all("SELECT * FROM magnet_files ORDER BY updated_at DESC LIMIT 25")],
        }
        print(json.dumps(payload, indent=2))
        return
    if args.command == "doctor":
        print(json.dumps(reconcile_service.doctor(), indent=2))
        return
    if args.command == "worker":
        worker.run_forever()
        return


if __name__ == "__main__":
    main()
