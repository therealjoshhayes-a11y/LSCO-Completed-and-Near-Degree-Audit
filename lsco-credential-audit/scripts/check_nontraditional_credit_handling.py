from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ATTEMPTS = Path(
    "data/processed/all_student_course_attempts_normalized.csv"
)

AUDIT_HISTORY = Path(
    "data/processed/normalized_actual_student_course_history.csv"
)

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / (
    "nontraditional_credit_shadow_check_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Nontraditional_Credit_KPI.csv"
SAFE_METHODS = OUTPUT_DIR / "FERPA_SAFE_Nontraditional_Credit_By_Method.csv"
SAFE_GAPS = OUTPUT_DIR / "FERPA_SAFE_Nontraditional_Credit_Audit_Gaps.csv"
SAFE_COLUMNS = OUTPUT_DIR / "FERPA_SAFE_Nontraditional_Credit_Column_Profile.csv"


PASSING_GRADES = {
    "A", "B", "C", "D", "S", "P", "CR", "T",
    "TA", "TB", "TC", "TD", "TS",
}

METHOD_COLUMN_CANDIDATES = [
    "credit_type",
    "credit_source",
    "source_type",
    "institution_type",
    "course_source",
    "transfer_indicator",
    "transfer_flag",
    "nontraditional_credit_type",
    "prior_learning_type",
    "registration_status",
]

TRANSFER_COLUMN_CANDIDATES = [
    "transfer_indicator",
    "transfer_flag",
    "is_transfer",
    "transfer_course",
]

INSTITUTION_COLUMN_CANDIDATES = [
    "institution",
    "institution_name",
    "source_institution",
    "transfer_institution",
    "school_name",
]

GRADE_COLUMN_CANDIDATES = [
    "final_grade",
    "grade",
]

TERM_COLUMN_CANDIDATES = [
    "term_sort",
    "term_taken",
]


def norm(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def first_existing(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def truthy(value: object) -> bool:
    return norm(value) in {
        "TRUE", "1", "YES", "Y", "T", "TRANSFER",
    }


def classify_method(
    row: pd.Series,
    method_columns: list[str],
    transfer_columns: list[str],
    institution_columns: list[str],
) -> str:
    values = []

    for column in method_columns:
        value = norm(row.get(column, ""))
        if value:
            values.append(value)

    joined = " | ".join(values)

    if any(
        token in joined
        for token in (
            "CLEP",
            "AP ",
            "ADVANCED PLACEMENT",
            "IB ",
            "INTERNATIONAL BACCALAUREATE",
            "DSST",
            "EXAM",
            "TEST CREDIT",
        )
    ):
        return "EXAM_OR_TEST_CREDIT"

    if any(
        token in joined
        for token in (
            "MILITARY",
            "JST",
            "ACE",
        )
    ):
        return "MILITARY_OR_ACE_CREDIT"

    if any(
        token in joined
        for token in (
            "PRIOR LEARNING",
            "PLA",
            "PORTFOLIO",
            "ARTICULATED",
            "ARTICULATION",
        )
    ):
        return "PRIOR_LEARNING_OR_ARTICULATED"

    if any(
        truthy(row.get(column, ""))
        for column in transfer_columns
    ):
        return "TRANSFER_CREDIT"

    institution_values = [
        norm(row.get(column, ""))
        for column in institution_columns
        if norm(row.get(column, ""))
    ]

    if institution_values:
        institution_joined = " | ".join(institution_values)

        if not any(
            token in institution_joined
            for token in (
                "LAMAR STATE COLLEGE ORANGE",
                "LSCO",
                "LAMAR STATE COLLEGE-ORANGE",
            )
        ):
            return "TRANSFER_OR_EXTERNAL_INSTITUTION"

    if any(
        token in joined
        for token in (
            "TRANSFER",
            "TRNS",
            "EXTERNAL",
        )
    ):
        return "TRANSFER_CREDIT"

    if joined:
        return "OTHER_IDENTIFIED_METHOD"

    return "NO_METHOD_IDENTIFIED"


def main() -> None:
    for path in (ATTEMPTS, AUDIT_HISTORY):
        if not path.exists():
            raise FileNotFoundError(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    attempts = pd.read_csv(
        ATTEMPTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    audit = pd.read_csv(
        AUDIT_HISTORY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required = {
        "student_id",
        "course_code",
    }

    for frame, name in (
        (attempts, "attempts"),
        (audit, "audit history"),
    ):
        missing = required - set(frame.columns)

        if missing:
            raise RuntimeError(
                f"{name} missing columns: "
                + ", ".join(sorted(missing))
            )

    grade_col = first_existing(
        list(attempts.columns),
        GRADE_COLUMN_CANDIDATES,
    )

    if grade_col is None:
        raise RuntimeError(
            "Could not locate a grade column in all-attempts file."
        )

    method_columns = [
        column
        for column in METHOD_COLUMN_CANDIDATES
        if column in attempts.columns
    ]

    transfer_columns = [
        column
        for column in TRANSFER_COLUMN_CANDIDATES
        if column in attempts.columns
    ]

    institution_columns = [
        column
        for column in INSTITUTION_COLUMN_CANDIDATES
        if column in attempts.columns
    ]

    attempts["course_code_norm"] = attempts[
        "course_code"
    ].map(norm)

    audit["course_code_norm"] = audit[
        "course_code"
    ].map(norm)

    passed = attempts[
        attempts[grade_col]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(PASSING_GRADES)
    ].copy()

    passed["credit_method_class"] = passed.apply(
        classify_method,
        axis=1,
        method_columns=method_columns,
        transfer_columns=transfer_columns,
        institution_columns=institution_columns,
    )

    term_col = first_existing(
        list(passed.columns),
        TERM_COLUMN_CANDIDATES,
    )

    attempt_grain = [
        "student_id",
        "course_code_norm",
        grade_col,
    ]

    if term_col is not None:
        attempt_grain.append(term_col)

    passed = passed.drop_duplicates(
        subset=attempt_grain,
    ).copy()

    audit_pairs = audit[
        ["student_id", "course_code_norm"]
    ].drop_duplicates()

    passed = passed.merge(
        audit_pairs.assign(in_audit_history=True),
        on=["student_id", "course_code_norm"],
        how="left",
    )

    passed["in_audit_history"] = (
        passed["in_audit_history"]
        .fillna(False)
        .astype(bool)
    )

    nontraditional_mask = ~passed[
        "credit_method_class"
    ].eq("NO_METHOD_IDENTIFIED")

    nontraditional = passed[
        nontraditional_mask
    ].copy()

    by_method = (
        nontraditional.groupby(
            "credit_method_class",
            dropna=False,
        )
        .agg(
            passed_attempt_rows=(
                "course_code_norm",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            distinct_courses=(
                "course_code_norm",
                "nunique",
            ),
            rows_present_in_audit_history=(
                "in_audit_history",
                "sum",
            ),
        )
        .reset_index()
    )

    by_method[
        "rows_missing_from_audit_history"
    ] = (
        by_method["passed_attempt_rows"]
        - by_method["rows_present_in_audit_history"]
    )

    by_method[
        "audit_capture_rate"
    ] = (
        by_method["rows_present_in_audit_history"]
        / by_method["passed_attempt_rows"]
    ).round(4)

    gaps = (
        nontraditional[
            ~nontraditional["in_audit_history"]
        ]
        .groupby(
            [
                "credit_method_class",
                "course_code_norm",
            ],
            dropna=False,
        )
        .agg(
            missing_attempt_rows=(
                "course_code_norm",
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
                "missing_attempt_rows",
                "credit_method_class",
                "course_code_norm",
            ],
            ascending=[False, True, True],
            kind="mergesort",
        )
    )

    column_profile_rows = []

    for column in sorted(
        set(
            method_columns
            + transfer_columns
            + institution_columns
            + [grade_col]
            + ([term_col] if term_col else [])
        )
    ):
        values = attempts[column].astype(str)

        column_profile_rows.append(
            {
                "column_name": column,
                "nonblank_rows": int(
                    values.str.strip().ne("").sum()
                ),
                "distinct_nonblank_values": int(
                    values[
                        values.str.strip().ne("")
                    ].nunique()
                ),
                "sample_values": " | ".join(
                    sorted(
                        set(
                            values[
                                values.str.strip().ne("")
                            ].head(25)
                        )
                    )[:10]
                ),
            }
        )

    column_profile = pd.DataFrame(
        column_profile_rows
    )

    kpis = pd.DataFrame(
        [
            {
                "metric": "Passed attempt rows",
                "value": len(passed),
            },
            {
                "metric": "Passed rows with identified nontraditional/external method",
                "value": len(nontraditional),
            },
            {
                "metric": "Distinct students with identified nontraditional/external credit",
                "value": nontraditional["student_id"].nunique(),
            },
            {
                "metric": "Identified rows present in audit history",
                "value": int(
                    nontraditional[
                        "in_audit_history"
                    ].sum()
                ),
            },
            {
                "metric": "Identified rows missing from audit history",
                "value": int(
                    (
                        ~nontraditional[
                            "in_audit_history"
                        ]
                    ).sum()
                ),
            },
            {
                "metric": "Method columns detected",
                "value": " | ".join(method_columns),
            },
            {
                "metric": "Transfer columns detected",
                "value": " | ".join(transfer_columns),
            },
            {
                "metric": "Institution columns detected",
                "value": " | ".join(institution_columns),
            },
            {
                "metric": "Grade column used",
                "value": grade_col,
            },
        ]
    )

    kpis.to_csv(SAFE_KPI, index=False)
    by_method.to_csv(SAFE_METHODS, index=False)
    gaps.to_csv(SAFE_GAPS, index=False)
    column_profile.to_csv(SAFE_COLUMNS, index=False)

    print("=" * 100)
    print("TRANSFER AND NONTRADITIONAL CREDIT SHADOW CHECK")
    print("=" * 100)
    print(f"Passed attempt rows: {len(passed):,}")
    print(
        "Passed rows with identified nontraditional/external method: "
        f"{len(nontraditional):,}"
    )
    print(
        "Distinct students with identified nontraditional/external credit: "
        f"{nontraditional['student_id'].nunique():,}"
    )
    print(
        "Identified rows missing from audit history: "
        f"{int((~nontraditional['in_audit_history']).sum()):,}"
    )
    print()
    print(f"Method columns detected: {method_columns}")
    print(f"Transfer columns detected: {transfer_columns}")
    print(f"Institution columns detected: {institution_columns}")
    print()
    print(f"KPI: {SAFE_KPI}")
    print(f"By method: {SAFE_METHODS}")
    print(f"Audit gaps: {SAFE_GAPS}")
    print(f"Column profile: {SAFE_COLUMNS}")
    print()
    print("UPLOAD ALL FOUR FERPA-SAFE CSV FILES.")
    print("NONTRADITIONAL-CREDIT GATE: PASSED")


if __name__ == "__main__":
    main()
