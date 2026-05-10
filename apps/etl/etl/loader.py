"""Upserts transformed rows to Postgres in batches (ETL.md §4 step 5)."""
from __future__ import annotations

from typing import Any

import structlog
from psycopg import AsyncConnection, sql

log = structlog.get_logger()

BATCH_SIZE = 5_000


async def upsert_batch(
    conn: AsyncConnection[Any],
    table: str,
    pk_col: str,
    rows: list[dict[str, Any]],
) -> int:
    """INSERT … ON CONFLICT (pk_col) DO UPDATE for one batch.

    Uses psycopg.sql for identifier quoting — not string concatenation.
    All values are parameterised; table/column names come from internal
    constants, never from user input.
    Returns the number of rows upserted.
    """
    if not rows:
        return 0

    columns = list(rows[0].keys())

    stmt = sql.SQL(
        "INSERT INTO {tbl} ({cols}) VALUES ({vals}) "
        "ON CONFLICT ({pk}) DO UPDATE SET {updates}"
    ).format(
        tbl=sql.Identifier(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, columns)),
        vals=sql.SQL(", ").join(sql.Placeholder(c) for c in columns),
        pk=sql.Identifier(pk_col),
        updates=sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c))
            for c in columns
            if c != pk_col
        ),
    )

    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.executemany(stmt, rows)

    log.info("batch_upserted", table=table, count=len(rows))
    return len(rows)


async def upsert_in_batches(
    conn: AsyncConnection[Any],
    table: str,
    pk_col: str,
    rows: list[dict[str, Any]],
) -> int:
    """Split rows into BATCH_SIZE chunks and upsert each. Returns total upserted."""
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        total += await upsert_batch(conn, table, pk_col, rows[i : i + BATCH_SIZE])
    return total
