"""Streams rows from the Socrata SODA API (ETL.md §1)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()

_BASE_URL = "https://data.cityofnewyork.us/resource/{dataset_id}.json"
_PAGE_SIZE = 50_000


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    reraise=True,
)
async def _fetch_page(
    client: httpx.AsyncClient,
    dataset_id: str,
    offset: int,
    where: str | None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "$limit": _PAGE_SIZE,
        "$order": ":id",
        "$offset": offset,
    }
    if where:
        params["$where"] = where
    resp = await client.get(
        _BASE_URL.format(dataset_id=dataset_id), params=params
    )
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


async def stream_dataset(
    dataset_id: str,
    app_token: str,
    high_watermark: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield rows from a Socrata dataset, filtered to rows newer than high_watermark.

    Uses keyset pagination ($order/:id + $offset) per ETL.md §1.
    Each page is retried up to 5 times with exponential backoff.
    """
    where = f":updated_at > '{high_watermark}'" if high_watermark else None
    headers = {"X-App-Token": app_token}

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        offset = 0
        while True:
            log.info("fetching_page", dataset_id=dataset_id, offset=offset)
            page = await _fetch_page(client, dataset_id, offset, where)
            if not page:
                break
            for row in page:
                yield row
            offset += len(page)
            if len(page) < _PAGE_SIZE:
                break
