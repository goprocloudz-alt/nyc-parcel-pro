"""Shared types for the ETL pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import psycopg


@dataclass
class SyncResult:
    rows_fetched: int
    rows_upserted: int
    high_watermark: str | None  # None for full-replace datasets (e.g. PLUTO)


class SyncFn(Protocol):
    """Protocol for a dataset sync function.

    Every dataset module in etl/datasets/ must expose a module-level async
    function matching this signature so run.py can dispatch to it generically.
    """

    async def __call__(
        self,
        conn: psycopg.AsyncConnection[Any],
        app_token: str,
        limit: int | None,
        dry_run: bool,
    ) -> SyncResult: ...


@dataclass
class DatasetConfig:
    name: str          # short name accepted by --dataset flag, e.g. "pluto"
    dataset_id: str    # Socrata dataset ID, e.g. "64uk-42ks"
    dataset_name: str  # human-readable name written to sync_log.dataset_name
    sync_fn: SyncFn
