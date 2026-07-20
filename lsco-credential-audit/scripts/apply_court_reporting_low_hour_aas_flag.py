from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd


SUMMARY = Path(
    "data/processed/full_actual_audit/"
    "full_actual_credential_summary.csv"
)

VALIDATION = Path(
    "data/interim/catalogs/"
    "requirement_total_validation.csv"
)

EXCEPTION_REGISTRY = Path(
    "config/catalog_source_exceptions.csv"
)

TARGETS = {
    "COURT_REPORTING_AAS_2022",
    "COURT_REPORTING_AAS_2023",
    "COURT_REPORTING_AAS_2024",
}

FLAG = "LOW_HOUR_AAS_CATALOG_FLAG"

NOTE = (
    "Official catalog lists a 60-SCH program total, but the "
    "published required courses total 56 SCH. Completion is "
    "based on satisfaction of all published course requirements."
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def backup(path: Path) -> Path:
    target = path.with_suffix(
        path.suffix + f".before_low_hour_aas_fix_{STAMP}.bak"
    )
    shutil.copy2(path, target)
    return target


def update_summary() -> tuple[int, Path]:
    if not SUMMARY.exists():
        raise FileNotFoundError(SUMMARY)

    frame = pd.read_csv(
        SUMMARY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    for column in (
        "catalog_exception_flag",
        "catalog_exception_note",
    ):
        if column not in frame.columns:
            frame[column] = ""

    mask = frame["credential_id"].isin(TARGETS)
    affected = int(mask.sum())

    if affected == 0:
        raise RuntimeError(
            "No Court Reporting AAS rows found in summary."
        )

    summary_backup = backup(SUMMARY)

    frame.loc[mask, "catalog_exception_flag"] = FLAG
    frame.loc[mask, "catalog_exception_note"] = NOTE

    frame.to_csv(SUMMARY, index=False)

    return affected, summary_backup


def update_validation() -> tuple[int, Path]:
    if not VALIDATION.exists():
        raise FileNotFoundError(VALIDATION)

    frame = pd.read_csv(
        VALIDATION,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required = {
        "validation_level",
        "credential_id",
        "parsed_hours",
        "expected_hours",
        "delta",
        "status",
        "classified_status",
        "validation_note",
    }

    missing = required - set(frame.columns)

    if missing:
        raise RuntimeError(
            "Validation file missing columns: "
            + ", ".join(sorted(missing))
        )

    mask = (
        frame["validation_level"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("PROGRAM")
        & frame["credential_id"].isin(TARGETS)
    )

    affected = int(mask.sum())

    if affected != 3:
        raise RuntimeError(
            f"Expected 3 program rows; found {affected}."
        )

    validation_backup = backup(VALIDATION)

    frame.loc[mask, "parsed_hours"] = "56"
    frame.loc[mask, "expected_hours"] = "60"
    frame.loc[mask, "delta"] = "-4"
    frame.loc[mask, "status"] = "MISMATCH"
    frame.loc[
        mask,
        "classified_status",
    ] = "OK_OFFICIAL_LOW_HOUR_AAS"
    frame.loc[mask, "validation_note"] = NOTE

    frame.to_csv(VALIDATION, index=False)

    return affected, validation_backup


def update_registry() -> Path | None:
    EXCEPTION_REGISTRY.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry_backup = None

    if EXCEPTION_REGISTRY.exists():
        frame = pd.read_csv(
            EXCEPTION_REGISTRY,
            dtype=str,
            low_memory=False,
        ).fillna("")
        registry_backup = backup(EXCEPTION_REGISTRY)
    else:
        frame = pd.DataFrame(
            columns=[
                "credential_id",
                "catalog_exception_flag",
                "catalog_exception_note",
                "published_program_hours",
                "executable_requirement_hours",
                "resolution_policy",
            ]
        )

    for column in (
        "credential_id",
        "catalog_exception_flag",
        "catalog_exception_note",
        "published_program_hours",
        "executable_requirement_hours",
        "resolution_policy",
    ):
        if column not in frame.columns:
            frame[column] = ""

    frame = frame[
        ~frame["credential_id"].isin(TARGETS)
    ].copy()

    additions = pd.DataFrame(
        [
            {
                "credential_id": credential_id,
                "catalog_exception_flag": FLAG,
                "catalog_exception_note": NOTE,
                "published_program_hours": "60",
                "executable_requirement_hours": "56",
                "resolution_policy": (
                    "Award completion when all published course "
                    "requirements are satisfied. Do not add or "
                    "infer an unpublished requirement."
                ),
            }
            for credential_id in sorted(TARGETS)
        ]
    )

    frame = pd.concat(
        [frame, additions],
        ignore_index=True,
    ).sort_values(
        "credential_id",
        kind="mergesort",
    )

    frame.to_csv(EXCEPTION_REGISTRY, index=False)

    return registry_backup


def validate() -> None:
    summary = pd.read_csv(
        SUMMARY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    summary_rows = summary[
        summary["credential_id"].isin(TARGETS)
    ]

    if not summary_rows[
        "catalog_exception_flag"
    ].eq(FLAG).all():
        raise RuntimeError(
            "Summary flag validation failed."
        )

    validation = pd.read_csv(
        VALIDATION,
        dtype=str,
        low_memory=False,
    ).fillna("")

    rows = validation[
        validation["validation_level"]
        .astype(str)
        .str.upper()
        .eq("PROGRAM")
        & validation["credential_id"].isin(TARGETS)
    ]

    if len(rows) != 3:
        raise RuntimeError(
            "Validation row-count check failed."
        )

    checks = {
        "parsed_hours": "56",
        "expected_hours": "60",
        "delta": "-4",
        "classified_status": "OK_OFFICIAL_LOW_HOUR_AAS",
    }

    for column, expected in checks.items():
        if not rows[column].eq(expected).all():
            raise RuntimeError(
                f"Validation check failed for {column}."
            )


def main() -> None:
    print("=" * 100)
    print("COURT REPORTING AAS — LOW-HOUR CATALOG EXCEPTION FIX")
    print("=" * 100)

    summary_count, summary_backup = update_summary()
    validation_count, validation_backup = update_validation()
    registry_backup = update_registry()
    validate()

    print(f"Audit-summary rows flagged: {summary_count:,}")
    print(f"Validation rows corrected: {validation_count:,}")
    print()
    print(f"Summary backup: {summary_backup}")
    print(f"Validation backup: {validation_backup}")
    if registry_backup is not None:
        print(f"Registry backup: {registry_backup}")
    print(f"Exception registry: {EXCEPTION_REGISTRY}")
    print()
    print("No course requirements were changed.")
    print("LOW-HOUR AAS EXCEPTION GATE: PASSED")


if __name__ == "__main__":
    main()
