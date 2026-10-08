from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

BASE = (
    ROOT
    / "data/processed/reporting/"
    "additional_awards_clean_query_20260803"
)

SELECTED_PATH = (
    BASE / "06_selected_student_lineage_completions_before_awards.csv"
)

OFFICIAL_PATH = BASE / "08_official_awards_normalized.csv"

GOVERNED_PATH = (
    ROOT
    / "data/interim/institutional_awards/"
    "governed_lineage_relationships_final.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data/processed/reporting/"
    "additional_awards_revised_query_20260803"
)


CONFIRMED_EQUIVALENT_RELATIONSHIPS = {
    "ALTERNATE_GENERATION",
    "ALTERNATE_CERTIFICATE_GENERATION",
}

REVIEW_ONLY_RELATIONSHIPS = {
    "ALTERNATE_OR_PARENT_CERTIFICATE",
}

STACKABLE_RELATIONSHIPS = {
    "PARENT_CHILD_STACK",
}


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    ).upper()


def normalize_id(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]

    return text


def academic_year_start(value: object) -> float:
    match = re.search(r"(19|20)\d{2}", str(value))

    if not match:
        return np.nan

    return float(match.group(0))


def corrected_completion_year(
    completion_year: object,
    catalog_year: object,
) -> str:
    completion_start = academic_year_start(completion_year)
    catalog_start = academic_year_start(catalog_year)

    if pd.isna(catalog_start):
        return str(completion_year).strip()

    if pd.isna(completion_start):
        return str(catalog_year).strip()

    start = int(max(completion_start, catalog_start))
    return f"{start}-{start + 1}"


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found:\n{path}")


def write_csv(
    frame: pd.DataFrame,
    filename: str,
) -> None:
    path = OUTPUT_DIR / filename
    frame.to_csv(path, index=False)

    print(
        f"Wrote {len(frame):,} rows: "
        f"{path.relative_to(ROOT)}"
    )


def main() -> None:
    print("=" * 100)
    print("REVISED ADDITIONAL-AWARD QUERY")
    print("=" * 100)

    for path in [
        SELECTED_PATH,
        OFFICIAL_PATH,
        GOVERNED_PATH,
    ]:
        require_file(path)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    selected = pd.read_csv(
        SELECTED_PATH,
        dtype="string",
        low_memory=False,
    ).fillna("")

    official = pd.read_csv(
        OFFICIAL_PATH,
        dtype="string",
        low_memory=False,
    ).fillna("")

    governed = pd.read_csv(
        GOVERNED_PATH,
        dtype="string",
        low_memory=False,
    ).fillna("")

    selected["student_id"] = selected["student_id"].map(
        normalize_id
    )

    selected["canonical_lineage"] = selected[
        "canonical_lineage"
    ].map(normalize_text)

    official["student_id"] = official["student_id"].map(
        normalize_id
    )

    official["institutional_lineage"] = official[
        "institutional_lineage"
    ].map(normalize_text)

    governed["detected_lineage"] = governed[
        "detected_lineage"
    ].map(normalize_text)

    governed["institutional_lineage"] = governed[
        "institutional_lineage"
    ].map(normalize_text)

    governed["relationship_type"] = governed[
        "relationship_type"
    ].map(normalize_text)

    selected = selected.rename(
        columns={
            "canonical_lineage": "detected_lineage",
        }
    )

    print(
        "Selected student-lineage completions: "
        f"{len(selected):,}"
    )

    # ---------------------------------------------------------------------
    # 1. Correct completion-year allocation
    # ---------------------------------------------------------------------

    selected["reported_completion_academic_year"] = selected[
        "query_completion_academic_year"
    ]

    selected["completion_academic_year"] = selected.apply(
        lambda row: corrected_completion_year(
            row["query_completion_academic_year"],
            row["catalog_year"],
        ),
        axis=1,
    )

    selected["completion_year_shifted_to_catalog_opening"] = (
        selected["completion_academic_year"]
        != selected["reported_completion_academic_year"]
    )

    print(
        "Completion years shifted to catalog opening: "
        f"{selected['completion_year_shifted_to_catalog_opening'].sum():,}"
    )

    # ---------------------------------------------------------------------
    # 2. Exact institutional awards
    # ---------------------------------------------------------------------

    official_student_lineages = (
        official[
            [
                "student_id",
                "institutional_lineage",
            ]
        ]
        .loc[
            lambda frame:
            frame["student_id"].ne("")
            & frame["institutional_lineage"].ne("")
        ]
        .drop_duplicates()
    )

    exact_awards = official_student_lineages.rename(
        columns={
            "institutional_lineage": "detected_lineage",
        }
    )

    exact_awards["exact_lineage_awarded"] = True

    reconciled = selected.merge(
        exact_awards,
        on=[
            "student_id",
            "detected_lineage",
        ],
        how="left",
        validate="one_to_one",
    )

    reconciled["exact_lineage_awarded"] = (
        reconciled["exact_lineage_awarded"]
        .fillna(False)
        .astype(bool)
    )

    # ---------------------------------------------------------------------
    # 3. Confirmed same-award cross-generation equivalents
    # ---------------------------------------------------------------------

    confirmed_equivalents = governed.loc[
        governed["relationship_type"].isin(
            CONFIRMED_EQUIVALENT_RELATIONSHIPS
        ),
        [
            "detected_lineage",
            "institutional_lineage",
            "relationship_type",
            "governance_status",
            "governance_note",
        ],
    ].drop_duplicates()

    equivalent_awards = official_student_lineages.merge(
        confirmed_equivalents,
        on="institutional_lineage",
        how="inner",
        validate="many_to_many",
    )

    equivalent_awards = (
        equivalent_awards
        .groupby(
            [
                "student_id",
                "detected_lineage",
            ],
            as_index=False,
        )
        .agg(
            equivalent_lineage_awarded=(
                "institutional_lineage",
                lambda values: " | ".join(
                    sorted(set(values))
                ),
            ),
            equivalent_relationship_types=(
                "relationship_type",
                lambda values: " | ".join(
                    sorted(set(values))
                ),
            ),
        )
    )

    reconciled = reconciled.merge(
        equivalent_awards,
        on=[
            "student_id",
            "detected_lineage",
        ],
        how="left",
        validate="one_to_one",
    )

    reconciled[
        "confirmed_equivalent_award"
    ] = reconciled[
        "equivalent_lineage_awarded"
    ].fillna("").ne("")

    # ---------------------------------------------------------------------
    # 4. Stackable and ambiguous relationships: flag, do not remove
    # ---------------------------------------------------------------------

    retained_relationships = governed.loc[
        governed["relationship_type"].isin(
            STACKABLE_RELATIONSHIPS
            | REVIEW_ONLY_RELATIONSHIPS
        ),
        [
            "detected_lineage",
            "institutional_lineage",
            "relationship_type",
        ],
    ].drop_duplicates()

    retained_matches = official_student_lineages.merge(
        retained_relationships,
        on="institutional_lineage",
        how="inner",
        validate="many_to_many",
    )

    retained_matches = (
        retained_matches
        .groupby(
            [
                "student_id",
                "detected_lineage",
            ],
            as_index=False,
        )
        .agg(
            related_existing_lineages=(
                "institutional_lineage",
                lambda values: " | ".join(
                    sorted(set(values))
                ),
            ),
            retained_relationship_types=(
                "relationship_type",
                lambda values: " | ".join(
                    sorted(set(values))
                ),
            ),
        )
    )

    reconciled = reconciled.merge(
        retained_matches,
        on=[
            "student_id",
            "detected_lineage",
        ],
        how="left",
        validate="one_to_one",
    )

    reconciled["has_stackable_related_award"] = (
        reconciled["retained_relationship_types"]
        .fillna("")
        .str.contains("PARENT_CHILD_STACK")
    )

    reconciled["requires_relationship_review"] = (
        reconciled["retained_relationship_types"]
        .fillna("")
        .str.contains("ALTERNATE_OR_PARENT_CERTIFICATE")
    )

    # ---------------------------------------------------------------------
    # 5. Final additional-award disposition
    # ---------------------------------------------------------------------

    reconciled["reconciliation_disposition"] = (
        "ADDITIONAL_AWARD"
    )

    reconciled.loc[
        reconciled["exact_lineage_awarded"],
        "reconciliation_disposition",
    ] = "EXACT_LINEAGE_ALREADY_AWARDED"

    reconciled.loc[
        ~reconciled["exact_lineage_awarded"]
        & reconciled["confirmed_equivalent_award"],
        "reconciliation_disposition",
    ] = "CONFIRMED_EQUIVALENT_ALREADY_AWARDED"

    additional = reconciled.loc[
        reconciled["reconciliation_disposition"].eq(
            "ADDITIONAL_AWARD"
        )
    ].copy()

    additional["additional_award_flag"] = 1

    # ---------------------------------------------------------------------
    # 6. First-ever LSCO credential timing
    # ---------------------------------------------------------------------

    official["StudGradTerm_numeric"] = pd.to_numeric(
        official["StudGradTerm"],
        errors="coerce",
    )

    first_official_award = (
        official
        .loc[
            official["student_id"].ne("")
            & official["StudGradTerm_numeric"].notna()
        ]
        .groupby(
            "student_id",
            as_index=False,
        )
        .agg(
            first_official_grad_term=(
                "StudGradTerm_numeric",
                "min",
            ),
            official_award_count=(
                "institutional_lineage",
                "size",
            ),
            existing_official_lineage_count=(
                "institutional_lineage",
                "nunique",
            ),
        )
    )

    additional["modeled_completion_term_numeric"] = (
        pd.to_numeric(
            additional["award_term_sort_numeric"],
            errors="coerce",
        )
    )

    additional = additional.merge(
        first_official_award,
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    additional["had_lsco_award_before_completion"] = (
        additional["first_official_grad_term"].notna()
        & additional["modeled_completion_term_numeric"].notna()
        & (
            additional["first_official_grad_term"]
            <= additional["modeled_completion_term_numeric"]
        )
    )

    additional["credential_recipient_status"] = np.where(
        additional["had_lsco_award_before_completion"],
        "PRIOR_LSCO_CREDENTIAL_RECIPIENT",
        "FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE",
    )

    # Find each student's earliest newly identified completion event.
    additional["student_first_additional_completion_term"] = (
        additional.groupby("student_id")[
            "modeled_completion_term_numeric"
        ].transform("min")
    )

    additional["at_student_first_additional_event"] = (
        additional["modeled_completion_term_numeric"]
        == additional["student_first_additional_completion_term"]
    )

    additional[
        "first_time_lsco_credential_event"
    ] = (
        additional["credential_recipient_status"].eq(
            "FIRST_TIME_LSCO_CREDENTIAL_CANDIDATE"
        )
        & additional["at_student_first_additional_event"]
    )

    # ---------------------------------------------------------------------
    # 7. Outputs
    # ---------------------------------------------------------------------

    write_csv(
        reconciled,
        "01_all_selected_completions_reconciled.csv",
    )

    write_csv(
        reconciled.loc[
            reconciled["exact_lineage_awarded"]
        ].copy(),
        "02_exact_lineage_already_awarded.csv",
    )

    write_csv(
        reconciled.loc[
            ~reconciled["exact_lineage_awarded"]
            & reconciled["confirmed_equivalent_award"]
        ].copy(),
        "03_confirmed_equivalent_already_awarded.csv",
    )

    write_csv(
        additional,
        "04_final_additional_awards_student_detail.csv",
    )

    write_csv(
        additional.loc[
            additional["has_stackable_related_award"]
        ].copy(),
        "05_additional_awards_with_stackable_parent_child_award.csv",
    )

    write_csv(
        additional.loc[
            additional["requires_relationship_review"]
        ].copy(),
        "06_additional_awards_requiring_relationship_review.csv",
    )

    # ---------------------------------------------------------------------
    # 8. Main aggregation
    # ---------------------------------------------------------------------

    by_catalog_lineage_year = (
        additional
        .groupby(
            [
                "catalog_year",
                "detected_lineage",
                "completion_academic_year",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            first_time_candidate_awards=(
                "first_time_lsco_credential_event",
                "sum",
            ),
            first_time_candidate_students=(
                "student_id",
                lambda values: additional.loc[
                    values.index
                ].loc[
                    lambda frame:
                    frame["first_time_lsco_credential_event"]
                ]["student_id"].nunique(),
            ),
            prior_recipient_awards=(
                "had_lsco_award_before_completion",
                "sum",
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

    by_completion_year = (
        additional
        .groupby(
            "completion_academic_year",
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            credential_lineages=(
                "detected_lineage",
                "nunique",
            ),
            first_time_candidate_awards=(
                "first_time_lsco_credential_event",
                "sum",
            ),
            first_time_candidate_students=(
                "student_id",
                lambda values: additional.loc[
                    values.index
                ].loc[
                    lambda frame:
                    frame["first_time_lsco_credential_event"]
                ]["student_id"].nunique(),
            ),
        )
        .sort_values("completion_academic_year")
    )

    by_catalog = (
        additional
        .groupby(
            "catalog_year",
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            credential_lineages=(
                "detected_lineage",
                "nunique",
            ),
            first_time_candidate_students=(
                "student_id",
                lambda values: additional.loc[
                    values.index
                ].loc[
                    lambda frame:
                    frame["first_time_lsco_credential_event"]
                ]["student_id"].nunique(),
            ),
        )
        .sort_values("catalog_year")
    )

    by_lineage = (
        additional
        .groupby(
            "detected_lineage",
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            first_time_candidate_students=(
                "student_id",
                lambda values: additional.loc[
                    values.index
                ].loc[
                    lambda frame:
                    frame["first_time_lsco_credential_event"]
                ]["student_id"].nunique(),
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
            ascending=[
                False,
                True,
            ],
        )
    )

    write_csv(
        by_catalog_lineage_year,
        "07_additional_awards_by_catalog_lineage_completion_year.csv",
    )

    write_csv(
        by_completion_year,
        "08_additional_awards_by_completion_year.csv",
    )

    write_csv(
        by_catalog,
        "09_additional_awards_by_catalog.csv",
    )

    write_csv(
        by_lineage,
        "10_additional_awards_by_credential_lineage.csv",
    )

    # ---------------------------------------------------------------------
    # 9. President-facing summary
    # ---------------------------------------------------------------------

    first_time_students = additional.loc[
        additional["first_time_lsco_credential_event"]
    ]["student_id"].nunique()

    prior_recipient_students = additional.loc[
        additional["had_lsco_award_before_completion"]
    ]["student_id"].nunique()

    headline = pd.DataFrame(
        [
            {
                "metric": "Selected student-lineage completions",
                "value": len(selected),
            },
            {
                "metric": "Exact same-lineage awards removed",
                "value": int(
                    reconciled["exact_lineage_awarded"].sum()
                ),
            },
            {
                "metric": "Confirmed alternate-generation equivalents removed",
                "value": int(
                    (
                        ~reconciled["exact_lineage_awarded"]
                        & reconciled[
                            "confirmed_equivalent_award"
                        ]
                    ).sum()
                ),
            },
            {
                "metric": "Final additional awards",
                "value": len(additional),
            },
            {
                "metric": "Students receiving additional awards",
                "value": additional["student_id"].nunique(),
            },
            {
                "metric": "First-time LSCO credential candidate students",
                "value": first_time_students,
            },
            {
                "metric": "Students who already held an LSCO credential",
                "value": prior_recipient_students,
            },
            {
                "metric": "Additional awards with stackable parent-child relationship",
                "value": int(
                    additional[
                        "has_stackable_related_award"
                    ].sum()
                ),
            },
            {
                "metric": "Additional awards requiring relationship review",
                "value": int(
                    additional[
                        "requires_relationship_review"
                    ].sum()
                ),
            },
        ]
    )

    write_csv(
        headline,
        "00_president_headline_metrics.csv",
    )

    print()
    print("=" * 100)
    print("REVISED RESULT")
    print("=" * 100)
    print(headline.to_string(index=False))

    print()
    print("ADDITIONAL AWARDS BY COMPLETION YEAR")
    print(by_completion_year.to_string(index=False))

    print()
    print("ADDITIONAL AWARDS BY CATALOG")
    print(by_catalog.to_string(index=False))

    print()
    print(f"Output directory:\n{OUTPUT_DIR}")


if __name__ == "__main__":
    main()