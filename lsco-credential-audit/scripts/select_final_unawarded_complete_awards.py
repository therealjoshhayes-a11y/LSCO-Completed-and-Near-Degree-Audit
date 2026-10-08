from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# PRODUCT 1 — FINAL UNAWARDED-BUT-COMPLETE SELECTION
# ======================================================================================
#
# Product rule:
#   For each student + canonical credential lineage:
#
#       LATEST AWARDABLE COMPLETE CATALOG WINS
#
#   "Latest" is evaluated ONLY among candidates that have already passed:
#       * curriculum completion,
#       * official-award suppression / governance,
#       * ordinary catalog awardability,
#       * multiple-award rules.
#
#   A later FAIL or REVIEW catalog version does NOT suppress an older catalog
#   version that is independently awardable.
#
# Different canonical lineages remain separately awardable.
#
# This script:
#   * consumes the consolidated multiple-award gate;
#   * selects exactly one latest awardable catalog per student / lineage;
#   * retains ALL source columns on the selected recommendation rows;
#   * emits superseded awardable catalog versions separately;
#   * annotates selected rows when later NON-AWARDABLE catalog versions exist;
#   * carries REVIEW rows separately;
#   * hard-stops if a recommended student/lineage is also represented by an
#     existing official award.
#
# It DOES NOT:
#   * alter any upstream audit result;
#   * hide empirical catalog states;
#   * collapse different credential lineages;
#   * backdate an award term;
#   * decide the unresolved REVIEW cases.
#
# Run from repository root:
#   python -u .\scripts\select_final_unawarded_complete_awards.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_GATE_PASS = 792
EXPECTED_SELECTED_STUDENT_LINEAGES = 430
EXPECTED_SUPERSEDED_AWARDABLE_ROWS = 362

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]

LINEAGE_KEY = [
    "student_id",
    "candidate_lineage",
]

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = (
    REPORTING
    / f"final_unawarded_complete_{STAMP}"
)

FINAL_OUT = (
    OUT_DIR
    / "RESTRICTED_FINAL_unawarded_complete_awards.csv"
)

SUPERSEDED_OUT = (
    OUT_DIR
    / "RESTRICTED_superseded_awardable_catalog_versions.csv"
)

REVIEWS_OUT = (
    OUT_DIR
    / "RESTRICTED_unresolved_awardability_reviews.csv"
)

FULL_TRACE_OUT = (
    OUT_DIR
    / "RESTRICTED_final_selection_trace.csv"
)

SAFE_METRICS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_final_unawarded_complete_metrics.csv"
)

SAFE_CATALOG_OUT = (
    OUT_DIR
    / "FERPA_SAFE_final_awards_by_catalog.csv"
)

SAFE_CATEGORY_OUT = (
    OUT_DIR
    / "FERPA_SAFE_final_awards_by_category.csv"
)

SAFE_MULTIPLICITY_OUT = (
    OUT_DIR
    / "FERPA_SAFE_final_awards_per_student_distribution.csv"
)

SAFE_LATER_STATE_OUT = (
    OUT_DIR
    / "FERPA_SAFE_selected_with_later_nonawardable_catalogs.csv"
)

SAFE_REVIEW_OUT = (
    OUT_DIR
    / "FERPA_SAFE_unresolved_review_summary.csv"
)


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def catalog_start_year(value: object) -> int:
    value = txt(value)

    try:
        return int(
            value[:4]
        )
    except Exception as exc:
        raise RuntimeError(
            f"Cannot parse catalog year: {value!r}"
        ) from exc


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


def joined(values) -> str:
    return " | ".join(
        sorted(
            {
                txt(value)
                for value in values
                if txt(value)
            }
        )
    )


def main() -> None:
    gate_dir = latest_dir(
        "current_multiple_award_gate_*",
        "RESTRICTED_current_multiple_award_gate.csv",
    )

    gate_path = (
        gate_dir
        / "RESTRICTED_current_multiple_award_gate.csv"
    )

    gate = pd.read_csv(
        gate_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    # ------------------------------------------------------------------
    # Basic controls.
    # ------------------------------------------------------------------
    required = {
        "student_id",
        "catalog_year",
        "credential_id",
        "candidate_lineage",
        "candidate_award_category",
        "multiple_award_gate_status",
    }

    missing = required - set(gate.columns)

    if missing:
        raise RuntimeError(
            "Multiple-award gate missing required columns: "
            + ", ".join(sorted(missing))
        )

    if gate.duplicated(KEY).any():
        raise RuntimeError(
            "Multiple-award gate is not unique at student/catalog/credential."
        )

    if gate[
        "candidate_lineage"
    ].eq("").any():
        # Blank lineages are acceptable only on rows that can never be issued.
        blank_issueable = gate[
            gate[
                "candidate_lineage"
            ].eq("")
            & gate[
                "multiple_award_gate_status"
            ].eq(
                "PASS_MULTIPLE_AWARD_GATE"
            )
        ]

        if not blank_issueable.empty:
            raise RuntimeError(
                "PASS candidate has blank canonical lineage."
            )

    gate[
        "_catalog_start_year"
    ] = gate[
        "catalog_year"
    ].map(
        catalog_start_year
    )

    ready = gate[
        gate[
            "multiple_award_gate_status"
        ].eq(
            "PASS_MULTIPLE_AWARD_GATE"
        )
    ].copy()

    if len(ready) != EXPECTED_GATE_PASS:
        raise RuntimeError(
            "Multiple-award PASS universe changed: "
            f"{len(ready):,} != {EXPECTED_GATE_PASS:,}"
        )

    # ------------------------------------------------------------------
    # Critical official-award guard:
    # no recommended student/lineage may coexist with a represented stop for
    # that same canonical lineage.
    # ------------------------------------------------------------------
    represented = gate[
        gate[
            "multiple_award_gate_status"
        ].eq(
            "STOP_REPRESENTED_BY_OFFICIAL_AWARD"
        )
        & gate[
            "candidate_lineage"
        ].ne("")
    ].copy()

    ready_lineages = set(
        ready[
            LINEAGE_KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    represented_lineages = set(
        represented[
            LINEAGE_KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    collision = (
        ready_lineages
        & represented_lineages
    )

    if collision:
        raise RuntimeError(
            "A PASS recommendation lineage is also represented by an official "
            f"award for {len(collision):,} student/lineage key(s). "
            "Do not issue until upstream official suppression is reconciled."
        )

    # ------------------------------------------------------------------
    # Select latest AWARDABLE catalog within student + canonical lineage.
    # ------------------------------------------------------------------
    max_awardable_year = (
        ready.groupby(
            LINEAGE_KEY
        )[
            "_catalog_start_year"
        ]
        .transform(
            "max"
        )
    )

    ready[
        "is_latest_awardable_catalog_in_lineage"
    ] = (
        ready[
            "_catalog_start_year"
        ]
        == max_awardable_year
    )

    latest = ready[
        ready[
            "is_latest_awardable_catalog_in_lineage"
        ]
    ].copy()

    # More than one candidate at the same latest catalog year in the same
    # canonical lineage would make the final recommendation ambiguous.
    duplicate_latest = latest[
        latest.duplicated(
            LINEAGE_KEY,
            keep=False,
        )
    ].copy()

    if not duplicate_latest.empty:
        safe = (
            duplicate_latest.groupby(
                [
                    "catalog_year",
                    "candidate_lineage",
                ],
                dropna=False,
            )
            .size()
            .reset_index(
                name="candidate_rows"
            )
        )

        raise RuntimeError(
            "Latest-awardable selection has a same-year lineage tie:\n"
            + safe.to_string(index=False)
        )

    if len(latest) != EXPECTED_SELECTED_STUDENT_LINEAGES:
        raise RuntimeError(
            "Final selected student/lineage count changed: "
            f"{len(latest):,} != "
            f"{EXPECTED_SELECTED_STUDENT_LINEAGES:,}"
        )

    superseded = ready[
        ~ready[
            "is_latest_awardable_catalog_in_lineage"
        ]
    ].copy()

    if len(superseded) != EXPECTED_SUPERSEDED_AWARDABLE_ROWS:
        raise RuntimeError(
            "Superseded awardable catalog count changed: "
            f"{len(superseded):,} != "
            f"{EXPECTED_SUPERSEDED_AWARDABLE_ROWS:,}"
        )

    # ------------------------------------------------------------------
    # Annotate whether a later catalog state exists but is NOT awardable.
    #
    # This is important evidence that the implementation really follows:
    #     latest AWARDABLE COMPLETE catalog wins
    # rather than:
    #     latest catalog wins.
    # ------------------------------------------------------------------
    selected_year_lookup = {
        (
            txt(row.student_id),
            txt(row.candidate_lineage),
        ):
            int(row._catalog_start_year)
        for row in latest.itertuples(
            index=False
        )
    }

    nonawardable = gate[
        ~gate[
            "multiple_award_gate_status"
        ].eq(
            "PASS_MULTIPLE_AWARD_GATE"
        )
        & gate[
            "candidate_lineage"
        ].ne("")
    ].copy()

    later_rows = []

    for row in nonawardable.itertuples(
        index=False
    ):
        lineage_key = (
            txt(row.student_id),
            txt(row.candidate_lineage),
        )

        selected_year = (
            selected_year_lookup.get(
                lineage_key
            )
        )

        if selected_year is None:
            continue

        row_year = int(
            row._catalog_start_year
        )

        if row_year <= selected_year:
            continue

        later_rows.append(
            {
                "student_id":
                    txt(row.student_id),
                "candidate_lineage":
                    txt(row.candidate_lineage),
                "later_catalog_year":
                    txt(row.catalog_year),
                "later_credential_id":
                    txt(row.credential_id),
                "later_gate_status":
                    txt(
                        row.multiple_award_gate_status
                    ),
            }
        )

    later = pd.DataFrame(
        later_rows
    )

    if later.empty:
        later_summary = pd.DataFrame(
            columns=[
                "student_id",
                "candidate_lineage",
                "later_nonawardable_catalog_count",
                "later_nonawardable_catalogs",
                "later_nonawardable_statuses",
            ]
        )
    else:
        later_summary = (
            later.groupby(
                LINEAGE_KEY
            )
            .agg(
                later_nonawardable_catalog_count=(
                    "later_catalog_year",
                    "size",
                ),
                later_nonawardable_catalogs=(
                    "later_catalog_year",
                    joined,
                ),
                later_nonawardable_statuses=(
                    "later_gate_status",
                    joined,
                ),
            )
            .reset_index()
        )

    latest = latest.merge(
        later_summary,
        on=LINEAGE_KEY,
        how="left",
        validate="one_to_one",
    )

    latest[
        "later_nonawardable_catalog_count"
    ] = pd.to_numeric(
        latest[
            "later_nonawardable_catalog_count"
        ],
        errors="coerce",
    ).fillna(
        0
    ).astype(
        int
    )

    for column in [
        "later_nonawardable_catalogs",
        "later_nonawardable_statuses",
    ]:
        latest[
            column
        ] = latest[
            column
        ].fillna("")

    latest[
        "final_product1_selection_status"
    ] = "RECOMMEND_AWARD"

    latest[
        "final_product1_selection_basis"
    ] = (
        "LATEST_AWARDABLE_COMPLETE_CATALOG_IN_CANONICAL_LINEAGE"
    )

    superseded[
        "final_product1_selection_status"
    ] = "SUPERSEDED_BY_LATER_AWARDABLE_CATALOG"

    superseded[
        "final_product1_selection_basis"
    ] = (
        "OLDER_AWARDABLE_CATALOG_VERSION_WITHIN_CANONICAL_LINEAGE"
    )

    # ------------------------------------------------------------------
    # Reviews are carried separately and NEVER suppress a selected older
    # awardable catalog.
    # ------------------------------------------------------------------
    reviews = gate[
        gate[
            "multiple_award_gate_status"
        ].str.startswith(
            "REVIEW_",
            na=False,
        )
    ].copy()

    # ------------------------------------------------------------------
    # Full trace: selected + superseded + all other gate outcomes.
    # ------------------------------------------------------------------
    selected_keys = set(
        latest[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    superseded_keys = set(
        superseded[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    trace = gate.copy()

    trace[
        "final_product1_selection_status"
    ] = ""

    trace[
        "final_product1_selection_basis"
    ] = ""

    for index, row in trace.iterrows():
        key = (
            txt(row["student_id"]),
            txt(row["catalog_year"]),
            txt(row["credential_id"]),
        )

        if key in selected_keys:
            trace.at[
                index,
                "final_product1_selection_status",
            ] = "RECOMMEND_AWARD"

            trace.at[
                index,
                "final_product1_selection_basis",
            ] = (
                "LATEST_AWARDABLE_COMPLETE_CATALOG_IN_CANONICAL_LINEAGE"
            )

        elif key in superseded_keys:
            trace.at[
                index,
                "final_product1_selection_status",
            ] = "SUPERSEDED_BY_LATER_AWARDABLE_CATALOG"

            trace.at[
                index,
                "final_product1_selection_basis",
            ] = (
                "OLDER_AWARDABLE_CATALOG_VERSION_WITHIN_CANONICAL_LINEAGE"
            )

        else:
            trace.at[
                index,
                "final_product1_selection_status",
            ] = txt(
                row[
                    "multiple_award_gate_status"
                ]
            )

            trace.at[
                index,
                "final_product1_selection_basis",
            ] = txt(
                row[
                    "multiple_award_gate_reason"
                ]
            )

    # ------------------------------------------------------------------
    # Restricted outputs.
    # ------------------------------------------------------------------
    latest = latest.sort_values(
        [
            "student_id",
            "candidate_lineage",
            "_catalog_start_year",
        ]
    ).copy()

    superseded = superseded.sort_values(
        [
            "student_id",
            "candidate_lineage",
            "_catalog_start_year",
        ]
    ).copy()

    latest.to_csv(
        FINAL_OUT,
        index=False,
    )

    superseded.to_csv(
        SUPERSEDED_OUT,
        index=False,
    )

    reviews.to_csv(
        REVIEWS_OUT,
        index=False,
    )

    trace.to_csv(
        FULL_TRACE_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe summaries.
    # ------------------------------------------------------------------
    catalog_safe = (
        latest.groupby(
            [
                "catalog_year",
                "candidate_award_category",
            ],
            dropna=False,
        )
        .agg(
            recommended_awards=(
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
                "catalog_year",
                "candidate_award_category",
            ]
        )
    )

    catalog_safe.to_csv(
        SAFE_CATALOG_OUT,
        index=False,
    )

    category_safe = (
        latest.groupby(
            "candidate_award_category",
            dropna=False,
        )
        .agg(
            recommended_awards=(
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
            "recommended_awards",
            ascending=False,
        )
    )

    category_safe.to_csv(
        SAFE_CATEGORY_OUT,
        index=False,
    )

    per_student = (
        latest.groupby(
            "student_id"
        )
        .size()
        .rename(
            "recommended_awards"
        )
        .reset_index()
    )

    multiplicity_safe = (
        per_student.groupby(
            "recommended_awards"
        )
        .size()
        .rename(
            "students"
        )
        .reset_index()
        .sort_values(
            "recommended_awards"
        )
    )

    multiplicity_safe.to_csv(
        SAFE_MULTIPLICITY_OUT,
        index=False,
    )

    selected_with_later = latest[
        latest[
            "later_nonawardable_catalog_count"
        ].gt(0)
    ].copy()

    if selected_with_later.empty:
        later_safe = pd.DataFrame(
            columns=[
                "catalog_year",
                "candidate_award_category",
                "later_nonawardable_statuses",
                "recommended_awards",
                "distinct_students",
            ]
        )
    else:
        later_safe = (
            selected_with_later.groupby(
                [
                    "catalog_year",
                    "candidate_award_category",
                    "later_nonawardable_statuses",
                ],
                dropna=False,
            )
            .agg(
                recommended_awards=(
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
                "recommended_awards",
                ascending=False,
            )
        )

    later_safe.to_csv(
        SAFE_LATER_STATE_OUT,
        index=False,
    )

    if reviews.empty:
        review_safe = pd.DataFrame(
            columns=[
                "multiple_award_gate_status",
                "candidate_award_category",
                "catalog_year",
                "review_combinations",
                "distinct_students",
            ]
        )
    else:
        review_safe = (
            reviews.groupby(
                [
                    "multiple_award_gate_status",
                    "candidate_award_category",
                    "catalog_year",
                ],
                dropna=False,
            )
            .agg(
                review_combinations=(
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

    review_safe.to_csv(
        SAFE_REVIEW_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "awardable_catalog_combinations_before_lineage_selection",
                "value":
                    len(ready),
            },
            {
                "metric":
                    "final_recommended_awards",
                "value":
                    len(latest),
            },
            {
                "metric":
                    "final_distinct_students",
                "value":
                    latest[
                        "student_id"
                    ].nunique(),
            },
            {
                "metric":
                    "superseded_awardable_catalog_versions",
                "value":
                    len(superseded),
            },
            {
                "metric":
                    "final_distinct_student_lineages",
                "value":
                    len(
                        latest[
                            LINEAGE_KEY
                        ].drop_duplicates()
                    ),
            },
            {
                "metric":
                    "selected_awards_with_later_nonawardable_catalog_state",
                "value":
                    len(
                        selected_with_later
                    ),
            },
            {
                "metric":
                    "unresolved_review_combinations",
                "value":
                    len(reviews),
            },
            {
                "metric":
                    "official_award_lineage_collisions",
                "value":
                    len(collision),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 116)
    print("PRODUCT 1 — FINAL UNAWARDED-BUT-COMPLETE SELECTION")
    print("=" * 116)
    print(
        "Awardable catalog combinations before selection: "
        f"{len(ready):,}"
    )
    print(
        "Superseded older awardable catalog versions:      "
        f"{len(superseded):,}"
    )
    print(
        "FINAL RECOMMENDED AWARDS:                         "
        f"{len(latest):,}"
    )
    print(
        "DISTINCT STUDENTS:                               "
        f"{latest['student_id'].nunique():,}"
    )
    print(
        "Official-award lineage collisions:               "
        f"{len(collision):,}"
    )
    print(
        "Selected awards with later non-awardable state:   "
        f"{len(selected_with_later):,}"
    )
    print(
        "Unresolved review combinations carried separately:"
        f" {len(reviews):,}"
    )
    print()
    print("FINAL AWARDS BY CATEGORY")
    print(
        category_safe.to_string(
            index=False,
        )
    )
    print()
    print("FINAL AWARDS BY CATALOG")
    print(
        catalog_safe.to_string(
            index=False,
        )
    )
    print()
    print("RECOMMENDED AWARDS PER STUDENT")
    print(
        multiplicity_safe.to_string(
            index=False,
        )
    )
    print()
    if later_safe.empty:
        print(
            "LATEST-AWARDABLE SEMANTIC CHECK: "
            "no selected recommendation has a later non-awardable catalog state."
        )
    else:
        print(
            "LATEST-AWARDABLE SEMANTIC CHECK — SELECTED OLDER AWARDABLE "
            "CATALOGS WITH LATER NON-AWARDABLE STATE"
        )
        print(
            later_safe.to_string(
                index=False,
            )
        )
    print()
    print(
        "Control: selection occurred ONLY among PASS_MULTIPLE_AWARD_GATE rows."
    )
    print(
        "Control: different canonical lineages remain separate recommendations."
    )
    print(
        "Control: later FAIL/REVIEW catalog states do not suppress an older "
        "awardable catalog."
    )
    print(
        "Control: no recommended student/lineage is also represented by an "
        "existing official award."
    )
    print()
    print(
        f"FINAL LIST:       {FINAL_OUT}"
    )
    print(
        f"REVIEWS:          {REVIEWS_OUT}"
    )
    print(
        f"SELECTION TRACE:  {FULL_TRACE_OUT}"
    )
    print(
        f"Output directory: {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
