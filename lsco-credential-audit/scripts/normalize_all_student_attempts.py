"""Build the full course-attempt activity record (all grades, not just passing).

WHY THIS SCRIPT EXISTS
-----------------------
`normalize_actual_student_course_history.py` filters to `is_passing_grade`
before it writes output (see its `df = df[df["is_passing"]].copy()` step).
That's correct for a completion/GPA record, but `build_student_catalog_eligibility.py`
also needs to know about terms where the student was *enrolled but not passing*
(W, F, I, Q, or a blank current-term grade) in order to correctly detect
enrollment gaps. Today, nothing in the pipeline ever writes that file, so
`build_student_catalog_eligibility.py` silently falls back to the passing-only
file for both "earned" and "activity" — meaning a semester where a student
picked up only an F or a W is invisible to the continuity check, and can
produce a false gap.

This script performs no completion logic. It emits one row per raw
attempt with normalized student_id / term_sort, keeping every FinalGrade
value including blanks (current term, still enrolled).

Output columns: student_id, student_major, course_code, final_grade,
term_taken, term_sort.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

INPUT_PATH = Path("data/raw/student_exports/banner_course_history_actual.csv")
OUTPUT_PATH = Path("data/processed/all_student_course_attempts_normalized.csv")

REQUIRED_COLUMNS = [
    "StudenID",
    "StudentMajor",
    "Subject",
    "CrseNumb",
    "FinalGrade",
    "Term",
]


def normalize_course_code(subject: str, number: str) -> str:
    subject = str(subject).strip().upper()
    number = str(number).strip()

    if subject in {"", "NAN"} or number in {"", "NAN"}:
        return ""

    number = number.split(".")[0].zfill(4)
    return f"{subject} {number}"


def main(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    raw = pd.read_csv(input_path, dtype=str).fillna("")

    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = pd.DataFrame()
    df["student_id"] = raw["StudenID"].astype(str).str.strip()
    df["student_major"] = raw["StudentMajor"].astype(str).str.strip()
    df["subject"] = raw["Subject"].astype(str).str.strip().str.upper()
    df["course_number"] = raw["CrseNumb"].astype(str).str.strip()
    df["course_code"] = [
        normalize_course_code(subject, number)
        for subject, number in zip(df["subject"], df["course_number"])
    ]
    df["final_grade"] = raw["FinalGrade"].astype(str).str.strip().str.upper()
    df["term_taken"] = raw["Term"].astype(str).str.strip()
    df["term_sort"] = pd.to_numeric(df["term_taken"], errors="coerce")

    # NOTE: deliberately no filter on final_grade/is_passing here.
    # A blank grade means "current term" (LSCO_Grades.md) -- still enrolled,
    # still relevant to gap detection, and must NOT be dropped.
    df = df[df["student_id"].ne("")]
    df = df[df["term_sort"].notna()]
    df = df[df["term_sort"].ge(197000)]

    output_cols = [
        "student_id",
        "student_major",
        "course_code",
        "final_grade",
        "term_taken",
        "term_sort",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df[output_cols].to_csv(output_path, index=False)

    print(f"Wrote {len(df)} attempt rows (all grades) to {output_path}")
    return df[output_cols]


if __name__ == "__main__":
    main()
