"""Explicit source-backed LSCO catalog conferral deadlines. Unknown -> REVIEW.

Maintain data/policy/catalog_expiration_dates.csv from a published catalog.
This module does not infer deadlines or conferability from a five-year formula.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

EVALUATION_DATE = date(2026, 10, 8)
POLICY_FILE = Path(__file__).resolve().parent.parent / "data/policy/catalog_expiration_dates.csv"
REQUIRED_YEARS = {f"{y}-{y+1}" for y in range(2021, 2027)}


def load_catalog_policy() -> dict[str, dict[str, str]]:
    if not POLICY_FILE.is_file():
        raise FileNotFoundError(f"Required institutional catalog deadline table missing: {POLICY_FILE}")
    with POLICY_FILE.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    required = {"catalog_year", "expiration_date", "source_status", "source_document",
                "source_location", "source_url"}
    if not records or not required.issubset(records[0]):
        raise RuntimeError("Catalog deadline table missing required columns")
    by_year = {}
    for record in records:
        year = record["catalog_year"].strip()
        if year in by_year or not year:
            raise RuntimeError(f"Duplicate/blank catalog-year policy key: {year!r}")
        status = record["source_status"].strip()
        expiry = record["expiration_date"].strip()
        if status == "VERIFIED":
            if not expiry or not record["source_document"].strip() or not record["source_location"].strip():
                raise RuntimeError(f"Verified catalog lacks source or expiration: {year}")
            date.fromisoformat(expiry)
        elif status == "REVIEW_SOURCE_REQUIRED":
            if expiry:
                raise RuntimeError(f"Unverified catalog must not specify a made-up deadline: {year}")
        else:
            raise RuntimeError(f"Unrecognized catalog policy status for {year}: {status}")
        by_year[year] = record
    if not REQUIRED_YEARS.issubset(by_year):
        raise RuntimeError(f"Missing required catalog policy records: {sorted(REQUIRED_YEARS - by_year.keys())}")
    return by_year


CATALOG_POLICY = load_catalog_policy()


def catalog_temporal_fields(catalog_year: object) -> dict[str, str]:
    value = str(catalog_year).strip()
    record = CATALOG_POLICY.get(value)
    if record is None or record["source_status"] != "VERIFIED":
        return dict(catalog_expiration_date="", catalog_temporal_status="CATALOG_DATE_REVIEW",
                    catalog_policy_evidence=("UNMAPPED_CATALOG_YEAR" if record is None
                                             else "SOURCE_REVIEW_REQUIRED:" + record["source_document"]),
                    conferral_temporal_eligibility="REVIEW")
    expiry = date.fromisoformat(record["expiration_date"].strip())
    status = "CATALOG_EXPIRED" if expiry < EVALUATION_DATE else "CATALOG_CURRENT"
    return dict(catalog_expiration_date=expiry.isoformat(), catalog_temporal_status=status,
                catalog_policy_evidence="VERIFIED:" + record["source_document"] +
                                        " / " + record["source_location"],
                conferral_temporal_eligibility=("FAIL_EXPIRED" if status == "CATALOG_EXPIRED"
                                                else "PASS_VERIFIED_POLICY"))
