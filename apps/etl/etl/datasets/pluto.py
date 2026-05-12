"""PLUTO (64uk-42ks) dataset module.

Implements the ETL.md §4 pipeline contract for the master parcel table.
This module is the template for all future dataset modules (ACRIS, DOB, HPD, 311).

PLUTO sync mode: full replace (ETL.md §2). No high-watermark is used.
Staging-table swap (ETL.md §5) is deferred; this sprint uses direct upsert.
"""
from __future__ import annotations

import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import structlog

from etl.fetcher import stream_dataset
from etl.loader import upsert_in_batches
from etl.transformer import build_bbl, normalize_row
from etl.types import SyncResult

log = structlog.get_logger()

# CLAUDE.md cheat sheet: always reference Socrata datasets by ID, not by name.
DATASET_ID = "64uk-42ks"
TABLE = "properties"
PK_COL = "bbl"

_METADATA_URL = f"https://data.cityofnewyork.us/api/views/{DATASET_ID}.json"


# ── BBL helpers ───────────────────────────────────────────────────────────────

def _bbl_from_row(row: dict[str, Any]) -> str:
    """Return zero-padded 10-char BBL string (SCHEMA.md §1, CLAUDE.md rule 8).

    PLUTO Socrata rows (64uk-42ks) contain BOTH:
      - `bbl`:      10-digit numeric, may be float-encoded ("1000160001.0")
      - `borocode`: integer 1-5
      - `borough`:  2-char code ("MN"/"BX"/"BK"/"QN"/"SI") — stored in `borough` column

    Prefers the `bbl` field (strip float suffix + zero-pad to 10 chars).
    Falls back to build_bbl(borocode, block, lot) from etl.transformer.
    """
    if bbl_raw := row.get("bbl"):
        # Strip ".0" suffix that Socrata sometimes appends when the field is
        # stored as a float internally; then zero-pad to ensure 10 chars.
        return str(bbl_raw).split(".")[0].zfill(10)
    # Fallback: assemble from individual components (ETL.md §4 step 4)
    return build_bbl(row["borocode"], row["block"], row["lot"])


# ── Type coercion helpers ─────────────────────────────────────────────────────

def _to_int(value: Any) -> int | None:
    """Cast to int, returning None for None or unparseable values."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        log.warning("pluto_int_cast_failed", value=value)
        return None


def _parse_splitzone(value: str | None) -> bool | None:
    """Convert PLUTO splitzone string to Python bool (SCHEMA.md §2.1).

    Socrata returns "Y" / "N" as strings; empty string has been coerced to
    None by normalize_row() before this is called.
    """
    if value == "Y":
        return True
    if value == "N":
        return False
    return None  # None / unexpected → NULL


# ── Version detection ─────────────────────────────────────────────────────────

async def fetch_pluto_version(app_token: str) -> str:
    """Fetch the PLUTO version string from the Socrata metadata API (ETL.md §5).

    Parses a pattern like "25v4" from the dataset description or name.
    Falls back to "unknown" with a warning if the pattern is not found.
    """
    headers = {"X-App-Token": app_token}
    try:
        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            resp = await client.get(_METADATA_URL)
            resp.raise_for_status()
            meta: dict[str, Any] = resp.json()
            for field in ("description", "name"):
                text: str = meta.get(field, "") or ""
                if m := re.search(r"\d{2}v\d+", text):
                    return m.group(0)
    except Exception as exc:  # noqa: BLE001
        log.warning("pluto_version_fetch_failed", error=str(exc))
    log.warning("pluto_version_not_detected")
    return "unknown"


# ── Row transformer ───────────────────────────────────────────────────────────

def transform_row(
    raw: dict[str, Any],
    pluto_version: str,
    synced_at: datetime,
) -> dict[str, Any] | None:
    """Map one raw Socrata PLUTO row to the `properties` table schema.

    Implements ETL.md §4 step 4:
      - Builds BBL (always a string, CLAUDE.md rule 8)
      - Coerces empty strings → NULL (via normalize_row from etl.transformer)
      - Strips whitespace from text fields
      - Maps abbreviated Socrata field names to snake_case DB columns
      - Casts integer fields; leaves Decimal fields as strings (psycopg casts)
      - Injects provenance fields (source_dataset, pluto_version, last_synced_at)

    Returns None to signal that this row should be skipped (caller logs and
    continues — ETL.md §4 step 4: "log and skip on failure").
    """
    # ETL.md §4 step 4: strip whitespace + coerce "" → None across all fields
    row = normalize_row(raw)

    # BBL — CLAUDE.md rule 8: always a string, never numeric
    try:
        bbl = _bbl_from_row(row)
    except (KeyError, TypeError) as exc:
        log.warning("pluto_skip_missing_bbl", error=str(exc))
        return None

    return {
        "bbl": bbl,
        # borough: 2-char letter code ("MN"/"BX"/"BK"/"QN"/"SI") — pass through
        # borocode (integer 1-5) is used only for BBL fallback; NOT stored as a column.
        "borough": row.get("borough"),
        "block": _to_int(row.get("block")),
        "lot": _to_int(row.get("lot")),
        "cd": _to_int(row.get("cd")),
        "council_district": _to_int(row.get("council")),
        # SCHEMA.md: zip_code is CHAR(5)
        "zip_code": row.get("zipcode"),
        "address": row.get("address"),
        "owner_name": row.get("ownername"),
        # Areas (sq ft) — PLUTO uses abbreviated names (strge/factry, not storage/factory)
        "lot_area": _to_int(row.get("lotarea")),
        "bldg_area": _to_int(row.get("bldgarea")),
        "com_area": _to_int(row.get("comarea")),
        "res_area": _to_int(row.get("resarea")),
        "office_area": _to_int(row.get("officearea")),
        "retail_area": _to_int(row.get("retailarea")),
        "garage_area": _to_int(row.get("garagearea")),
        "storage_area": _to_int(row.get("strgearea")),   # "strge" ≠ "storage"
        "factory_area": _to_int(row.get("factryarea")),  # "factry" ≠ "factory"
        "other_area": _to_int(row.get("otherarea")),
        # Building characteristics
        "num_bldgs": _to_int(row.get("numbldgs")),
        # num_floors: NUMERIC(5,2) — pass as string, psycopg casts automatically
        "num_floors": row.get("numfloors"),
        "units_res": _to_int(row.get("unitsres")),
        "units_total": _to_int(row.get("unitstotal")),
        "year_built": _to_int(row.get("yearbuilt")),
        "year_alter1": _to_int(row.get("yearalter1")),
        "year_alter2": _to_int(row.get("yearalter2")),
        "bldg_class": row.get("bldgclass"),
        "land_use": row.get("landuse"),
        # Lot dimensions — NUMERIC(8,2): pass as string, psycopg casts
        "lot_front": row.get("lotfront"),
        "lot_depth": row.get("lotdepth"),
        "bldg_front": row.get("bldgfront"),
        "bldg_depth": row.get("bldgdepth"),
        # Zoning
        "zone_dist1": row.get("zonedist1"),
        "zone_dist2": row.get("zonedist2"),
        "zone_dist3": row.get("zonedist3"),
        "zone_dist4": row.get("zonedist4"),
        "overlay1": row.get("overlay1"),
        "overlay2": row.get("overlay2"),
        "spec_dist1": row.get("spdist1"),   # spdist1 → spec_dist1
        "spec_dist2": row.get("spdist2"),
        "ltd_height": row.get("ltdheight"),
        "split_zone": _parse_splitzone(row.get("splitzone")),
        # FAR — NUMERIC(6,2): pass as string
        "resid_far": row.get("residfar"),
        "comm_far": row.get("commfar"),
        "facil_far": row.get("facilfar"),
        "built_far": row.get("builtfar"),
        # Assessment — NUMERIC(14,2): pass as string (SCHEMA.md: never floats)
        "assess_land": row.get("assessland"),
        "assess_tot": row.get("assesstot"),
        "exempt_tot": row.get("exempttot"),
        # Misc
        "landmark": row.get("landmark"),
        "easements": _to_int(row.get("easements")),
        "owner_type": row.get("ownertype"),
        "hist_dist": row.get("histdist"),
        # Geo — NUMERIC(10,7): pass as string
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        # Provenance — required on every NYC-data table row (SCHEMA.md §2)
        "pluto_version": pluto_version,
        "source_dataset": DATASET_ID,      # always by Socrata ID (CLAUDE.md)
        "last_synced_at": synced_at,       # UTC; set at transform time, not upsert time
    }


# ── Main sync function ────────────────────────────────────────────────────────

async def sync(
    conn: psycopg.AsyncConnection[Any],
    app_token: str,
    limit: int | None,
    dry_run: bool,
) -> SyncResult:
    """Fetch, transform, and upsert PLUTO rows into the `properties` table.

    Implements the ETL.md §4 contract:
      Step 1: open sync_log row        (handled by run.py caller)
      Step 2: fetch with retries       (stream_dataset — fetcher.py)
      Step 3: stream to NDJSON on disk (crash safety — this function)
      Step 4: transform each row       (transform_row — this function)
      Step 5: upsert in batches        (upsert_in_batches — loader.py)
      Steps 6-8: watermark / log close (handled by run.py caller)

    PLUTO is full-replace (ETL.md §2) — no high_watermark is returned.
    """
    synced_at = datetime.now(tz=UTC)
    version_from_row: str | None = None
    tmp_path: Path | None = None

    try:
        # ── Phase 1: Stream Socrata → NDJSON temp file (ETL.md §4 step 3) ──
        # Writing to disk first means a process crash after fetching but before
        # upserting does not lose the fetched data — resume from the file.
        with tempfile.NamedTemporaryFile(
            suffix=".ndjson", mode="w", delete=False, encoding="utf-8"
        ) as tmp:
            tmp_path = Path(tmp.name)
            rows_fetched = 0
            log.info("pluto_fetch_start", limit=limit)

            async for raw_row in stream_dataset(DATASET_ID, app_token):
                tmp.write(json.dumps(raw_row) + "\n")
                rows_fetched += 1
                # Capture version from first row that has it (ETL.md §5)
                if version_from_row is None and "version" in raw_row:
                    version_from_row = str(raw_row["version"])
                if limit is not None and rows_fetched >= limit:
                    log.info("pluto_fetch_limit_reached", rows=rows_fetched)
                    break
            # File closed here by context manager exit

        # Resolve PLUTO version string (ETL.md §5)
        if version_from_row:
            pluto_version = version_from_row
        else:
            # Version not in row data — fall back to Socrata metadata endpoint
            pluto_version = await fetch_pluto_version(app_token)

        log.info(
            "pluto_fetch_complete",
            rows_fetched=rows_fetched,
            pluto_version=pluto_version,
        )

        if dry_run:
            log.info("pluto_dry_run_skip_upsert", rows_fetched=rows_fetched)
            return SyncResult(rows_fetched=rows_fetched, rows_upserted=0, high_watermark=None)

        # ── Phase 2: Transform + upsert (ETL.md §4 steps 4–5) ──────────────
        rows_upserted = 0
        batch: list[dict[str, Any]] = []

        with tmp_path.open(encoding="utf-8") as f:
            for line in f:
                raw_row = json.loads(line)
                transformed = transform_row(raw_row, pluto_version, synced_at)
                if transformed is None:
                    continue  # skip invalid rows (logged inside transform_row)
                batch.append(transformed)
                # Flush in 5k batches to bound memory usage (full PLUTO = 870k rows)
                if len(batch) >= 5_000:
                    rows_upserted += await upsert_in_batches(conn, TABLE, PK_COL, batch)
                    batch = []
            if batch:
                rows_upserted += await upsert_in_batches(conn, TABLE, PK_COL, batch)

        log.info("pluto_upsert_complete", rows_upserted=rows_upserted)
        return SyncResult(
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
            high_watermark=None,  # PLUTO is full-replace — no watermark (ETL.md §2)
        )

    finally:
        # Always clean up temp file — even if we crash mid-upsert (ETL.md §4 step 3)
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
