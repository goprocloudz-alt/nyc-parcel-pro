"""Posts ETL run summaries to Slack and email (ETL.md §4 final step)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class DatasetResult:
    name: str
    status: str                  # success | failed | skipped
    rows_upserted: int | None = None
    error_message: str | None = None


async def post_slack_summary(
    results: list[DatasetResult],
    runtime_seconds: float,
    run_date: str,
) -> None:
    """Post a run summary to the configured Slack webhook.

    Matches the format shown in ETL.md §4.
    No-ops if SLACK_WEBHOOK_URL is not set.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        log.warning("slack_webhook_not_configured")
        return

    lines = [f"*NYC Parcel Pro ETL — {run_date}*"]
    for r in results:
        icon = "✓" if r.status == "success" else "✗"
        if r.rows_upserted is not None:
            detail = f"{r.rows_upserted:,} rows upserted"
        else:
            detail = r.error_message or r.status
        lines.append(f"{icon} {r.name:<25} {detail}")

    minutes, seconds = divmod(int(runtime_seconds), 60)
    lines.append(f"Total runtime: {minutes}m {seconds}s")

    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json={"text": "\n".join(lines)})
        if resp.status_code != 200:
            log.error(
                "slack_post_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
