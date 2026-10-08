from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# STEP 5C — CLOSE CROSS-LINEAGE GOVERNANCE UNDER THE PRIOR CANONICAL IDENTITY MODEL
# ======================================================================================
#
# Recovered prior invariant:
#   After canonical alias repair, the old workflow explicitly required ZERO
#   consuming governance rows and hard-failed if any remained.
#
# Therefore:
#   * exact canonical identity may consume / represent a candidate;
#   * a distinct, nonblank canonical lineage is not representationally consuming;
#   * cross-lineage governance rows may describe stack / parent-child / unrelated
#     behavior, but they do not suppress the candidate after the consuming layer
#     has been closed.
#
# This script does NOT alter the final governance table.
# It only removes artificial REVIEW status created by the interim v3 screen for
# previously unseen but fully canonicalized cross-lineage pairs.
#
# Hard-stop safeguards:
#   1. final governance table must contain zero consuming rows;
#   2. every candidate currently in governance REVIEW must be supported only by
#      REVIEW_UNGOVERNED_PAIR rows (not unmapped official lineages);
#   3. every such pair must have two nonblank, distinct canonical lineages;
#   4. exact-lineage represented candidates remain represented;
#   5. ordinary PASS universe stays 1,108 rows.
#
# No second-associate arithmetic.
# No 25% additional-certificate arithmetic.
# No latest-catalog lineage selection.
#
# Run:
#   python -u .\scripts\close_cross_lineage_governance_reviews.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_PASS = 1_108

GOVERNANCE = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "governed_lineage_relationships_final.csv"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"closed_cross_lineage_governance_{STAMP}"
)

CANDIDATE_OUT = (
    OUT_DIR
    / "RESTRICTED_closed_cross_lineage_governance_candidates.csv"
)

PAIR_OUT = (
    OUT_DIR
    / "RESTRICTED_closed_cross_lineage_governance_pairs.csv"
)

SAFE_METRICS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_closed_cross_lineage_governance_metrics.csv"
)

SAFE_ROUTE_OUT = (
    OUT_DIR
    / "FERPA_SAFE_closed_cross_lineage_route_counts.csv"
)

SAFE_PAIR_OUT = (
    OUT_DIR
    / "FERPA_SAFE_closed_cross_lineage_pair_status.csv"
)

SAFE_REMAINING_REVIEW_OUT = (
    OUT_DIR
    / "FERPA_SAFE_remaining_review_counts.csv"
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


def truthy(value: object) -> bool:
    return txt(value).upper() in {
        "TRUE",
        "T",
        "YES",
        "Y",
        "1",
    }


def as_int(value: object) -> int:
    value = txt(value)
    if not value:
        return 0
    return int(float(value))


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
    matches = sorted(
        [
            path
            for path in REPORTING.glob(pattern)
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

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return matches[0]


def route_row(row: pd.Series) -> str:
    governed = txt(
        row.get(
            "governed_dependency_disposition",
            "",
        )
    )

    if governed == "REPRESENTED_BY_OFFICIAL_AWARD":
        return "STOP_REPRESENTED_BY_OFFICIAL_AWARD"

    if governed == "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING":
        return "REVIEW_BEFORE_MULTIPLE_AWARD_TEST"

    if txt(
        row.get(
            "candidate_metadata_status",
            "",
        )
    ) == "REVIEW":
        return "REVIEW_CANDIDATE_AWARD_METADATA"

    category = txt(
        row.get(
            "candidate_award_category",
            "",
        )
    )

    if category == "ASSOCIATE":
        if as_int(
            row.get(
                "official_associate_award_count",
                0,
            )
        ) > 0:
            return "SECOND_ASSOCIATE_TEST_PENDING"

        return "NO_SECOND_ASSOCIATE_RULE"

    if category == "CERTIFICATE":
        if as_int(
            row.get(
                "official_certificate_award_count",
                0,
            )
        ) > 0:
            return "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"

        return "NO_ADDITIONAL_CERTIFICATE_RULE"

    if category == "INSTITUTIONAL_AWARD":
        return "INSTITUTIONAL_AWARD_MULTIPLE_POLICY_REVIEW"

    return "REVIEW_CANDIDATE_AWARD_METADATA"


def main() -> None:
    source_dir = latest_dir(
        "source_backed_award_metadata_*",
        "RESTRICTED_source_backed_award_metadata_candidates.csv",
    )

    gov_screen_dir = latest_dir(
        "current_governed_dependency_screen_*",
        "RESTRICTED_current_candidate_official_governance_pairs.csv",
    )

    candidate_path = (
        source_dir
        / "RESTRICTED_source_backed_award_metadata_candidates.csv"
    )

    pair_path = (
        gov_screen_dir
        / "RESTRICTED_current_candidate_official_governance_pairs.csv"
    )

    candidates = pd.read_csv(
        candidate_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    pairs = pd.read_csv(
        pair_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    governance = pd.read_csv(
        GOVERNANCE,
        dtype=str,
        low_memory=False,
    ).fillna("")

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    # ------------------------------------------------------------------
    # Global invariant: consuming governance was intentionally closed.
    # ------------------------------------------------------------------
    consuming = governance[
        governance[
            "awarded_represents_detected"
        ].map(
            truthy
        )
        & ~governance[
            "detected_remains_additional_award"
        ].map(
            truthy
        )
    ].copy()

    if not consuming.empty:
        raise RuntimeError(
            "Final governance table contains consuming relationships. "
            "The closed canonical-identity invariant cannot be applied."
        )

    if len(
        candidates
    ) != EXPECTED_PASS:
        raise RuntimeError(
            f"Candidate universe changed: {len(candidates):,} != {EXPECTED_PASS:,}"
        )

    if candidates.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Candidate universe is not unique at student/catalog/credential."
        )

    # ------------------------------------------------------------------
    # Identify the current candidate-level governance review universe.
    # ------------------------------------------------------------------
    review_candidates = candidates[
        candidates[
            "governed_dependency_disposition"
        ].eq(
            "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
        )
    ].copy()

    review_keys = set(
        review_candidates[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    pair_keys = list(
        pairs[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    pairs[
        "_candidate_is_review"
    ] = [
        key in review_keys
        for key in pair_keys
    ]

    relevant_pairs = pairs[
        pairs[
            "_candidate_is_review"
        ]
        & pairs[
            "governance_pair_status"
        ].str.startswith(
            "REVIEW_",
            na=False,
        )
    ].copy()

    if len(
        review_candidates
    ) and relevant_pairs.empty:
        raise RuntimeError(
            "Candidate governance REVIEW exists but no REVIEW pair evidence was found."
        )

    # The closure operation is valid only for previously unseen, fully
    # canonicalized cross-lineage pairs.
    bad_status = relevant_pairs[
        ~relevant_pairs[
            "governance_pair_status"
        ].eq(
            "REVIEW_UNGOVERNED_PAIR"
        )
    ].copy()

    if not bad_status.empty:
        raise RuntimeError(
            "Governance REVIEW includes a status other than "
            "REVIEW_UNGOVERNED_PAIR. Do not auto-close."
        )

    blank_identity = relevant_pairs[
        relevant_pairs[
            "candidate_lineage"
        ].eq("")
        | relevant_pairs[
            "official_family"
        ].eq("")
    ].copy()

    if not blank_identity.empty:
        raise RuntimeError(
            "At least one ungoverned review pair has a blank canonical lineage."
        )

    exact_identity = relevant_pairs[
        relevant_pairs[
            "candidate_lineage"
        ].eq(
            relevant_pairs[
                "official_family"
            ]
        )
    ].copy()

    if not exact_identity.empty:
        raise RuntimeError(
            "At least one supposedly ungoverned review pair is exact canonical identity."
        )

    review_pair_candidate_keys = set(
        relevant_pairs[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    missing_pair_support = (
        review_keys
        - review_pair_candidate_keys
    )

    if missing_pair_support:
        raise RuntimeError(
            "Some candidate governance REVIEW rows lack pair support: "
            f"{len(missing_pair_support):,}"
        )

    # ------------------------------------------------------------------
    # Close the artificial cross-lineage review.
    # ------------------------------------------------------------------
    work = candidates.copy()

    work[
        "governance_disposition_before_closure"
    ] = work[
        "governed_dependency_disposition"
    ]

    work[
        "cross_lineage_closure_applied"
    ] = False

    review_mask = work[
        "governed_dependency_disposition"
    ].eq(
        "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
    )

    work.loc[
        review_mask,
        "governed_dependency_disposition",
    ] = "REMAINS_ADDITIONAL_CANDIDATE"

    work.loc[
        review_mask,
        "cross_lineage_closure_applied",
    ] = True

    work[
        "multiple_award_route_before_cross_lineage_closure"
    ] = work[
        "multiple_award_route"
    ]

    work[
        "multiple_award_route"
    ] = work.apply(
        route_row,
        axis=1,
    )

    work[
        "cross_lineage_route_changed"
    ] = (
        work[
            "multiple_award_route"
        ]
        != work[
            "multiple_award_route_before_cross_lineage_closure"
        ]
    )

    # Pair evidence is copied with a derived status; the source governance
    # table itself is never mutated.
    pair_work = pairs.copy()

    pair_mask = (
        pair_work[
            "_candidate_is_review"
        ]
        & pair_work[
            "governance_pair_status"
        ].eq(
            "REVIEW_UNGOVERNED_PAIR"
        )
    )

    pair_work[
        "governance_pair_status_before_closure"
    ] = pair_work[
        "governance_pair_status"
    ]

    pair_work[
        "cross_lineage_closure_applied"
    ] = False

    pair_work.loc[
        pair_mask,
        "governance_pair_status",
    ] = (
        "NONCONSUMING_BY_CLOSED_CANONICAL_IDENTITY_MODEL"
    )

    pair_work.loc[
        pair_mask,
        "cross_lineage_closure_applied",
    ] = True

    pair_work = pair_work.drop(
        columns=[
            "_candidate_is_review",
        ]
    )

    # ------------------------------------------------------------------
    # Regression guards.
    # ------------------------------------------------------------------
    represented_before = int(
        candidates[
            "governed_dependency_disposition"
        ].eq(
            "REPRESENTED_BY_OFFICIAL_AWARD"
        ).sum()
    )

    represented_after = int(
        work[
            "governed_dependency_disposition"
        ].eq(
            "REPRESENTED_BY_OFFICIAL_AWARD"
        ).sum()
    )

    if represented_before != represented_after:
        raise RuntimeError(
            "Represented-candidate count changed during cross-lineage closure."
        )

    if work[
        "governed_dependency_disposition"
    ].eq(
        "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
    ).any():
        raise RuntimeError(
            "Candidate governance REVIEW remains after closure."
        )

    if len(
        work
    ) != EXPECTED_PASS:
        raise RuntimeError(
            "Candidate row count changed during cross-lineage closure."
        )

    if work.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Candidate keys duplicated during cross-lineage closure."
        )

    # ------------------------------------------------------------------
    # Outputs.
    # ------------------------------------------------------------------
    work.to_csv(
        CANDIDATE_OUT,
        index=False,
    )

    pair_work.to_csv(
        PAIR_OUT,
        index=False,
    )

    route_summary = (
        work.groupby(
            [
                "candidate_award_category",
                "governed_dependency_disposition",
                "multiple_award_route",
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

    route_summary.to_csv(
        SAFE_ROUTE_OUT,
        index=False,
    )

    pair_summary = (
        pair_work.groupby(
            "governance_pair_status",
            dropna=False,
        )
        .size()
        .reset_index(
            name="pair_rows"
        )
        .sort_values(
            "pair_rows",
            ascending=False,
        )
    )

    pair_summary.to_csv(
        SAFE_PAIR_OUT,
        index=False,
    )

    remaining_review = (
        work[
            work[
                "multiple_award_route"
            ].str.startswith(
                "REVIEW_",
                na=False,
            )
        ]
        .groupby(
            [
                "catalog_year",
                "credential_id",
                "candidate_award_category",
                "multiple_award_route",
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
    )

    remaining_review.to_csv(
        SAFE_REMAINING_REVIEW_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "ordinary_awardability_pass_combinations",
                "value": len(
                    work
                ),
            },
            {
                "metric": "final_governance_consuming_rows",
                "value": len(
                    consuming
                ),
            },
            {
                "metric": "candidate_governance_reviews_before_closure",
                "value": len(
                    review_candidates
                ),
            },
            {
                "metric": "cross_lineage_review_pair_rows_closed",
                "value": int(
                    pair_mask.sum()
                ),
            },
            {
                "metric": "candidate_governance_reviews_after_closure",
                "value": int(
                    work[
                        "governed_dependency_disposition"
                    ].eq(
                        "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
                    ).sum()
                ),
            },
            {
                "metric": "represented_candidates_preserved",
                "value": represented_after,
            },
            {
                "metric": "remaining_metadata_review_candidates",
                "value": int(
                    work[
                        "candidate_metadata_status"
                    ].eq(
                        "REVIEW"
                    ).sum()
                ),
            },
            {
                "metric": "second_associate_test_pending",
                "value": int(
                    work[
                        "multiple_award_route"
                    ].eq(
                        "SECOND_ASSOCIATE_TEST_PENDING"
                    ).sum()
                ),
            },
            {
                "metric": "additional_certificate_25_percent_test_pending",
                "value": int(
                    work[
                        "multiple_award_route"
                    ].eq(
                        "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"
                    ).sum()
                ),
            },
            {
                "metric": "no_second_associate_rule",
                "value": int(
                    work[
                        "multiple_award_route"
                    ].eq(
                        "NO_SECOND_ASSOCIATE_RULE"
                    ).sum()
                ),
            },
            {
                "metric": "no_additional_certificate_rule",
                "value": int(
                    work[
                        "multiple_award_route"
                    ].eq(
                        "NO_ADDITIONAL_CERTIFICATE_RULE"
                    ).sum()
                ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 112)
    print("CROSS-LINEAGE GOVERNANCE CLOSURE — COMPLETE")
    print("=" * 112)
    print(
        f"Ordinary awardability PASS combinations:      {len(work):,}"
    )
    print(
        f"Final governance consuming rows:             {len(consuming):,}"
    )
    print(
        "Candidate governance REVIEW before closure:  "
        f"{len(review_candidates):,}"
    )
    print(
        "Cross-lineage REVIEW pair rows closed:       "
        f"{int(pair_mask.sum()):,}"
    )
    print(
        "Candidate governance REVIEW after closure:   "
        f"{int(work['governed_dependency_disposition'].eq('REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING').sum()):,}"
    )
    print(
        "Represented candidates preserved:            "
        f"{represented_after:,}"
    )
    print(
        "Remaining candidate metadata REVIEW:         "
        f"{int(work['candidate_metadata_status'].eq('REVIEW').sum()):,}"
    )
    print()
    print("ROUTES")
    print(
        route_summary.to_string(
            index=False
        )
    )
    print()
    print("PAIR STATUS")
    print(
        pair_summary.to_string(
            index=False
        )
    )
    print()
    if remaining_review.empty:
        print("REMAINING REVIEW ROUTES: 0")
    else:
        print("REMAINING REVIEW ROUTES")
        print(
            remaining_review.to_string(
                index=False
            )
        )
    print()
    print(
        "Control: final governance table was not mutated."
    )
    print(
        "Control: only fully canonicalized, nonblank, distinct-lineage "
        "REVIEW_UNGOVERNED_PAIR evidence was closed."
    )
    print(
        "Control: no second-associate / additional-certificate arithmetic "
        "was performed."
    )
    print()
    print(
        f"Source metadata layer: {source_dir}"
    )
    print(
        f"Pair evidence source:  {gov_screen_dir}"
    )
    print(
        f"Output directory:      {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
