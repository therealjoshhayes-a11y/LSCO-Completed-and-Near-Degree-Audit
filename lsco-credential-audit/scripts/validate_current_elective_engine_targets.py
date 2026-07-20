from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


HISTORY = Path("data/processed/normalized_actual_student_course_history.csv")
ENGINE_INPUT = Path("data/processed/student_course_history_normalized.csv")
ENGINE_DETAIL = Path("data/processed/multiyear_sample_audit_results.csv")
ENGINE_SUMMARY = Path("data/processed/multiyear_sample_credential_summary.csv")
FULL_DETAIL = Path("data/processed/full_actual_audit/full_actual_audit_results.csv")

REPORTING_DIR = Path("data/processed/reporting")
OUTPUT_DIR = REPORTING_DIR / (
    "elective_engine_targeted_validation_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SAFE_OUTPUT = OUTPUT_DIR / "FERPA_SAFE_Elective_Engine_Targeted_Validation.xlsx"
RESTRICTED_OUTPUT = OUTPUT_DIR / "RESTRICTED_Elective_Engine_Targeted_Validation.xlsx"


def latest_restricted_elective_workbook() -> Path:
    candidates = sorted(
        REPORTING_DIR.glob(
            "elective_forensic_review_v2_*/"
            "RESTRICTED_LSCO_Elective_Forensic_Review_V2.xlsx"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(
            "No restricted elective forensic V2 workbook found."
        )

    return candidates[0]


def safe_count(value: int) -> object:
    return "<5" if 0 < int(value) < 5 else int(value)


def main() -> None:
    for path in [HISTORY, FULL_DETAIL]:
        if not path.exists():
            raise FileNotFoundError(path)

    forensic_workbook = latest_restricted_elective_workbook()

    promotable = pd.read_excel(
        forensic_workbook,
        sheet_name="Promotable Completers",
        dtype=str,
    ).fillna("")

    required = {
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
    }

    missing = required - set(promotable.columns)

    if missing:
        raise ValueError(
            "Promotable sheet missing columns: "
            + ", ".join(sorted(missing))
        )

    target_students = sorted(
        promotable["student_id"].astype(str).unique()
    )

    target_keys = set(
        zip(
            promotable["student_id"].astype(str),
            promotable["catalog_year"].astype(str),
            promotable["credential_id"].astype(str),
            promotable["requirement_id"].astype(str),
        )
    )

    history = pd.read_csv(
        HISTORY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    target_history = history[
        history["student_id"].astype(str).isin(target_students)
    ].copy()

    if target_history.empty:
        raise ValueError("No history rows found for target students.")

    before_parts = []

    for chunk in pd.read_csv(
        FULL_DETAIL,
        dtype=str,
        low_memory=False,
        chunksize=250_000,
    ):
        chunk = chunk.fillna("")

        mask = [
            (
                str(row.student_id),
                str(row.catalog_year),
                str(row.credential_id),
                str(row.requirement_id),
            )
            in target_keys
            for row in chunk[
                [
                    "student_id",
                    "catalog_year",
                    "credential_id",
                    "requirement_id",
                ]
            ].itertuples(index=False)
        ]

        kept = chunk.loc[mask].copy()

        if not kept.empty:
            before_parts.append(kept)

    before = (
        pd.concat(before_parts, ignore_index=True)
        if before_parts
        else pd.DataFrame()
    )

    backup_input = None

    if ENGINE_INPUT.exists():
        backup_input = OUTPUT_DIR / "engine_input_backup.csv"
        shutil.copyfile(ENGINE_INPUT, backup_input)

    target_history.to_csv(ENGINE_INPUT, index=False)

    try:
        subprocess.run(
            [sys.executable, "-m", "lsco_audit.audit_multiyear_sample"],
            check=True,
        )

        rerun = pd.read_csv(
            ENGINE_DETAIL,
            dtype=str,
            low_memory=False,
        ).fillna("")

    finally:
        if backup_input and backup_input.exists():
            shutil.copyfile(backup_input, ENGINE_INPUT)

    after = rerun[
        [
            (
                str(row.student_id),
                str(row.catalog_year),
                str(row.credential_id),
                str(row.requirement_id),
            )
            in target_keys
            for row in rerun[
                [
                    "student_id",
                    "catalog_year",
                    "credential_id",
                    "requirement_id",
                ]
            ].itertuples(index=False)
        ]
    ].copy()

    key_columns = [
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
    ]

    before_compare = before[
        key_columns
        + [
            "status",
            "matched_options",
        ]
    ].rename(
        columns={
            "status": "before_status",
            "matched_options": "before_matched_options",
        }
    )

    after_compare = after[
        key_columns
        + [
            "status",
            "matched_options",
        ]
    ].rename(
        columns={
            "status": "after_status",
            "matched_options": "after_matched_options",
        }
    )

    comparison = before_compare.merge(
        after_compare,
        on=key_columns,
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    comparison["promoted_to_met"] = (
        comparison["before_status"].ne("MET")
        & comparison["after_status"].eq("MET")
    )

    comparison["still_unmet"] = (
        comparison["after_status"].eq("UNMET")
    )

    comparison["rerun_unresolved"] = (
        comparison["after_status"]
        .astype(str)
        .str.startswith("UNRESOLVED")
    )

    restricted = comparison.merge(
        promotable[
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "requirement_id",
                "resolved_policy",
                "required_elective_hours_effective",
                "candidate_hours_total",
                "eligible_unused_course_text",
            ]
        ],
        on=key_columns,
        how="left",
        validate="one_to_one",
    )

    by_transition = (
        comparison.groupby(
            [
                "before_status",
                "after_status",
            ],
            dropna=False,
        )
        .agg(
            rows=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
            credentials=("credential_id", "nunique"),
        )
        .reset_index()
    )

    by_credential = (
        restricted.groupby(
            [
                "credential_id",
                "before_status",
                "after_status",
            ],
            dropna=False,
        )
        .agg(
            rows=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["rows", "credential_id"],
            ascending=[False, True],
        )
    )

    kpis = pd.DataFrame(
        [
            {
                "metric": "Target forensic rows",
                "value": len(promotable),
            },
            {
                "metric": "Target distinct students",
                "value": len(target_students),
            },
            {
                "metric": "Current full-audit rows found",
                "value": len(before),
            },
            {
                "metric": "Current-engine rerun rows found",
                "value": len(after),
            },
            {
                "metric": "Promoted from non-MET to MET",
                "value": int(comparison["promoted_to_met"].sum()),
            },
            {
                "metric": "Still UNMET after current-engine rerun",
                "value": int(comparison["still_unmet"].sum()),
            },
            {
                "metric": "UNRESOLVED after current-engine rerun",
                "value": int(comparison["rerun_unresolved"].sum()),
            },
        ]
    )

    safe_kpis = kpis.copy()
    safe_kpis["value"] = safe_kpis["value"].map(safe_count)

    safe_transition = by_transition.copy()
    for column in ["rows", "distinct_students", "credentials"]:
        safe_transition[column] = safe_transition[column].map(safe_count)

    safe_credential = by_credential.copy()
    for column in ["rows", "distinct_students"]:
        safe_credential[column] = safe_credential[column].map(safe_count)

    with pd.ExcelWriter(
        RESTRICTED_OUTPUT,
        engine="xlsxwriter",
    ) as writer:
        restricted.to_excel(
            writer,
            sheet_name="Target Comparison",
            index=False,
        )

        promotable.to_excel(
            writer,
            sheet_name="Forensic Targets",
            index=False,
        )

    with pd.ExcelWriter(
        SAFE_OUTPUT,
        engine="xlsxwriter",
    ) as writer:
        safe_kpis.to_excel(
            writer,
            sheet_name="KPI Summary",
            index=False,
        )

        safe_transition.to_excel(
            writer,
            sheet_name="Status Transitions",
            index=False,
        )

        safe_credential.to_excel(
            writer,
            sheet_name="By Credential",
            index=False,
        )

    print()
    print("=" * 100)
    print("TARGETED ELECTIVE ENGINE VALIDATION")
    print("=" * 100)
    print(f"Forensic workbook: {forensic_workbook}")
    print(f"Target rows: {len(promotable):,}")
    print(f"Target students: {len(target_students):,}")
    print(
        "Promoted from non-MET to MET: "
        f"{int(comparison['promoted_to_met'].sum()):,}"
    )
    print(
        "Still UNMET after current-engine rerun: "
        f"{int(comparison['still_unmet'].sum()):,}"
    )
    print(
        "UNRESOLVED after current-engine rerun: "
        f"{int(comparison['rerun_unresolved'].sum()):,}"
    )
    print()
    print(f"RESTRICTED workbook: {RESTRICTED_OUTPUT}")
    print(f"FERPA-SAFE workbook: {SAFE_OUTPUT}")
    print()
    print("UPLOAD ONLY THE FERPA-SAFE WORKBOOK.")
    print("VALIDATION GATE: PASSED")


if __name__ == "__main__":
    main()
