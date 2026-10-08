from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    ROOT
    / "data/processed/reporting/"
      "additional_awards_revised_query_20260803"
)

SOURCE_DETAIL = (
    SOURCE_DIR / "04_final_additional_awards_student_detail.csv"
)

SOURCE_RECONCILED = (
    SOURCE_DIR / "01_all_selected_completions_reconciled.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data/processed/reporting/"
      "final_additional_award_numbers_20260803"
)

CJ_DETECTED = "CRIMINAL_JUSTICE_LAW_ENFORCEMENT"
CJ_PARENT = "CRIMINAL_JUSTICE_CERTIFICATE_OF_COMPLETION"


def write_csv(df: pd.DataFrame, filename: str) -> None:
    path = OUTPUT_DIR / filename
    df.to_csv(path, index=False)
    print(f"Wrote {len(df):,} rows: {path.relative_to(ROOT)}")


def main() -> None:
    print("=" * 100)
    print("FINAL ADDITIONAL-AWARD NUMBER PACKAGE")
    print("=" * 100)

    if not SOURCE_DETAIL.exists():
        raise FileNotFoundError(SOURCE_DETAIL)

    if not SOURCE_RECONCILED.exists():
        raise FileNotFoundError(SOURCE_RECONCILED)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    detail = pd.read_csv(
        SOURCE_DETAIL,
        dtype="string",
        low_memory=False,
    ).fillna("")

    reconciled = pd.read_csv(
        SOURCE_RECONCILED,
        dtype="string",
        low_memory=False,
    ).fillna("")

    detail["student_id"] = detail["student_id"].astype(str).str.strip()
    detail["detected_lineage"] = (
        detail["detected_lineage"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    reconciled["student_id"] = (
        reconciled["student_id"].astype(str).str.strip()
    )
    reconciled["detected_lineage"] = (
        reconciled["detected_lineage"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # ------------------------------------------------------------------
    # 1. Final Criminal Justice adjudication
    # ------------------------------------------------------------------

    cj_mask = detail["detected_lineage"].eq(CJ_DETECTED)

    detail.loc[
        cj_mask,
        "requires_relationship_review",
    ] = "False"

    detail.loc[
        cj_mask,
        "final_relationship_disposition",
    ] = "SEPARATE_STACKABLE_AWARD"

    detail.loc[
        ~cj_mask,
        "final_relationship_disposition",
    ] = np.where(
        detail.loc[
            ~cj_mask,
            "has_stackable_related_award",
        ].astype(str).str.upper().isin({"TRUE", "1", "YES"}),
        "SEPARATE_STACKABLE_AWARD",
        "NO_SPECIAL_RELATIONSHIP",
    )

    # ------------------------------------------------------------------
    # 2. Numeric completion term
    # ------------------------------------------------------------------

    detail["modeled_completion_term_numeric"] = pd.to_numeric(
        detail["modeled_completion_term_numeric"],
        errors="coerce",
    )

    if detail["modeled_completion_term_numeric"].isna().any():
        missing = detail.loc[
            detail["modeled_completion_term_numeric"].isna(),
            [
                "student_id",
                "detected_lineage",
                "catalog_year",
                "credential_id",
                "award_term_sort",
                "award_term_taken",
            ],
        ]

        write_csv(
            missing,
            "ERROR_missing_completion_term.csv",
        )

        raise RuntimeError(
            "Some final awards lack a usable modeled completion term."
        )

    # ------------------------------------------------------------------
    # 3. Mutually exclusive student classification
    # ------------------------------------------------------------------

    detail["had_lsco_award_before_completion_bool"] = (
        detail["had_lsco_award_before_completion"]
        .astype(str)
        .str.upper()
        .isin({"TRUE", "1", "YES"})
    )

    student_first_event = (
        detail.groupby(
            "student_id",
            as_index=False,
        )
        .agg(
            first_additional_completion_term=(
                "modeled_completion_term_numeric",
                "min",
            ),
            additional_award_count=(
                "detected_lineage",
                "size",
            ),
            distinct_additional_lineages=(
                "detected_lineage",
                "nunique",
            ),
        )
    )

    detail = detail.merge(
        student_first_event,
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    detail["is_student_earliest_additional_event"] = (
        detail["modeled_completion_term_numeric"]
        == detail["first_additional_completion_term"]
    )

    earliest_event = detail.loc[
        detail["is_student_earliest_additional_event"]
    ].copy()

    student_first_status = (
        earliest_event
        .groupby(
            "student_id",
            as_index=False,
        )
        .agg(
            had_prior_lsco_award_at_first_event=(
                "had_lsco_award_before_completion_bool",
                "max",
            ),
            first_event_completion_year=(
                "completion_academic_year",
                "min",
            ),
            first_event_additional_awards=(
                "detected_lineage",
                "size",
            ),
            first_event_lineages=(
                "detected_lineage",
                lambda values: " | ".join(
                    sorted(set(values.astype(str)))
                ),
            ),
        )
    )

    student_first_status["final_student_recipient_class"] = np.where(
        student_first_status[
            "had_prior_lsco_award_at_first_event"
        ],
        "PRIOR_LSCO_CREDENTIAL_RECIPIENT",
        "FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE",
    )

    detail = detail.merge(
        student_first_status,
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    detail["first_time_student_flag"] = (
        detail["final_student_recipient_class"]
        .eq("FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE")
    )

    detail["prior_recipient_student_flag"] = (
        detail["final_student_recipient_class"]
        .eq("PRIOR_LSCO_CREDENTIAL_RECIPIENT")
    )

    detail["first_time_award_event_flag"] = (
        detail["first_time_student_flag"]
        & detail["is_student_earliest_additional_event"]
    )

    # ------------------------------------------------------------------
    # 4. Final controls
    # ------------------------------------------------------------------

    final_awards = len(detail)
    final_students = detail["student_id"].nunique()
    final_lineages = detail["detected_lineage"].nunique()

    first_time_students = student_first_status.loc[
        student_first_status[
            "final_student_recipient_class"
        ].eq("FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE")
    ]["student_id"].nunique()

    prior_recipient_students = student_first_status.loc[
        student_first_status[
            "final_student_recipient_class"
        ].eq("PRIOR_LSCO_CREDENTIAL_RECIPIENT")
    ]["student_id"].nunique()

    if first_time_students + prior_recipient_students != final_students:
        raise RuntimeError(
            "Student recipient classes are not mutually exclusive."
        )

    if detail.duplicated(
        subset=["student_id", "detected_lineage"]
    ).any():
        duplicates = detail.loc[
            detail.duplicated(
                subset=["student_id", "detected_lineage"],
                keep=False,
            )
        ].copy()

        write_csv(
            duplicates,
            "ERROR_duplicate_student_lineages.csv",
        )

        raise RuntimeError(
            "Duplicate student × lineage rows remain."
        )

    # ------------------------------------------------------------------
    # 5. Final summaries
    # ------------------------------------------------------------------

    by_completion_year = (
        detail.groupby(
            "completion_academic_year",
            as_index=False,
            dropna=False,
        )
        .agg(
            additional_awards=(
                "detected_lineage",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            credential_lineages=(
                "detected_lineage",
                "nunique",
            ),
            first_time_students=(
                "student_id",
                lambda values: student_first_status.loc[
                    student_first_status[
                        "first_event_completion_year"
                    ].eq(values.name)
                    & student_first_status[
                        "final_student_recipient_class"
                    ].eq("FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE")
                ]["student_id"].nunique(),
            ),
        )
        .sort_values("completion_academic_year")
    )

    first_time_by_year = (
        student_first_status.loc[
            student_first_status[
                "final_student_recipient_class"
            ].eq("FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE")
        ]
        .groupby(
            "first_event_completion_year",
            as_index=False,
        )
        .agg(
            first_time_students=(
                "student_id",
                "nunique",
            ),
            first_event_additional_awards=(
                "first_event_additional_awards",
                "sum",
            ),
        )
        .rename(
            columns={
                "first_event_completion_year":
                    "completion_academic_year"
            }
        )
    )

    by_completion_year = (
        by_completion_year
        .drop(columns=["first_time_students"])
        .merge(
            first_time_by_year,
            on="completion_academic_year",
            how="left",
        )
    )

    by_completion_year[
        [
            "first_time_students",
            "first_event_additional_awards",
        ]
    ] = (
        by_completion_year[
            [
                "first_time_students",
                "first_event_additional_awards",
            ]
        ]
        .fillna(0)
        .astype(int)
    )

    by_catalog = (
        detail.groupby(
            "catalog_year",
            as_index=False,
            dropna=False,
        )
        .agg(
            additional_awards=(
                "detected_lineage",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            credential_lineages=(
                "detected_lineage",
                "nunique",
            ),
        )
        .sort_values("catalog_year")
    )

    by_lineage = (
        detail.groupby(
            "detected_lineage",
            as_index=False,
            dropna=False,
        )
        .agg(
            additional_awards=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            catalog_versions=(
                "catalog_year",
                "nunique",
            ),
            first_completion_year=(
                "completion_academic_year",
                "min",
            ),
            last_completion_year=(
                "completion_academic_year",
                "max",
            ),
        )
        .sort_values(
            [
                "additional_awards",
                "detected_lineage",
            ],
            ascending=[False, True],
        )
    )

    by_catalog_lineage_year = (
        detail.groupby(
            [
                "catalog_year",
                "detected_lineage",
                "completion_academic_year",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            additional_awards=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
        .sort_values(
            [
                "completion_academic_year",
                "catalog_year",
                "detected_lineage",
            ]
        )
    )

    reconciliation_summary = (
        reconciled.groupby(
            "reconciliation_disposition",
            as_index=False,
            dropna=False,
        )
        .agg(
            student_lineages=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
    )

    headline = pd.DataFrame(
        [
            {
                "metric": "Selected completed student-lineages",
                "value": len(reconciled),
            },
            {
                "metric": "Exact same-lineage awards removed",
                "value": int(
                    reconciled[
                        "exact_lineage_awarded"
                    ]
                    .astype(str)
                    .str.upper()
                    .isin({"TRUE", "1", "YES"})
                    .sum()
                ),
            },
            {
                "metric": "Confirmed same-award equivalents removed",
                "value": int(
                    reconciled[
                        "reconciliation_disposition"
                    ]
                    .eq(
                        "CONFIRMED_EQUIVALENT_ALREADY_AWARDED"
                    )
                    .sum()
                ),
            },
            {
                "metric": "Final additional awards",
                "value": final_awards,
            },
            {
                "metric": "Students receiving additional awards",
                "value": final_students,
            },
            {
                "metric": "Credential lineages represented",
                "value": final_lineages,
            },
            {
                "metric": "First-time LSCO credential candidate students",
                "value": first_time_students,
            },
            {
                "metric": "Prior LSCO credential recipients",
                "value": prior_recipient_students,
            },
            {
                "metric": "Unresolved relationship cases",
                "value": 0,
            },
        ]
    )

    # ------------------------------------------------------------------
    # 6. Write frozen package
    # ------------------------------------------------------------------

    write_csv(
        headline,
        "00_final_headline_metrics.csv",
    )

    write_csv(
        detail,
        "01_final_additional_awards_student_detail.csv",
    )

    write_csv(
        student_first_status,
        "02_final_student_recipient_classification.csv",
    )

    write_csv(
        by_completion_year,
        "03_final_additional_awards_by_completion_year.csv",
    )

    write_csv(
        by_catalog,
        "04_final_additional_awards_by_catalog.csv",
    )

    write_csv(
        by_lineage,
        "05_final_additional_awards_by_credential_lineage.csv",
    )

    write_csv(
        by_catalog_lineage_year,
        "06_final_catalog_lineage_completion_year_matrix.csv",
    )

    write_csv(
        reconciliation_summary,
        "07_final_reconciliation_summary.csv",
    )

    write_csv(
        detail.loc[
            detail["final_relationship_disposition"]
            .eq("SEPARATE_STACKABLE_AWARD")
        ].copy(),
        "08_final_stackable_additional_awards.csv",
    )

    print()
    print("=" * 100)
    print("FINAL HEADLINE METRICS")
    print("=" * 100)
    print(headline.to_string(index=False))

    print()
    print("FINAL ADDITIONAL AWARDS BY COMPLETION YEAR")
    print(by_completion_year.to_string(index=False))

    print()
    print("FINAL ADDITIONAL AWARDS BY CATALOG")
    print(by_catalog.to_string(index=False))

    print()
    print(f"Frozen output directory:\n{OUTPUT_DIR}")


if __name__ == "__main__":
    main()