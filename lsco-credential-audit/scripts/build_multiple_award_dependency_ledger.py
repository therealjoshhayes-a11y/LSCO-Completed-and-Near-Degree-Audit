from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# STEP 5 — BUILD THE MULTIPLE-AWARD / DEPENDENCY LEDGER
# ======================================================================================
#
# Purpose:
#   Take only the ordinary-awardability PASS combinations and identify which
#   candidates need a second-associate or additional-certificate rule.
#
# This script DOES NOT adjudicate the extra-hours rule yet.
# It creates the exact student/candidate/prior-award pairs needed for that step.
#
# Governed architecture carried forward from the prior additional-award work:
#   * parent/child credential stacks are NON-CONSUMING — both credentials can be
#     separately awardable; stack relationships do not suppress the candidate.
#   * same credential/equivalent lineage was already removed upstream by the
#     official-award suppression stage.
#
# Additional-award rule routing:
#   * candidate associate + >=1 official associate -> second-associate rule
#   * candidate certificate + >=1 official certificate -> additional-certificate
#     25% overlap/residency check
#   * otherwise -> no additional same-level award rule at this stage
#
# GOVERNED HUMAN DECISION
# Authorized by: Joshua Hayes
# Date: 2026-10-08
# Decision: Additional certificates must be checked for a 25% additional
#           unique/resident-hour requirement against prior certificate awards.
# Basis: User-directed institutional rule for this audit.
# Do not alter without renewed review.
#
# No latest-catalog lineage selection is performed here.
#
# Run from repository root:
#   python -u .\scripts\build_multiple_award_dependency_ledger.py


ROOT = Path.cwd()
REPORTING = Path("data/processed/reporting")

EXPECTED_ORDINARY_PASS = 1_108

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = (
    REPORTING
    / f"multiple_award_dependency_ledger_{RUN_STAMP}"
)

CANDIDATE_LEDGER_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_multiple_award_candidate_ledger.csv"
)

PAIR_LEDGER_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_multiple_award_pair_ledger.csv"
)

SAME_FAMILY_ERROR_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_ERROR_same_family_official_award_survived.csv"
)

SAFE_METRICS_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_multiple_award_ledger_metrics.csv"
)

SAFE_ROUTE_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_multiple_award_route_counts.csv"
)

SAFE_PAIR_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_multiple_award_pair_counts.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
    candidates = sorted(
        [
            path
            for path in REPORTING.glob(
                pattern
            )
            if (
                path.is_dir()
                and (
                    path
                    / required_name
                ).exists()
            )
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(
            f"No directory matching {pattern} with {required_name}"
        )

    return candidates[0]


def first_existing_column(
    frame: pd.DataFrame,
    candidates: list[str],
    *,
    label: str,
    required: bool = True,
) -> str:
    for column in candidates:
        if column in frame.columns:
            return column

    if required:
        raise RuntimeError(
            f"Could not resolve {label}. Tried: "
            + ", ".join(
                candidates
            )
            + "\nColumns found: "
            + " | ".join(
                map(
                    str,
                    frame.columns,
                )
            )
        )

    return ""


def normalize_family(
    value: object,
) -> str:
    return (
        txt(
            value
        )
        .upper()
        .replace(
            " ",
            "_",
        )
    )


def official_award_type(
    degree_code: object,
) -> str:
    code = txt(
        degree_code
    ).upper()

    if code in {
        "AA",
        "AS",
        "AAS",
        "AAT",
    }:
        return "ASSOCIATE"

    if (
        code.startswith(
            "CERT"
        )
        or code == "IA"
    ):
        return "CERT"

    return "REVIEW"


def candidate_type(
    value: object,
) -> str:
    code = txt(
        value
    ).upper()

    if code == "ASSOCIATE":
        return "ASSOCIATE"

    if code == "CERT":
        return "CERT"

    return "REVIEW"


def catalog_start_year(
    catalog_year: object,
) -> int | None:
    value = txt(
        catalog_year
    )

    if len(
        value
    ) < 4:
        return None

    try:
        return int(
            value[:4]
        )
    except ValueError:
        return None


def second_associate_policy(
    catalog_year: object,
) -> str:
    start = catalog_start_year(
        catalog_year
    )

    if start is None:
        return "REVIEW_CATALOG_YEAR"

    if start >= 2025:
        return (
            "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
        )

    return (
        "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
    )


def main() -> None:
    current_dir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_awardability_pass_combinations.csv",
    )

    official_dir = latest_dir(
        "official_award_screening_final_*",
        "RESTRICTED_canonical_official_awards_final_mapping.csv",
    )

    pass_path = (
        current_dir
        / "RESTRICTED_awardability_pass_combinations.csv"
    )

    official_path = (
        official_dir
        / "RESTRICTED_canonical_official_awards_final_mapping.csv"
    )

    candidates = pd.read_csv(
        pass_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    official = pd.read_csv(
        official_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    if len(
        candidates
    ) != EXPECTED_ORDINARY_PASS:
        raise RuntimeError(
            "Ordinary PASS universe changed: "
            f"{len(candidates):,} != "
            f"{EXPECTED_ORDINARY_PASS:,}"
        )

    for column in KEY:
        if column not in candidates.columns:
            raise RuntimeError(
                f"Candidate PASS file missing {column}"
            )

        candidates[
            column
        ] = (
            candidates[
                column
            ]
            .astype(str)
            .str.strip()
        )

    if candidates.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Ordinary PASS universe is not unique at candidate key."
        )

    candidate_family_col = first_existing_column(
        candidates,
        [
            "suppression_family",
            "canonical_suppression_family",
            "credential_lineage",
            "detected_lineage",
        ],
        label="candidate canonical family",
    )

    candidate_type_col = first_existing_column(
        candidates,
        [
            "awardability_credential_type",
            "credential_type",
        ],
        label="candidate credential type",
    )

    candidate_hours_col = first_existing_column(
        candidates,
        [
            "awardability_program_hours",
            "program_hours",
        ],
        label="candidate program hours",
    )

    # ------------------------------------------------------------------
    # Resolve official-award schema.
    # ------------------------------------------------------------------
    official_student_col = first_existing_column(
        official,
        [
            "student_id",
            "ID",
            "StudenID",
        ],
        label="official-award student ID",
    )

    official_family_col = first_existing_column(
        official,
        [
            "suppression_family",
            "canonical_suppression_family",
            "mapped_suppression_family",
            "credential_lineage",
            "institutional_lineage",
        ],
        label="official-award canonical family",
    )

    official_degree_col = first_existing_column(
        official,
        [
            "DegreeCode",
            "degree_code",
            "official_degree_code",
        ],
        label="official-award degree code",
    )

    official_term_col = first_existing_column(
        official,
        [
            "StudGradTerm",
            "grad_term",
            "award_term",
            "official_award_term",
        ],
        label="official-award term",
        required=False,
    )

    official_program_col = first_existing_column(
        official,
        [
            "Curr1ProgramCode",
            "program_code",
            "official_program_code",
        ],
        label="official program code",
        required=False,
    )

    official_major_col = first_existing_column(
        official,
        [
            "Major1Code",
            "major_code",
            "official_major_code",
        ],
        label="official major code",
        required=False,
    )

    # Canonicalize official awards.
    off = pd.DataFrame()

    off[
        "student_id"
    ] = (
        official[
            official_student_col
        ]
        .astype(str)
        .str.strip()
    )

    off[
        "official_family"
    ] = official[
        official_family_col
    ].map(
        normalize_family
    )

    off[
        "official_degree_code"
    ] = (
        official[
            official_degree_col
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    off[
        "official_award_type"
    ] = off[
        "official_degree_code"
    ].map(
        official_award_type
    )

    off[
        "official_award_term"
    ] = (
        official[
            official_term_col
        ].astype(str).str.strip()
        if official_term_col
        else ""
    )

    off[
        "official_program_code"
    ] = (
        official[
            official_program_col
        ].astype(str).str.strip()
        if official_program_col
        else ""
    )

    off[
        "official_major_code"
    ] = (
        official[
            official_major_col
        ].astype(str).str.strip()
        if official_major_col
        else ""
    )

    off = off[
        off[
            "student_id"
        ].ne("")
        & off[
            "official_family"
        ].ne("")
    ].copy()

    # Preserve distinct canonical official awards. Exact duplicate source rows
    # should already have been removed upstream, but this protects the ledger.
    off = off.drop_duplicates(
        [
            "student_id",
            "official_family",
            "official_degree_code",
            "official_award_term",
            "official_program_code",
            "official_major_code",
        ]
    ).copy()

    # ------------------------------------------------------------------
    # Candidate canonical fields.
    # ------------------------------------------------------------------
    work = candidates.copy()

    work[
        "candidate_family"
    ] = work[
        candidate_family_col
    ].map(
        normalize_family
    )

    work[
        "candidate_award_type"
    ] = work[
        candidate_type_col
    ].map(
        candidate_type
    )

    work[
        "candidate_program_hours_numeric"
    ] = pd.to_numeric(
        work[
            candidate_hours_col
        ],
        errors="coerce",
    )

    unresolved_type = work[
        work[
            "candidate_award_type"
        ].eq(
            "REVIEW"
        )
    ]

    if not unresolved_type.empty:
        raise RuntimeError(
            "Ordinary PASS universe contains unresolved candidate award type."
        )

    unresolved_hours = work[
        work[
            "candidate_program_hours_numeric"
        ].isna()
    ]

    if not unresolved_hours.empty:
        raise RuntimeError(
            "Ordinary PASS universe contains unresolved candidate program hours."
        )

    # ------------------------------------------------------------------
    # Same-family guard. Official-award screening should have removed every
    # candidate whose canonical family is already awarded.
    # ------------------------------------------------------------------
    official_family_pairs = set(
        off[
            [
                "student_id",
                "official_family",
            ]
        ]
        .itertuples(
            index=False,
            name=None,
        )
    )

    work[
        "same_family_official_award_exists"
    ] = [
        (
            student_id,
            family,
        )
        in official_family_pairs
        for student_id, family
        in work[
            [
                "student_id",
                "candidate_family",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    same_family = work[
        work[
            "same_family_official_award_exists"
        ]
    ].copy()

    if not same_family.empty:
        same_family.to_csv(
            SAME_FAMILY_ERROR_OUT,
            index=False,
        )

        raise RuntimeError(
            "Same-family official awards survived upstream suppression: "
            f"{len(same_family):,}. Diagnostic written."
        )

    # ------------------------------------------------------------------
    # Student-level official award inventory.
    # ------------------------------------------------------------------
    official_by_student = {
        student_id: group.copy()
        for student_id, group
        in off.groupby(
            "student_id",
            sort=False,
        )
    }

    candidate_rows = []
    pair_rows = []

    for candidate in work.itertuples(
        index=False
    ):
        student_official = official_by_student.get(
            candidate.student_id,
            off.iloc[
                0:0
            ].copy(),
        )

        associate_awards = student_official[
            student_official[
                "official_award_type"
            ].eq(
                "ASSOCIATE"
            )
        ].copy()

        certificate_awards = student_official[
            student_official[
                "official_award_type"
            ].eq(
                "CERT"
            )
        ].copy()

        review_awards = student_official[
            student_official[
                "official_award_type"
            ].eq(
                "REVIEW"
            )
        ].copy()

        distinct_official_families = (
            student_official[
                "official_family"
            ].nunique()
        )

        distinct_associate_families = (
            associate_awards[
                "official_family"
            ].nunique()
        )

        distinct_certificate_families = (
            certificate_awards[
                "official_family"
            ].nunique()
        )

        candidate_award_type = (
            candidate.candidate_award_type
        )

        if (
            distinct_official_families
            == 0
        ):
            route = (
                "FIRST_LSCO_CREDENTIAL"
            )
            rule = (
                "NO_ADDITIONAL_AWARD_RULE"
            )

        elif (
            candidate_award_type
            == "ASSOCIATE"
            and distinct_associate_families
            > 0
        ):
            route = (
                "SECOND_ASSOCIATE_REQUIRES_EXTRA_HOURS_TEST"
            )
            rule = second_associate_policy(
                candidate.catalog_year
            )

        elif (
            candidate_award_type
            == "CERT"
            and distinct_certificate_families
            > 0
        ):
            route = (
                "ADDITIONAL_CERTIFICATE_REQUIRES_25_PERCENT_TEST"
            )
            rule = (
                "ADDITIONAL_CERTIFICATE_25_PERCENT_UNIQUE_RESIDENT"
            )

        elif (
            candidate_award_type
            == "ASSOCIATE"
        ):
            route = (
                "ASSOCIATE_WITH_PRIOR_CERTIFICATE_ONLY"
            )
            rule = (
                "NO_SECOND_ASSOCIATE_RULE"
            )

        elif (
            candidate_award_type
            == "CERT"
        ):
            route = (
                "CERTIFICATE_WITH_PRIOR_ASSOCIATE_ONLY"
            )
            rule = (
                "NO_ADDITIONAL_CERTIFICATE_RULE"
            )

        else:
            route = (
                "REVIEW"
            )
            rule = (
                "REVIEW"
            )

        required_unique_hours = ""

        if (
            route
            == "ADDITIONAL_CERTIFICATE_REQUIRES_25_PERCENT_TEST"
        ):
            required_unique_hours = int(
                math.ceil(
                    float(
                        candidate.candidate_program_hours_numeric
                    )
                    * 0.25
                )
            )

        candidate_rows.append(
            {
                **candidate._asdict(),
                "official_award_family_count": (
                    distinct_official_families
                ),
                "official_associate_family_count": (
                    distinct_associate_families
                ),
                "official_certificate_family_count": (
                    distinct_certificate_families
                ),
                "official_review_award_count": len(
                    review_awards
                ),
                "multiple_award_route": route,
                "multiple_award_rule": rule,
                "additional_certificate_required_unique_resident_hours": (
                    required_unique_hours
                ),
            }
        )

        # Pair only with prior official awards relevant to the same-level rule.
        if (
            route
            == "SECOND_ASSOCIATE_REQUIRES_EXTRA_HOURS_TEST"
        ):
            relevant = (
                associate_awards
            )
            pair_type = (
                "SECOND_ASSOCIATE_PAIR"
            )

        elif (
            route
            == "ADDITIONAL_CERTIFICATE_REQUIRES_25_PERCENT_TEST"
        ):
            relevant = (
                certificate_awards
            )
            pair_type = (
                "ADDITIONAL_CERTIFICATE_PAIR"
            )

        else:
            relevant = (
                student_official.iloc[
                    0:0
                ]
            )
            pair_type = ""

        for prior in relevant.itertuples(
            index=False
        ):
            pair_rows.append(
                {
                    "student_id": candidate.student_id,
                    "candidate_catalog_year": candidate.catalog_year,
                    "candidate_credential_id": candidate.credential_id,
                    "candidate_family": candidate.candidate_family,
                    "candidate_award_type": candidate.candidate_award_type,
                    "candidate_program_hours": candidate.candidate_program_hours_numeric,
                    "pair_type": pair_type,
                    "multiple_award_rule": rule,
                    "candidate_required_unique_resident_hours": (
                        required_unique_hours
                    ),
                    "prior_official_family": prior.official_family,
                    "prior_official_award_type": prior.official_award_type,
                    "prior_official_degree_code": prior.official_degree_code,
                    "prior_official_award_term": prior.official_award_term,
                    "prior_official_program_code": prior.official_program_code,
                    "prior_official_major_code": prior.official_major_code,
                    # Deliberately unresolved at ledger stage:
                    # these require mapping the official award family to an
                    # appropriate historical modeled plan before overlap math.
                    "prior_modeled_plan_status": "NOT_YET_MAPPED",
                    "prior_modeled_program_hours": "",
                    "old_rule_total_earned_threshold": "",
                    "unique_resident_hours_beyond_prior_plan": "",
                    "unique_resident_gpa": "",
                    "pair_adjudication_status": "PENDING_PLAN_OVERLAP_TEST",
                }
            )

    candidate_ledger = pd.DataFrame(
        candidate_rows
    )

    pair_ledger = pd.DataFrame(
        pair_rows
    )

    if len(
        candidate_ledger
    ) != EXPECTED_ORDINARY_PASS:
        raise RuntimeError(
            "Candidate ledger row count changed."
        )

    if candidate_ledger.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Candidate ledger is not unique at candidate key."
        )

    candidate_ledger.to_csv(
        CANDIDATE_LEDGER_OUT,
        index=False,
    )

    pair_ledger.to_csv(
        PAIR_LEDGER_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe output.
    # ------------------------------------------------------------------
    route_counts = (
        candidate_ledger.groupby(
            [
                "candidate_award_type",
                "multiple_award_route",
                "multiple_award_rule",
            ],
            dropna=False,
        )
        .agg(
            candidate_combinations=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
        .reset_index()
        .sort_values(
            "candidate_combinations",
            ascending=False,
        )
    )

    route_counts.to_csv(
        SAFE_ROUTE_OUT,
        index=False,
    )

    if pair_ledger.empty:
        pair_counts = pd.DataFrame(
            columns=[
                "pair_type",
                "multiple_award_rule",
                "candidate_combinations",
                "distinct_students",
                "prior_official_families",
            ]
        )
    else:
        pair_counts = (
            pair_ledger.groupby(
                [
                    "pair_type",
                    "multiple_award_rule",
                ],
                dropna=False,
            )
            .agg(
                candidate_combinations=(
                    "candidate_credential_id",
                    "size",
                ),
                distinct_students=(
                    "student_id",
                    "nunique",
                ),
                prior_official_families=(
                    "prior_official_family",
                    "nunique",
                ),
            )
            .reset_index()
        )

    pair_counts.to_csv(
        SAFE_PAIR_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "ordinary_awardability_pass_combinations",
                "value": len(
                    candidate_ledger
                ),
            },
            {
                "metric": "first_lsco_credential_candidates",
                "value": int(
                    candidate_ledger[
                        "multiple_award_route"
                    ].eq(
                        "FIRST_LSCO_CREDENTIAL"
                    ).sum()
                ),
            },
            {
                "metric": "second_associate_candidates",
                "value": int(
                    candidate_ledger[
                        "multiple_award_route"
                    ].eq(
                        "SECOND_ASSOCIATE_REQUIRES_EXTRA_HOURS_TEST"
                    ).sum()
                ),
            },
            {
                "metric": "additional_certificate_candidates",
                "value": int(
                    candidate_ledger[
                        "multiple_award_route"
                    ].eq(
                        "ADDITIONAL_CERTIFICATE_REQUIRES_25_PERCENT_TEST"
                    ).sum()
                ),
            },
            {
                "metric": "associate_with_prior_certificate_only",
                "value": int(
                    candidate_ledger[
                        "multiple_award_route"
                    ].eq(
                        "ASSOCIATE_WITH_PRIOR_CERTIFICATE_ONLY"
                    ).sum()
                ),
            },
            {
                "metric": "certificate_with_prior_associate_only",
                "value": int(
                    candidate_ledger[
                        "multiple_award_route"
                    ].eq(
                        "CERTIFICATE_WITH_PRIOR_ASSOCIATE_ONLY"
                    ).sum()
                ),
            },
            {
                "metric": "same_family_official_award_survivors",
                "value": len(
                    same_family
                ),
            },
            {
                "metric": "same_level_pair_rows",
                "value": len(
                    pair_ledger
                ),
            },
            {
                "metric": "unresolved_official_award_type_rows_in_candidate_students",
                "value": int(
                    candidate_ledger[
                        "official_review_award_count"
                    ].gt(
                        0
                    ).sum()
                ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 110)
    print("MULTIPLE-AWARD / DEPENDENCY LEDGER — BUILT")
    print("=" * 110)
    print(
        f"Ordinary awardability PASS combinations:  {len(candidate_ledger):,}"
    )
    print(
        f"Same-family award survivors:              {len(same_family):,}"
    )
    print()
    print("ROUTING COUNTS")
    print(
        route_counts.to_string(
            index=False
        )
    )
    print()
    print("PAIR COUNTS")
    if pair_counts.empty:
        print("None")
    else:
        print(
            pair_counts.to_string(
                index=False
            )
        )
    print()
    print(
        "Parent/child stack rule: NON-CONSUMING. "
        "No stack relationship suppresses a candidate here."
    )
    print(
        "Second-associate and additional-certificate pairs remain PENDING "
        "until the prior official award is mapped to its modeled plan and "
        "course-set overlap is calculated."
    )
    print()
    print(
        f"Current awardability source: {current_dir}"
    )
    print(
        f"Official-award source:       {official_dir}"
    )
    print(
        f"Output directory:            {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
