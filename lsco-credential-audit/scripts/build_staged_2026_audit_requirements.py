#!/usr/bin/env python
"""
Build the isolated LSCO 2026-2027 executable requirements stage.

This script DOES NOT modify production requirements files.

Input:
    data/processed/catalogs/staging_2026/
    requirements_master_2026_staged.csv

Output:
    data/processed/catalogs/staging_2026/
    requirements_master_multiyear_2026_staged.csv

Expected output:
- 1,825 executable option rows
- 139 credential-years
- 0 blank requirement IDs
- 0 blank option values
- 0 duplicate option rows

The builder also validates the staged Logistics Management (Maritime)
semantic-policy linkage:
- alternative path membership = R16-R26
- compound requirement policy = R26 only
- elective runtime policy = R19 only
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


YEAR = "2026-2027"

SOURCE_PATH = Path(
    "data/processed/catalogs/staging_2026/"
    "requirements_master_2026_staged.csv"
)

OUTPUT_PATH = Path(
    "data/processed/catalogs/staging_2026/"
    "requirements_master_multiyear_2026_staged.csv"
)

PRODUCTION_OUTPUT_PATH = Path(
    "data/processed/catalogs/"
    "requirements_master_multiyear.csv"
)

EXECUTABLE_BUILDER_PATH = Path(
    "scripts/build_audit_requirements_multiyear.py"
)

PATH_POLICY_PATH = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_"
    "alternative_requirement_paths.csv"
)

COMPOUND_POLICY_PATH = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_"
    "compound_requirement_alternatives.csv"
)

ELECTIVE_POLICY_PATH = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_"
    "elective_runtime_overlay.csv"
)

LOGISTICS_CREDENTIAL = (
    "LOGISTICS_MANAGEMENT_MARITIME_AAS_2026"
)

EXPECTED_SOURCE_ROWS = 1648
EXPECTED_SOURCE_CREDENTIALS = 139

EXPECTED_EXECUTABLE_ROWS = 1825
EXPECTED_EXECUTABLE_CREDENTIALS = 139

EXPECTED_EXECUTABLE_COLUMNS = [
    "catalog_year",
    "credential_id",
    "credential_title",
    "requirement_id",
    "sequence",
    "rule_type",
    "min_required",
    "group_name",
    "credit_hours",
    "semester_label",
    "source_requirement_text",
    "option_type",
    "option_value",
]


def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path) -> None:
    if not path.exists():
        fail(f"Required file not found: {path}")


def load_executable_builder():
    spec = importlib.util.spec_from_file_location(
        "staged_2026_executable_builder",
        EXECUTABLE_BUILDER_PATH,
    )

    if spec is None or spec.loader is None:
        fail(
            "Cannot load executable requirements builder: "
            f"{EXECUTABLE_BUILDER_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_rows"):
        fail(
            "Executable requirements builder has no build_rows() function."
        )

    return module


def validate_source(source: pd.DataFrame) -> None:
    if len(source) != EXPECTED_SOURCE_ROWS:
        fail(
            f"Source row count is {len(source)}; "
            f"expected {EXPECTED_SOURCE_ROWS}"
        )

    credential_count = (
        source[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )

    if credential_count != EXPECTED_SOURCE_CREDENTIALS:
        fail(
            f"Source credential-year count is "
            f"{credential_count}; "
            f"expected {EXPECTED_SOURCE_CREDENTIALS}"
        )

    if (
        source["catalog_year"]
        .astype(str)
        .ne(YEAR)
        .any()
    ):
        fail(
            "Source contains catalog years other than "
            f"{YEAR}."
        )

    blank_requirement_ids = (
        source["requirement_id"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_requirement_ids:
        fail(
            "Source contains blank requirement IDs: "
            f"{blank_requirement_ids}"
        )

    duplicate_requirement_ids = (
        source["requirement_id"]
        .duplicated()
        .sum()
    )

    if duplicate_requirement_ids:
        fail(
            "Source contains duplicate requirement IDs: "
            f"{duplicate_requirement_ids}"
        )


def validate_executable(audit: pd.DataFrame) -> None:
    missing_columns = [
        column
        for column in EXPECTED_EXECUTABLE_COLUMNS
        if column not in audit.columns
    ]

    if missing_columns:
        fail(
            "Executable output missing columns: "
            f"{missing_columns}"
        )

    if len(audit) != EXPECTED_EXECUTABLE_ROWS:
        fail(
            f"Executable row count is {len(audit)}; "
            f"expected {EXPECTED_EXECUTABLE_ROWS}"
        )

    credential_count = (
        audit[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )

    if credential_count != EXPECTED_EXECUTABLE_CREDENTIALS:
        fail(
            "Executable credential-year count is "
            f"{credential_count}; "
            f"expected {EXPECTED_EXECUTABLE_CREDENTIALS}"
        )

    if (
        audit["catalog_year"]
        .astype(str)
        .ne(YEAR)
        .any()
    ):
        fail(
            "Executable output contains catalog years "
            f"other than {YEAR}."
        )

    blank_requirement_ids = (
        audit["requirement_id"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_requirement_ids:
        fail(
            "Executable output contains blank "
            "requirement IDs: "
            f"{blank_requirement_ids}"
        )

    blank_option_values = (
        audit["option_value"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_option_values:
        fail(
            "Executable output contains blank "
            "option values: "
            f"{blank_option_values}"
        )

    duplicate_options = audit.duplicated(
        subset=[
            "catalog_year",
            "credential_id",
            "requirement_id",
            "option_type",
            "option_value",
        ]
    ).sum()

    if duplicate_options:
        fail(
            "Executable output contains duplicate "
            f"option rows: {duplicate_options}"
        )

    missing_hours = (
        pd.to_numeric(
            audit["credit_hours"],
            errors="coerce",
        )
        .isna()
        .sum()
    )

    if missing_hours:
        fail(
            "Executable output contains missing "
            f"credit hours: {missing_hours}"
        )

    blank_rule_types = (
        audit["rule_type"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_rule_types:
        fail(
            "Executable output contains blank "
            f"rule types: {blank_rule_types}"
        )

    blank_option_types = (
        audit["option_type"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_option_types:
        fail(
            "Executable output contains blank "
            f"option types: {blank_option_types}"
        )


def validate_logistics_policies(
    audit: pd.DataFrame,
) -> None:
    logistics = audit[
        audit["credential_id"].eq(
            LOGISTICS_CREDENTIAL
        )
    ].copy()

    if logistics.empty:
        fail(
            "Logistics Management (Maritime) "
            "credential is absent from executable output."
        )

    executable_ids = set(
        logistics["requirement_id"]
        .astype(str)
        .str.strip()
    )

    path_policy = pd.read_csv(
        PATH_POLICY_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    compound_policy = pd.read_csv(
        COMPOUND_POLICY_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    elective_policy = pd.read_csv(
        ELECTIVE_POLICY_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    for label, frame in [
        ("PATH", path_policy),
        ("COMPOUND", compound_policy),
        ("ELECTIVE", elective_policy),
    ]:
        if "requirement_id" not in frame.columns:
            fail(
                f"{label} policy has no requirement_id column."
            )

        policy_ids = set(
            frame["requirement_id"]
            .astype(str)
            .str.strip()
        )

        if "" in policy_ids:
            fail(
                f"{label} policy contains blank requirement_id."
            )

        dangling = sorted(
            policy_ids - executable_ids
        )

        if dangling:
            fail(
                f"{label} policy contains dangling "
                f"requirement IDs: {dangling}"
            )

    expected_path_ids = {
        f"{LOGISTICS_CREDENTIAL}_R{i}"
        for i in range(16, 27)
    }

    actual_path_ids = set(
        path_policy["requirement_id"]
        .astype(str)
        .str.strip()
    )

    if actual_path_ids != expected_path_ids:
        fail(
            "Logistics alternative-path membership "
            "is not exactly R16-R26."
        )

    compound_ids = set(
        compound_policy["requirement_id"]
        .astype(str)
        .str.strip()
    )

    if compound_ids != {
        f"{LOGISTICS_CREDENTIAL}_R26"
    }:
        fail(
            "Logistics compound policy is not "
            "isolated to R26."
        )

    elective_ids = set(
        elective_policy["requirement_id"]
        .astype(str)
        .str.strip()
    )

    if elective_ids != {
        f"{LOGISTICS_CREDENTIAL}_R19"
    }:
        fail(
            "Logistics elective policy is not "
            "isolated to R19."
        )

    if len(path_policy) != 11:
        fail(
            "Logistics alternative-path policy row "
            f"count is {len(path_policy)}; expected 11."
        )

    if len(compound_policy) != 7:
        fail(
            "Logistics compound policy row count is "
            f"{len(compound_policy)}; expected 7."
        )

    if len(elective_policy) != 1:
        fail(
            "Logistics elective policy row count is "
            f"{len(elective_policy)}; expected 1."
        )


def main() -> None:
    for path in [
        SOURCE_PATH,
        EXECUTABLE_BUILDER_PATH,
        PATH_POLICY_PATH,
        COMPOUND_POLICY_PATH,
        ELECTIVE_POLICY_PATH,
    ]:
        require_file(path)

    if (
        OUTPUT_PATH.resolve()
        == PRODUCTION_OUTPUT_PATH.resolve()
    ):
        fail(
            "Staging output resolves to production "
            "requirements_master_multiyear.csv."
        )

    source = pd.read_csv(
        SOURCE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    validate_source(source)

    builder = load_executable_builder()

    rows = builder.build_rows(
        source
    )

    audit = pd.DataFrame(rows)

    validate_executable(audit)

    validate_logistics_policies(
        audit
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    duplicate_options = audit.duplicated(
        subset=[
            "catalog_year",
            "credential_id",
            "requirement_id",
            "option_type",
            "option_value",
        ]
    ).sum()

    print(
        f"Wrote {len(audit):,} staged executable "
        "option rows to:"
    )
    print(OUTPUT_PATH)

    print()
    print(
        "CREDENTIAL-YEARS:",
        audit[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .shape[0],
    )
    print(
        "BLANK REQUIREMENT IDS:",
        audit["requirement_id"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum(),
    )
    print(
        "BLANK OPTION VALUES:",
        audit["option_value"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum(),
    )
    print(
        "DUPLICATE OPTION ROWS:",
        duplicate_options,
    )

    print()
    print("RULE TYPES:")
    print(
        audit["rule_type"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print("OPTION TYPES:")
    print(
        audit["option_type"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        "PASS: Logistics Management (Maritime) "
        "path policy resolves to R16-R26"
    )
    print(
        "PASS: Logistics Management (Maritime) "
        "compound policy is isolated to R26"
    )
    print(
        "PASS: Logistics Management (Maritime) "
        "elective policy is isolated to R19"
    )

    print()
    print(
        "PRODUCTION EXECUTABLE MASTER MODIFIED: NO"
    )


if __name__ == "__main__":
    main()