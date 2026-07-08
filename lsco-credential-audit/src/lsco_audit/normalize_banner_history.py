"""Normalize Banner/Argos student course history exports for LSCO credential audits.

Supported raw shapes:

1. Legacy mock/test shape:
    ID, Course, Grade, Credits, Term Taken

2. Current Argos export shape:
    StudenID, FirstName, LastName, StudentMajor, Subject, CrseNumb,
    Section, FinalGrade, Term, DualCreditIndicator, HighSchool,
    LastTermDualCredit

Normalization rule for repeated courses:
    For each student_id + course_code, keep the best audit-eligible attempt.
    If attempts tie on grade rank, keep the latest term.

Outputs:
    all normalized attempts
    resolved audit-ready student course history
    normalization issues
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


PASSING_GRADES = {"A", "B", "C", "D", "S", "E", "T"}
NONPASSING_GRADES = {"F", "U", "Q", "QL", "W"}
PENDING_GRADES = {"", "I"}

GRADE_RANK: dict[str, int] = {
    "A": 12,
    "B": 11,
    "C": 10,
    "D": 9,
    "S": 8,
    "E": 8,
    "T": 8,
    "F": 7,
    "U": 6,
    "I": 5,
    "W": 4,
    "QL": 3,
    "Q": 2,
    "": 1,
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

LEGACY_RAW_COLUMNS = ["ID", "Course", "Grade", "Credits", "Term Taken"]

ARGOS_RAW_COLUMNS = [
    "StudenID",
    "FirstName",
    "LastName",
    "StudentMajor",
    "Subject",
    "CrseNumb",
    "Section",
    "FinalGrade",
    "Term",
    "DualCreditIndicator",
    "HighSchool",
    "LastTermDualCredit",
]

ALL_ATTEMPT_COLUMNS = [
    "student_id",
    "first_name",
    "last_name",
    "student_major",
    "term_taken",
    "term_sort",
    "subject",
    "course_number",
    "course_code",
    "section",
    "grade",
    "grade_rank",
    "credits",
    "passed",
    "audit_eligible",
    "pending_reason",
    "dual_credit_indicator",
    "high_school",
    "last_term_dual_credit",
]

RESOLVED_COLUMNS = ALL_ATTEMPT_COLUMNS

COURSE_PATTERN = re.compile(r"^([A-Z]{2,5})\s*([0-9]{3,4}[A-Z]?)$")
YEAR_PATTERN = re.compile(r"(19|20)\d{2}")
NUMERIC_GRADE_PATTERN = re.compile(r"^\d+(\.\d+)?$")


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip().upper())


def _clean_display(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def parse_course(course: object) -> tuple[str, str, str]:
    cleaned = _clean_text(course)
    match = COURSE_PATTERN.match(cleaned)

    if not match:
        raise ValueError(f"Could not parse course value: {course!r}")

    subject, course_number = match.groups()
    course_code = f"{subject} {course_number}"
    return subject, course_number, course_code


def parse_subject_number(subject: object, course_number: object) -> tuple[str, str, str]:
    subject_clean = _clean_text(subject)
    number_clean = _clean_text(course_number)

    if not subject_clean or not number_clean:
        raise ValueError(
            f"Could not parse subject/course number: {subject!r}, {course_number!r}"
        )

    return parse_course(f"{subject_clean} {number_clean}")


def parse_term_sort(term_taken: object) -> int:
    cleaned = _clean_text(term_taken)

    if cleaned.isdigit() and len(cleaned) >= 6:
        return int(cleaned[:6])

    year_match = YEAR_PATTERN.search(cleaned)

    if not year_match:
        raise ValueError(f"Could not parse year from term value: {term_taken!r}")

    year = int(year_match.group(0))
    term_label = YEAR_PATTERN.sub("", cleaned).strip(" -_")
    term_index = TERM_ORDER.get(term_label)

    if term_index is None:
        raise ValueError(f"Could not parse term label from term value: {term_taken!r}")

    return year * 10 + term_index


def normalize_grade(value: object) -> str:
    grade = _clean_text(value)

    if grade.endswith("S") and grade.startswith("Q"):
        return "QL"

    return grade


def classify_grade(grade: str) -> tuple[bool, bool, str]:
    if NUMERIC_GRADE_PATTERN.match(grade):
        return False, False, "NUMERIC_GRADE_NOT_ROLLED"

    if grade in PASSING_GRADES:
        return True, True, ""

    if grade in NONPASSING_GRADES:
        return False, True, ""

    if grade in PENDING_GRADES:
        if grade == "I":
            return False, False, "INCOMPLETE"
        return False, False, "BLANK_CURRENT_TERM_GRADE"

    return False, False, "UNKNOWN_GRADE"


def detect_raw_shape(raw: pd.DataFrame) -> str:
    if all(column in raw.columns for column in ARGOS_RAW_COLUMNS):
        return "argos"

    if all(column in raw.columns for column in LEGACY_RAW_COLUMNS):
        return "legacy"

    raise ValueError(
        "Raw Banner history does not match a supported shape. "
        "Expected either Argos columns or legacy mock columns."
    )


def normalize_legacy(raw: pd.DataFrame) -> pd.DataFrame:
    normalized = raw.copy()

    normalized["student_id"] = normalized["ID"].map(_clean_text)
    normalized["first_name"] = ""
    normalized["last_name"] = ""
    normalized["student_major"] = ""
    normalized["grade"] = normalized["Grade"].map(normalize_grade)
    normalized["credits"] = pd.to_numeric(normalized["Credits"], errors="coerce")
    normalized["term_taken"] = normalized["Term Taken"].astype(str).str.strip()
    normalized["term_sort"] = normalized["Term Taken"].map(parse_term_sort)

    parsed_courses = normalized["Course"].map(parse_course)
    normalized["subject"] = parsed_courses.map(lambda value: value[0])
    normalized["course_number"] = parsed_courses.map(lambda value: value[1])
    normalized["course_code"] = parsed_courses.map(lambda value: value[2])

    normalized["section"] = ""
    normalized["dual_credit_indicator"] = ""
    normalized["high_school"] = ""
    normalized["last_term_dual_credit"] = ""

    return normalized


def normalize_argos(raw: pd.DataFrame) -> pd.DataFrame:
    normalized = raw.copy()

    normalized["student_id"] = normalized["StudenID"].map(_clean_text)
    normalized["first_name"] = normalized["FirstName"].map(_clean_display)
    normalized["last_name"] = normalized["LastName"].map(_clean_display)
    normalized["student_major"] = normalized["StudentMajor"].map(_clean_display)
    normalized["grade"] = normalized["FinalGrade"].map(normalize_grade)
    normalized["credits"] = pd.NA
    normalized["term_taken"] = normalized["Term"].astype(str).str.strip()
    normalized["term_sort"] = normalized["Term"].map(parse_term_sort)

    parsed_courses = normalized.apply(
        lambda row: parse_subject_number(row["Subject"], row["CrseNumb"]),
        axis=1,
    )
    normalized["subject"] = parsed_courses.map(lambda value: value[0])
    normalized["course_number"] = parsed_courses.map(lambda value: value[1])
    normalized["course_code"] = parsed_courses.map(lambda value: value[2])

    normalized["section"] = normalized["Section"].map(_clean_text)
    normalized["dual_credit_indicator"] = normalized["DualCreditIndicator"].map(_clean_display)
    normalized["high_school"] = normalized["HighSchool"].map(_clean_display)
    normalized["last_term_dual_credit"] = normalized["LastTermDualCredit"].map(_clean_display)

    return normalized


def add_grade_classification(normalized: pd.DataFrame) -> pd.DataFrame:
    normalized = normalized.copy()

    classifications = normalized["grade"].map(classify_grade)
    normalized["passed"] = classifications.map(lambda value: value[0])
    normalized["audit_eligible"] = classifications.map(lambda value: value[1])
    normalized["pending_reason"] = classifications.map(lambda value: value[2])

    normalized["grade_rank"] = normalized["grade"].map(
        lambda grade: GRADE_RANK.get(grade, 0)
    )

    return normalized


def normalize_all_attempts(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    shape = detect_raw_shape(raw)

    issues = []

    try:
        if shape == "argos":
            normalized = normalize_argos(raw)
        else:
            normalized = normalize_legacy(raw)
    except Exception as exc:
        raise ValueError(f"Normalization failed: {exc}") from exc

    normalized = add_grade_classification(normalized)

    issue_rows = normalized[normalized["pending_reason"].astype(str) != ""].copy()
    if not issue_rows.empty:
        for _, row in issue_rows.iterrows():
            issues.append(
                {
                    "student_id": row.get("student_id", ""),
                    "term_taken": row.get("term_taken", ""),
                    "course_code": row.get("course_code", ""),
                    "grade": row.get("grade", ""),
                    "issue": row.get("pending_reason", ""),
                }
            )

    all_attempts = normalized[ALL_ATTEMPT_COLUMNS].sort_values(
        by=["student_id", "course_code", "term_sort"],
        kind="mergesort",
    )

    issues_df = pd.DataFrame(
        issues,
        columns=["student_id", "term_taken", "course_code", "grade", "issue"],
    )

    return all_attempts.reset_index(drop=True), issues_df


def resolve_best_attempts(all_attempts: pd.DataFrame) -> pd.DataFrame:
    # Resolved audit-ready history should include completed/earned attempts only.
    # Non-passing finalized attempts remain available in all_attempts output.
    eligible = all_attempts[all_attempts["passed"] == True].copy()

    eligible = eligible.sort_values(
        by=["student_id", "course_code", "passed", "grade_rank", "term_sort"],
        ascending=[True, True, False, False, False],
        kind="mergesort",
    )

    resolved = eligible.drop_duplicates(
        subset=["student_id", "course_code"],
        keep="first",
    )

    resolved = resolved[RESOLVED_COLUMNS].sort_values(
        by=["student_id", "course_code"],
        kind="mergesort",
    )

    return resolved.reset_index(drop=True)


def normalize_banner_history(raw: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible helper returning resolved audit-ready attempts only."""
    all_attempts, _issues = normalize_all_attempts(raw)
    return resolve_best_attempts(all_attempts)


def normalize_banner_history_csv(input_csv: str | Path, output_csv: str | Path) -> pd.DataFrame:
    raw = pd.read_csv(input_csv, encoding="cp1252")
    normalized = normalize_banner_history(raw)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_csv, index=False)
    return normalized


def normalize_banner_history_files(
    input_csv: str | Path,
    resolved_output_csv: str | Path,
    all_attempts_output_csv: str | Path,
    issues_output_csv: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(input_csv, encoding="cp1252")

    all_attempts, issues = normalize_all_attempts(raw)
    resolved = resolve_best_attempts(all_attempts)

    Path(resolved_output_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(all_attempts_output_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(issues_output_csv).parent.mkdir(parents=True, exist_ok=True)

    all_attempts.to_csv(all_attempts_output_csv, index=False)
    resolved.to_csv(resolved_output_csv, index=False)
    issues.to_csv(issues_output_csv, index=False)

    return resolved, all_attempts, issues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--resolved-output",
        default="data/processed/student_course_history_normalized.csv",
    )
    parser.add_argument(
        "--all-attempts-output",
        default="data/processed/all_student_course_attempts_normalized.csv",
    )
    parser.add_argument(
        "--issues-output",
        default="data/interim/banner_normalization_issues.csv",
    )

    args = parser.parse_args()

    resolved, all_attempts, issues = normalize_banner_history_files(
        input_csv=args.input,
        resolved_output_csv=args.resolved_output,
        all_attempts_output_csv=args.all_attempts_output,
        issues_output_csv=args.issues_output,
    )

    print(f"Wrote {args.all_attempts_output}: {len(all_attempts)} rows")
    print(f"Wrote {args.resolved_output}: {len(resolved)} rows")
    print(f"Wrote {args.issues_output}: {len(issues)} rows")


if __name__ == "__main__":
    main()
