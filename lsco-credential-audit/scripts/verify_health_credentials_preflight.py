#!/usr/bin/env python
"""
Read-only preflight for the recovered nursing/PTA credential requirements.

Use immediately before a full audit run. It exits nonzero if a base-master rebuild
has erased or altered the approved health-program repair.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


TARGETS = {
    "REGISTERED_NURSING_AAS_2021": 36,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2021": 39,
    "REGISTERED_NURSING_TRANSITION_2022": 36,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2022": 39,
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2023": 46,
    "REGISTERED_NURSING_TRANSITION_2023": 36,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2023": 43,
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2024": 46,
    "REGISTERED_NURSING_TRANSITION_2024": 39,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2024": 43,
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2025": 46,
    "REGISTERED_NURSING_TRANSITION_2025": 39,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2025": 43,
    "PHYSICAL_THERAPY_ASSISTANT_2025": 52,
}

SOURCE_EXPECTED_ROWS = 200
ALLOWED_RULE_TYPES = {"EXACT", "ANY_N", "CORE_BUCKET", "ELECTIVE"}


def read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"Required file not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def hours(df: pd.DataFrame) -> dict[str, float]:
    work = df.copy()
    work["_hours"] = pd.to_numeric(work["credit_hours"], errors="coerce").fillna(0)
    return work.groupby("credential_id")["_hours"].sum().to_dict()


def main() -> int:
    root = Path(".").resolve()
    source_path = root / "data/processed/catalogs/requirements_master_multicatalog.csv"
    audit_path = root / "data/processed/catalogs/requirements_master_multiyear.csv"

    source = read(source_path)
    audit = read(audit_path)

    required_source = {
        "credential_id",
        "requirement_id",
        "catalog_year",
        "rule_type",
        "credit_hours",
    }
    required_audit = {
        "credential_id",
        "requirement_id",
        "catalog_year",
        "rule_type",
        "credit_hours",
    }

    missing_source_columns = sorted(required_source - set(source.columns))
    missing_audit_columns = sorted(required_audit - set(audit.columns))
    if missing_source_columns or missing_audit_columns:
        raise RuntimeError(
            "Requirements schema failure:\n"
            + json.dumps(
                {
                    "missing_source_columns": missing_source_columns,
                    "missing_audit_columns": missing_audit_columns,
                },
                indent=2,
            )
        )

    source_target = source[source["credential_id"].isin(TARGETS)].copy()
    audit_target = audit[audit["credential_id"].isin(TARGETS)].copy()

    failures: list[str] = []

    source_ids = set(source_target["credential_id"])
    audit_ids = set(audit_target["credential_id"])
    expected_ids = set(TARGETS)

    if source_ids != expected_ids:
        failures.append(
            "Source master target IDs mismatch: "
            f"missing={sorted(expected_ids - source_ids)}, "
            f"unexpected={sorted(source_ids - expected_ids)}"
        )

    if audit_ids != expected_ids:
        failures.append(
            "Executable master target IDs mismatch: "
            f"missing={sorted(expected_ids - audit_ids)}, "
            f"unexpected={sorted(audit_ids - expected_ids)}"
        )

    if len(source_target) != SOURCE_EXPECTED_ROWS:
        failures.append(
            f"Source target rows expected {SOURCE_EXPECTED_ROWS}; "
            f"found {len(source_target)}"
        )

    if source_target["requirement_id"].duplicated().any():
        failures.append("Source target requirements contain duplicate requirement IDs")

    bad_rule_types = sorted(set(source_target["rule_type"]) - ALLOWED_RULE_TYPES)
    if bad_rule_types:
        failures.append(f"Unsupported source target rule types: {bad_rule_types}")

    source_totals = hours(source_target)
    source_mismatches = {
        credential_id: {
            "expected": expected,
            "actual": source_totals.get(credential_id),
        }
        for credential_id, expected in TARGETS.items()
        if float(source_totals.get(credential_id, -1)) != float(expected)
    }
    if source_mismatches:
        failures.append(
            "Source auditable-hour mismatches: "
            + json.dumps(source_mismatches, indent=2)
        )

    source_requirement_ids = set(source_target["requirement_id"])
    audit_requirement_ids = set(audit_target["requirement_id"])
    missing_executable_requirements = sorted(
        source_requirement_ids - audit_requirement_ids
    )
    if missing_executable_requirements:
        failures.append(
            "Source requirements missing from executable master: "
            + json.dumps(missing_executable_requirements[:50], indent=2)
        )

    exact_target_duplicates = audit_target.duplicated(keep=False)
    if exact_target_duplicates.any():
        failures.append(
            f"Executable target contains "
            f"{int(exact_target_duplicates.sum())} exact duplicate rows"
        )

    if failures:
        print("=" * 118)
        print("HEALTH CREDENTIAL PREFLIGHT: FAIL")
        print("=" * 118)
        for failure in failures:
            print(f"\n- {failure}")
        print(
            "\nDo not start the full audit. Run "
            "`python .\\scripts\\rebuild_catalog_requirements_pipeline.py`."
        )
        return 2

    print("=" * 118)
    print("HEALTH CREDENTIAL PREFLIGHT: PASS")
    print("=" * 118)
    print(f"Recovered credential-years:          {len(TARGETS)}")
    print(f"Recovered source requirements:       {len(source_target)}")
    print(f"Recovered executable rows:           {len(audit_target)}")
    print(f"Source requirements represented:     {len(source_requirement_ids)}")
    print("Auditable totals:                    PASS")
    print("Duplicate target requirement IDs:    0")
    print("Exact duplicate target options:      0")
    print("Full audit may proceed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("=" * 118)
        print("HEALTH CREDENTIAL PREFLIGHT: ERROR")
        print("=" * 118)
        print(exc)
        raise SystemExit(2)
