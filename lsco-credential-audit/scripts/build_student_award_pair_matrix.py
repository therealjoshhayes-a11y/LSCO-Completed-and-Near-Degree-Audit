from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


RECON_ROOT = Path(
    r"data/processed/reporting/"
    r"institutional_award_reconciliation_20260730_173223"
)

INPUT_PATH = RECON_ROOT / "all_reconciled_student_lineages.csv"
OUTPUT_DIR = RECON_ROOT / "diagnostics" / "award_pair_matrix"

ACADEMIC_TRANSFER_FAMILY = {
    "GENERAL_STUDIES",
    "GENERAL_STUDIES_CORE_CURRICULUM",
    "LIBERAL_ARTS",
    "BUSINESS",
    "SOCIOLOGY",
    "NATURAL_SCIENCE",
    "BIOLOGY_MEDICAL_PROFESSIONS_EMPHASIS",
    "COMPUTER_SCIENCE",
    "TEACHING_AAT1",
    "TEACHING_AAT2",
    "TEACHING_T039",
    "TEACHING_T075",
    "TEACHER_EDUCATION_CERTIFICATE_OF_COMPLETION",
}

GENERIC_TOKENS = {
    "AAS",
    "AA",
    "AS",
    "AAT",
    "CERTIFICATE",
    "CERT",
    "COMPLETION",
    "BASIC",
    "ADVANCED",
    "TECHNOLOGY",
    "TECHNICIAN",
    "SPECIALIST",
    "ASSISTANT",
    "MANAGEMENT",
    "OPERATIONS",
    "OF",
    "AND",
    "THE",
    "I",
    "II",
    "III",
}


def clean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def safe_text(value: object) -> str:
    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_lineage_tokens(value: object) -> set[str]:
    text = safe_text(value).upper()

    if not text:
        return set()

    tokens = {
        token
        for token in re.split(r"[^A-Z0-9]+", text)
        if token and token not in GENERIC_TOKENS
    }

    return tokens


def lineage_similarity(left: object, right: object) -> float:
    left_tokens = normalize_lineage_tokens(left)
    right_tokens = normalize_lineage_tokens(right)

    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def joined_values(series: pd.Series) -> str:
    values = sorted(
        {
            str(value).strip()
            for value in series.dropna()
            if str(value).strip()
        }
    )
    return " | ".join(values)


def classify_pair(row: pd.Series) -> str:
    detected = safe_text(row["detected_lineage"])
    awarded = safe_text(row["institutional_lineage"])

    detected_family = safe_text(
        row["detected_program_family"]
    )
    awarded_family = safe_text(
        row["institutional_program_family"]
    )

    similarity_value = row["lineage_token_similarity"]

    if pd.isna(similarity_value):
        similarity = 0.0
    else:
        similarity = float(similarity_value)

    if awarded.startswith("IA_"):
        return "OTHER_AWARD_IS_INSTITUTIONAL_AWARD"

    if detected and detected == awarded:
        return "SAME_EXACT_LINEAGE"

    if (
        detected in ACADEMIC_TRANSFER_FAMILY
        and awarded in ACADEMIC_TRANSFER_FAMILY
    ):
        return "ACADEMIC_TRANSFER_AWARD_FAMILY"

    if (
        detected_family
        and awarded_family
        and detected_family == awarded_family
    ):
        return "SAME_MODELED_PROGRAM_FAMILY"

    if similarity >= 0.50:
        return "LIKELY_RELATED_LINEAGE"

    if similarity > 0:
        return "POSSIBLY_RELATED_LINEAGE"

    return "UNRELATED_OR_UNRESOLVED"


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
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
        "MajorDesc",
        "DegreeDesc",
        "credential_id",
        "catalog_year",
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

    # ------------------------------------------------------------------
    # Build a governed lineage -> modeled program-family lookup.
    # ------------------------------------------------------------------
    modeled_rows = df[
        df["reconciliation_bucket"].isin(
            [
                "DETECTED_AND_AWARDED",
                "DETECTED_NOT_AWARDED",
            ]
        )
        & df["reconciliation_key"].notna()
        & df["program_family"].notna()
    ][
        [
            "reconciliation_key",
            "program_family",
        ]
    ].drop_duplicates()

    family_conflicts = (
        modeled_rows.groupby("reconciliation_key")["program_family"]
        .nunique()
        .reset_index(name="family_count")
    )

    conflicts = family_conflicts[
        family_conflicts["family_count"].gt(1)
    ]

    if not conflicts.empty:
        conflicts.to_csv(
            OUTPUT_DIR / "00_lineage_program_family_conflicts.csv",
            index=False,
        )

    lineage_family = (
        modeled_rows.groupby(
            "reconciliation_key",
            as_index=False,
        )
        .agg(
            institutional_program_family=(
                "program_family",
                joined_values,
            )
        )
        .rename(
            columns={
                "reconciliation_key": "institutional_lineage",
            }
        )
    )

    # ------------------------------------------------------------------
    # Detected-but-not-awarded modeled credentials.
    # ------------------------------------------------------------------
    detected = df[
        df["reconciliation_bucket"].eq("DETECTED_NOT_AWARDED")
    ][
        [
            "student_id",
            "reconciliation_key",
            "credential_id",
            "catalog_year",
            "program_family",
            "completion_academic_year",
        ]
    ].copy()

    detected = detected.rename(
        columns={
            "reconciliation_key": "detected_lineage",
            "credential_id": "detected_credential_id",
            "catalog_year": "detected_catalog_year",
            "program_family": "detected_program_family",
            "completion_academic_year": (
                "detected_completion_academic_year"
            ),
        }
    )

    # ------------------------------------------------------------------
    # Institutional awards received by each student.
    # ------------------------------------------------------------------
    institutional = df[
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
            "last_institutional_grad_date",
        ]
    ].copy()

    institutional = institutional.rename(
        columns={
            "reconciliation_key": "institutional_lineage",
            "award_level": "institutional_award_level",
            "Curr1ProgramCode": "institutional_program_code",
            "Major1Code": "institutional_major_code",
            "DegreeCode": "institutional_degree_code",
            "MajorDesc": "institutional_major_description",
            "DegreeDesc": "institutional_degree_description",
            "last_institutional_grad_date": (
                "institutional_grad_date"
            ),
        }
    )

    institutional = institutional.merge(
        lineage_family,
        on="institutional_lineage",
        how="left",
        validate="many_to_one",
    )

    # ------------------------------------------------------------------
    # Create one row per modeled-unawarded lineage x actual award.
    # Students with no institutional award remain represented.
    # ------------------------------------------------------------------
    pairs = detected.merge(
        institutional,
        on="student_id",
        how="left",
        validate="many_to_many",
    )

    pairs["has_other_institutional_award"] = (
        pairs["institutional_lineage"].notna()
        & pairs["institutional_lineage"].ne("")
    )

    pairs["lineage_token_similarity"] = pairs.apply(
        lambda row: lineage_similarity(
            row["detected_lineage"],
            row["institutional_lineage"],
        ),
        axis=1,
    )

    pairs["pair_classification"] = pairs.apply(
        classify_pair,
        axis=1,
    )

    pairs["institutional_grad_year"] = pd.to_datetime(
        pairs["institutional_grad_date"],
        errors="coerce",
    ).dt.year.astype("Int64")

    # ------------------------------------------------------------------
    # Full student-level pair detail.
    # ------------------------------------------------------------------
    detail_columns = [
        "student_id",
        "detected_lineage",
        "detected_credential_id",
        "detected_catalog_year",
        "detected_program_family",
        "detected_completion_academic_year",
        "institutional_lineage",
        "institutional_award_level",
        "institutional_program_family",
        "institutional_program_code",
        "institutional_major_code",
        "institutional_degree_code",
        "institutional_major_description",
        "institutional_degree_description",
        "institutional_grad_date",
        "institutional_grad_year",
        "has_other_institutional_award",
        "lineage_token_similarity",
        "pair_classification",
    ]

    pairs[
        detail_columns
    ].sort_values(
        [
            "detected_lineage",
            "student_id",
            "pair_classification",
            "institutional_lineage",
        ]
    ).to_csv(
        OUTPUT_DIR / "01_student_award_pair_detail.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # Pair-frequency matrix.
    # ------------------------------------------------------------------
    pair_matrix = (
        pairs[
            pairs["has_other_institutional_award"]
        ]
        .groupby(
            [
                "detected_lineage",
                "institutional_lineage",
                "pair_classification",
            ],
            dropna=False,
        )
        .agg(
            student_pairs=("student_id", "nunique"),
            detected_program_families=(
                "detected_program_family",
                joined_values,
            ),
            institutional_program_families=(
                "institutional_program_family",
                joined_values,
            ),
            institutional_award_levels=(
                "institutional_award_level",
                joined_values,
            ),
            institutional_program_codes=(
                "institutional_program_code",
                joined_values,
            ),
            institutional_major_codes=(
                "institutional_major_code",
                joined_values,
            ),
            first_institutional_grad_year=(
                "institutional_grad_year",
                "min",
            ),
            last_institutional_grad_year=(
                "institutional_grad_year",
                "max",
            ),
            mean_token_similarity=(
                "lineage_token_similarity",
                "mean",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "student_pairs",
                "detected_lineage",
                "institutional_lineage",
            ],
            ascending=[False, True, True],
        )
    )

    pair_matrix.to_csv(
        OUTPUT_DIR / "02_award_pair_frequency_matrix.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # One summary row per detected-not-awarded lineage.
    # Count unique students, not pair rows.
    # ------------------------------------------------------------------
    lineage_students = (
        detected.groupby(
            [
                "detected_lineage",
                "detected_program_family",
            ],
            dropna=False,
        )["student_id"]
        .nunique()
        .reset_index(name="detected_not_awarded_students")
    )

    classification_students = (
        pairs.groupby(
            [
                "detected_lineage",
                "detected_program_family",
                "pair_classification",
            ],
            dropna=False,
        )["student_id"]
        .nunique()
        .reset_index(name="students")
    )

    classification_pivot = (
        classification_students.pivot_table(
            index=[
                "detected_lineage",
                "detected_program_family",
            ],
            columns="pair_classification",
            values="students",
            fill_value=0,
            aggfunc="sum",
        )
        .reset_index()
    )

    classification_pivot.columns.name = None

    lineage_summary = lineage_students.merge(
        classification_pivot,
        on=[
            "detected_lineage",
            "detected_program_family",
        ],
        how="left",
        validate="one_to_one",
    )

    class_columns = [
        column
        for column in lineage_summary.columns
        if column
        not in {
            "detected_lineage",
            "detected_program_family",
            "detected_not_awarded_students",
        }
    ]

    for column in class_columns:
        lineage_summary[column] = (
            lineage_summary[column]
            .fillna(0)
            .astype(int)
        )

    related_columns = [
        column
        for column in [
            "SAME_EXACT_LINEAGE",
            "ACADEMIC_TRANSFER_AWARD_FAMILY",
            "SAME_MODELED_PROGRAM_FAMILY",
            "LIKELY_RELATED_LINEAGE",
        ]
        if column in lineage_summary.columns
    ]

    if related_columns:
        lineage_summary[
            "students_with_related_award"
        ] = lineage_summary[related_columns].max(axis=1)
    else:
        lineage_summary[
            "students_with_related_award"
        ] = 0

    if "UNRELATED_OR_UNRESOLVED" in lineage_summary.columns:
        lineage_summary[
            "students_with_unrelated_or_unresolved_award"
        ] = lineage_summary["UNRELATED_OR_UNRESOLVED"]
    else:
        lineage_summary[
            "students_with_unrelated_or_unresolved_award"
        ] = 0

    if "OTHER_AWARD_IS_INSTITUTIONAL_AWARD" in lineage_summary.columns:
        lineage_summary[
            "students_whose_other_award_is_ia"
        ] = lineage_summary[
            "OTHER_AWARD_IS_INSTITUTIONAL_AWARD"
        ]
    else:
        lineage_summary[
            "students_whose_other_award_is_ia"
        ] = 0

    if "UNRELATED_OR_UNRESOLVED" in lineage_summary.columns:
        no_award_mask = pairs[
            "has_other_institutional_award"
        ].eq(False)

        no_award_counts = (
            pairs[no_award_mask]
            .groupby(
                [
                    "detected_lineage",
                    "detected_program_family",
                ],
                dropna=False,
            )["student_id"]
            .nunique()
            .reset_index(name="students_with_no_institutional_award")
        )

        lineage_summary = lineage_summary.merge(
            no_award_counts,
            on=[
                "detected_lineage",
                "detected_program_family",
            ],
            how="left",
            validate="one_to_one",
        )
    else:
        lineage_summary[
            "students_with_no_institutional_award"
        ] = 0

    lineage_summary[
        "students_with_no_institutional_award"
    ] = (
        lineage_summary[
            "students_with_no_institutional_award"
        ]
        .fillna(0)
        .astype(int)
    )

    lineage_summary[
        "related_award_share"
    ] = (
        lineage_summary["students_with_related_award"]
        / lineage_summary["detected_not_awarded_students"]
    )

    lineage_summary = lineage_summary.sort_values(
        [
            "detected_not_awarded_students",
            "students_with_related_award",
        ],
        ascending=False,
    )

    lineage_summary.to_csv(
        OUTPUT_DIR / "03_detected_lineage_pair_summary.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # Academic transfer cluster only.
    # ------------------------------------------------------------------
    academic_pairs = pairs[
        pairs["detected_lineage"].isin(
            ACADEMIC_TRANSFER_FAMILY
        )
        | pairs["institutional_lineage"].isin(
            ACADEMIC_TRANSFER_FAMILY
        )
    ].copy()

    academic_pairs[
        detail_columns
    ].sort_values(
        [
            "detected_lineage",
            "institutional_lineage",
            "student_id",
        ]
    ).to_csv(
        OUTPUT_DIR / "04_academic_transfer_award_pairs.csv",
        index=False,
    )

    academic_matrix = (
        academic_pairs[
            academic_pairs["has_other_institutional_award"]
        ]
        .groupby(
            [
                "detected_lineage",
                "institutional_lineage",
                "pair_classification",
            ],
            dropna=False,
        )["student_id"]
        .nunique()
        .reset_index(name="student_pairs")
        .sort_values(
            "student_pairs",
            ascending=False,
        )
    )

    academic_matrix.to_csv(
        OUTPUT_DIR / "05_academic_transfer_pair_matrix.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # Mixed associate/certificate institutional rows.
    # ------------------------------------------------------------------
    mixed_levels = df[
        df["award_level"].fillna("").str.contains(
            r"ASSOCIATE.*CERTIFICATE|CERTIFICATE.*ASSOCIATE",
            regex=True,
        )
    ].copy()

    mixed_levels.to_csv(
        OUTPUT_DIR / "06_mixed_associate_certificate_rows.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # Console report.
    # ------------------------------------------------------------------
    detected_students = detected["student_id"].nunique()

    with_any_award = pairs.loc[
        pairs["has_other_institutional_award"],
        "student_id",
    ].nunique()

    related_students = pairs.loc[
        pairs["pair_classification"].isin(
            [
                "SAME_EXACT_LINEAGE",
                "ACADEMIC_TRANSFER_AWARD_FAMILY",
                "SAME_MODELED_PROGRAM_FAMILY",
                "LIKELY_RELATED_LINEAGE",
            ]
        ),
        "student_id",
    ].nunique()

    print("=" * 112)
    print("STUDENT-LEVEL AWARD PAIR MATRIX COMPLETE")
    print("=" * 112)

    print(
        f"Detected-not-awarded lineages: "
        f"{len(detected):,}"
    )

    print(
        f"Unique students represented: "
        f"{detected_students:,}"
    )

    print(
        f"Students with at least one institutional award: "
        f"{with_any_award:,}"
    )

    print(
        f"Students with at least one related or academic-family award: "
        f"{related_students:,}"
    )

    print()
    print("PAIR CLASSIFICATION — UNIQUE STUDENTS")

    class_summary = (
        pairs.groupby(
            "pair_classification",
            dropna=False,
        )["student_id"]
        .nunique()
        .sort_values(
            ascending=False,
        )
    )

    print(class_summary.to_string())

    print()
    print("TOP AWARD PAIRS")

    print(
        pair_matrix[
            [
                "detected_lineage",
                "institutional_lineage",
                "pair_classification",
                "student_pairs",
                "detected_program_families",
                "institutional_program_families",
                "institutional_award_levels",
            ]
        ]
        .head(40)
        .to_string(index=False)
    )

    print()
    print(f"Outputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()


