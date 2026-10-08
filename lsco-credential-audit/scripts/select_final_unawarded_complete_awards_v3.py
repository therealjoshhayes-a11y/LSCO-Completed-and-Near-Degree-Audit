from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from catalog_temporal_policy import EVALUATION_DATE, catalog_temporal_fields


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

EXPECTED_GATE_PASS = 795
# The post-expiration recommendation counts are derived from the governed input,
# never rebaselined from an earlier, temporally ineligible final product.
AS_OF_DATE = EVALUATION_DATE


KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]

LINEAGE_KEY = [
    "student_id",
    "candidate_lineage",
]

# Recovered canonical identity repair: the 2021-2022 catalog contains duplicate
# published occurrences of the same Teaching AAT plans. The parser therefore
# produced two legacy modeled IDs for each canonical Teaching lineage.
#
# The source catalog contains ONE AAT2 credential identity (Grades 8-12 / EC-12)
# repeated in the catalog, and the prior canonical repair explicitly maps:
#   T039 + T075 -> TEACHING_AAT2
#   T038 + T074 -> TEACHING_AAT1
#
# These are technical duplicate source occurrences, not separate awards.
KNOWN_SAME_YEAR_ALIAS_GROUPS = {
    (
        "2021-2022",
        "TEACHING_AAT1",
    ): [
        "TEACHING_T038_2021",
        "TEACHING_T074_2021",
    ],
    (
        "2021-2022",
        "TEACHING_AAT2",
    ): [
        "TEACHING_T039_2021",
        "TEACHING_T075_2021",
    ],
}

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = (
    REPORTING
    / f"final_unawarded_complete_{STAMP}"
)

EXPIRED_OUT = OUT_DIR / "RESTRICTED_historical_complete_expired_catalog_candidates.csv"

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
        "catalog_start_year_numeric"
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

    # Independent temporal conferral guard, BEFORE latest-catalog selection.
    # Historical academic PASS is preserved, but a catalog that expired before
    # the evaluation date is not a current award recommendation. The fixed
    # AS_OF_DATE makes this run reproducible; update and review it for new runs.
    temporal = pd.DataFrame(
        [catalog_temporal_fields(year) for year in gate["catalog_year"]],
        index=gate.index,
    )
    for field in temporal.columns:
        if field in gate.columns:
            # Upstream metadata must agree with the independent selector guard.
            mismatch = gate[field].astype(str).ne(temporal[field].astype(str))
            if mismatch.any():
                raise RuntimeError(f"Upstream temporal-policy disagreement in {field}: {int(mismatch.sum())} rows.")
        gate[field] = temporal[field]
    if gate["catalog_temporal_status"].eq("CATALOG_DATE_REVIEW").any():
        raise RuntimeError("Unresolved catalog date found; cannot finalize conferral population.")
    # ready was copied before temporal fields were attached to gate. Refresh
    # from the now-annotated gate so selected rows retain the source fields.
    ready = gate.loc[ready.index].copy()
    expired_ready = ready.loc[
        gate.loc[ready.index, "catalog_temporal_status"].eq("CATALOG_EXPIRED")
    ].copy()
    expired_ready["catalog_expiration_date"] = gate.loc[
        expired_ready.index, "catalog_expiration_date"
    ]
    expired_ready["catalog_temporal_status"] = "CATALOG_EXPIRED"
    expired_ready["historical_completion_disposition"] = (
        "ACADEMICALLY_COMPLETE_BUT_EXPIRED_NOT_CURRENTLY_CONFERABLE"
    )
    ready = ready.loc[
        gate.loc[ready.index, "catalog_temporal_status"].eq("CATALOG_CURRENT")
    ].copy()
    expired_ready.to_csv(EXPIRED_OUT, index=False)
    if ready.empty:
        raise RuntimeError("No current-catalog PASS candidates remain.")

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
            "catalog_start_year_numeric"
        ]
        .transform(
            "max"
        )
    )

    ready[
        "is_latest_awardable_catalog_in_lineage"
    ] = (
        ready[
            "catalog_start_year_numeric"
        ]
        == max_awardable_year
    )

    latest = ready[
        ready[
            "is_latest_awardable_catalog_in_lineage"
        ]
    ].copy()

    # A same-year tie is allowed ONLY when it is a previously proven canonical
    # alias duplication from the 2021-2022 Teaching source. Any other same-year
    # lineage tie remains a hard stop.
    duplicate_latest = latest[
        latest.duplicated(
            LINEAGE_KEY,
            keep=False,
        )
    ].copy()

    same_year_alias_drop_keys = set()
    same_year_alias_notes = {}

    if not duplicate_latest.empty:
        for (
            student_id,
            lineage,
        ), group in duplicate_latest.groupby(
            LINEAGE_KEY,
            sort=False,
        ):
            catalog_years = sorted(
                set(
                    group[
                        "catalog_year"
                    ].astype(str)
                )
            )

            if len(catalog_years) != 1:
                raise RuntimeError(
                    "Same-lineage latest tie spans multiple catalog years, "
                    "which should be impossible after latest-year filtering."
                )

            catalog_year = catalog_years[0]

            alias_key = (
                catalog_year,
                txt(lineage),
            )

            allowed_ids = (
                KNOWN_SAME_YEAR_ALIAS_GROUPS.get(
                    alias_key
                )
            )

            actual_ids = sorted(
                set(
                    group[
                        "credential_id"
                    ].astype(str)
                )
            )

            if allowed_ids is None:
                raise RuntimeError(
                    "Latest-awardable selection has an ungoverned same-year "
                    "lineage tie:\n"
                    + group[
                        [
                            "catalog_year",
                            "candidate_lineage",
                            "credential_id",
                            "credential_title",
                            "candidate_award_category",
                            "awardability_program_hours",
                        ]
                    ].to_string(
                        index=False
                    )
                )

            if set(actual_ids) != set(allowed_ids):
                raise RuntimeError(
                    "Known same-year Teaching alias group does not match the "
                    "expected legacy IDs. Expected "
                    f"{allowed_ids}; found {actual_ids}."
                )

            # Technical-equivalence guards. These rows may differ in raw parser
            # ID, but not in award identity or ordinary awardability metadata.
            for column in [
                "candidate_award_category",
                "awardability_program_hours",
                "multiple_award_gate_status",
            ]:
                values = {
                    txt(value)
                    for value in group[
                        column
                    ]
                }

                if len(values) != 1:
                    raise RuntimeError(
                        "Known same-year alias rows disagree on "
                        f"{column}: {values}"
                    )

            # Choose the first legacy ID in the recovered canonical mapping as
            # the stable technical representative. The final recommendation is
            # still identified by canonical lineage, not by this parser ID.
            representative_id = next(
                credential_id
                for credential_id in allowed_ids
                if credential_id in actual_ids
            )

            representative = group[
                group[
                    "credential_id"
                ].eq(
                    representative_id
                )
            ]

            if len(representative) != 1:
                raise RuntimeError(
                    "Could not isolate exactly one representative legacy row "
                    f"for {alias_key}."
                )

            representative_key = tuple(
                representative.iloc[0][
                    KEY
                ].astype(str)
            )

            alias_ids = " | ".join(
                actual_ids
            )

            same_year_alias_notes[
                (
                    txt(student_id),
                    txt(lineage),
                )
            ] = alias_ids

            for row in group.itertuples(
                index=False
            ):
                row_key = (
                    txt(row.student_id),
                    txt(row.catalog_year),
                    txt(row.credential_id),
                )

                if row_key != representative_key:
                    same_year_alias_drop_keys.add(
                        row_key
                    )

        latest_keys_before_alias_collapse = list(
            latest[
                KEY
            ].itertuples(
                index=False,
                name=None,
            )
        )

        keep_mask = [
            tuple(
                str(value)
                for value in key
            )
            not in same_year_alias_drop_keys
            for key in latest_keys_before_alias_collapse
        ]

        latest = latest.loc[
            keep_mask
        ].copy()

    latest[
        "same_year_canonical_alias_ids"
    ] = [
        same_year_alias_notes.get(
            (
                txt(student_id),
                txt(lineage),
            ),
            "",
        )
        for (
            student_id,
            lineage,
        )
        in latest[
            LINEAGE_KEY
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    latest[
        "same_year_alias_collapse_applied"
    ] = latest[
        "same_year_canonical_alias_ids"
    ].ne("")

    if latest.duplicated(LINEAGE_KEY).any():
        raise RuntimeError("Selected multiple catalog versions for one student/lineage.")
    if latest["catalog_temporal_status"].ne("CATALOG_CURRENT").any():
        raise RuntimeError("Expired catalog reached the selection layer.")

    selected_key_set = set(
        latest[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    ready_keys = list(
        ready[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    superseded_mask = [
        key not in selected_key_set
        for key in ready_keys
    ]

    superseded = ready.loc[
        superseded_mask
    ].copy()

    if len(superseded) + len(latest) != len(ready):
        raise RuntimeError("Current PASS selection does not reconcile.")

    selected_year_by_lineage = {
        (
            txt(row.student_id),
            txt(row.candidate_lineage),
        ):
            int(row.catalog_start_year_numeric)
        for row in latest.itertuples(
            index=False
        )
    }

    superseded[
        "nonselection_reason"
    ] = ""

    for index, row in superseded.iterrows():
        lineage_key = (
            txt(
                row[
                    "student_id"
                ]
            ),
            txt(
                row[
                    "candidate_lineage"
                ]
            ),
        )

        row_key = (
            txt(
                row[
                    "student_id"
                ]
            ),
            txt(
                row[
                    "catalog_year"
                ]
            ),
            txt(
                row[
                    "credential_id"
                ]
            ),
        )

        selected_year = selected_year_by_lineage[
            lineage_key
        ]

        if row_key in same_year_alias_drop_keys:
            superseded.at[
                index,
                "nonselection_reason",
            ] = (
                "DUPLICATE_SAME_YEAR_CANONICAL_ALIAS"
            )

        elif int(
            row[
                "catalog_start_year_numeric"
            ]
        ) < selected_year:
            superseded.at[
                index,
                "nonselection_reason",
            ] = (
                "SUPERSEDED_BY_LATER_AWARDABLE_CATALOG"
            )

        else:
            raise RuntimeError(
                "Awardable row was not selected for an unrecognized reason."
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
            int(row.catalog_start_year_numeric)
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
            row.catalog_start_year_numeric
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
    ] = superseded[
        "nonselection_reason"
    ]

    superseded[
        "final_product1_selection_basis"
    ] = superseded[
        "nonselection_reason"
    ].map(
        {
            "SUPERSEDED_BY_LATER_AWARDABLE_CATALOG":
                "OLDER_AWARDABLE_CATALOG_VERSION_WITHIN_CANONICAL_LINEAGE",
            "DUPLICATE_SAME_YEAR_CANONICAL_ALIAS":
                "KNOWN_DUPLICATE_2021_TEACHING_SOURCE_OCCURRENCE_COLLAPSED_TO_CANONICAL_LINEAGE",
        }
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

        elif txt(row["catalog_temporal_status"]) == "CATALOG_EXPIRED" and txt(row["multiple_award_gate_status"]) == "PASS_MULTIPLE_AWARD_GATE":
            trace.at[index, "final_product1_selection_status"] = "HISTORICAL_COMPLETE_CATALOG_EXPIRED"
            trace.at[index, "final_product1_selection_basis"] = "CATALOG_EXPIRED_AT_EVALUATION_DATE"
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
            "catalog_start_year_numeric",
        ]
    ).copy()

    superseded = superseded.sort_values(
        [
            "student_id",
            "candidate_lineage",
            "catalog_start_year_numeric",
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
            {"metric": "evaluation_date", "value": AS_OF_DATE.isoformat()},
            {"metric": "expired_academic_pass_combinations_excluded", "value": len(expired_ready)},
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
                    "superseded_or_duplicate_awardable_catalog_versions",
                "value":
                    len(superseded),
            },
            {
                "metric":
                    "same_year_canonical_alias_rows_collapsed",
                "value":
                    len(
                        same_year_alias_drop_keys
                    ),
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
    print(f"Evaluation date: {AS_OF_DATE.isoformat()}")
    print("Catalog expiration evidence: 2021–22 source-documented; later years follow provisional five-year convention.")
    print(f"Expired historical academic PASS rows excluded: {len(expired_ready):,}")
    print("=" * 116)
    print(
        "Awardable catalog combinations before selection: "
        f"{len(ready):,}"
    )
    print(
        "Non-selected awardable catalog/source rows:       "
        f"{len(superseded):,}"
    )
    print(
        "  same-year canonical alias rows collapsed:       "
        f"{len(same_year_alias_drop_keys):,}"
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
    print(f"EXPIRED HISTORICAL COMPLETIONS: {EXPIRED_OUT}")
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
