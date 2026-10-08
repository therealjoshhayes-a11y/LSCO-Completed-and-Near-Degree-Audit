from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# CURRENT MULTIPLE-AWARD GATE — CONSOLIDATE / REPAIR
# ======================================================================================
#
# Purpose:
#   Consolidate the current multiple-award layer after direct catalog verification
#   established that LSCO does NOT impose a separate "25% additional unique/resident
#   hours beyond a prior certificate" rule.
#
#   The ordinary awardability layer already tested the catalog-year certificate
#   residency/GPA/minimum-C requirements. A prior DIFFERENT certificate therefore
#   creates no additional certificate-overlap gate. Same/equivalent certificates
#   are handled upstream by official-award suppression / canonical identity.
#
# GOVERNANCE CORRECTION — HUMAN AUTHORIZED
# Authorized by: Joshua Hayes
# Date: 2026-10-08
# Decision:
#   Rescind the earlier audit-specific rule that routed additional certificates to
#   a 25% UNIQUE/ADDITIONAL resident-hour test against prior certificate awards.
#   Distinct certificate candidates receive NO additional multiple-certificate
#   arithmetic beyond ordinary catalog awardability.
# Basis:
#   Direct review of LSCO catalogs. The 25% language is the ordinary residency
#   requirement for the certificate itself (2025-2026 forward), not a requirement
#   for 25% new coursework beyond another certificate. Older catalogs use the
#   ordinary 13-SCH residence requirement. Multiple-award language supplies a
#   separate extra-hours rule for associate degrees, not certificates.
# Do not restore the rescinded rule without renewed source review and authorization.
#
# This script:
#   * preserves the 1,108 ordinary-awardability PASS universe;
#   * preserves the source-validated represented-by-official-award stops;
#   * preserves the 4 unresolved 2021-2022 certificate-vs-IA metadata reviews;
#   * converts BOTH certificate routes
#         ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING
#         NO_ADDITIONAL_CERTIFICATE_RULE
#     to PASS_MULTIPLE_AWARD_GATE;
#   * consolidates the already-run second-associate Stage 1 / Stage 2 results;
#   * produces the candidate universe ready for LATEST-AWARDABLE-CATALOG selection
#     within each student / canonical lineage.
#
# This script DOES NOT:
#   * alter the final governance table;
#   * mutate ordinary awardability outputs;
#   * change second-associate decisions;
#   * select latest catalog within lineage;
#   * issue the final student award list yet.
#
# Run from repository root:
#   python -u .\scripts\finalize_current_multiple_award_gate.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_ORDINARY_PASS = 1_108
EXPECTED_RESCINDED_CERTIFICATE_ROUTE = 478
EXPECTED_SECOND_ASSOCIATE_ROUTE = 365
EXPECTED_REPRESENTED = 41
EXPECTED_METADATA_REVIEW = 4

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = (
    REPORTING
    / f"current_multiple_award_gate_{STAMP}"
)

FULL_OUT = (
    OUT_DIR
    / "RESTRICTED_current_multiple_award_gate.csv"
)

READY_OUT = (
    OUT_DIR
    / "RESTRICTED_unawarded_complete_awardable_before_lineage_selection.csv"
)

FAIL_OUT = (
    OUT_DIR
    / "RESTRICTED_multiple_award_gate_failures.csv"
)

REVIEW_OUT = (
    OUT_DIR
    / "RESTRICTED_multiple_award_gate_reviews.csv"
)

STOP_OUT = (
    OUT_DIR
    / "RESTRICTED_represented_by_official_award_stops.csv"
)

SAFE_SUMMARY_OUT = (
    OUT_DIR
    / "FERPA_SAFE_multiple_award_gate_summary.csv"
)

SAFE_ROUTE_OUT = (
    OUT_DIR
    / "FERPA_SAFE_multiple_award_gate_by_source_route.csv"
)

SAFE_LINEAGE_OUT = (
    OUT_DIR
    / "FERPA_SAFE_preselection_lineage_multiplicity.csv"
)

SAFE_METRICS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_multiple_award_gate_metrics.csv"
)


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


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


def main() -> None:
    source_dir = latest_dir(
        "closed_cross_lineage_governance_*",
        "RESTRICTED_closed_cross_lineage_governance_candidates.csv",
    )

    stage1_dir = latest_dir(
        "second_associate_stage1_current_*",
        "RESTRICTED_second_associate_stage1_current.csv",
    )

    stage2_dir = latest_dir(
        "second_associate_stage2_current_*",
        "RESTRICTED_second_associate_stage2_final.csv",
    )

    source_path = (
        source_dir
        / "RESTRICTED_closed_cross_lineage_governance_candidates.csv"
    )

    stage1_path = (
        stage1_dir
        / "RESTRICTED_second_associate_stage1_current.csv"
    )

    stage2_path = (
        stage2_dir
        / "RESTRICTED_second_associate_stage2_final.csv"
    )

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    source = pd.read_csv(
        source_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    stage1 = pd.read_csv(
        stage1_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    stage2 = pd.read_csv(
        stage2_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    # ------------------------------------------------------------------
    # Frozen-universe controls.
    # ------------------------------------------------------------------
    if len(source) != EXPECTED_ORDINARY_PASS:
        raise RuntimeError(
            "Ordinary-awardability PASS universe changed: "
            f"{len(source):,} != {EXPECTED_ORDINARY_PASS:,}"
        )

    if source.duplicated(KEY).any():
        raise RuntimeError(
            "Source candidate universe is not unique at student/catalog/credential."
        )

    represented_count = int(
        source[
            "governed_dependency_disposition"
        ].eq(
            "REPRESENTED_BY_OFFICIAL_AWARD"
        ).sum()
    )

    if represented_count != EXPECTED_REPRESENTED:
        raise RuntimeError(
            "Represented candidate count changed: "
            f"{represented_count:,} != {EXPECTED_REPRESENTED:,}"
        )

    metadata_review_count = int(
        source[
            "candidate_metadata_status"
        ].eq(
            "REVIEW"
        ).sum()
    )

    if metadata_review_count != EXPECTED_METADATA_REVIEW:
        raise RuntimeError(
            "Candidate metadata REVIEW count changed: "
            f"{metadata_review_count:,} != {EXPECTED_METADATA_REVIEW:,}"
        )

    rescinded_route_count = int(
        source[
            "multiple_award_route"
        ].eq(
            "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"
        ).sum()
    )

    if rescinded_route_count != EXPECTED_RESCINDED_CERTIFICATE_ROUTE:
        raise RuntimeError(
            "Rescinded certificate route count changed: "
            f"{rescinded_route_count:,} != "
            f"{EXPECTED_RESCINDED_CERTIFICATE_ROUTE:,}"
        )

    second_assoc_count = int(
        source[
            "multiple_award_route"
        ].eq(
            "SECOND_ASSOCIATE_TEST_PENDING"
        ).sum()
    )

    if second_assoc_count != EXPECTED_SECOND_ASSOCIATE_ROUTE:
        raise RuntimeError(
            "Second-associate route count changed: "
            f"{second_assoc_count:,} != "
            f"{EXPECTED_SECOND_ASSOCIATE_ROUTE:,}"
        )

    # ------------------------------------------------------------------
    # Stage-1 / Stage-2 coverage controls.
    # ------------------------------------------------------------------
    if stage1.duplicated(KEY).any():
        raise RuntimeError(
            "Stage-1 result is not unique at student/catalog/credential."
        )

    if len(stage1) != EXPECTED_SECOND_ASSOCIATE_ROUTE:
        raise RuntimeError(
            "Stage-1 second-associate universe changed: "
            f"{len(stage1):,} != {EXPECTED_SECOND_ASSOCIATE_ROUTE:,}"
        )

    pending_stage2 = stage1[
        stage1[
            "stage1_decision"
        ].eq(
            "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"
        )
    ].copy()

    if stage2.duplicated(KEY).any():
        raise RuntimeError(
            "Stage-2 result is not unique at student/catalog/credential."
        )

    pending_keys = set(
        pending_stage2[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    stage2_keys = set(
        stage2[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    if pending_keys != stage2_keys:
        raise RuntimeError(
            "Stage-2 final keys do not exactly match Stage-1 pending keys. "
            f"pending={len(pending_keys):,} stage2={len(stage2_keys):,}"
        )

    # ------------------------------------------------------------------
    # Merge second-associate evidence back to the full 1,108.
    # ------------------------------------------------------------------
    stage1_keep = stage1[
        KEY
        + [
            "stage1_decision",
            "stage1_reason",
            "stage1_evidence_basis",
        ]
    ].copy()

    stage2_keep = stage2[
        KEY
        + [
            "reconstructed_complete_prior_plan_count",
            "min_unique_resident_sch",
            "max_unique_resident_sch",
            "min_unique_resident_gpa",
            "max_unique_resident_gpa",
            "final_stage2_decision",
            "final_stage2_reason",
        ]
    ].copy()

    work = source.merge(
        stage1_keep,
        on=KEY,
        how="left",
        validate="one_to_one",
    )

    work = work.merge(
        stage2_keep,
        on=KEY,
        how="left",
        validate="one_to_one",
    )

    for column in (
        stage1_keep.columns.tolist()
        + stage2_keep.columns.tolist()
    ):
        if column in KEY:
            continue
        work[
            column
        ] = work[
            column
        ].fillna("")

    work[
        "certificate_25pct_additional_rule_rescinded"
    ] = work[
        "multiple_award_route"
    ].eq(
        "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"
    )

    work[
        "multiple_award_gate_status"
    ] = ""

    work[
        "multiple_award_gate_reason"
    ] = ""

    # ------------------------------------------------------------------
    # 1. Official representation remains a stop.
    # ------------------------------------------------------------------
    represented = work[
        "governed_dependency_disposition"
    ].eq(
        "REPRESENTED_BY_OFFICIAL_AWARD"
    )

    work.loc[
        represented,
        "multiple_award_gate_status",
    ] = "STOP_REPRESENTED_BY_OFFICIAL_AWARD"

    work.loc[
        represented,
        "multiple_award_gate_reason",
    ] = (
        "Candidate is represented by an existing official award after "
        "canonical identity/governance screening."
    )

    # ------------------------------------------------------------------
    # 2. Source metadata review remains review.
    # ------------------------------------------------------------------
    metadata_review = (
        ~represented
        & work[
            "candidate_metadata_status"
        ].eq(
            "REVIEW"
        )
    )

    work.loc[
        metadata_review,
        "multiple_award_gate_status",
    ] = "REVIEW_CANDIDATE_AWARD_METADATA"

    work.loc[
        metadata_review,
        "multiple_award_gate_reason",
    ] = (
        "Candidate award level remains unresolved from direct catalog evidence."
    )

    # ------------------------------------------------------------------
    # 3. DISTINCT certificates: no extra multiple-certificate arithmetic.
    #    Ordinary awardability already tested the actual catalog residency rule.
    # ------------------------------------------------------------------
    certificate_routes = (
        ~represented
        & ~metadata_review
        & work[
            "candidate_award_category"
        ].eq(
            "CERTIFICATE"
        )
        & work[
            "multiple_award_route"
        ].isin(
            [
                "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING",
                "NO_ADDITIONAL_CERTIFICATE_RULE",
            ]
        )
    )

    work.loc[
        certificate_routes,
        "multiple_award_gate_status",
    ] = "PASS_MULTIPLE_AWARD_GATE"

    work.loc[
        certificate_routes,
        "multiple_award_gate_reason",
    ] = (
        "Distinct certificate candidate; no catalog-supported additional "
        "certificate-overlap rule. Ordinary catalog residency/GPA/minimum-C "
        "requirements already passed."
    )

    # ------------------------------------------------------------------
    # 4. Associates with no prior associate award requiring an extra gate.
    # ------------------------------------------------------------------
    no_second_rule = (
        ~represented
        & ~metadata_review
        & work[
            "multiple_award_route"
        ].eq(
            "NO_SECOND_ASSOCIATE_RULE"
        )
    )

    work.loc[
        no_second_rule,
        "multiple_award_gate_status",
    ] = "PASS_MULTIPLE_AWARD_GATE"

    work.loc[
        no_second_rule,
        "multiple_award_gate_reason",
    ] = (
        "No second-associate rule is triggered by official award history."
    )

    # ------------------------------------------------------------------
    # 5. Consolidate second-associate Stage 1 and Stage 2.
    # ------------------------------------------------------------------
    second_rule = (
        ~represented
        & ~metadata_review
        & work[
            "multiple_award_route"
        ].eq(
            "SECOND_ASSOCIATE_TEST_PENDING"
        )
    )

    missing_stage1 = (
        second_rule
        & work[
            "stage1_decision"
        ].eq("")
    )

    if missing_stage1.any():
        raise RuntimeError(
            "Second-associate candidate missing Stage-1 decision."
        )

    old_pass = (
        second_rule
        & work[
            "stage1_decision"
        ].eq(
            "PASS_SECOND_ASSOCIATE_RULE"
        )
    )

    work.loc[
        old_pass,
        "multiple_award_gate_status",
    ] = "PASS_MULTIPLE_AWARD_GATE"

    work.loc[
        old_pass,
        "multiple_award_gate_reason",
    ] = work.loc[
        old_pass,
        "stage1_reason",
    ]

    old_fail = (
        second_rule
        & work[
            "stage1_decision"
        ].isin(
            [
                "FAIL_SECOND_ASSOCIATE_RULE",
                "FAIL_SAME_DEGREE_TYPE",
            ]
        )
    )

    work.loc[
        old_fail,
        "multiple_award_gate_status",
    ] = "FAIL_MULTIPLE_AWARD_GATE"

    work.loc[
        old_fail,
        "multiple_award_gate_reason",
    ] = work.loc[
        old_fail,
        "stage1_reason",
    ]

    needs_stage2 = (
        second_rule
        & work[
            "stage1_decision"
        ].eq(
            "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"
        )
    )

    missing_stage2 = (
        needs_stage2
        & work[
            "final_stage2_decision"
        ].eq("")
    )

    if missing_stage2.any():
        raise RuntimeError(
            "Stage-2-pending second-associate candidate missing final Stage-2 decision."
        )

    stage2_pass = (
        needs_stage2
        & work[
            "final_stage2_decision"
        ].eq(
            "PASS_SECOND_ASSOCIATE_2025_RULE"
        )
    )

    work.loc[
        stage2_pass,
        "multiple_award_gate_status",
    ] = "PASS_MULTIPLE_AWARD_GATE"

    work.loc[
        stage2_pass,
        "multiple_award_gate_reason",
    ] = work.loc[
        stage2_pass,
        "final_stage2_reason",
    ]

    stage2_fail = (
        needs_stage2
        & work[
            "final_stage2_decision"
        ].eq(
            "FAIL_SECOND_ASSOCIATE_2025_RULE"
        )
    )

    work.loc[
        stage2_fail,
        "multiple_award_gate_status",
    ] = "FAIL_MULTIPLE_AWARD_GATE"

    work.loc[
        stage2_fail,
        "multiple_award_gate_reason",
    ] = work.loc[
        stage2_fail,
        "final_stage2_reason",
    ]

    stage2_review = (
        needs_stage2
        & work[
            "final_stage2_decision"
        ].eq(
            "REVIEW_SECOND_ASSOCIATE_2025_RULE"
        )
    )

    work.loc[
        stage2_review,
        "multiple_award_gate_status",
    ] = "REVIEW_MULTIPLE_AWARD_GATE"

    work.loc[
        stage2_review,
        "multiple_award_gate_reason",
    ] = work.loc[
        stage2_review,
        "final_stage2_reason",
    ]

    # ------------------------------------------------------------------
    # Any unmatched route is a hard stop.
    # ------------------------------------------------------------------
    unresolved = work[
        "multiple_award_gate_status"
    ].eq(
        ""
    )

    if unresolved.any():
        show = (
            work.loc[
                unresolved,
                [
                    "candidate_award_category",
                    "candidate_metadata_status",
                    "governed_dependency_disposition",
                    "multiple_award_route",
                    "stage1_decision",
                    "final_stage2_decision",
                ],
            ]
            .drop_duplicates()
        )

        raise RuntimeError(
            "Unresolved multiple-award route remains:\n"
            + show.to_string(
                index=False
            )
        )

    # ------------------------------------------------------------------
    # Split outputs.
    # ------------------------------------------------------------------
    ready = work[
        work[
            "multiple_award_gate_status"
        ].eq(
            "PASS_MULTIPLE_AWARD_GATE"
        )
    ].copy()

    failed = work[
        work[
            "multiple_award_gate_status"
        ].eq(
            "FAIL_MULTIPLE_AWARD_GATE"
        )
    ].copy()

    review = work[
        work[
            "multiple_award_gate_status"
        ].str.startswith(
            "REVIEW_",
            na=False,
        )
    ].copy()

    stopped = work[
        work[
            "multiple_award_gate_status"
        ].eq(
            "STOP_REPRESENTED_BY_OFFICIAL_AWARD"
        )
    ].copy()

    if (
        len(ready)
        + len(failed)
        + len(review)
        + len(stopped)
        != len(work)
    ):
        raise RuntimeError(
            "Final multiple-award partition does not reconcile to 1,108."
        )

    if ready[
        "candidate_lineage"
    ].eq("").any():
        raise RuntimeError(
            "Awardability-ready candidate has blank canonical lineage."
        )

    # ------------------------------------------------------------------
    # Latest-awardable-catalog preselection diagnostics.
    # ------------------------------------------------------------------
    lineage_counts = (
        ready.groupby(
            [
                "student_id",
                "candidate_lineage",
            ],
            dropna=False,
        )
        .size()
        .rename(
            "awardable_catalog_combinations"
        )
        .reset_index()
    )

    multiplicity = (
        lineage_counts.groupby(
            "awardable_catalog_combinations",
            dropna=False,
        )
        .agg(
            student_lineages=(
                "candidate_lineage",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
        .reset_index()
        .sort_values(
            "awardable_catalog_combinations"
        )
    )

    # ------------------------------------------------------------------
    # Restricted outputs.
    # ------------------------------------------------------------------
    work.to_csv(
        FULL_OUT,
        index=False,
    )

    ready.to_csv(
        READY_OUT,
        index=False,
    )

    failed.to_csv(
        FAIL_OUT,
        index=False,
    )

    review.to_csv(
        REVIEW_OUT,
        index=False,
    )

    stopped.to_csv(
        STOP_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe outputs.
    # ------------------------------------------------------------------
    summary = (
        work.groupby(
            [
                "multiple_award_gate_status",
                "candidate_award_category",
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
            [
                "multiple_award_gate_status",
                "candidate_award_category",
            ]
        )
    )

    summary.to_csv(
        SAFE_SUMMARY_OUT,
        index=False,
    )

    route_summary = (
        work.groupby(
            [
                "multiple_award_route",
                "multiple_award_gate_status",
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

    multiplicity.to_csv(
        SAFE_LINEAGE_OUT,
        index=False,
    )

    multi_lineages = int(
        lineage_counts[
            "awardable_catalog_combinations"
        ].gt(1).sum()
    )

    duplicate_catalog_combinations = int(
        (
            lineage_counts[
                "awardable_catalog_combinations"
            ]
            - 1
        )
        .clip(lower=0)
        .sum()
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "ordinary_awardability_pass_combinations",
                "value":
                    len(work),
            },
            {
                "metric":
                    "certificate_candidates_released_from_rescinded_25pct_rule",
                "value":
                    rescinded_route_count,
            },
            {
                "metric":
                    "multiple_award_gate_pass_combinations",
                "value":
                    len(ready),
            },
            {
                "metric":
                    "multiple_award_gate_fail_combinations",
                "value":
                    len(failed),
            },
            {
                "metric":
                    "multiple_award_gate_review_combinations",
                "value":
                    len(review),
            },
            {
                "metric":
                    "represented_by_official_award_stops",
                "value":
                    len(stopped),
            },
            {
                "metric":
                    "awardable_distinct_students_before_lineage_selection",
                "value":
                    ready[
                        "student_id"
                    ].nunique(),
            },
            {
                "metric":
                    "awardable_student_lineages_before_selection",
                "value":
                    len(lineage_counts),
            },
            {
                "metric":
                    "awardable_student_lineages_with_multiple_catalogs",
                "value":
                    multi_lineages,
            },
            {
                "metric":
                    "extra_catalog_combinations_to_remove_by_latest_awardable_selection",
                "value":
                    duplicate_catalog_combinations,
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 116)
    print("CURRENT MULTIPLE-AWARD GATE — CONSOLIDATED")
    print("=" * 116)
    print(
        f"Ordinary awardability PASS combinations:       {len(work):,}"
    )
    print(
        "Certificate rows released from rescinded rule:"
        f" {rescinded_route_count:,}"
    )
    print()
    print(
        f"PASS multiple-award gate:                      {len(ready):,}"
    )
    print(
        f"FAIL multiple-award gate:                      {len(failed):,}"
    )
    print(
        f"REVIEW multiple-award gate / metadata:         {len(review):,}"
    )
    print(
        f"STOP represented by official award:            {len(stopped):,}"
    )
    print()
    print("STATUS BY AWARD CATEGORY")
    print(
        summary.to_string(
            index=False
        )
    )
    print()
    print("SOURCE ROUTES -> FINAL GATE STATUS")
    print(
        route_summary.to_string(
            index=False
        )
    )
    print()
    print("PRE-LINEAGE-SELECTION MULTIPLICITY")
    print(
        multiplicity.to_string(
            index=False
        )
    )
    print()
    print(
        "Awardability-ready distinct students:         "
        f"{ready['student_id'].nunique():,}"
    )
    print(
        "Awardability-ready student/lineages:          "
        f"{len(lineage_counts):,}"
    )
    print(
        "Student/lineages with >1 awardable catalog:   "
        f"{multi_lineages:,}"
    )
    print(
        "Extra catalog combinations awaiting latest-"
        "awardable selection:                         "
        f"{duplicate_catalog_combinations:,}"
    )
    print()
    print(
        "Control: the final governance table was not mutated."
    )
    print(
        "Control: the rescinded certificate rule is removed only in this "
        "derived multiple-award gate; source artifacts remain auditable."
    )
    print(
        "Control: second-associate PASS/FAIL/REVIEW decisions are imported "
        "unchanged from the completed Stage-1 / Stage-2 runs."
    )
    print(
        "NEXT: latest awardable COMPLETE catalog wins within each "
        "student/canonical-lineage, then issue the unawarded-complete list."
    )
    print()
    print(
        f"Candidate source:       {source_dir}"
    )
    print(
        f"Second-associate S1:    {stage1_dir}"
    )
    print(
        f"Second-associate S2:    {stage2_dir}"
    )
    print(
        f"Output directory:       {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
