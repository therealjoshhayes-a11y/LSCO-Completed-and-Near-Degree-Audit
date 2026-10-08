from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path.cwd()
REPORTING = Path("data/processed/reporting")

PRIOR_APPLIED = Path(
    "data/processed/full_actual_audit/evidence/awardability/"
    "selected_awards_applied_courses.csv"
)

PRIOR_ISSUES = Path(
    "data/processed/full_actual_audit/evidence/awardability/"
    "awardability_screen_issues.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"awardability_parity_diagnostics_{RUN_STAMP}"
)

SAFE_METRICS = (
    OUT_DIR
    / "FERPA_SAFE_unexpected_difference_metrics.csv"
)

SAFE_TRANSITIONS = (
    OUT_DIR
    / "FERPA_SAFE_gate_transition_counts.csv"
)

SAFE_CREDENTIALS = (
    OUT_DIR
    / "FERPA_SAFE_unexpected_differences_by_credential.csv"
)

SAFE_CAUSES = (
    OUT_DIR
    / "FERPA_SAFE_applied_evidence_difference_causes.csv"
)

SAFE_GRADE_CODES = (
    OUT_DIR
    / "FERPA_SAFE_current_only_grade_codes.csv"
)

SAFE_MAJOR_TRANSITIONS = (
    OUT_DIR
    / "FERPA_SAFE_minimum_c_transition_by_credential.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def latest_dir(pattern: str, required_name: str) -> Path:
    candidates = sorted(
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

    if not candidates:
        raise FileNotFoundError(
            f"No directory matching {pattern} with {required_name}"
        )

    return candidates[0]


def normalize_bool(value: object) -> bool:
    return txt(value).upper() in {
        "TRUE",
        "T",
        "YES",
        "Y",
        "1",
    }


def course_keyed(frame: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, tuple[str, bool]]]:
    """
    Return:
      candidate_key -> course -> (grade, estimated_major)
    """
    result: dict[
        tuple[str, str, str],
        dict[str, tuple[str, bool]],
    ] = {}

    if frame.empty:
        return result

    for row in frame.itertuples(index=False):
        candidate = (
            txt(row.student_id),
            txt(row.catalog_year),
            txt(row.credential_id),
        )

        course = txt(
            getattr(
                row,
                "course",
                "",
            )
        )

        if not course:
            continue

        grade = txt(
            getattr(
                row,
                "grade",
                "",
            )
        ).upper()

        estimated_major = normalize_bool(
            getattr(
                row,
                "estimated_major",
                "",
            )
        )

        result.setdefault(
            candidate,
            {},
        )[course] = (
            grade,
            estimated_major,
        )

    return result


def main() -> None:
    parity_dir = latest_dir(
        "awardability_parity_review_*",
        "RESTRICTED_unexpected_awardability_differences.csv",
    )

    current_applied_dir = latest_dir(
        "current_unsuppressed_applied_courses_*",
        "RESTRICTED_unsuppressed_complete_applied_courses.csv",
    )

    unexpected_path = (
        parity_dir
        / "RESTRICTED_unexpected_awardability_differences.csv"
    )

    current_applied_path = (
        current_applied_dir
        / "RESTRICTED_unsuppressed_complete_applied_courses.csv"
    )

    for path in (
        unexpected_path,
        current_applied_path,
        PRIOR_APPLIED,
    ):
        require(path)

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    unexpected = pd.read_csv(
        unexpected_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    current_applied = pd.read_csv(
        current_applied_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    prior_applied = pd.read_csv(
        PRIOR_APPLIED,
        dtype=str,
        low_memory=False,
    ).fillna("")

    for frame in (
        unexpected,
        current_applied,
        prior_applied,
    ):
        for column in KEY:
            if column in frame.columns:
                frame[column] = (
                    frame[column]
                    .astype(str)
                    .str.strip()
                )

    if unexpected.empty:
        raise RuntimeError(
            "Unexpected-difference file is empty; nothing to diagnose."
        )

    unexpected_keys = set(
        unexpected[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    current_subset = current_applied[
        [
            key in unexpected_keys
            for key in current_applied[
                KEY
            ].itertuples(
                index=False,
                name=None,
            )
        ]
    ].copy()

    prior_subset = prior_applied[
        [
            key in unexpected_keys
            for key in prior_applied[
                KEY
            ].itertuples(
                index=False,
                name=None,
            )
        ]
    ].copy()

    current_map = course_keyed(
        current_subset
    )

    prior_map = course_keyed(
        prior_subset
    )

    if PRIOR_ISSUES.exists():
        prior_issues = pd.read_csv(
            PRIOR_ISSUES,
            dtype=str,
            low_memory=False,
        ).fillna("")

        for column in KEY:
            if column in prior_issues.columns:
                prior_issues[column] = (
                    prior_issues[column]
                    .astype(str)
                    .str.strip()
                )

        prior_issue_keys = set(
            prior_issues[
                KEY
            ].itertuples(
                index=False,
                name=None,
            )
        )
    else:
        prior_issue_keys = set()

    # ------------------------------------------------------------------
    # Gate transition inventory.
    # ------------------------------------------------------------------
    transition_specs = [
        (
            "minimum_c_status",
            "minimum_c_status_prior",
            "minimum_c_status_current",
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
            "awardability_status",
            "awardability_status_prior",
            "awardability_status_current",
        ),
    ]

    transition_rows = []

    for (
        gate,
        prior_col,
        current_col,
    ) in transition_specs:
        if (
            prior_col
            not in unexpected.columns
            or current_col
            not in unexpected.columns
        ):
            continue

        changed = unexpected[
            unexpected[
                prior_col
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .ne(
                unexpected[
                    current_col
                ]
                .astype(str)
                .str.strip()
                .str.upper()
            )
        ].copy()

        if changed.empty:
            continue

        grouped = (
            changed.groupby(
                [
                    prior_col,
                    current_col,
                ],
                dropna=False,
            )
            .size()
            .reset_index(
                name="candidate_combinations"
            )
        )

        for row in grouped.itertuples(
            index=False
        ):
            transition_rows.append(
                {
                    "gate": gate,
                    "prior_value": getattr(
                        row,
                        prior_col,
                    ),
                    "current_value": getattr(
                        row,
                        current_col,
                    ),
                    "candidate_combinations": int(
                        row.candidate_combinations
                    ),
                }
            )

    transitions = pd.DataFrame(
        transition_rows
    )

    transitions.to_csv(
        SAFE_TRANSITIONS,
        index=False,
    )

    # ------------------------------------------------------------------
    # Applied-evidence differences.
    # ------------------------------------------------------------------
    cause_rows = []
    current_only_grade_counter = Counter()

    per_candidate_cause = []

    for key in sorted(
        unexpected_keys
    ):
        old = prior_map.get(
            key,
            {},
        )

        new = current_map.get(
            key,
            {},
        )

        old_courses = set(
            old
        )

        new_courses = set(
            new
        )

        current_only = (
            new_courses
            - old_courses
        )

        prior_only = (
            old_courses
            - new_courses
        )

        common = (
            old_courses
            & new_courses
        )

        grade_changes = [
            course
            for course in common
            if old[
                course
            ][0]
            != new[
                course
            ][0]
        ]

        major_flag_changes = [
            course
            for course in common
            if old[
                course
            ][1]
            != new[
                course
            ][1]
        ]

        for course in current_only:
            current_only_grade_counter[
                new[
                    course
                ][0]
            ] += 1

        if current_only or prior_only:
            cause = (
                "APPLIED_COURSE_SET_CHANGED"
            )

        elif grade_changes:
            cause = (
                "APPLIED_GRADE_CHANGED"
            )

        elif major_flag_changes:
            cause = (
                "ESTIMATED_MAJOR_FLAG_CHANGED"
            )

        elif key in prior_issue_keys:
            cause = (
                "PRIOR_PARSE_ISSUE_PRESENT"
            )

        else:
            cause = (
                "STATUS_OR_NUMERIC_ONLY_NO_APPLIED_EVIDENCE_DELTA"
            )

        per_candidate_cause.append(
            cause
        )

        cause_rows.append(
            {
                "catalog_year": key[1],
                "credential_id": key[2],
                "cause": cause,
                "current_only_course_count": len(
                    current_only
                ),
                "prior_only_course_count": len(
                    prior_only
                ),
                "grade_change_count": len(
                    grade_changes
                ),
                "major_flag_change_count": len(
                    major_flag_changes
                ),
                "prior_parse_issue_present": (
                    key
                    in prior_issue_keys
                ),
            }
        )

    cause_detail = pd.DataFrame(
        cause_rows
    )

    cause_summary = (
        cause_detail.groupby(
            "cause",
            dropna=False,
        )
        .agg(
            candidate_combinations=(
                "credential_id",
                "size",
            ),
            current_only_courses=(
                "current_only_course_count",
                "sum",
            ),
            prior_only_courses=(
                "prior_only_course_count",
                "sum",
            ),
            grade_changes=(
                "grade_change_count",
                "sum",
            ),
            major_flag_changes=(
                "major_flag_change_count",
                "sum",
            ),
        )
        .reset_index()
        .sort_values(
            "candidate_combinations",
            ascending=False,
        )
    )

    cause_summary.to_csv(
        SAFE_CAUSES,
        index=False,
    )

    grade_codes = pd.DataFrame(
        [
            {
                "current_only_grade_code": grade,
                "course_occurrences": count,
            }
            for grade, count
            in current_only_grade_counter.most_common()
        ]
    )

    grade_codes.to_csv(
        SAFE_GRADE_CODES,
        index=False,
    )

    # ------------------------------------------------------------------
    # Credential/catalog concentration.
    # ------------------------------------------------------------------
    by_credential = (
        unexpected.groupby(
            [
                "catalog_year",
                "credential_id",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="unexpected_candidate_combinations"
        )
        .sort_values(
            [
                "unexpected_candidate_combinations",
                "catalog_year",
                "credential_id",
            ],
            ascending=[
                False,
                True,
                True,
            ],
        )
    )

    by_credential.to_csv(
        SAFE_CREDENTIALS,
        index=False,
    )

    # Minimum-C transition concentration.
    if (
        "minimum_c_status_prior"
        in unexpected.columns
        and "minimum_c_status_current"
        in unexpected.columns
    ):
        minc = unexpected[
            unexpected[
                "minimum_c_status_prior"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .ne(
                unexpected[
                    "minimum_c_status_current"
                ]
                .astype(str)
                .str.strip()
                .str.upper()
            )
        ].copy()

        if not minc.empty:
            minc_summary = (
                minc.groupby(
                    [
                        "catalog_year",
                        "credential_id",
                        "minimum_c_status_prior",
                        "minimum_c_status_current",
                    ],
                    dropna=False,
                )
                .size()
                .reset_index(
                    name="candidate_combinations"
                )
                .sort_values(
                    [
                        "candidate_combinations",
                        "catalog_year",
                        "credential_id",
                    ],
                    ascending=[
                        False,
                        True,
                        True,
                    ],
                )
            )
        else:
            minc_summary = pd.DataFrame(
                columns=[
                    "catalog_year",
                    "credential_id",
                    "minimum_c_status_prior",
                    "minimum_c_status_current",
                    "candidate_combinations",
                ]
            )
    else:
        minc_summary = pd.DataFrame()

    minc_summary.to_csv(
        SAFE_MAJOR_TRANSITIONS,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "unexpected_stable_difference_rows",
                "value": len(
                    unexpected
                ),
            },
            {
                "metric": "unexpected_rows_with_prior_parse_issue",
                "value": sum(
                    key in prior_issue_keys
                    for key in unexpected_keys
                ),
            },
            {
                "metric": "unexpected_rows_with_current_applied_evidence",
                "value": sum(
                    key in current_map
                    for key in unexpected_keys
                ),
            },
            {
                "metric": "unexpected_rows_with_prior_applied_evidence",
                "value": sum(
                    key in prior_map
                    for key in unexpected_keys
                ),
            },
            {
                "metric": "unexpected_rows_course_set_changed",
                "value": per_candidate_cause.count(
                    "APPLIED_COURSE_SET_CHANGED"
                ),
            },
            {
                "metric": "unexpected_rows_grade_changed",
                "value": per_candidate_cause.count(
                    "APPLIED_GRADE_CHANGED"
                ),
            },
            {
                "metric": "unexpected_rows_major_flag_changed",
                "value": per_candidate_cause.count(
                    "ESTIMATED_MAJOR_FLAG_CHANGED"
                ),
            },
            {
                "metric": "unexpected_rows_status_numeric_only",
                "value": per_candidate_cause.count(
                    "STATUS_OR_NUMERIC_ONLY_NO_APPLIED_EVIDENCE_DELTA"
                ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 110)
    print("AWARDABILITY PARITY — UNEXPECTED DIFFERENCE DIAGNOSTICS")
    print("=" * 110)
    print(
        f"Unexpected stable differences:             {len(unexpected):,}"
    )
    print(
        f"Prior parse-issue keys among them:          "
        f"{sum(key in prior_issue_keys for key in unexpected_keys):,}"
    )
    print()
    print("APPLIED-EVIDENCE CAUSE CLASSIFICATION")
    print(
        cause_summary.to_string(
            index=False
        )
    )
    print()
    print("GATE TRANSITIONS")
    if transitions.empty:
        print("None")
    else:
        print(
            transitions.to_string(
                index=False
            )
        )
    print()
    print("CURRENT-ONLY APPLIED GRADE CODES")
    if grade_codes.empty:
        print("None")
    else:
        print(
            grade_codes.to_string(
                index=False
            )
        )
    print()
    print("TOP CREDENTIAL/CATALOG CONCENTRATIONS")
    print(
        by_credential.head(
            20
        ).to_string(
            index=False
        )
    )
    print()
    print(
        f"Parity source: {parity_dir}"
    )
    print(
        f"Current applied evidence: {current_applied_dir}"
    )
    print(
        f"Output directory: {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
