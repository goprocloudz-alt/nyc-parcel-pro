"""Entry point: python -m etl.run [--dataset=<id> | --all] [--dry-run] [--limit=N].

Examples (ETL.md §9):
    uv run python -m etl.run --dataset=pluto --limit=10000   # dev: first 10k rows
    uv run python -m etl.run --dataset=pluto --dry-run       # fetch+transform, no DB
    uv run python -m etl.run --all                           # full pipeline
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import psycopg
import structlog
from dotenv import load_dotenv

# CLAUDE.md: .env lives only at repo root, symlinked into apps/etl/ as apps/etl/.env.
# Path(__file__).parent.parent resolves to apps/etl/ — the symlink target is repo root .env.
load_dotenv(Path(__file__).parent.parent / ".env")

from etl.datasets import pluto as _pluto_mod  # noqa: E402
from etl.types import DatasetConfig, SyncResult  # noqa: E402

log = structlog.get_logger()

# ── Dataset registry ──────────────────────────────────────────────────────────
# Add a DatasetConfig entry for every new dataset module.
# Both the short name ("pluto") and the Socrata ID ("64uk-42ks") are valid
# values for the --dataset flag.

_DATASETS: list[DatasetConfig] = [
    DatasetConfig(
        name="pluto",
        dataset_id="64uk-42ks",
        dataset_name="PLUTO",
        sync_fn=_pluto_mod.sync,
    ),
]

_REGISTRY: dict[str, DatasetConfig] = {}
for _cfg in _DATASETS:
    _REGISTRY[_cfg.name] = _cfg
    _REGISTRY[_cfg.dataset_id] = _cfg


# ── sync_log helpers (ETL.md §4 steps 1 and 7) ───────────────────────────────

async def _open_sync_log(
    conn: psycopg.AsyncConnection[Any],
    dataset_id: str,
    dataset_name: str,
) -> int:
    """INSERT a sync_log row with status='running'. Returns the new row id."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO sync_log (dataset_id, dataset_name, started_at, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (dataset_id, dataset_name, datetime.now(tz=UTC)),
        )
        row = await cur.fetchone()
        # row is always non-None after a successful RETURNING INSERT
        return int(row[0])  # type: ignore[index]


async def _close_sync_log(
    conn: psycopg.AsyncConnection[Any],
    log_id: int,
    *,
    status: str,
    rows_fetched: int | None = None,
    rows_upserted: int | None = None,
    error_message: str | None = None,
    high_watermark: str | None = None,
) -> None:
    """UPDATE the sync_log row with final status and metrics (ETL.md §4 step 7)."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE sync_log
               SET status        = %s,
                   completed_at  = %s,
                   rows_fetched  = %s,
                   rows_upserted = %s,
                   error_message = %s,
                   high_watermark = %s
             WHERE id = %s
            """,
            (
                status,
                datetime.now(tz=UTC),
                rows_fetched,
                rows_upserted,
                error_message,
                high_watermark,
                log_id,
            ),
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--dataset", default=None, help="Dataset name or Socrata ID (e.g. pluto, 64uk-42ks)")
@click.option("--all", "run_all", is_flag=True, help="Run all configured datasets")
@click.option("--since", default=None, help="Override high-watermark (ISO 8601 UTC)")
@click.option("--limit", type=int, default=None, help="Cap rows fetched (dev/test use)")
@click.option("--dry-run", is_flag=True, help="Fetch and transform rows; skip all DB writes")
def main(
    dataset: str | None,
    run_all: bool,
    since: str | None,
    limit: int | None,
    dry_run: bool,
) -> None:
    if not dataset and not run_all:
        raise click.UsageError("Pass --dataset=<name|id> or --all")
    # asyncio.run returns None on normal exit; Click exits 0. No sys.exit needed.
    asyncio.run(
        _run(dataset=dataset, run_all=run_all, since=since, limit=limit, dry_run=dry_run)
    )


# ── Orchestration ─────────────────────────────────────────────────────────────

async def _run(
    dataset: str | None,
    run_all: bool,
    since: str | None,
    limit: int | None,
    dry_run: bool,
) -> None:
    log.info("etl_start", dataset=dataset, run_all=run_all, limit=limit, dry_run=dry_run)

    app_token = os.environ.get("SOCRATA_APP_TOKEN", "")
    if not app_token:
        log.warning("socrata_app_token_missing", hint="set SOCRATA_APP_TOKEN in .env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is not set — check your .env file")

    # Resolve which dataset configs to run
    if run_all:
        configs = _DATASETS
    else:
        assert dataset is not None  # guaranteed by CLI validation above
        cfg = _REGISTRY.get(dataset)
        if cfg is None:
            known = sorted({c.name for c in _DATASETS})
            raise click.ClickException(
                f"Unknown dataset '{dataset}'. Known: {', '.join(known)}"
            )
        configs = [cfg]

    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        for cfg in configs:
            await _run_one(conn, cfg, app_token=app_token, limit=limit, dry_run=dry_run)

    log.info("etl_complete")


async def _run_one(
    conn: psycopg.AsyncConnection[Any],
    cfg: DatasetConfig,
    *,
    app_token: str,
    limit: int | None,
    dry_run: bool,
) -> None:
    """Run a single dataset sync and update sync_log (ETL.md §4 steps 1–8)."""
    log_id: int | None = None

    # Step 1: open sync_log row (skip when dry_run — no DB writes)
    if not dry_run:
        log_id = await _open_sync_log(conn, cfg.dataset_id, cfg.dataset_name)
        log.info(
            "sync_log_opened",
            dataset=cfg.name,
            log_id=log_id,
        )

    result: SyncResult | None = None
    try:
        result = await cfg.sync_fn(conn, app_token, limit, dry_run)
        log.info(
            "dataset_sync_success",
            dataset=cfg.name,
            rows_fetched=result.rows_fetched,
            rows_upserted=result.rows_upserted,
        )

        # Step 7: close sync_log row with success
        if log_id is not None:
            await _close_sync_log(
                conn,
                log_id,
                status="success",
                rows_fetched=result.rows_fetched,
                rows_upserted=result.rows_upserted,
                high_watermark=result.high_watermark,
            )

    except Exception as exc:
        log.error(
            "dataset_sync_failed",
            dataset=cfg.name,
            error=str(exc),
        )
        # Step 8: close sync_log row with failure
        if log_id is not None:
            await _close_sync_log(
                conn,
                log_id,
                status="failed",
                rows_fetched=result.rows_fetched if result else None,
                error_message=str(exc),
            )
        raise


if __name__ == "__main__":
    main()
