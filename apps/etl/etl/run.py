"""Entry point: python -m etl.run [--dataset=<id> | --all] [--dry-run].

Examples (ETL.md §9):
    uv run python -m etl.run --dataset=64uk-42ks --dry-run
    uv run python -m etl.run --all
    uv run python -m etl.run --dataset=acris_master --since=2026-04-01
"""
from __future__ import annotations

import asyncio

import click
import structlog

log = structlog.get_logger()


@click.command()
@click.option("--dataset", default=None, help="Socrata dataset ID (e.g. 64uk-42ks)")
@click.option("--all", "run_all", is_flag=True, help="Run all configured datasets")
@click.option("--since", default=None, help="Override high-watermark (ISO 8601 UTC)")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Fetch and transform rows but skip all DB writes",
)
def main(
    dataset: str | None,
    run_all: bool,
    since: str | None,
    dry_run: bool,
) -> None:
    if not dataset and not run_all:
        raise click.UsageError("Pass --dataset=<id> or --all")
    # asyncio.run returns None on normal completion; Click exits 0. No sys.exit needed.
    asyncio.run(_run(dataset=dataset, run_all=run_all, since=since, dry_run=dry_run))


async def _run(
    dataset: str | None,
    run_all: bool,
    since: str | None,
    dry_run: bool,
) -> None:
    log.info("etl_start", dataset=dataset, run_all=run_all, dry_run=dry_run)
    # TODO: wire fetcher → transformer → loader → refresher → notifier
    #       open sync_log row, iterate stream_dataset(), call upsert_in_batches(),
    #       update high_watermark, close sync_log row, call refresh_all().
    log.info("etl_complete")


if __name__ == "__main__":
    main()
