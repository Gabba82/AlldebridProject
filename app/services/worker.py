from __future__ import annotations

import logging
import time

from app.services.magnets import MagnetService
from app.services.reconcile import ReconcileService
from app.services.refresh import RefreshService

LOGGER = logging.getLogger(__name__)


class WorkerService:
    def __init__(self, magnet_service: MagnetService, refresh_service: RefreshService, reconcile_service: ReconcileService, polling_interval_seconds: int, refresh_every_cycles: int) -> None:
        self.magnet_service = magnet_service
        self.refresh_service = refresh_service
        self.reconcile_service = reconcile_service
        self.polling_interval_seconds = polling_interval_seconds
        self.refresh_every_cycles = max(refresh_every_cycles, 1)

    def run_forever(self) -> None:
        cycle = 0
        while True:
            cycle += 1
            LOGGER.info("Worker cycle %s starting", cycle)
            self.magnet_service.scan_inbox()
            self.magnet_service.process_pending(wait=False)
            if cycle % self.refresh_every_cycles == 0:
                self.refresh_service.refresh_links()
                self.reconcile_service.reconcile()
            LOGGER.info("Worker cycle %s finished; sleeping %s seconds", cycle, self.polling_interval_seconds)
            time.sleep(self.polling_interval_seconds)
