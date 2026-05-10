"""Refreshes materialized views after each ETL run (ETL.md §4 final step)."""
from __future__ import annotations

from typing import Any

import structlog
from psycopg import AsyncConnection, sql

log = structlog.get_logger()

# Views must exist before the first ETL run; they are created by separate
# migrations added when the features that depend on them are built.
MATERIALIZED_VIEWS = [
    "mv_property_latest_sale",
    "mv_property_violation_counts",
    "mv_comps_recent",
]


async def refresh_all(conn: AsyncConnection[Any]) -> None:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY for every view in MATERIALIZED_VIEWS.

    Uses psycopg.sql.Identifier for view-name quoting — not string formatting.
    Concurrent refresh requires a unique index on each view (see SCHEMA.md §4).
    """
    for view in MATERIALIZED_VIEWS:
        log.info("refreshing_view", view=view)
        await conn.execute(
            sql.SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}").format(
                sql.Identifier(view)
            )
        )
        log.info("refreshed_view", view=view)
