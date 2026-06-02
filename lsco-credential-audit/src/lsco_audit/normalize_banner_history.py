"""Normalize Banner student course history exports for LSCO credential audits.

Raw Banner/Argos export shape expected:
    ID, Course, Grade, Credits, Term Taken

Normalization rule for repeated courses:
    For each ID + Course, keep the attempt with the highest grade rank.
    If attempts tie on grade rank, keep the latest term.

The normalized output shape is compatible with the existing audit engine's
student course history assumptions:
    student_id, term_taken, term_sort, subject, course_number,
    course_code, grade, grade_rank, credits
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


GRADE_RANK: dict[str, int] = {
    "A": 11,
    "B": 10,
    "C": 9,
    "D": 8,
    "F": 7,
    "TS": 6,
    "CR": 5,
    "S": 4,
    "U": 3,
    "W": 2,
    "QL": 1,
    "Q": 0,
}

TERM_ORDER: dict[str, int] = {
    "WINTER": 0,
    "SPRING": 1,
    "MAYMESTER": 2,
    "MAY": 2,
    "SUMMER I": 3,
    "SUMMER 1": 3,
    "SUMMER": 4,
    "SUMMER II": 5,
    "SUMMER 2": 5,
    "FALL": 6,
}

REQUIRED_RAW_COLUMNS = ["ID", "Course", "Grade", "Credits", "Term Taken"]
NORMALIZED_COLUMNS = [
    "student_id",
    "term_taken",
    "term_sort",
    "subject",
    "course_number",
    "course_code",
    "grade",
    "grade_rank",
    "credits",
]

COURSE_PATTERN = re.compile(r"^([A-Z]{2,5})\s*([0-9]{4}[A-Z]?)$")
YEAR_PATTERN = re.compile(r"(19|20)\d{2}")


def _clean_text(value: object) -> str:
    """Return a stripped uppercase string, with internal whitespace collapsed."""
    return re.sub(r"\s+", " ", str(value).strip().upper())


def parse_course(course: object) -> tuple[str, str, str]:
    """Parse Banner course text into subject, course number, and canonical code."""
    cleaned = _clean_text(course)
    match = COURSE_PATTERN.match(cleaned)

    if not match:
        raise ValueError(f"Could not parse course value: {course!r}")

    subject, course_number = match.groups()
    course_code = f"{subject} {course_number}"
    return subject, course_number, course_code


def parse_term_sort(term_taken: object) -> int:
    """Convert term labels such as 'Fall 2007' into sortable integer keys."""
    cleaned = _clean_text(term_taken)
    year_match = YEAR_PATTERN.search(cleaned)

    if not year_match:
        raise ValueError(f"Could not parse year from term value: {term_taken!r}")

    year = int(year_match.group(0))
    term_label = YEAR_PATTERN.sub("", cleaned).strip(" -_")
    term_index = TERM_ORDER.get(term_label)

    if term_index is None:
        raise ValueError(f"Could not parse term label from term value: {term_taken!r}")

    return year * 10 + term_index


def validate_raw_columns(raw: pd.DataFrame) -> None:
    """Raise a clear error if the raw Banner export lacks expected columns."""
    missing = [column for column in REQUIRED_RAW_COLUMNS if column not in raw.columns]

    if missing:
        raise ValueError(
            "Raw Banner history is missing required column(s): "
            + ", ".join(missing)
        )


def normalize_banner_history(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw Banner course history into one auditable row per ID + Course."""
    validate_raw_columns(raw)

    normalized = raw.copy()
    normalized["student_id"] = normalized["ID"].map(_clean_text)
    normalized["grade"] = normalized["Grade"].map(_clean_text)
    normalized["credits"] = pd.to_numeric(normalized["Credits"], errors="raise")
    normalized["term_taken"] = normalized["Term Taken"].astype(str).str.strip()
    normalized["term_sort"] = normalized["Term Taken"].map(parse_term_sort)

    parsed_courses = normalized["Course"].map(parse_course)
    normalized["subject"] = parsed_courses.map(lambda value: value[0])
    normalized["course_number"] = parsed_courses.map(lambda value: value[1])
    normalized["course_code"] = parsed_courses.map(lambda value: value[2])

    unknown_grades = sorted(set(normalized["grade"]) - set(GRADE_RANK))
    if unknown_grades:
        raise ValueError("Unknown grade code(s): " + ", ".join(unknown_grades))

    normalized["grade_rank"] = normalized["grade"].map(GRADE_RANK)

    normalized = normalized.sort_values(
        by=["student_id", "course_code", "grade_rank", "term_sort"],
        ascending=[True, True, False, False],
        kind="mergesort",
    )

    normalized = normalized.drop_duplicates(
        subset=["student_id", "course_code"],
        keep="first",
    )

    normalized = normalized[NORMALIZED_COLUMNS].sort_values(
        by=["student_id", "course_code"],
        kind="mergesort",
    )

    return normalized.reset_index(drop=True)


def normalize_banner_history_csv(input_csv: str | Path, output_csv: str | Path) -> pd.DataFrame:
    """Read raw Banner CSV, normalize it, write normalized CSV, and return it."""
    raw = pd.read_csv(input_csv)
    normalized = normalize_banner_history(raw)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_csv, index=False)
    return normalized


if __name__ == "__main__":
    from lsco_audit.paths import DATA_DIR

    normalize_banner_history_csv(
        DATA_DIR / "test" / "banner_student_course_history_mock.csv",
        DATA_DIR / "test" / "student_course_history_normalized.csv",
    )
