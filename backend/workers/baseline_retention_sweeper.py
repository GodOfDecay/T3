"""BaselineRetentionSweeper — keeps the Equivalence Testing baseline store inside its retention rules
(Track 3, Phase G).

A capture that never became a baseline holds recordings nobody will use; they are deleted once past
`SDLC_BASELINE_RETENTION_DAYS` (default 90). A capture recorded as a baseline (`keep`) is never
deleted here. A capture still `running` long after any capture could (its server stopped during
it) is marked failed and its sandbox objects are removed by label.

Each capture already tidies its own project before it starts (`equivalence_tools._tidy`); this sweep
covers the projects nobody captures in any more. Files only: no database, so no tenant session.
Usage (process_api lifespan):
    task = asyncio.create_task(BaselineRetentionSweeper().run())
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = float(os.environ.get("BASELINE_RETENTION_SWEEP_INTERVAL_SECONDS", "3600"))
#: As the SLA sweep: not at boot, so a process stopped seconds after starting is not cut mid-sweep.
FIRST_SWEEP_DELAY_SECONDS = float(os.environ.get("BASELINE_RETENTION_FIRST_SWEEP_DELAY_SECONDS", "120"))


class BaselineRetentionSweeper:
    def __init__(self, store=None):
        self._store = store

    def _the_store(self):
        if self._store is None:
            from agents_orchestrator.testing_modernization_agent.store import LocalBaselineStore  # noqa: PLC0415

            self._store = LocalBaselineStore()
        return self._store

    def sweep_once(self, now: Optional[datetime] = None) -> dict[str, list[str]]:
        """{"purged": [...], "interrupted": [...]} across every project in the store."""
        from agents_orchestrator.testing_modernization_agent.sandbox import runner  # noqa: PLC0415
        from agents_orchestrator.testing_modernization_agent.store import project_ids  # noqa: PLC0415

        store = self._the_store()
        purged, interrupted = [], []
        for project_id in project_ids(store.root):
            try:
                gone = store.reap_interrupted(project_id, now)
                for capture_id in gone:
                    runner.cleanup(capture_id)
                interrupted += gone
                purged += store.purge_expired(project_id, now)
            except Exception:  # noqa: BLE001 — one project's problem never stops the sweep
                logger.exception("baseline retention: sweeping project %s failed", project_id)
        if purged or interrupted:
            logger.info("baseline retention: purged %d capture(s), marked %d interrupted", len(purged), len(interrupted))
        return {"purged": purged, "interrupted": interrupted}

    async def run(self) -> None:
        await asyncio.sleep(FIRST_SWEEP_DELAY_SECONDS)
        while True:
            try:
                await asyncio.to_thread(self.sweep_once)
            except Exception:  # noqa: BLE001
                logger.exception("baseline retention: sweep failed")
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
