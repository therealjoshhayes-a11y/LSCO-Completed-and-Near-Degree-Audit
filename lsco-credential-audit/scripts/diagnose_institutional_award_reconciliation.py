from __future__ import annotations

from pathlib import Path
import pandas as pd


RECON_ROOT = Path(
    r"data/processed/reporting/"
    r"institutional_award_reconciliation_20260730_173223"
)

INPUT_PATH = RECON_ROOT / "all_reconciled_student_lineages.csv"
OUTPUT_DIR = RECON_ROOT / "diagnostics"


def clean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def joined_values(series: pd.Series) -> str:
    values = sorted(
        {
            str(value).strip()
            for value in series.dropna()
            if str(value).strip()
        }
    )
    return " | ".join(values)


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing reconciliation file: {INPUT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_PATH, dtype=str, low_memory=False)

    required = [
        "student_id",
        "reconciliation_key",
        "reconciliation_bucket",
        "award_level",
        "canonical_lineage_institutional",
        "canonical_lineage_modeled",
        "modeled_lineage_present",
        "institutional_source_rows",
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
        "MajorDesc",
        "DegreeDesc",
        "catalog_year",
        "credential_id",
        "program_family",
        "completion_academic_year",
        "last_institutional_grad_date",
    ]

    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(
            "Reconciliation file is missing required columns:\n"
            + "\n".join(missing)
        )

    for column in required:
        df[column] = clean(df[column])

    df["modeled_lineage_present_bool"] = (
        df["modeled_lineage_present"]
        .str.upper()
        .map(
            {
                "TRUE": True,
                "FALSE": False,
                "YES": True,
                "NO": False,
                "1": True,
                "0": False,
            }
        )
    )

    df["institutional_grad_year"] = pd.to_datetime(
        df["last_institutional_grad_date"],
        errors="coerce",
    ).dt.year.astype("Int64")

    # ================================================================
    # 1. MERGED ASSOCIATE / CERTIFICATE KEYS
    # ================================================================
    mixed_level = df[
        df["award_level"].fillna("").str.contains(
            r"ASSOCIATE.*CERTIFICATE|CERTIFICATE.*ASSOCIATE",
            regex=True,
        )
    ].copy()

    mixed_level_columns = [
        "student_id",
        "reconciliation_bucket",
        "reconciliation_key",
        "award_level",
        "institutional_source_rows",
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
        "MajorDesc",
        "DegreeDesc",
        "canonical_lineage_institutional",
        "credential_id",
        "canonical_lineage_modeled",
        "catalog_year",
        "completion_academic_year",
    ]

    mixed_level[
        mixed_level_columns
    ].sort_values(
        [
            "reconciliation_key",
            "student_id",
        ]
    ).to_csv(
        OUTPUT_DIR / "01_mixed_associate_certificate_rows.csv",
        index=False,
    )

    mixed_level_summary = (
        mixed_level.groupby(
            [
                "reconciliation_bucket",
                "reconciliation_key",
            ],
            dropna=False,
        )
        .agg(
            student_lineages=("student_id", "size"),
            institutional_program_codes=(
                "Curr1ProgramCode",
                joined_values,
            ),
            institutional_major_codes=(
                "Major1Code",
                joined_values,
            ),
            institutional_degree_codes=(
                "DegreeCode",
                joined_values,
            ),
            institutional_descriptions=(
                "MajorDesc",
                joined_values,
            ),
        )
        .reset_index()
        .sort_values(
            [
                "reconciliation_bucket",
                "student_lineages",
            ],
            ascending=[True, False],
        )
    )

    mixed_level_summary.to_csv(
        OUTPUT_DIR / "02_mixed_associate_certificate_summary.csv",
        index=False,
    )

    # ================================================================
    # 2. INSTITUTIONAL LINEAGES NOT PRESENT IN MODEL
    # ================================================================
    awarded_not_detected = df[
        df["reconciliation_bucket"].eq("AWARDED_NOT_DETECTED")
    ].copy()

    not_modeled = awarded_not_detected[
        awarded_not_detected[
            "modeled_lineage_present_bool"
        ].eq(False)
    ].copy()

    not_modeled_summary = (
        not_modeled.groupby(
            [
                "reconciliation_key",
                "award_level",
            ],
            dropna=False,
        )
        .agg(
            student_lineages=("student_id", "size"),
            unique_students=("student_id", "nunique"),
            institutional_program_codes=(
                "Curr1ProgramCode",
                joined_values,
            ),
            institutional_major_codes=(
                "Major1Code",
                joined_values,
            ),
            institutional_degree_codes=(
                "DegreeCode",
                joined_values,
            ),
            institutional_descriptions=(
                "MajorDesc",
                joined_values,
            ),
            first_grad_year=(
                "institutional_grad_year",
                "min",
            ),
            last_grad_year=(
                "institutional_grad_year",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            "student_lineages",
            ascending=False,
        )
    )

    not_modeled_summary.to_csv(
        OUTPUT_DIR / "03_awarded_lineages_not_present_in_model.csv",
        index=False,
    )

    # ================================================================
    # 3. LINEAGES PRESENT ON BOTH SIDES BUT STUDENTS DO NOT MATCH
    # ================================================================
    institutional_counts = (
        df[
            df["reconciliation_bucket"].isin(
                [
                    "DETECTED_AND_AWARDED",
                    "AWARDED_NOT_DETECTED",
                ]
            )
        ]
        .groupby(
            "reconciliation_key",
            dropna=False,
        )
        .agg(
            institutional_total=("student_id", "size"),
            detected_and_awarded=(
                "reconciliation_bucket",
                lambda s: int(
                    s.eq("DETECTED_AND_AWARDED").sum()
                ),
            ),
            awarded_not_detected=(
                "reconciliation_bucket",
                lambda s: int(
                    s.eq("AWARDED_NOT_DETECTED").sum()
                ),
            ),
        )
        .reset_index()
    )

    modeled_counts = (
        df[
            df["reconciliation_bucket"].isin(
                [
                    "DETECTED_AND_AWARDED",
                    "DETECTED_NOT_AWARDED",
                ]
            )
        ]
        .groupby(
            "reconciliation_key",
            dropna=False,
        )
        .agg(
            modeled_total=("student_id", "size"),
            detected_not_awarded=(
                "reconciliation_bucket",
                lambda s: int(
                    s.eq("DETECTED_NOT_AWARDED").sum()
                ),
            ),
        )
        .reset_index()
    )

    overlap = institutional_counts.merge(
        modeled_counts,
        on="reconciliation_key",
        how="outer",
        validate="one_to_one",
    ).fillna(0)

    numeric_columns = [
        "institutional_total",
        "detected_and_awarded",
        "awarded_not_detected",
        "modeled_total",
        "detected_not_awarded",
    ]

    for column in numeric_columns:
        overlap[column] = overlap[column].astype(int)

    overlap = overlap[
        overlap["institutional_total"].gt(0)
        & overlap["modeled_total"].gt(0)
    ].copy()

    overlap["institutional_match_rate"] = (
        overlap["detected_and_awarded"]
        / overlap["institutional_total"]
    )

    overlap["modeled_award_rate"] = (
        overlap["detected_and_awarded"]
        / overlap["modeled_total"]
    )

    overlap["total_mismatch"] = (
        overlap["awarded_not_detected"]
        + overlap["detected_not_awarded"]
    )

    overlap = overlap.sort_values(
        [
            "total_mismatch",
            "institutional_total",
            "modeled_total",
        ],
        ascending=False,
    )

    overlap.to_csv(
        OUTPUT_DIR / "04_lineages_present_on_both_sides.csv",
        index=False,
    )

    # ================================================================
    # 4. POSSIBLE STACKING / NESTED-AWARD BEHAVIOR
    #    Student has a modeled-unawarded lineage and another award in
    #    the same program family or closely related lineage.
    # ================================================================
    detected_not_awarded = df[
        df["reconciliation_bucket"].eq("DETECTED_NOT_AWARDED")
    ].copy()

    institutional_student_awards = df[
        df["reconciliation_bucket"].isin(
            [
                "DETECTED_AND_AWARDED",
                "AWARDED_NOT_DETECTED",
            ]
        )
    ][
        [
            "student_id",
            "reconciliation_key",
            "award_level",
            "Curr1ProgramCode",
            "Major1Code",
            "DegreeCode",
            "MajorDesc",
            "DegreeDesc",
        ]
    ].copy()

    institutional_student_awards = (
        institutional_student_awards.groupby(
            "student_id",
            as_index=False,
        )
        .agg(
            other_institutional_lineages=(
                "reconciliation_key",
                joined_values,
            ),
            other_institutional_award_levels=(
                "award_level",
                joined_values,
            ),
            other_institutional_program_codes=(
                "Curr1ProgramCode",
                joined_values,
            ),
            other_institutional_major_codes=(
                "Major1Code",
                joined_values,
            ),
            other_institutional_degree_codes=(
                "DegreeCode",
                joined_values,
            ),
            other_institutional_descriptions=(
                "MajorDesc",
                joined_values,
            ),
        )
    )

    stacking_candidates = detected_not_awarded.merge(
        institutional_student_awards,
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    stacking_candidates[
        "has_other_institutional_award"
    ] = (
        stacking_candidates[
            "other_institutional_lineages"
        ].notna()
        & stacking_candidates[
            "other_institutional_lineages"
        ].ne("")
    )

    stacking_candidates[
        "other_award_contains_same_lineage"
    ] = stacking_candidates.apply(
        lambda row: (
            str(row["reconciliation_key"])
            in str(row["other_institutional_lineages"])
        ),
        axis=1,
    )

    stacking_candidates[
        [
            "student_id",
            "reconciliation_key",
            "credential_id",
            "catalog_year",
            "program_family",
            "completion_academic_year",
            "has_other_institutional_award",
            "other_award_contains_same_lineage",
            "other_institutional_lineages",
            "other_institutional_award_levels",
            "other_institutional_program_codes",
            "other_institutional_major_codes",
            "other_institutional_degree_codes",
            "other_institutional_descriptions",
        ]
    ].sort_values(
        [
            "has_other_institutional_award",
            "reconciliation_key",
            "student_id",
        ],
        ascending=[False, True, True],
    ).to_csv(
        OUTPUT_DIR / "05_detected_not_awarded_with_other_awards.csv",
        index=False,
    )

    stacking_summary = (
        stacking_candidates.groupby(
            [
                "reconciliation_key",
                "program_family",
            ],
            dropna=False,
        )
        .agg(
            detected_not_awarded=("student_id", "size"),
            with_other_institutional_award=(
                "has_other_institutional_award",
                "sum",
            ),
            without_other_institutional_award=(
                "has_other_institutional_award",
                lambda s: int((~s).sum()),
            ),
        )
        .reset_index()
    )

    stacking_summary[
        "share_with_other_institutional_award"
    ] = (
        stacking_summary[
            "with_other_institutional_award"
        ]
        / stacking_summary[
            "detected_not_awarded"
        ]
    )

    stacking_summary = stacking_summary.sort_values(
        [
            "detected_not_awarded",
            "with_other_institutional_award",
        ],
        ascending=False,
    )

    stacking_summary.to_csv(
        OUTPUT_DIR / "06_stacking_candidate_summary.csv",
        index=False,
    )

    # ================================================================
    # 5. HIGH-PRIORITY REVIEW TABLE
    # ================================================================
    priority = overlap.copy()

    priority["review_category"] = "BOTH_SIDES_STUDENT_MISMATCH"

    priority.loc[
        priority["detected_not_awarded"].ge(20)
        & priority["awarded_not_detected"].le(5),
        "review_category",
    ] = "LIKELY_UNCLAIMED_OR_UNPOSTED_AWARDS"

    priority.loc[
        priority["awarded_not_detected"].ge(20)
        & priority["detected_not_awarded"].le(5),
        "review_category",
    ] = "LIKELY_MODEL_COVERAGE_OR_FALSE_NEGATIVE"

    priority.loc[
        priority["awarded_not_detected"].ge(20)
        & priority["detected_not_awarded"].ge(20),
        "review_category",
    ] = "HIGH_VOLUME_BIDIRECTIONAL_MISMATCH"

    priority.to_csv(
        OUTPUT_DIR / "07_priority_lineage_review.csv",
        index=False,
    )

    # ================================================================
    # CONSOLE SUMMARY
    # ================================================================
    print("=" * 108)
    print("RECONCILIATION DIAGNOSTICS COMPLETE")
    print("=" * 108)

    print(
        f"Mixed associate/certificate student-lineages: "
        f"{len(mixed_level):,}"
    )

    print(
        f"Awarded-not-detected rows whose lineage is absent "
        f"from the model: {len(not_modeled):,}"
    )

    print(
        f"Lineages represented on both institutional and "
        f"modeled sides: {len(overlap):,}"
    )

    print(
        f"Detected-not-awarded rows with another institutional "
        f"award for the same student: "
        f"{int(stacking_candidates['has_other_institutional_award'].sum()):,}"
    )

    print()
    print("TOP BIDIRECTIONAL MISMATCH LINEAGES")
    print(
        overlap[
            [
                "reconciliation_key",
                "institutional_total",
                "modeled_total",
                "detected_and_awarded",
                "awarded_not_detected",
                "detected_not_awarded",
                "institutional_match_rate",
                "modeled_award_rate",
            ]
        ]
        .head(25)
        .to_string(index=False)
    )

    print()
    print(f"Diagnostics written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
