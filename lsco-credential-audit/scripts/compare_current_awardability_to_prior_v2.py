from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


# ======================================================================================
# STEP 4 — PARITY REVIEW: CURRENT AWARDABILITY VS PRIOR VALIDATED AWARDABILITY
# ======================================================================================
#
# Purpose:
#   Compare the new six-year/current-state awardability results against the
#   previously validated awardability screen wherever the exact
#   student + catalog + credential key exists in both products.
#
# This script DOES NOT change classifications.
# It only classifies differences as:
#   - EXPECTED_REFRESH_EFFECT
#   - EXPECTED_PATH_AWARE_EFFECT
#   - EXPECTED_TRANSFER_REVIEW_EFFECT
#   - EXACT_PARITY
#   - UNEXPECTED_DIFFERENCE_REVIEW
#
# The strictest regression subset is:
#   * exact key exists in both products
#   * current result provenance == CACHE_PRIOR_202607
#   * student has no Summer/Fall 2026 attempt in the authoritative current state
#   * candidate is not using an alternative dependency path
#   * current minimum-C logic is not explicitly a transfer/special-grade REVIEW
#
# Run from repository root:
#   python -u .\scripts\compare_current_awardability_to_prior.py


ROOT = Path.cwd()

REPORTING_ROOT = Path(
    "data/processed/reporting"
)

def discover_latest_current_awardability_dir() -> Path:
    candidates = sorted(
        [
            path
            for path in REPORTING_ROOT.glob(
                "current_awardability_screen_*"
            )
            if (
                path.is_dir()
                and (
                    path
                    / "RESTRICTED_current_unsuppressed_awardability.csv"
                ).exists()
                and (
                    path
                    / "RESTRICTED_current_attempt_state_candidate_students.csv"
                ).exists()
            )
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(
            "No completed current_awardability_screen_* directory found."
        )

    return candidates[0]

CURRENT_DIR = discover_latest_current_awardability_dir()

CURRENT = (
    CURRENT_DIR
    / "RESTRICTED_current_unsuppressed_awardability.csv"
)

CURRENT_ATTEMPTS = (
    CURRENT_DIR
    / "RESTRICTED_current_attempt_state_candidate_students.csv"
)

PRIOR_DIR = Path(
    "data/processed/full_actual_audit/evidence/awardability"
)

PRIOR = (
    PRIOR_DIR
    / "selected_awards_awardability_screen_finalized.csv"
)

PRIOR_TRANSFER_SUMMARY = (
    PRIOR_DIR
    / "remaining_26_transfer_major_summary.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = (
    Path("data/processed/reporting")
    / f"awardability_parity_review_{RUN_STAMP}"
)

DETAIL_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_awardability_parity_detail.csv"
)

UNEXPECTED_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_unexpected_awardability_differences.csv"
)

SAFE_METRICS_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_parity_metrics.csv"
)

SAFE_GATE_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_parity_by_gate.csv"
)

SAFE_CLASS_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_parity_classification.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]

STATUS_PAIRS = [
    (
        "credential_type",
        "credential_type_prior",
        "awardability_credential_type_current",
    ),
    (
        "residency_status",
        "residency_status_prior",
        "residency_status_current",
    ),
    (
        "institutional_gpa_status",
        "institutional_gpa_status_prior",
        "institutional_gpa_status_current",
    ),
    (
        "certificate_plan_gpa_status",
        "certificate_plan_gpa_status_prior",
        "certificate_plan_gpa_status_current",
    ),
    (
        "minimum_c_status",
        "minimum_c_status_prior",
        "minimum_c_status_current",
    ),
    (
        "awardability_status",
        "awardability_status_prior",
        "awardability_status_current",
    ),
]

NUMERIC_PAIRS = [
    (
        "program_hours",
        "program_hours_prior",
        "awardability_program_hours_current",
    ),
    (
        "resident_applied_hours",
        "estimated_resident_applied_hours_prior",
        "estimated_resident_applied_hours_current",
    ),
    (
        "special_resident_hours",
        "estimated_special_resident_hours_prior",
        "estimated_special_resident_hours_current",
    ),
    (
        "institutional_gpa",
        "estimated_institutional_gpa_prior",
        "estimated_institutional_gpa_current",
    ),
    (
        "certificate_plan_gpa",
        "estimated_certificate_plan_gpa_prior",
        "estimated_certificate_plan_gpa_current",
    ),
    (
        "major_gpa",
        "estimated_major_gpa_prior",
        "estimated_major_gpa_current",
    ),
]


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def clean(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index)

    return (
        frame[column]
        .fillna("")
        .astype(str)
        .str.strip()
    )


def boolish(series: pd.Series) -> pd.Series:
    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(
            {
                "TRUE",
                "T",
                "YES",
                "Y",
                "1",
            }
        )
    )


def numeric_equal(
    left: pd.Series,
    right: pd.Series,
    tolerance: float = 1e-9,
) -> pd.Series:
    l = pd.to_numeric(
        left,
        errors="coerce",
    )

    r = pd.to_numeric(
        right,
        errors="coerce",
    )

    both_nan = (
        l.isna()
        & r.isna()
    )

    both_num = (
        l.notna()
        & r.notna()
        & (
            l.sub(r)
            .abs()
            .le(
                tolerance
            )
        )
    )

    return (
        both_nan
        | both_num
    )


def main() -> None:
    for path in (
        CURRENT,
        CURRENT_ATTEMPTS,
        PRIOR,
    ):
        require(path)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    current = pd.read_csv(
        CURRENT,
        dtype=str,
        low_memory=False,
    ).fillna("")

    prior = pd.read_csv(
        PRIOR,
        dtype=str,
        low_memory=False,
    ).fillna("")

    attempts = pd.read_csv(
        CURRENT_ATTEMPTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    for frame in (
        current,
        prior,
        attempts,
    ):
        if "student_id" in frame.columns:
            frame["student_id"] = clean(
                frame,
                "student_id",
            )

    for frame in (
        current,
        prior,
    ):
        for column in (
            "catalog_year",
            "credential_id",
        ):
            frame[column] = clean(
                frame,
                column,
            )

    if current.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Current awardability output is not unique at exact candidate key."
        )

    if prior.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Prior finalized awardability output is not unique at exact candidate key."
        )

    # ------------------------------------------------------------------
    # Normalize current field names to avoid hidden x/y merge semantics.
    # ------------------------------------------------------------------
    current_rename = {
        "awardability_credential_type":
            "awardability_credential_type_current",
        "awardability_program_hours":
            "awardability_program_hours_current",
        "residency_status":
            "residency_status_current",
        "institutional_gpa_status":
            "institutional_gpa_status_current",
        "certificate_plan_gpa_status":
            "certificate_plan_gpa_status_current",
        "minimum_c_status":
            "minimum_c_status_current",
        "awardability_status":
            "awardability_status_current",
        "estimated_resident_applied_hours":
            "estimated_resident_applied_hours_current",
        "estimated_special_resident_hours":
            "estimated_special_resident_hours_current",
        "estimated_institutional_gpa":
            "estimated_institutional_gpa_current",
        "estimated_certificate_plan_gpa":
            "estimated_certificate_plan_gpa_current",
        "estimated_major_gpa":
            "estimated_major_gpa_current",
        "awardability_reasons":
            "awardability_reasons_current",
    }

    prior_rename = {
        "credential_type":
            "credential_type_prior",
        "program_hours":
            "program_hours_prior",
        "residency_status":
            "residency_status_prior",
        "institutional_gpa_status":
            "institutional_gpa_status_prior",
        "certificate_plan_gpa_status":
            "certificate_plan_gpa_status_prior",
        "minimum_c_status":
            "minimum_c_status_prior",
        "awardability_status":
            "awardability_status_prior",
        "estimated_resident_applied_hours":
            "estimated_resident_applied_hours_prior",
        "estimated_special_resident_hours":
            "estimated_special_resident_hours_prior",
        "estimated_institutional_gpa":
            "estimated_institutional_gpa_prior",
        "estimated_certificate_plan_gpa":
            "estimated_certificate_plan_gpa_prior",
        "estimated_major_gpa":
            "estimated_major_gpa_prior",
        "awardability_reasons":
            "awardability_reasons_prior",
    }

    current_cmp = current.rename(
        columns=current_rename
    ).copy()

    prior_cmp = prior.rename(
        columns=prior_rename
    ).copy()

    overlap = current_cmp.merge(
        prior_cmp,
        on=KEY,
        how="inner",
        suffixes=(
            "_current_extra",
            "_prior_extra",
        ),
        validate="one_to_one",
    )

    # ------------------------------------------------------------------
    # Flag students whose transcript state changed in the refresh window.
    # ------------------------------------------------------------------
    attempts["term_sort_numeric"] = pd.to_numeric(
        attempts["term_sort"],
        errors="coerce",
    )

    refresh_students = set(
        attempts.loc[
            attempts[
                "term_sort_numeric"
            ].isin(
                [
                    202660,
                    202690,
                ]
            ),
            "student_id",
        ]
    )

    overlap[
        "has_summer_or_fall_2026_attempt"
    ] = overlap[
        "student_id"
    ].isin(
        refresh_students
    )

    if "result_provenance" in overlap.columns:
        overlap[
            "is_prior_cache_result"
        ] = (
            clean(
                overlap,
                "result_provenance",
            )
            .str.upper()
            .eq(
                "CACHE_PRIOR_202607"
            )
        )
    else:
        overlap[
            "is_prior_cache_result"
        ] = False

    if (
        "uses_alternative_dependency_path"
        in overlap.columns
    ):
        overlap[
            "uses_alternative_dependency_path_bool"
        ] = boolish(
            overlap[
                "uses_alternative_dependency_path"
            ]
        )
    else:
        overlap[
            "uses_alternative_dependency_path_bool"
        ] = False

    overlap[
        "current_transfer_review_effect"
    ] = (
        clean(
            overlap,
            "minimum_c_status_current",
        )
        .str.upper()
        .eq(
            "REVIEW"
        )
        & clean(
            overlap,
            "awardability_reasons_current",
        )
        .str.upper()
        .str.contains(
            "TRANSFER_OR_SPECIAL_MAJOR_GRADE_UNVERIFIED",
            regex=False,
        )
    )

    # ------------------------------------------------------------------
    # Gate-level parity.
    # ------------------------------------------------------------------
    gate_rows = []

    comparison_columns = []

    for (
        label,
        prior_col,
        current_col,
    ) in STATUS_PAIRS:
        if (
            prior_col
            not in overlap.columns
            or current_col
            not in overlap.columns
        ):
            continue

        match_col = (
            f"match_{label}"
        )

        overlap[
            match_col
        ] = (
            clean(
                overlap,
                prior_col,
            )
            .str.upper()
            .eq(
                clean(
                    overlap,
                    current_col,
                )
                .str.upper()
            )
        )

        comparison_columns.append(
            match_col
        )

        gate_rows.append(
            {
                "gate": label,
                "comparison_type": "STATUS",
                "overlap_rows": len(
                    overlap
                ),
                "matches": int(
                    overlap[
                        match_col
                    ].sum()
                ),
                "differences": int(
                    (
                        ~overlap[
                            match_col
                        ]
                    ).sum()
                ),
            }
        )

    for (
        label,
        prior_col,
        current_col,
    ) in NUMERIC_PAIRS:
        if (
            prior_col
            not in overlap.columns
            or current_col
            not in overlap.columns
        ):
            continue

        match_col = (
            f"match_{label}"
        )

        overlap[
            match_col
        ] = numeric_equal(
            overlap[
                prior_col
            ],
            overlap[
                current_col
            ],
            tolerance=1e-8,
        )

        comparison_columns.append(
            match_col
        )

        gate_rows.append(
            {
                "gate": label,
                "comparison_type": "NUMERIC",
                "overlap_rows": len(
                    overlap
                ),
                "matches": int(
                    overlap[
                        match_col
                    ].sum()
                ),
                "differences": int(
                    (
                        ~overlap[
                            match_col
                        ]
                    ).sum()
                ),
            }
        )

    if not comparison_columns:
        raise RuntimeError(
            "No comparable prior/current gate columns were found."
        )

    overlap[
        "all_compared_fields_match"
    ] = overlap[
        comparison_columns
    ].all(
        axis=1
    )

    # ------------------------------------------------------------------
    # Difference classification.
    # ------------------------------------------------------------------
    stable_regression_mask = (
        overlap[
            "is_prior_cache_result"
        ]
        & ~overlap[
            "has_summer_or_fall_2026_attempt"
        ]
        & ~overlap[
            "uses_alternative_dependency_path_bool"
        ]
        & ~overlap[
            "current_transfer_review_effect"
        ]
    )

    overlap[
        "strict_stable_regression_subset"
    ] = stable_regression_mask

    def classify(row) -> str:
        if bool(
            row[
                "all_compared_fields_match"
            ]
        ):
            return "EXACT_PARITY"

        if bool(
            row[
                "has_summer_or_fall_2026_attempt"
            ]
        ):
            return "EXPECTED_REFRESH_EFFECT"

        if bool(
            row[
                "uses_alternative_dependency_path_bool"
            ]
        ):
            return "EXPECTED_PATH_AWARE_EFFECT"

        if bool(
            row[
                "current_transfer_review_effect"
            ]
        ):
            return "EXPECTED_TRANSFER_REVIEW_EFFECT"

        return (
            "UNEXPECTED_DIFFERENCE_REVIEW"
        )

    overlap[
        "parity_classification"
    ] = overlap.apply(
        classify,
        axis=1,
    )

    strict = overlap[
        overlap[
            "strict_stable_regression_subset"
        ]
    ].copy()

    strict_unexpected = strict[
        ~strict[
            "all_compared_fields_match"
        ]
    ].copy()

    unexpected = overlap[
        overlap[
            "parity_classification"
        ].eq(
            "UNEXPECTED_DIFFERENCE_REVIEW"
        )
    ].copy()

    # Prior transfer-test evidence is not used to mutate parity. It is attached
    # only as provenance/context when the file exists.
    prior_transfer_rows = 0

    if PRIOR_TRANSFER_SUMMARY.exists():
        transfer = pd.read_csv(
            PRIOR_TRANSFER_SUMMARY,
            dtype=str,
            low_memory=False,
        ).fillna("")

        for column in KEY:
            if column in transfer.columns:
                transfer[column] = clean(
                    transfer,
                    column,
                )

        if set(
            KEY
        ).issubset(
            transfer.columns
        ):
            transfer_context = transfer[
                KEY
                + [
                    column
                    for column in [
                        "conclusion",
                        "applied_transfer_major_matches",
                        "unique_transfer_major_matches",
                    ]
                    if column in transfer.columns
                ]
            ].drop_duplicates(
                KEY
            )

            prior_transfer_rows = len(
                transfer_context
            )

            overlap = overlap.merge(
                transfer_context,
                on=KEY,
                how="left",
                validate="one_to_one",
            )

    overlap.to_csv(
        DETAIL_OUT,
        index=False,
    )

    unexpected.to_csv(
        UNEXPECTED_OUT,
        index=False,
    )

    pd.DataFrame(
        gate_rows
    ).to_csv(
        SAFE_GATE_OUT,
        index=False,
    )

    classification = (
        overlap[
            "parity_classification"
        ]
        .value_counts(
            dropna=False
        )
        .rename_axis(
            "parity_classification"
        )
        .reset_index(
            name="candidate_combinations"
        )
    )

    classification.to_csv(
        SAFE_CLASS_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "current_awardability_rows",
                "value": len(
                    current
                ),
            },
            {
                "metric": "prior_finalized_awardability_rows",
                "value": len(
                    prior
                ),
            },
            {
                "metric": "exact_candidate_key_overlap",
                "value": len(
                    overlap
                ),
            },
            {
                "metric": "strict_stable_regression_subset",
                "value": len(
                    strict
                ),
            },
            {
                "metric": "strict_stable_exact_parity",
                "value": int(
                    strict[
                        "all_compared_fields_match"
                    ].sum()
                ),
            },
            {
                "metric": "strict_stable_differences",
                "value": len(
                    strict_unexpected
                ),
            },
            {
                "metric": "all_overlap_unexpected_difference_review",
                "value": len(
                    unexpected
                ),
            },
            {
                "metric": "overlap_refresh_effect",
                "value": int(
                    overlap[
                        "parity_classification"
                    ].eq(
                        "EXPECTED_REFRESH_EFFECT"
                    ).sum()
                ),
            },
            {
                "metric": "overlap_path_aware_effect",
                "value": int(
                    overlap[
                        "parity_classification"
                    ].eq(
                        "EXPECTED_PATH_AWARE_EFFECT"
                    ).sum()
                ),
            },
            {
                "metric": "overlap_transfer_review_effect",
                "value": int(
                    overlap[
                        "parity_classification"
                    ].eq(
                        "EXPECTED_TRANSFER_REVIEW_EFFECT"
                    ).sum()
                ),
            },
            {
                "metric": "prior_transfer_summary_rows_available",
                "value": prior_transfer_rows,
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 100)
    print("AWARDABILITY PARITY REVIEW")
    print("=" * 100)
    print(
        f"Current awardability rows:                 {len(current):,}"
    )
    print(
        f"Prior finalized awardability rows:         {len(prior):,}"
    )
    print(
        f"Exact candidate-key overlap:               {len(overlap):,}"
    )
    print()
    print(
        f"Strict stable regression subset:           {len(strict):,}"
    )
    print(
        "Strict stable exact parity:               "
        f"{int(strict['all_compared_fields_match'].sum()):,}"
    )
    print(
        f"Strict stable differences:                 {len(strict_unexpected):,}"
    )
    print()
    print("ALL OVERLAP CLASSIFICATION")
    print(
        overlap[
            "parity_classification"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )
    print()
    print("GATE DIFFERENCES ACROSS ALL EXACT-KEY OVERLAP")
    print(
        pd.DataFrame(
            gate_rows
        )[
            [
                "gate",
                "differences",
                "overlap_rows",
            ]
        ]
        .to_string(
            index=False
        )
    )
    print()

    if len(
        strict_unexpected
    ) == 0:
        print(
            "STRICT REGRESSION RESULT: PASS — no unexplained differences "
            "in the stable historical subset."
        )
    else:
        print(
            "STRICT REGRESSION RESULT: REVIEW REQUIRED — "
            f"{len(strict_unexpected):,} unexplained stable differences."
        )
        print(
            f"See: {UNEXPECTED_OUT}"
        )

    print()
    print(
        f"Current awardability source: {CURRENT_DIR}"
    )
    print(
        f"Output directory: {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
