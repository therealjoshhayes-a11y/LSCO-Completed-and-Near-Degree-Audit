"""Catalog temporal eligibility policy shared by awardability and final selection.

The 2021-2022 August 31, 2026 deadline is documented in the archived
expiring-catalog work. Other catalog-year deadlines follow the same five-year
pattern provisionally pending institutional policy confirmation. Historical
academic completion is never erased by a temporal exclusion.
"""
from __future__ import annotations
from datetime import date

EVALUATION_DATE = date(2026, 10, 8)
CATALOG_LIFETIME_YEARS = 5

def catalog_temporal_fields(catalog_year: object) -> dict[str, str]:
    value = str(catalog_year).strip()
    if len(value) != 9 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit():
        return dict(catalog_expiration_date="", catalog_temporal_status="CATALOG_DATE_REVIEW",
                    catalog_policy_evidence="UNRESOLVED_CATALOG_YEAR",
                    conferral_temporal_eligibility="REVIEW")
    start = int(value[:4])
    if int(value[5:]) != start + 1:
        return dict(catalog_expiration_date="", catalog_temporal_status="CATALOG_DATE_REVIEW",
                    catalog_policy_evidence="INVALID_YEAR_SPAN",
                    conferral_temporal_eligibility="REVIEW")
    expiry = date(start + CATALOG_LIFETIME_YEARS, 8, 31)
    status = "CATALOG_EXPIRED" if expiry < EVALUATION_DATE else "CATALOG_CURRENT"
    basis = ("SOURCE_DOCUMENTED_2021_2022_AUG31_2026" if start == 2021
             else "FIVE_YEAR_CONVENTION_PROVISIONAL_VERIFY_INSTITUTIONAL_POLICY")
    return dict(catalog_expiration_date=expiry.isoformat(), catalog_temporal_status=status,
                catalog_policy_evidence=basis,
                conferral_temporal_eligibility=("FAIL_EXPIRED" if status == "CATALOG_EXPIRED" else "PASS_PROVISIONAL_POLICY"))
