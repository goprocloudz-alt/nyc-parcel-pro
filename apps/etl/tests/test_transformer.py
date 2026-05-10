"""Unit tests for transformer.py.

Fixtures for Socrata payloads live in tests/fixtures/ per CLAUDE.md conventions.
"""
from etl.transformer import build_bbl, coerce_empty_to_none, normalize_row


def test_build_bbl_pads_correctly() -> None:
    # SCHEMA.md §1 example: Manhattan block 16 lot 1 → "1000160001"
    assert build_bbl(1, 16, 1) == "1000160001"


def test_build_bbl_accepts_strings() -> None:
    assert build_bbl("1", "16", "1") == "1000160001"


def test_build_bbl_pads_brooklyn() -> None:
    # Brooklyn (3), block 100, lot 1 → "3001000001"
    assert build_bbl(3, 100, 1) == "3001000001"


def test_coerce_empty_string_to_none() -> None:
    assert coerce_empty_to_none("") is None


def test_coerce_non_empty_string_unchanged() -> None:
    assert coerce_empty_to_none("hello") == "hello"


def test_coerce_zero_unchanged() -> None:
    # 0 is falsy but must not be coerced to None
    assert coerce_empty_to_none(0) == 0


def test_coerce_none_unchanged() -> None:
    assert coerce_empty_to_none(None) is None


def test_normalize_row_strips_whitespace() -> None:
    row = {"address": "  123 MAIN ST  ", "zip_code": "10001"}
    result = normalize_row(row)
    assert result["address"] == "123 MAIN ST"
    assert result["zip_code"] == "10001"


def test_normalize_row_coerces_empty_strings() -> None:
    row = {"owner_name": "", "bldg_class": "A1"}
    result = normalize_row(row)
    assert result["owner_name"] is None
    assert result["bldg_class"] == "A1"
