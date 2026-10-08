from __future__ import annotations

from pathlib import Path

import pandas as pd


REVIEW_PATH = Path(
    "data/interim/institutional_awards/"
    "LSCO_lineage_relationship_human_review_completed.xlsx"
)

EXISTING_RELATIONSHIPS_PATH = Path(
    "data/interim/institutional_awards/"
    "governed_lineage_relationships.csv"
)

PAIR_PATH = Path(
    "data/processed/reporting/"
    "institutional_award_reconciliation_20260730_173223/"
    "diagnostics/award_pair_matrix/"
    "01_student_award_pair_detail.csv"
)

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    "final_award_stack_classification"
)

FINAL_RELATIONSHIPS_PATH = Path(
    "data/interim/institutional_awards/"
    "governed_lineage_relationships_final.csv"
)


def clean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def to_bool(value: object) -> bool:
    if pd.isna(value):
        return False

    if isinstance(value, bool):
        return value

    return str(value).strip().upper() in {
        "TRUE",
        "YES",
        "1",
    }


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
    for path in (
        REVIEW_PATH,
        EXISTING_RELATIONSHIPS_PATH,
        PAIR_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(f"Required input not found: {path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # LOAD COMPLETED HUMAN REVIEW
    # ================================================================
    review = pd.read_excel(
        REVIEW_PATH,
        sheet_name="Relationship Review",
        dtype=object,
    )

    review_required = [
        "Detected Lineage",
        "Institutional Lineage",
        "Reviewer Relationship Type",
        "Awarded Represents Detected?",
        "Detected Remains Additional Award?",
        "Governance Status",
    ]

    missing = sorted(set(review_required) - set(review.columns))
    if missing:
        raise ValueError(
            f"Review workbook is missing columns: {missing}"
        )

    review = review[
        review["Detected Lineage"].notna()
    ].copy()

    if len(review) != 313:
        raise ValueError(
            f"Expected 313 reviewed relationships; found {len(review):,}."
        )

    for column in review_required:
        review[column] = clean(review[column])

    incomplete = review[
        review["Reviewer Relationship Type"].isna()
        | review["Reviewer Relationship Type"].eq("")
        | review["Governance Status"].ne("GOVERNED")
        | review["Awarded Represents Detected?"].isna()
        | review["Detected Remains Additional Award?"].isna()
    ]

    if not incomplete.empty:
        raise ValueError(
            f"{len(incomplete):,} review relationships are incomplete."
        )

    reviewed = review.rename(
        columns={
            "Detected Lineage": "detected_lineage",
            "Institutional Lineage": "institutional_lineage",
            "Reviewer Relationship Type": "relationship_type",
            "Awarded Represents Detected?": (
                "awarded_represents_detected"
            ),
            "Detected Remains Additional Award?": (
                "detected_remains_additional_award"
            ),
            "Governance Status": "governance_status",
            "Reviewer Note": "governance_note",
        }
    )

    reviewed[
        "awarded_represents_detected"
    ] = reviewed[
        "awarded_represents_detected"
    ].map(to_bool)

    reviewed[
        "detected_remains_additional_award"
    ] = reviewed[
        "detected_remains_additional_award"
    ].map(to_bool)

    reviewed["governance_source"] = "HUMAN_REVIEW"

    reviewed = reviewed[
        [
            "detected_lineage",
            "institutional_lineage",
            "relationship_type",
            "awarded_represents_detected",
            "detected_remains_additional_award",
            "governance_status",
            "governance_note",
            "governance_source",
        ]
    ]

    # ================================================================
    # LOAD THE 25 PREVIOUSLY GOVERNED SEED RELATIONSHIPS
    # ================================================================
    existing = pd.read_csv(
        EXISTING_RELATIONSHIPS_PATH,
        dtype=object,
        low_memory=False,
    )

    existing_required = [
        "detected_lineage",
        "institutional_lineage",
        "relationship_type",
        "awarded_represents_detected",
        "detected_remains_additional_award",
        "governance_status",
        "governance_note",
    ]

    missing = sorted(set(existing_required) - set(existing.columns))
    if missing:
        raise ValueError(
            f"Existing relationship file is missing columns: {missing}"
        )

    for column in existing_required:
        existing[column] = clean(existing[column])

    existing = existing[
        existing["governance_status"].eq("GOVERNED")
    ].copy()

    existing[
        "awarded_represents_detected"
    ] = existing[
        "awarded_represents_detected"
    ].map(to_bool)

    existing[
        "detected_remains_additional_award"
    ] = existing[
        "detected_remains_additional_award"
    ].map(to_bool)

    existing["governance_source"] = "PREVIOUSLY_GOVERNED"

    existing = existing[
        [
            "detected_lineage",
            "institutional_lineage",
            "relationship_type",
            "awarded_represents_detected",
            "detected_remains_additional_award",
            "governance_status",
            "governance_note",
            "governance_source",
        ]
    ]

    # Human review overrides any duplicate seed relationship.
    reviewed_keys = set(
        zip(
            reviewed["detected_lineage"],
            reviewed["institutional_lineage"],
        )
    )

    existing = existing[
        ~existing.apply(
            lambda row: (
                row["detected_lineage"],
                row["institutional_lineage"],
            )
            in reviewed_keys,
            axis=1,
        )
    ].copy()

    relationships = pd.concat(
        [existing, reviewed],
        ignore_index=True,
    )

    duplicate_relationships = relationships.duplicated(
        subset=[
            "detected_lineage",
            "institutional_lineage",
        ],
        keep=False,
    )

    if duplicate_relationships.any():
        raise ValueError(
            "Final relationship table contains duplicate lineage pairs."
        )

    # IA awards can never consume a certificate or degree.
    ia_relationships = relationships[
        relationships["institutional_lineage"]
        .fillna("")
        .str.startswith("IA_")
    ]

    bad_ia = ia_relationships[
        ia_relationships[
            "awarded_represents_detected"
        ].eq(True)
        | ia_relationships[
            "detected_remains_additional_award"
        ].eq(False)
    ]

    if not bad_ia.empty:
        raise ValueError(
            "IA governance failure: an IA was allowed to consume "
            "a modeled certificate or degree."
        )

    relationships.to_csv(
        FINAL_RELATIONSHIPS_PATH,
        index=False,
    )

    relationships.to_csv(
        OUTPUT_DIR / "01_final_governed_relationships.csv",
        index=False,
    )

    # ================================================================
    # APPLY GOVERNANCE TO ALL DETECTED-NOT-AWARDED PAIRS
    # ================================================================
    pairs = pd.read_csv(
        PAIR_PATH,
        dtype=object,
        low_memory=False,
    )

    pair_required = [
        "student_id",
        "detected_lineage",
        "detected_credential_id",
        "detected_catalog_year",
        "detected_program_family",
        "detected_completion_academic_year",
        "institutional_lineage",
        "has_other_institutional_award",
    ]

    missing = sorted(set(pair_required) - set(pairs.columns))
    if missing:
        raise ValueError(
            f"Award-pair file is missing columns: {missing}"
        )

    for column in pair_required:
        pairs[column] = clean(pairs[column])

    pairs["has_other_institutional_award_bool"] = pairs[
        "has_other_institutional_award"
    ].map(to_bool)

    governed_pairs = pairs.merge(
        relationships,
        on=[
            "detected_lineage",
            "institutional_lineage",
        ],
        how="left",
        validate="many_to_one",
    )

    award_pair_mask = governed_pairs[
        "has_other_institutional_award_bool"
    ].eq(True)

    unresolved = governed_pairs[
        award_pair_mask
        & governed_pairs["governance_status"].ne("GOVERNED")
    ]

    if not unresolved.empty:
        unresolved[
            [
                "detected_lineage",
                "institutional_lineage",
            ]
        ].drop_duplicates().to_csv(
            OUTPUT_DIR / "ERROR_unresolved_relationships.csv",
            index=False,
        )

        raise ValueError(
            f"{len(unresolved):,} student-pair rows remain unresolved."
        )

    governed_pairs.to_csv(
        OUTPUT_DIR / "02_all_student_award_pairs_governed.csv",
        index=False,
    )

    # ================================================================
    # FINAL STUDENT + DETECTED-LINEAGE CLASSIFICATION
    #
    # Precedence:
    # 1. Any consuming relationship TRUE/FALSE means already represented.
    # 2. Otherwise any relationship with additional=TRUE remains awardable.
    # 3. Otherwise no institutional award.
    # ================================================================
    final_rows: list[dict[str, object]] = []

    grouped = governed_pairs.groupby(
        [
            "student_id",
            "detected_lineage",
        ],
        dropna=False,
        sort=False,
    )

    for (student_id, detected_lineage), group in grouped:
        first = group.iloc[0]

        has_award = group[
            "has_other_institutional_award_bool"
        ].any()

        consuming = group[
            group["awarded_represents_detected"].eq(True)
            & group[
                "detected_remains_additional_award"
            ].eq(False)
        ]

        nonconsuming = group[
            group[
                "detected_remains_additional_award"
            ].eq(True)
        ]

        if not consuming.empty:
            classification = (
                "REPRESENTED_BY_AWARDED_PARENT_OR_ALTERNATE"
            )
            governing = consuming

        elif not nonconsuming.empty:
            classification = (
                "ADDITIONAL_STACKABLE_AWARD_NOT_POSTED"
            )
            governing = nonconsuming

        elif not has_award:
            classification = "NO_INSTITUTIONAL_AWARD"
            governing = group.iloc[0:0]

        else:
            raise ValueError(
                "Governed award pair produced no final disposition for "
                f"student {student_id}, lineage {detected_lineage}."
            )

        final_rows.append(
            {
                "student_id": student_id,
                "detected_lineage": detected_lineage,
                "detected_credential_id": first[
                    "detected_credential_id"
                ],
                "detected_catalog_year": first[
                    "detected_catalog_year"
                ],
                "detected_program_family": first[
                    "detected_program_family"
                ],
                "detected_completion_academic_year": first[
                    "detected_completion_academic_year"
                ],
                "final_stack_classification": classification,
                "governing_institutional_lineages": joined_values(
                    governing["institutional_lineage"]
                ),
                "governing_relationship_types": joined_values(
                    governing["relationship_type"]
                ),
                "all_institutional_lineages": joined_values(
                    group["institutional_lineage"]
                ),
                "institutional_award_count": int(
                    group.loc[
                        group[
                            "has_other_institutional_award_bool"
                        ],
                        "institutional_lineage",
                    ].nunique()
                ),
            }
        )

    final = pd.DataFrame(final_rows)

    if len(final) != 1563:
        raise ValueError(
            f"Expected 1,563 detected student-lineages; found {len(final):,}."
        )

    final.to_csv(
        OUTPUT_DIR / "03_final_detected_not_awarded_classification.csv",
        index=False,
    )

    summary = (
        final.groupby(
            "final_stack_classification",
            dropna=False,
        )
        .agg(
            detected_student_lineages=("detected_lineage", "size"),
            unique_students=("student_id", "nunique"),
        )
        .reset_index()
        .sort_values(
            "detected_student_lineages",
            ascending=False,
        )
    )

    summary.to_csv(
        OUTPUT_DIR / "04_final_classification_summary.csv",
        index=False,
    )

    by_lineage = (
        final.groupby(
            [
                "detected_lineage",
                "final_stack_classification",
            ],
            dropna=False,
        )
        .agg(
            detected_student_lineages=("student_id", "size"),
            unique_students=("student_id", "nunique"),
        )
        .reset_index()
        .sort_values(
            [
                "detected_student_lineages",
                "detected_lineage",
            ],
            ascending=[False, True],
        )
    )

    by_lineage.to_csv(
        OUTPUT_DIR / "05_final_classification_by_lineage.csv",
        index=False,
    )

    additional = final[
        final["final_stack_classification"].isin(
            [
                "ADDITIONAL_STACKABLE_AWARD_NOT_POSTED",
                "NO_INSTITUTIONAL_AWARD",
            ]
        )
    ].copy()

    additional.to_csv(
        OUTPUT_DIR / "06_final_additional_credentials.csv",
        index=False,
    )

    print("=" * 100)
    print("FINAL GOVERNED AWARD-STACK CLASSIFICATION COMPLETE")
    print("=" * 100)
    print(summary.to_string(index=False))

    print()
    print("FINAL OPPORTUNITY")
    print(
        f"Additional credential student-lineages: "
        f"{len(additional):,}"
    )
    print(
        f"Unique students with at least one additional credential: "
        f"{additional['student_id'].nunique():,}"
    )

    print()
    print("GOVERNANCE")
    print(f"Human-reviewed relationships: {len(reviewed):,}")
    print(f"Previously governed relationships retained: {len(existing):,}")
    print(f"Final governed relationships: {len(relationships):,}")
    print(f"IA relationships: {len(ia_relationships):,}")
    print("IA relationships consuming a certificate or degree: 0")

    print()
    print(f"Final relationship table: {FINAL_RELATIONSHIPS_PATH}")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
