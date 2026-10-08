#!/usr/bin/env python
"""
Build the isolated LSCO 2026-2027 staged source master.

This script DOES NOT modify the production multicatalog master.

It assembles:
- surviving generic 2026-2027 requirements
- controlled Electromechanical recovery
- controlled Logistics Management (Maritime) recovery
- controlled 2026-2027 Nursing recovery

Output:
    data/processed/catalogs/staging_2026/
    requirements_master_2026_staged.csv

Expected final shape:
- 1,648 requirement rows
- 139 credentials
- 22 production-master columns
- 0 blank requirement IDs
- 0 duplicate requirement IDs
- 0 missing credit hours
- 0 blank rule types
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pandas as pd


YEAR = "2026-2027"

REPLACED_GENERIC_CREDENTIALS = {
    "ELECTROMECHANICAL_TECHNOLOGY_2026",
}

PRODUCTION_MASTER_PATH = Path(
    "data/processed/catalogs/requirements_master_multicatalog.csv"
)

GENERIC_REQUIREMENTS_PATH = Path(
    "data/processed/catalogs/2026-2027/"
    "requirements_docx_draft.csv"
)

GENERIC_TOTALS_PATH = Path(
    "data/processed/catalogs/2026-2027/"
    "requirement_totals_docx_draft.csv"
)

ELECTROMECHANICAL_OVERLAY_PATH = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "electromechanical_requirements_overlay.csv"
)

LOGISTICS_OVERLAY_PATH = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_requirements_overlay.csv"
)

NURSING_OVERLAY_PATH = Path(
    "data/processed/catalogs/missing_health_credentials_overlay/"
    "missing_health_requirements_overlay.csv"
)

MASTER_BUILDER_PATH = Path(
    "scripts/build_multicatalog_requirements_master.py"
)

VALIDATOR_PATH = Path(
    "scripts/validate_docx_requirement_totals.py"
)

OUTPUT_PATH = Path(
    "data/processed/catalogs/staging_2026/"
    "requirements_master_2026_staged.csv"
)

EXPECTED_ROWS = 1648
EXPECTED_CREDENTIALS = 139
EXPECTED_MASTER_COLUMNS = 22

EXPECTED_CONTROLLED_IDS = {
    "ELECTROMECHANICAL_TECHNOLOGY_2026",
    "ELECTROMECHANICAL_TECHNOLOGY_AAS_2026",
    "LOGISTICS_MANAGEMENT_MARITIME_AAS_2026",
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2026",
    "REGISTERED_NURSING_TRANSITION_2026",
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2026",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path) -> None:
    if not path.exists():
        fail(f"Required file not found: {path}")


def to_int(value) -> int | None:
    value = str(value).strip()

    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def load_master_builder():
    spec = importlib.util.spec_from_file_location(
        "master_builder_2026_staging",
        MASTER_BUILDER_PATH,
    )

    if spec is None or spec.loader is None:
        fail(
            f"Cannot load master builder: "
            f"{MASTER_BUILDER_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def load_validator_classifier():
    source = VALIDATOR_PATH.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(source)

    wanted = {
        "_is_blank",
        "_as_float",
        "classify_validation_row",
    }

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]

    found = {
        node.name
        for node in nodes
    }

    if found != wanted:
        fail(
            "Could not isolate validator functions. "
            f"Expected {sorted(wanted)}, "
            f"found {sorted(found)}"
        )

    namespace = {}

    exec(
        compile(
            ast.Module(
                body=nodes,
                type_ignores=[],
            ),
            str(VALIDATOR_PATH),
            "exec",
        ),
        namespace,
    )

    return namespace["classify_validation_row"]


def transform_draft(
    df: pd.DataFrame,
    source_file: Path,
    builder,
) -> pd.DataFrame:
    missing = [
        column
        for column in builder.REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        fail(
            f"{source_file} missing draft fields: "
            f"{missing}"
        )

    out = df[
        builder.REQUIRED_COLUMNS
    ].copy()

    out["source_file"] = str(source_file)

    for column in [
        "catalog_year",
        "credential_id",
        "credential_title",
        "semester_label",
        "raw_requirement_text",
        "raw_credit_hours_text",
        "rule_type",
        "course_codes",
        "issue_flags",
        "source_file",
    ]:
        out[column] = out[column].apply(
            builder.normalize_text
        )

    out["original_rule_type"] = out["rule_type"]

    out["rule_type"] = out.apply(
        builder.normalize_rule_type,
        axis=1,
    )

    out["correction_note"] = ""

    out = builder.apply_documented_corrections(
        out
    )

    out["credit_hours"] = pd.to_numeric(
        out["credit_hours"],
        errors="coerce",
    )

    out["requirement_id"] = out.apply(
        builder.build_requirement_id,
        axis=1,
    )

    out["catalog_year_start"] = (
        out["catalog_year"]
        .str.slice(0, 4)
    )

    out["credential_family"] = (
        out["credential_id"]
        .str.replace(
            r"_[0-9]{4}$",
            "",
            regex=True,
        )
        .str.strip()
    )

    return out


def build_generic_validation(
    requirements: pd.DataFrame,
    totals: pd.DataFrame,
    classify,
) -> pd.DataFrame:
    semester_totals = {}
    program_totals = {}

    for _, row in totals.iterrows():
        key = (
            row["catalog_year"],
            row["credential_id"],
            row["credential_title"],
        )

        semester_key = key + (
            row["semester_label"],
        )

        semester_hours = to_int(
            row.get("semester_hours", "")
        )

        program_hours = to_int(
            row.get("total_program_hours", "")
        )

        if semester_hours is not None:
            semester_totals[
                semester_key
            ] = semester_hours

        if program_hours is not None:
            program_totals[
                key
            ] = program_hours

    rows = []

    for key, group in requirements.groupby(
        [
            "catalog_year",
            "credential_id",
            "credential_title",
            "semester_label",
        ],
        sort=True,
        dropna=False,
    ):
        parsed = sum(
            to_int(value) or 0
            for value in group["credit_hours"]
        )

        expected = semester_totals.get(
            tuple(key)
        )

        if expected is None:
            status = "NO_SEMESTER_TOTAL"
            delta = ""
        else:
            delta = str(
                parsed - expected
            )

            status = (
                "OK"
                if parsed == expected
                else "SEMESTER_TOTAL_MISMATCH"
            )

        row = {
            "validation_level": "SEMESTER",
            "catalog_year": key[0],
            "credential_id": key[1],
            "credential_title": key[2],
            "semester_label": key[3],
            "parsed_hours": str(parsed),
            "expected_hours": (
                ""
                if expected is None
                else str(expected)
            ),
            "delta": delta,
            "status": status,
        }

        classified_status, note = classify(
            row
        )

        row[
            "classified_status"
        ] = classified_status

        row[
            "validation_note"
        ] = note

        rows.append(row)

    for key, group in requirements.groupby(
        [
            "catalog_year",
            "credential_id",
            "credential_title",
        ],
        sort=True,
        dropna=False,
    ):
        parsed = sum(
            to_int(value) or 0
            for value in group["credit_hours"]
        )

        expected = program_totals.get(
            tuple(key)
        )

        if expected is None:
            status = "NO_PROGRAM_TOTAL"
            delta = ""
        else:
            delta = str(
                parsed - expected
            )

            status = (
                "OK"
                if parsed == expected
                else "PROGRAM_TOTAL_MISMATCH"
            )

        row = {
            "validation_level": "PROGRAM",
            "catalog_year": key[0],
            "credential_id": key[1],
            "credential_title": key[2],
            "semester_label": "",
            "parsed_hours": str(parsed),
            "expected_hours": (
                ""
                if expected is None
                else str(expected)
            ),
            "delta": delta,
            "status": status,
        }

        classified_status, note = classify(
            row
        )

        row[
            "classified_status"
        ] = classified_status

        row[
            "validation_note"
        ] = note

        rows.append(row)

    validation = pd.DataFrame(rows)

    validation = validation[
        ~validation[
            "credential_id"
        ].isin(
            REPLACED_GENERIC_CREDENTIALS
        )
    ].copy()

    unresolved = validation[
        ~validation[
            "classified_status"
        ]
        .astype(str)
        .str.startswith(
            "OK",
            na=False,
        )
    ].copy()

    if not unresolved.empty:
        fail(
            "Surviving generic validation "
            "contains unresolved rows:\n"
            + unresolved.to_string(
                index=False
            )
        )

    return validation


def summarize_validation(
    validation: pd.DataFrame,
) -> pd.DataFrame:
    return (
        validation
        .groupby(
            [
                "catalog_year",
                "credential_id",
            ],
            dropna=False,
        )
        .agg(
            validation_rows=(
                "classified_status",
                "size",
            ),
            validation_statuses=(
                "classified_status",
                lambda values: ";".join(
                    sorted(
                        set(
                            map(
                                str,
                                values,
                            )
                        )
                    )
                ),
            ),
            validation_notes=(
                "validation_note",
                lambda values: " | ".join(
                    sorted(
                        set(
                            map(
                                str,
                                values,
                            )
                        )
                    )
                ),
            ),
        )
        .reset_index()
    )


def align_master_schema(
    df: pd.DataFrame,
    master_columns: list[str],
) -> pd.DataFrame:
    out = df.copy()

    for column in master_columns:
        if column not in out.columns:
            out[column] = ""

    return out[
        master_columns
    ]


def main() -> None:
    required_files = [
        PRODUCTION_MASTER_PATH,
        GENERIC_REQUIREMENTS_PATH,
        GENERIC_TOTALS_PATH,
        ELECTROMECHANICAL_OVERLAY_PATH,
        LOGISTICS_OVERLAY_PATH,
        NURSING_OVERLAY_PATH,
        MASTER_BUILDER_PATH,
        VALIDATOR_PATH,
    ]

    for path in required_files:
        require_file(path)

    if (
        OUTPUT_PATH.resolve()
        == PRODUCTION_MASTER_PATH.resolve()
    ):
        fail(
            "Output path resolves to production "
            "master path."
        )

    master_columns = list(
        pd.read_csv(
            PRODUCTION_MASTER_PATH,
            nrows=0,
        ).columns
    )

    if len(master_columns) != EXPECTED_MASTER_COLUMNS:
        fail(
            "Unexpected production master schema: "
            f"{len(master_columns)} columns; "
            f"expected {EXPECTED_MASTER_COLUMNS}"
        )

    builder = load_master_builder()
    classify = load_validator_classifier()

    generic_raw = pd.read_csv(
        GENERIC_REQUIREMENTS_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    totals = pd.read_csv(
        GENERIC_TOTALS_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if set(
        generic_raw["catalog_year"]
    ) != {YEAR}:
        fail(
            "Generic source contains unexpected "
            "catalog years."
        )

    validation = build_generic_validation(
        generic_raw,
        totals,
        classify,
    )

    validation_summary = (
        summarize_validation(
            validation
        )
    )

    generic_surviving_raw = generic_raw[
        ~generic_raw[
            "credential_id"
        ].isin(
            REPLACED_GENERIC_CREDENTIALS
        )
    ].copy()

    generic = transform_draft(
        generic_surviving_raw,
        GENERIC_REQUIREMENTS_PATH,
        builder,
    )

    generic = generic.merge(
        validation_summary,
        on=[
            "catalog_year",
            "credential_id",
        ],
        how="left",
    )

    electromechanical_raw = pd.read_csv(
        ELECTROMECHANICAL_OVERLAY_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    electromechanical = transform_draft(
        electromechanical_raw,
        ELECTROMECHANICAL_OVERLAY_PATH,
        builder,
    )

    electromechanical[
        "validation_rows"
    ] = ""

    electromechanical[
        "validation_statuses"
    ] = ""

    electromechanical[
        "validation_notes"
    ] = ""

    controlled_master_frames = []

    for path in [
        LOGISTICS_OVERLAY_PATH,
        NURSING_OVERLAY_PATH,
    ]:
        frame = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        )

        frame = frame[
            frame["catalog_year"].eq(
                YEAR
            )
        ].copy()

        frame = align_master_schema(
            frame,
            master_columns,
        )

        controlled_master_frames.append(
            frame
        )

    controlled_master = pd.concat(
        controlled_master_frames,
        ignore_index=True,
    )

    for column in [
        "validation_rows",
        "validation_statuses",
        "validation_notes",
    ]:
        populated = (
            controlled_master[column]
            .astype(str)
            .str.strip()
            .ne("")
        )

        if populated.any():
            fail(
                "Controlled master-schema "
                f"overlay has populated {column}."
            )

    generic = align_master_schema(
        generic,
        master_columns,
    )

    electromechanical = (
        align_master_schema(
            electromechanical,
            master_columns,
        )
    )

    staged = pd.concat(
        [
            generic,
            electromechanical,
            controlled_master,
        ],
        ignore_index=True,
    )

    if len(staged) != EXPECTED_ROWS:
        fail(
            f"Staged row count is {len(staged)}; "
            f"expected {EXPECTED_ROWS}"
        )

    credential_count = (
        staged["credential_id"]
        .nunique()
    )

    if credential_count != EXPECTED_CREDENTIALS:
        fail(
            f"Staged credential count is "
            f"{credential_count}; "
            f"expected {EXPECTED_CREDENTIALS}"
        )

    if len(staged.columns) != EXPECTED_MASTER_COLUMNS:
        fail(
            f"Staged schema has "
            f"{len(staged.columns)} columns; "
            f"expected {EXPECTED_MASTER_COLUMNS}"
        )

    blank_ids = (
        staged["requirement_id"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_ids:
        fail(
            f"Blank requirement IDs: "
            f"{blank_ids}"
        )

    duplicate_ids = (
        staged["requirement_id"]
        .duplicated()
        .sum()
    )

    if duplicate_ids:
        fail(
            f"Duplicate requirement IDs: "
            f"{duplicate_ids}"
        )

    missing_hours = (
        pd.to_numeric(
            staged["credit_hours"],
            errors="coerce",
        )
        .isna()
        .sum()
    )

    if missing_hours:
        fail(
            f"Missing credit hours: "
            f"{missing_hours}"
        )

    blank_rule_types = (
        staged["rule_type"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank_rule_types:
        fail(
            f"Blank rule types: "
            f"{blank_rule_types}"
        )

    controlled_ids = set(
        electromechanical[
            "credential_id"
        ]
    ) | set(
        controlled_master[
            "credential_id"
        ]
    )

    if controlled_ids != EXPECTED_CONTROLLED_IDS:
        fail(
            "Controlled credential set mismatch.\n"
            f"Expected: "
            f"{sorted(EXPECTED_CONTROLLED_IDS)}\n"
            f"Actual: "
            f"{sorted(controlled_ids)}"
        )

    if (
        staged["catalog_year"]
        .astype(str)
        .ne(YEAR)
        .any()
    ):
        fail(
            "Staged output contains catalog "
            "years other than 2026-2027."
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    staged.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print(
        f"Wrote {len(staged):,} staged "
        f"requirement rows to:"
    )
    print(OUTPUT_PATH)

    print()
    print(
        "STAGED CREDENTIALS:",
        credential_count,
    )
    print(
        "MASTER COLUMNS:",
        len(staged.columns),
    )
    print(
        "BLANK REQUIREMENT IDS:",
        blank_ids,
    )
    print(
        "DUPLICATE REQUIREMENT IDS:",
        duplicate_ids,
    )
    print(
        "MISSING CREDIT HOURS:",
        missing_hours,
    )
    print(
        "BLANK RULE TYPES:",
        blank_rule_types,
    )

    print()
    print(
        "GENERIC CREDENTIALS:",
        generic[
            "credential_id"
        ].nunique(),
    )
    print(
        "ELECTROMECHANICAL CONTROLLED "
        "CREDENTIALS:",
        electromechanical[
            "credential_id"
        ].nunique(),
    )
    print(
        "MASTER-SCHEMA CONTROLLED "
        "CREDENTIALS:",
        controlled_master[
            "credential_id"
        ].nunique(),
    )

    print()
    print(
        "PRODUCTION MASTER MODIFIED: NO"
    )


if __name__ == "__main__":
    main()