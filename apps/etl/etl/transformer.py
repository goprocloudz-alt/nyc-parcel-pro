"""Normalises raw Socrata rows to match the DB schema (ETL.md §4)."""
from __future__ import annotations

from typing import Any


def coerce_empty_to_none(value: Any) -> Any:
    """Coerce empty strings to None per SCHEMA.md §1 and ETL.md §4 step 4."""
    return None if value == "" else value


def build_bbl(borough: str | int, block: str | int, lot: str | int) -> str:
    """Return zero-padded 10-char BBL string (SCHEMA.md §1: B(1)+Block(5)+Lot(4)).

    Always returns a string — never coerce to int (CLAUDE.md rule 8).
    """
    return str(borough).zfill(1) + str(block).zfill(5) + str(lot).zfill(4)


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Apply common normalisation rules to a raw Socrata row.

    - Coerces empty strings to None (ETL.md §4 step 4).
    - Strips leading/trailing whitespace from string values.
    """
    result: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, str):
            v = v.strip()
        result[k] = coerce_empty_to_none(v)
    return result
