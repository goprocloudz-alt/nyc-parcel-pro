"""Unit tests for the PLUTO ETL module (apps/etl/etl/datasets/pluto.py).

All tests run without a live database or live Socrata API.
Fixture rows are in tests/fixtures/pluto_sample.json (CLAUDE.md convention).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

from etl.datasets.pluto import (
    DATASET_ID,
    _bbl_from_row,
    _parse_splitzone,
    transform_row,
)
from etl.fetcher import stream_dataset

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixtures() -> list[dict[str, Any]]:
    return json.loads((FIXTURES_DIR / "pluto_sample.json").read_text())  # type: ignore[no-any-return]


FIXTURES = _load_fixtures()
ROW_MN = FIXTURES[0]   # Manhattan, all fields populated, splitzone="N", version="25v4"
ROW_BK = FIXTURES[1]   # Brooklyn, empty ownername/histdist/ownertype, splitzone="N"
ROW_SPLIT = FIXTURES[2]  # Manhattan, splitzone="Y", bbl as float-string, no version field

_SYNCED_AT = datetime(2026, 5, 11, 2, 0, 0, tzinfo=timezone.utc)


# ── transform_row: standard row ───────────────────────────────────────────────

def test_transform_standard_row_bbl() -> None:
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["bbl"] == "1000160001"


def test_transform_standard_row_borough() -> None:
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    # borough is the 2-char letter code stored in the DB column (SCHEMA.md §2.1)
    assert result["borough"] == "MN"


def test_transform_standard_row_int_fields() -> None:
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["lot_area"] == 89100
    assert result["year_built"] == 1914
    assert result["num_bldgs"] == 1
    assert result["units_total"] == 0


def test_transform_standard_row_string_decimal_fields() -> None:
    # Decimal fields are kept as strings; psycopg casts them to NUMERIC
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["lot_front"] == "245.25"
    assert result["assess_tot"] == "63450150.00"
    assert result["resid_far"] == "10.0"


# ── transform_row: empty strings → None ──────────────────────────────────────

def test_transform_empty_strings_become_none() -> None:
    result = transform_row(ROW_BK, "25v4", _SYNCED_AT)
    assert result is not None
    # "ownername": "" should become None (ETL.md §4 step 4)
    assert result["owner_name"] is None


def test_transform_empty_owner_type_becomes_none() -> None:
    result = transform_row(ROW_BK, "25v4", _SYNCED_AT)
    assert result is not None
    # "ownertype": "" → None
    assert result["owner_type"] is None


# ── transform_row: splitzone boolean coercion ─────────────────────────────────

def test_transform_splitzone_false() -> None:
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["split_zone"] is False


def test_transform_splitzone_true() -> None:
    result = transform_row(ROW_SPLIT, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["split_zone"] is True


# ── transform_row: BBL normalization ─────────────────────────────────────────

def test_transform_bbl_from_float_string() -> None:
    # Row 3 has bbl="1000020001.0" — must strip .0 and zero-pad to 10 chars
    result = transform_row(ROW_SPLIT, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["bbl"] == "1000020001"
    assert len(result["bbl"]) == 10


def test_bbl_from_row_fallback_to_components() -> None:
    # If bbl field is absent, build from borocode+block+lot
    row_no_bbl = {k: v for k, v in ROW_MN.items() if k != "bbl"}
    bbl = _bbl_from_row(row_no_bbl)
    assert bbl == "1000160001"


# ── transform_row: provenance fields ─────────────────────────────────────────

def test_transform_provenance_source_dataset() -> None:
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    # CLAUDE.md: always cite source_dataset by Socrata ID, not name
    assert result["source_dataset"] == "64uk-42ks"


def test_transform_provenance_pluto_version() -> None:
    result = transform_row(ROW_MN, "99v1", _SYNCED_AT)
    assert result is not None
    assert result["pluto_version"] == "99v1"


def test_transform_provenance_last_synced_at() -> None:
    result = transform_row(ROW_MN, "25v4", _SYNCED_AT)
    assert result is not None
    assert result["last_synced_at"] == _SYNCED_AT
    assert result["last_synced_at"].tzinfo is timezone.utc


# ── _parse_splitzone unit tests ───────────────────────────────────────────────

def test_parse_splitzone_y() -> None:
    assert _parse_splitzone("Y") is True


def test_parse_splitzone_n() -> None:
    assert _parse_splitzone("N") is False


def test_parse_splitzone_none() -> None:
    assert _parse_splitzone(None) is None


# ── fetcher: URL and token header (respx mock) ────────────────────────────────

@pytest.mark.asyncio
async def test_fetcher_url_and_token(respx_mock: respx.MockRouter) -> None:
    """Assert stream_dataset hits the correct Socrata URL with X-App-Token."""
    base = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
    # First call returns one row; second returns [] to stop pagination
    respx_mock.get(base).mock(
        side_effect=[
            Response(200, json=[{"bbl": "1000160001", "borough": "MN"}]),
            Response(200, json=[]),
        ]
    )
    rows: list[Any] = []
    async for row in stream_dataset(DATASET_ID, "test-token"):
        rows.append(row)

    assert len(rows) == 1
    # Verify the header was sent on the request
    assert respx_mock.calls[0].request.headers.get("x-app-token") == "test-token"


@pytest.mark.asyncio
async def test_fetcher_pagination_stops_at_empty_page(respx_mock: respx.MockRouter) -> None:
    """Assert the pagination loop exits when Socrata returns an empty page.

    The first page must be exactly PAGE_SIZE rows so the fetcher's partial-page
    short-circuit doesn't fire first; only then does it request page 2 and see [].
    """
    from etl.fetcher import _PAGE_SIZE

    base = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
    full_page = [{"bbl": str(i).zfill(10)} for i in range(_PAGE_SIZE)]

    respx_mock.get(base).mock(
        side_effect=[
            Response(200, json=full_page),
            Response(200, json=[]),  # empty page → stop
        ]
    )
    count = 0
    async for _ in stream_dataset(DATASET_ID, "test-token"):
        count += 1

    assert count == _PAGE_SIZE
    # Exactly 2 GET requests: first full page + empty terminator
    assert len(respx_mock.calls) == 2
