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

ELIGIBILITY = Path(
    "data/processed/student_catalog_eligibility.csv"
)

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / (
    "grade_current_term_shadow_check_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Grade_Current_Term_KPI.csv"
SAFE_GRADES = OUTPUT_DIR / "FERPA_SAFE_Grade_Disposition.csv"
SAFE_AUDIT_GAPS = OUTPUT_DIR / "FERPA_SAFE_Grade_Audit_History_Gaps.csv"
SAFE_TERM_PROFILE = OUTPUT_DIR / "FERPA_SAFE_Current_Term_Profile.csv"


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


def main() -> None:
    for path in (ATTEMPTS, AUDIT_HISTORY, ELIGIBILITY):
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

    eligibility = pd.read_csv(
        ELIGIBILITY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    grade_col = first_existing(
        list(attempts.columns),
        ["final_grade", "grade"],
    )

    term_col = first_existing(
        list(attempts.columns),
        ["term_sort", "term_taken"],
    )

    if grade_col is None or term_col is None:
        raise RuntimeError(
            "Could not identify grade and term columns."
        )

    required = {"student_id", "course_code"}

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

    attempts["grade_norm"] = attempts[grade_col].map(norm)
    attempts["grade_class"] = attempts["grade_norm"].map(classify_grade)

    attempts["course_code_norm"] = (
        attempts["course_code"]
        .astype(str)
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    audit["course_code_norm"] = (
        audit["course_code"]
        .astype(str)
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    audit_pairs = (
        audit[
            ["student_id", "course_code_norm"]
        ]
        .drop_duplicates()
        .assign(in_audit_history=True)
    )

    attempt_pairs = attempts[
        [
            "student_id",
            "course_code_norm",
            "grade_norm",
            "grade_class",
            term_col,
        ]
    ].drop_duplicates()

    joined = attempt_pairs.merge(
        audit_pairs,
        on=["student_id", "course_code_norm"],
        how="left",
    )

    joined["in_audit_history"] = (
        joined["in_audit_history"]
        .fillna(False)
        .astype(bool)
    )

    grade_summary = (
        joined.groupby(
            ["grade_norm", "grade_class"],
            dropna=False,
        )
        .agg(
            attempt_rows=(
                "course_code_norm",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            rows_present_in_audit_history=(
                "in_audit_history",
                "sum",
            ),
        )
        .reset_index()
    )

    grade_summary[
        "rows_missing_from_audit_history"
    ] = (
        grade_summary["attempt_rows"]
        - grade_summary["rows_present_in_audit_history"]
    )

    grade_summary[
        "audit_capture_rate"
    ] = (
        grade_summary["rows_present_in_audit_history"]
        / grade_summary["attempt_rows"]
    ).round(4)

    audit_gaps = grade_summary[
        grade_summary["rows_missing_from_audit_history"] > 0
    ].copy()

    # Current/latest term profile
    numeric_terms = pd.to_numeric(
        attempts[term_col],
        errors="coerce",
    )

    latest_term = int(numeric_terms.max())

    current_term_rows = attempts[
        numeric_terms.eq(latest_term)
    ].copy()

    current_term_profile = (
        current_term_rows.groupby(
            ["grade_norm", "grade_class"],
            dropna=False,
        )
        .agg(
            attempt_rows=("course_code_norm", "size"),
            distinct_students=("student_id", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["grade_class", "grade_norm"],
            kind="mergesort",
        )
    )

    # Eligibility activity check for students whose only latest-term rows are pending.
    latest_student_term = (
        attempts.assign(term_numeric=numeric_terms)
        .groupby("student_id")["term_numeric"]
        .max()
        .rename("latest_term_numeric")
        .reset_index()
    )

    latest_attempts = attempts.merge(
        latest_student_term,
        on="student_id",
        how="left",
    )

    latest_attempts = latest_attempts[
        pd.to_numeric(
            latest_attempts[term_col],
            errors="coerce",
        ).eq(
            latest_attempts["latest_term_numeric"]
        )
    ].copy()

    latest_only_pending = (
        latest_attempts.groupby("student_id")["grade_class"]
        .apply(
            lambda s: set(s).issubset(
                {"INCOMPLETE_OR_PENDING"}
            )
        )
        .rename("latest_term_only_pending")
        .reset_index()
    )

    eligible_students = set(
        eligibility.loc[
            eligibility["catalog_eligible"]
            .astype(str)
            .str.upper()
            .isin({"TRUE", "1", "YES", "Y", "ELIGIBLE"}),
            "student_id",
        ]
        .astype(str)
        .tolist()
    )

    latest_only_pending[
        "has_any_catalog_eligibility"
    ] = latest_only_pending[
        "student_id"
    ].astype(str).isin(eligible_students)

    pending_students = latest_only_pending[
        latest_only_pending["latest_term_only_pending"]
    ]

    kpis = pd.DataFrame(
        [
            {
                "metric": "Latest term code",
                "value": latest_term,
            },
            {
                "metric": "Passing attempt rows",
                "value": int(
                    joined["grade_class"]
                    .eq("PASSING")
                    .sum()
                ),
            },
            {
                "metric": "Passing rows missing from audit history",
                "value": int(
                    joined[
                        joined["grade_class"].eq("PASSING")
                        & ~joined["in_audit_history"]
                    ].shape[0]
                ),
            },
            {
                "metric": "Nonpassing rows present in audit history",
                "value": int(
                    joined[
                        ~joined["grade_class"].eq("PASSING")
                        & joined["in_audit_history"]
                    ].shape[0]
                ),
            },
            {
                "metric": "Incomplete or pending rows present in audit history",
                "value": int(
                    joined[
                        joined["grade_class"]
                        .eq("INCOMPLETE_OR_PENDING")
                        & joined["in_audit_history"]
                    ].shape[0]
                ),
            },
            {
                "metric": "Experiential or special grade rows",
                "value": int(
                    joined["grade_class"]
                    .eq("EXPERIENTIAL_OR_SPECIAL")
                    .sum()
                ),
            },
            {
                "metric": "Experiential or special rows present in audit history",
                "value": int(
                    joined[
                        joined["grade_class"]
                        .eq("EXPERIENTIAL_OR_SPECIAL")
                        & joined["in_audit_history"]
                    ].shape[0]
                ),
            },
            {
                "metric": "Students whose latest term contains only pending grades",
                "value": int(len(pending_students)),
            },
            {
                "metric": "Pending-only latest-term students with catalog eligibility",
                "value": int(
                    pending_students[
                        "has_any_catalog_eligibility"
                    ].sum()
                ),
            },
        ]
    )

    kpis.to_csv(SAFE_KPI, index=False)
    grade_summary.to_csv(SAFE_GRADES, index=False)
    audit_gaps.to_csv(SAFE_AUDIT_GAPS, index=False)
    current_term_profile.to_csv(SAFE_TERM_PROFILE, index=False)

    print("=" * 100)
    print("GRADE AND CURRENT-TERM SHADOW CHECK")
    print("=" * 100)
    print(f"Latest term code: {latest_term}")
    print(
        "Passing rows missing from audit history: "
        f"{int(joined[joined['grade_class'].eq('PASSING') & ~joined['in_audit_history']].shape[0]):,}"
    )
    print(
        "Nonpassing rows present in audit history: "
        f"{int(joined[~joined['grade_class'].eq('PASSING') & joined['in_audit_history']].shape[0]):,}"
    )
    print(
        "Incomplete/pending rows present in audit history: "
        f"{int(joined[joined['grade_class'].eq('INCOMPLETE_OR_PENDING') & joined['in_audit_history']].shape[0]):,}"
    )
    print(
        "Experiential/special rows present in audit history: "
        f"{int(joined[joined['grade_class'].eq('EXPERIENTIAL_OR_SPECIAL') & joined['in_audit_history']].shape[0]):,}"
    )
    print(
        "Students whose latest term contains only pending grades: "
        f"{len(pending_students):,}"
    )
    print(
        "Pending-only latest-term students with catalog eligibility: "
        f"{int(pending_students['has_any_catalog_eligibility'].sum()):,}"
    )
    print()
    print(f"KPI: {SAFE_KPI}")
    print(f"Grade disposition: {SAFE_GRADES}")
    print(f"Audit gaps: {SAFE_AUDIT_GAPS}")
    print(f"Current-term profile: {SAFE_TERM_PROFILE}")
    print()
    print("UPLOAD ALL FOUR FERPA-SAFE CSV FILES.")
    print("GRADE/CURRENT-TERM GATE: PASSED")


if __name__ == "__main__":
    main()
