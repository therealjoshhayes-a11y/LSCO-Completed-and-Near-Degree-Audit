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
    "grade_current_term_exact_check_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Grade_Current_Term_Exact_KPI.csv"
SAFE_GRADES = OUTPUT_DIR / "FERPA_SAFE_Grade_Exact_Disposition.csv"
SAFE_GAPS = OUTPUT_DIR / "FERPA_SAFE_Grade_Exact_Audit_Gaps.csv"


PASSING_GRADES = {
    "A", "B", "C", "D", "S",
    "T", "TA", "TB", "TC", "TD", "TS",
}

NONPASS_TERMINAL_GRADES = {
    "F", "TF", "U", "TU", "W", "Q", "QL",
}

INCOMPLETE_OR_PENDING_GRADES = {
    "", "I", "NG",
}

EXPERIENTIAL_OR_SPECIAL_GRADES = {
    "EA", "EB", "ES",
}


def norm(value: object) -> str:
    return str(value).strip().upper()


def first_existing(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def classify_grade(value: object) -> str:
    grade = norm(value)

    if grade in PASSING_GRADES:
        return "PASSING"

    if grade in NONPASS_TERMINAL_GRADES:
        return "NONPASS_TERMINAL"

    if grade in INCOMPLETE_OR_PENDING_GRADES:
        return "INCOMPLETE_OR_PENDING"

    if grade in EXPERIENTIAL_OR_SPECIAL_GRADES:
        return "EXPERIENTIAL_OR_SPECIAL"

    return "UNCLASSIFIED"


def normalize_course(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )


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

    attempts_grade = first_existing(
        list(attempts.columns),
        ["final_grade", "grade"],
    )

    audit_grade = first_existing(
        list(audit.columns),
        ["final_grade", "grade"],
    )

    attempts_term = first_existing(
        list(attempts.columns),
        ["term_sort", "term_taken"],
    )

    audit_term = first_existing(
        list(audit.columns),
        ["term_sort", "term_taken"],
    )

    if attempts_grade is None or attempts_term is None:
        raise RuntimeError(
            "All-attempts file lacks a usable grade or term column."
        )

    if audit_grade is None or audit_term is None:
        raise RuntimeError(
            "Audit history lacks a usable grade or term column. "
            f"Columns found: {', '.join(audit.columns)}"
        )

    for frame, name in (
        (attempts, "attempts"),
        (audit, "audit history"),
    ):
        required = {"student_id", "course_code"}
        missing = required - set(frame.columns)
        if missing:
            raise RuntimeError(
                f"{name} missing columns: "
                + ", ".join(sorted(missing))
            )

    attempts["course_code_norm"] = normalize_course(
        attempts["course_code"]
    )
    attempts["grade_norm"] = attempts[
        attempts_grade
    ].map(norm)
    attempts["term_norm"] = attempts[
        attempts_term
    ].astype(str).str.strip()
    attempts["grade_class"] = attempts[
        "grade_norm"
    ].map(classify_grade)

    audit["course_code_norm"] = normalize_course(
        audit["course_code"]
    )
    audit["grade_norm"] = audit[
        audit_grade
    ].map(norm)
    audit["term_norm"] = audit[
        audit_term
    ].astype(str).str.strip()

    exact_key = [
        "student_id",
        "course_code_norm",
        "term_norm",
        "grade_norm",
    ]

    attempts_exact = attempts[
        exact_key + ["grade_class"]
    ].drop_duplicates()

    audit_exact = (
        audit[exact_key]
        .drop_duplicates()
        .assign(in_audit_history=True)
    )

    joined = attempts_exact.merge(
        audit_exact,
        on=exact_key,
        how="left",
    )

    joined["in_audit_history"] = (
        joined["in_audit_history"]
        .fillna(False)
        .astype(bool)
    )

    disposition = (
        joined.groupby(
            ["grade_norm", "grade_class"],
            dropna=False,
        )
        .agg(
            exact_attempt_rows=("course_code_norm", "size"),
            distinct_students=("student_id", "nunique"),
            exact_rows_present_in_audit_history=(
                "in_audit_history",
                "sum",
            ),
        )
        .reset_index()
    )

    disposition[
        "exact_rows_missing_from_audit_history"
    ] = (
        disposition["exact_attempt_rows"]
        - disposition[
            "exact_rows_present_in_audit_history"
        ]
    )

    disposition["audit_capture_rate"] = (
        disposition[
            "exact_rows_present_in_audit_history"
        ]
        / disposition["exact_attempt_rows"]
    ).round(4)

    gaps = disposition[
        (
            disposition["grade_class"].eq("PASSING")
            & (
                disposition[
                    "exact_rows_missing_from_audit_history"
                ] > 0
            )
        )
        | (
            ~disposition["grade_class"].eq("PASSING")
            & (
                disposition[
                    "exact_rows_present_in_audit_history"
                ] > 0
            )
        )
    ].copy()

    passing_missing = int(
        joined[
            joined["grade_class"].eq("PASSING")
            & ~joined["in_audit_history"]
        ].shape[0]
    )

    nonpassing_present = int(
        joined[
            ~joined["grade_class"].eq("PASSING")
            & joined["in_audit_history"]
        ].shape[0]
    )

    pending_present = int(
        joined[
            joined["grade_class"].eq(
                "INCOMPLETE_OR_PENDING"
            )
            & joined["in_audit_history"]
        ].shape[0]
    )

    special_present = int(
        joined[
            joined["grade_class"].eq(
                "EXPERIENTIAL_OR_SPECIAL"
            )
            & joined["in_audit_history"]
        ].shape[0]
    )

    kpis = pd.DataFrame(
        [
            {
                "metric": "Exact passing attempts missing from audit history",
                "value": passing_missing,
            },
            {
                "metric": "Exact nonpassing attempts present in audit history",
                "value": nonpassing_present,
            },
            {
                "metric": "Exact incomplete/pending attempts present in audit history",
                "value": pending_present,
            },
            {
                "metric": "Exact experiential/special attempts present in audit history",
                "value": special_present,
            },
            {
                "metric": "Attempts grade column",
                "value": attempts_grade,
            },
            {
                "metric": "Audit grade column",
                "value": audit_grade,
            },
            {
                "metric": "Attempts term column",
                "value": attempts_term,
            },
            {
                "metric": "Audit term column",
                "value": audit_term,
            },
        ]
    )

    kpis.to_csv(SAFE_KPI, index=False)
    disposition.to_csv(SAFE_GRADES, index=False)
    gaps.to_csv(SAFE_GAPS, index=False)

    print("=" * 100)
    print("GRADE AND CURRENT-TERM EXACT-ATTEMPT CHECK")
    print("=" * 100)
    print(
        "Exact passing attempts missing from audit history: "
        f"{passing_missing:,}"
    )
    print(
        "Exact nonpassing attempts present in audit history: "
        f"{nonpassing_present:,}"
    )
    print(
        "Exact incomplete/pending attempts present in audit history: "
        f"{pending_present:,}"
    )
    print(
        "Exact experiential/special attempts present in audit history: "
        f"{special_present:,}"
    )
    print()
    print(f"KPI: {SAFE_KPI}")
    print(f"Grade disposition: {SAFE_GRADES}")
    print(f"Review gaps: {SAFE_GAPS}")
    print()
    print("UPLOAD ALL THREE FERPA-SAFE CSV FILES.")
    print("EXACT GRADE GATE: PASSED")


if __name__ == "__main__":
    main()
