from __future__ import annotations

from pathlib import Path

import pandas as pd


RECON_ROOT = Path(
    r"data/processed/reporting/"
    r"institutional_award_reconciliation_20260730_173223"
)

PAIR_PATH = (
    RECON_ROOT
    / "diagnostics"
    / "award_pair_matrix"
    / "01_student_award_pair_detail.csv"
)

RELATIONSHIP_PATH = Path(
    r"data/interim/institutional_awards/"
    r"governed_lineage_relationships.csv"
)

OUTPUT_DIR = Path(r"data/processed/reporting/award_stack_classification")


RELATIONSHIP_COLUMNS = [
    "detected_lineage",
    "institutional_lineage",
    "relationship_type",
    "awarded_represents_detected",
    "detected_remains_additional_award",
    "governance_status",
    "governance_note",
]


# ----------------------------------------------------------------------
# High-confidence, direction-specific relationships.
#
# awarded_represents_detected:
#   TRUE  = the awarded lineage already represents or contains the
#           detected lineage for reclamation-count purposes.
#   FALSE = the detected lineage remains an additional possible award.
#
# An awarded lower-level certificate never consumes a detected AAS.
# IA awards never consume any certificate or degree lineage.
# ----------------------------------------------------------------------
GOVERNED_SEEDS = [
    # Academic core / transfer stack
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "GENERAL_STUDIES",
        "relationship_type": "ALTERNATE_CERTIFICATE_GENERATION",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "General Studies and General Studies Core Curriculum "
            "are treated as alternate certificate generations."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "LIBERAL_ARTS",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded Liberal Arts associate represents the embedded "
            "general academic core certificate."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "BUSINESS",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded academic Business associate represents the "
            "embedded general academic core certificate."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "TEACHING_AAT1",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded AAT represents the embedded general academic "
            "core certificate."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "TEACHING_AAT2",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded AAT represents the embedded general academic "
            "core certificate."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "SOCIOLOGY",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded academic associate represents the embedded "
            "general academic core certificate."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "COMPUTER_SCIENCE",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded academic associate represents the embedded "
            "general academic core certificate."
        ),
    },
    {
        "detected_lineage": "GENERAL_STUDIES_CORE_CURRICULUM",
        "institutional_lineage": "BIOLOGY_MEDICAL_PROFESSIONS_EMPHASIS",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded academic associate represents the embedded "
            "general academic core certificate."
        ),
    },

    # Liberal Arts detected while only a lower certificate was awarded:
    # the lower award does not consume the associate.
    {
        "detected_lineage": "LIBERAL_ARTS",
        "institutional_lineage": "GENERAL_STUDIES",
        "relationship_type": "LOWER_AWARD_POSTED",
        "awarded_represents_detected": False,
        "detected_remains_additional_award": True,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded General Studies certificate does not consume "
            "a detected Liberal Arts associate degree."
        ),
    },

    # Instrumentation
    {
        "detected_lineage": "INSTRUMENTATION_BASIC",
        "institutional_lineage": (
            "INSTRUMENTATION_CERTIFICATE_OF_COMPLETION"
        ),
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Instrumentation Basic is embedded in the awarded "
            "Instrumentation certificate."
        ),
    },
    {
        "detected_lineage": "INSTRUMENTATION_BASIC",
        "institutional_lineage": "INSTRUMENTATION_AAS",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Instrumentation Basic is embedded in the awarded "
            "Instrumentation AAS."
        ),
    },

    # Process Technology: awarded certificate does not consume AAS.
    {
        "detected_lineage": "PROCESS_TECHNOLOGY_AAS",
        "institutional_lineage": "PROCESS_TECHNOLOGY_CERTIFICATE",
        "relationship_type": "LOWER_AWARD_POSTED",
        "awarded_represents_detected": False,
        "detected_remains_additional_award": True,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Awarded Process Technology certificate does not consume "
            "a detected Process Technology AAS."
        ),
    },

    # Criminal Justice
    {
        "detected_lineage": (
            "CRIMINAL_JUSTICE_LAW_ENFORCEMENT"
        ),
        "institutional_lineage": (
            "CRIMINAL_JUSTICE_CERTIFICATE_OF_COMPLETION"
        ),
        "relationship_type": "ALTERNATE_OR_PARENT_CERTIFICATE",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Law Enforcement lineage is represented by the posted "
            "Criminal Justice certificate."
        ),
    },

    # Pharmacy
    {
        "detected_lineage": "PHARMACY_TECHNOLOGY_BASIC",
        "institutional_lineage": (
            "RETAIL_PHARMACY_TECHNOLOGY_BASIC"
        ),
        "relationship_type": "ALTERNATE_GENERATION",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Retail Pharmacy Technology Basic is treated as an "
            "alternate generation of Pharmacy Technology Basic."
        ),
    },
    {
        "detected_lineage": "PHARMACY_TECHNOLOGY_BASIC",
        "institutional_lineage": (
            "HOSPITAL_PHARMACY_TECHNOLOGY"
        ),
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Pharmacy Technology Basic is represented by the awarded "
            "Hospital Pharmacy Technology certificate."
        ),
    },
    {
        "detected_lineage": "PHARMACY_TECHNOLOGY",
        "institutional_lineage": (
            "HOSPITAL_PHARMACY_TECHNOLOGY"
        ),
        "relationship_type": "ALTERNATE_GENERATION",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Hospital Pharmacy Technology is treated as an alternate "
            "historical Pharmacy Technology lineage."
        ),
    },
    {
        "detected_lineage": "PHARMACY_TECHNOLOGY",
        "institutional_lineage": (
            "RETAIL_PHARMACY_TECHNOLOGY_BASIC"
        ),
        "relationship_type": "LOWER_AWARD_POSTED",
        "awarded_represents_detected": False,
        "detected_remains_additional_award": True,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Retail Pharmacy Technology Basic does not consume the "
            "larger detected Pharmacy Technology credential."
        ),
    },

    # Maritime
    {
        "detected_lineage": (
            "ORDINARY_SEAMAN_BASIC_SAFETY_TRAINING"
        ),
        "institutional_lineage": "ORDINARY_SEAMAN_I",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Basic Safety Training is embedded in Ordinary Seaman I."
        ),
    },

    # Real Estate
    {
        "detected_lineage": "REAL_ESTATE",
        "institutional_lineage": "REAL_ESTATE_MANAGEMENT",
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Real Estate is represented by the awarded Real Estate "
            "Management credential."
        ),
    },

    # Welding
    {
        "detected_lineage": "WELDING_TECHNOLOGY",
        "institutional_lineage": (
            "WELDING_TECHNOLOGY_CERTIFICATE_OF_COMPLETION"
        ),
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Welding Technology is represented by the awarded Welding "
            "Technology certificate."
        ),
    },

    # Electromechanical
    {
        "detected_lineage": (
            "ELECTROMECHANICAL_TECHNOLOGY_BASIC"
        ),
        "institutional_lineage": (
            "ELECTROMECHANICAL_TECHNOLOGY"
        ),
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Electromechanical Basic is embedded in the awarded "
            "Electromechanical Technology credential."
        ),
    },

    # Safety / Industrial Systems
    {
        "detected_lineage": (
            "SAFETY_HEALTH_AND_ENVIRONMENT"
        ),
        "institutional_lineage": (
            "SAFETY_HEALTH_ENVIRONMENT_CERTIFICATE"
        ),
        "relationship_type": "ALTERNATE_GENERATION",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Safety lineage naming variants are treated as alternate "
            "credential generations."
        ),
    },
    {
        "detected_lineage": (
            "SAFETY_HEALTH_AND_ENVIRONMENT"
        ),
        "institutional_lineage": (
            "SAFETY_HEALTH_AND_ENVIRONMENT_AAS"
        ),
        "relationship_type": "PARENT_CHILD_STACK",
        "awarded_represents_detected": True,
        "detected_remains_additional_award": False,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Safety certificate lineage is embedded in the awarded AAS."
        ),
    },

    # Business
    {
        "detected_lineage": "BUSINESS_OPERATIONS",
        "institutional_lineage": "BUSINESS_MANAGEMENT",
        "relationship_type": "SAME_FAMILY_NONCONSUMING",
        "awarded_represents_detected": False,
        "detected_remains_additional_award": True,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Business Management does not automatically consume "
            "Business Operations."
        ),
    },
    {
        "detected_lineage": "BUSINESS_OPERATIONS",
        "institutional_lineage": (
            "BUSINESS_MANAGEMENT_ACCOUNTING"
        ),
        "relationship_type": "SAME_FAMILY_NONCONSUMING",
        "awarded_represents_detected": False,
        "detected_remains_additional_award": True,
        "governance_status": "GOVERNED",
        "governance_note": (
            "Business Management Accounting does not automatically "
            "consume Business Operations."
        ),
    },
]


def clean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def bool_value(value: object) -> bool:
    if pd.isna(value):
        return False

    return str(value).strip().upper() in {
        "TRUE",
        "YES",
        "1",
    }


def build_relationship_table(
    pairs: pd.DataFrame,
) -> pd.DataFrame:
    governed = pd.DataFrame(
        GOVERNED_SEEDS,
        columns=RELATIONSHIP_COLUMNS,
    )

    observed = (
        pairs[
            pairs["has_other_institutional_award"]
            .astype("string")
            .str.upper()
            .isin(["TRUE", "YES", "1"])
        ][
            [
                "detected_lineage",
                "institutional_lineage",
            ]
        ]
        .dropna()
        .drop_duplicates()
    )

    combined = observed.merge(
        governed,
        on=[
            "detected_lineage",
            "institutional_lineage",
        ],
        how="left",
        validate="one_to_one",
    )

    unresolved = combined[
        combined["governance_status"].isna()
    ].copy()

    unresolved["relationship_type"] = "UNRESOLVED"
    unresolved["awarded_represents_detected"] = False
    unresolved["detected_remains_additional_award"] = False
    unresolved["governance_status"] = "REVIEW_REQUIRED"
    unresolved["governance_note"] = (
        "Observed student-level award pair; relationship not yet governed."
    )

    result = pd.concat(
        [
            governed,
            unresolved[RELATIONSHIP_COLUMNS],
        ],
        ignore_index=True,
    )

    result = result.drop_duplicates(
        subset=[
            "detected_lineage",
            "institutional_lineage",
        ],
        keep="first",
    )

    return result.sort_values(
        [
            "governance_status",
            "detected_lineage",
            "institutional_lineage",
        ]
    )


def classify_detected_lineage(
    group: pd.DataFrame,
) -> pd.Series:
    student_id, detected_lineage = group.name

    detected_credential_id = group[
        "detected_credential_id"
    ].iloc[0]

    detected_catalog_year = group[
        "detected_catalog_year"
    ].iloc[0]

    detected_program_family = group[
        "detected_program_family"
    ].iloc[0]

    detected_completion_year = group[
        "detected_completion_academic_year"
    ].iloc[0]

    has_award = group[
        "has_other_institutional_award"
    ].map(bool_value).any()

    governed = group[
        group["governance_status"].eq("GOVERNED")
    ].copy()

    representing = governed[
        governed[
            "awarded_represents_detected_bool"
        ].eq(True)
    ]

    additional = governed[
        governed[
            "detected_remains_additional_award_bool"
        ].eq(True)
    ]

    unresolved = group[
        group["governance_status"].eq("REVIEW_REQUIRED")
    ]

    if not representing.empty:
        final_classification = (
            "REPRESENTED_BY_AWARDED_PARENT_OR_ALTERNATE"
        )

        governing_awards = " | ".join(
            sorted(
                set(
                    representing[
                        "institutional_lineage"
                    ].dropna()
                )
            )
        )

        governing_relationships = " | ".join(
            sorted(
                set(
                    representing[
                        "relationship_type"
                    ].dropna()
                )
            )
        )

    elif not additional.empty:
        final_classification = (
            "ADDITIONAL_STACKABLE_AWARD_NOT_POSTED"
        )

        governing_awards = " | ".join(
            sorted(
                set(
                    additional[
                        "institutional_lineage"
                    ].dropna()
                )
            )
        )

        governing_relationships = " | ".join(
            sorted(
                set(
                    additional[
                        "relationship_type"
                    ].dropna()
                )
            )
        )

    elif not has_award:
        final_classification = "NO_INSTITUTIONAL_AWARD"

        governing_awards = ""
        governing_relationships = ""

    elif not unresolved.empty:
        final_classification = (
            "OTHER_AWARD_RELATIONSHIP_REVIEW_REQUIRED"
        )

        governing_awards = " | ".join(
            sorted(
                set(
                    unresolved[
                        "institutional_lineage"
                    ].dropna()
                )
            )
        )

        governing_relationships = "UNRESOLVED"

    else:
        final_classification = (
            "OTHER_AWARD_UNRELATED_OR_NONCONSUMING"
        )

        governing_awards = " | ".join(
            sorted(
                set(
                    group[
                        "institutional_lineage"
                    ].dropna()
                )
            )
        )

        governing_relationships = ""

    all_awards = " | ".join(
        sorted(
            set(
                group[
                    "institutional_lineage"
                ].dropna()
            )
        )
    )

    return pd.Series(
        {
            "student_id": student_id,
            "detected_lineage": detected_lineage,
            "detected_credential_id": detected_credential_id,
            "detected_catalog_year": detected_catalog_year,
            "detected_program_family": detected_program_family,
            "detected_completion_academic_year": (
                detected_completion_year
            ),
            "final_stack_classification": (
                final_classification
            ),
            "governing_awarded_lineages": governing_awards,
            "governing_relationship_types": (
                governing_relationships
            ),
            "all_institutional_awards_for_student": all_awards,
            "observed_award_pair_rows": len(group),
        }
    )


def main() -> None:
    if not PAIR_PATH.exists():
        raise FileNotFoundError(
            f"Missing award-pair detail: {PAIR_PATH}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RELATIONSHIP_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pairs = pd.read_csv(
        PAIR_PATH,
        dtype=str,
        low_memory=False,
    )

    required = [
        "student_id",
        "detected_lineage",
        "detected_credential_id",
        "detected_catalog_year",
        "detected_program_family",
        "detected_completion_academic_year",
        "institutional_lineage",
        "institutional_award_level",
        "has_other_institutional_award",
    ]

    missing = sorted(set(required) - set(pairs.columns))

    if missing:
        raise ValueError(
            "Award-pair file is missing required columns:\n"
            + "\n".join(missing)
        )

    for column in required:
        pairs[column] = clean(pairs[column])

    relationships = build_relationship_table(pairs)

    relationships.to_csv(
        RELATIONSHIP_PATH,
        index=False,
    )

    relationships.to_csv(
        OUTPUT_DIR / "01_governed_lineage_relationships.csv",
        index=False,
    )

    merged = pairs.merge(
        relationships,
        on=[
            "detected_lineage",
            "institutional_lineage",
        ],
        how="left",
        validate="many_to_one",
    )

    no_award_mask = ~merged[
        "has_other_institutional_award"
    ].map(bool_value)

    merged.loc[
        no_award_mask,
        "relationship_type",
    ] = "NO_INSTITUTIONAL_AWARD"

    merged.loc[
        no_award_mask,
        "governance_status",
    ] = "NOT_APPLICABLE"

    merged.loc[
        no_award_mask,
        "governance_note",
    ] = "Student has no institutional award in the awards file."

    merged[
        "awarded_represents_detected_bool"
    ] = merged[
        "awarded_represents_detected"
    ].map(bool_value)

    merged[
        "detected_remains_additional_award_bool"
    ] = merged[
        "detected_remains_additional_award"
    ].map(bool_value)

    # Mechanical IA guard:
    # IA can never represent or consume a modeled credential.
    ia_mask = merged[
        "institutional_lineage"
    ].fillna("").str.startswith("IA_")

    merged.loc[
        ia_mask,
        "relationship_type",
    ] = "INSTITUTIONAL_AWARD_NONCONSUMING"

    merged.loc[
        ia_mask,
        "awarded_represents_detected_bool",
    ] = False

    merged.loc[
        ia_mask,
        "detected_remains_additional_award_bool",
    ] = True

    merged.loc[
        ia_mask,
        "governance_status",
    ] = "GOVERNED"

    merged.loc[
        ia_mask,
        "governance_note",
    ] = (
        "Institutional Awards are independent and cannot consume "
        "certificate or associate-degree lineages."
    )

    merged.to_csv(
        OUTPUT_DIR / "02_student_award_pairs_governed.csv",
        index=False,
    )

    grouped = (
        merged.groupby(
            [
                "student_id",
                "detected_lineage",
            ],
            dropna=False,
            sort=False,
        )
        .apply(
            classify_detected_lineage,
            include_groups=False,
        )
        .reset_index(drop=True)
    )

    grouped.to_csv(
        OUTPUT_DIR
        / "03_detected_not_awarded_final_classification.csv",
        index=False,
    )

    summary = (
        grouped.groupby(
            "final_stack_classification",
            dropna=False,
        )
        .agg(
            detected_student_lineages=(
                "detected_lineage",
                "size",
            ),
            unique_students=(
                "student_id",
                "nunique",
            ),
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

    lineage_summary = (
        grouped.groupby(
            [
                "detected_lineage",
                "final_stack_classification",
            ],
            dropna=False,
        )
        .agg(
            detected_student_lineages=(
                "student_id",
                "size",
            ),
            unique_students=(
                "student_id",
                "nunique",
            ),
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

    lineage_summary.to_csv(
        OUTPUT_DIR / "05_final_classification_by_lineage.csv",
        index=False,
    )

    unresolved_relationships = relationships[
        relationships[
            "governance_status"
        ].eq("REVIEW_REQUIRED")
    ].copy()

    unresolved_relationships.to_csv(
        OUTPUT_DIR / "06_relationships_requiring_review.csv",
        index=False,
    )

    unresolved_student_lineages = grouped[
        grouped[
            "final_stack_classification"
        ].eq(
            "OTHER_AWARD_RELATIONSHIP_REVIEW_REQUIRED"
        )
    ].copy()

    unresolved_student_lineages.to_csv(
        OUTPUT_DIR
        / "07_student_lineages_requiring_relationship_review.csv",
        index=False,
    )

    ia_bad = merged[
        ia_mask
        & merged[
            "awarded_represents_detected_bool"
        ].eq(True)
    ]

    if not ia_bad.empty:
        raise ValueError(
            "IA governance failure: an IA was allowed to represent "
            "or consume a modeled certificate or degree."
        )

    print("=" * 108)
    print("GOVERNED STACK CLASSIFICATION COMPLETE")
    print("=" * 108)

    print(summary.to_string(index=False))

    print()
    print("GOVERNANCE CHECKS")
    print(
        f"Governed relationship pairs: "
        f"{relationships['governance_status'].eq('GOVERNED').sum():,}"
    )
    print(
        f"Relationship pairs requiring review: "
        f"{len(unresolved_relationships):,}"
    )
    print(
        f"Student-lineages requiring relationship review: "
        f"{len(unresolved_student_lineages):,}"
    )
    print(
        f"IA pair rows: {int(ia_mask.sum()):,}"
    )
    print("IA lineages consuming modeled credentials: 0")

    print()
    print(f"Relationship table: {RELATIONSHIP_PATH}")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()



