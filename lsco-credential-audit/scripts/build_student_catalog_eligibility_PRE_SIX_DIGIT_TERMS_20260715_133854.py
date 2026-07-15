"""Build student catalog-year eligibility flags.

Rules implemented:
    1. Student must have at least one earned course during the catalog year.
       Example: 2021-2022 means Fall 2021 through Summer 2022.

    2. Student may not have course activity after the five-year catalog life.
       Example: 2021-2022 valid through Summer 2026.

    3. Student is flagged for continuity review if earned coursework shows
       a break of two missed long semesters.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_STUDENT_HISTORY = Path("data") / "processed" / "student_course_history_normalized.csv"
DEFAULT_ALL_ATTEMPTS = Path("data") / "processed" / "all_student_course_attempts_normalized.csv"
DEFAULT_REQUIREMENTS = Path("data") / "processed" / "catalogs" / "requirements_master_multiyear.csv"
DEFAULT_OUTPUT = Path("data") / "processed" / "student_catalog_eligibility.csv"

PASSING_GRADES = {"A", "B", "C", "D", "S", "E", "T"}


def parse_catalog_start_year(catalog_year: str) -> int:
    return int(str(catalog_year).split("-")[0])


def catalog_start_term_sort(catalog_year: str) -> int:
    start_year = parse_catalog_start_year(catalog_year)
    return start_year * 10 + 6  # Fall


def catalog_year_end_term_sort(catalog_year: str) -> int:
    start_year = parse_catalog_start_year(catalog_year)
    return (start_year + 1) * 10 + 5  # Summer II / end of catalog year


def catalog_life_end_term_sort(catalog_year: str) -> int:
    start_year = parse_catalog_start_year(catalog_year)
    return (start_year + 5) * 10 + 5  # Summer II five years later


def term_sort_to_long_ordinal(term_sort: int) -> int | None:
    """Map Spring/Fall terms to a continuous long-semester ordinal.

    Spring YYYY -> YYYY * 2
    Fall YYYY   -> YYYY * 2 + 1

    Summer terms do not count as long semesters for continuity.
    """

    year = int(term_sort) // 10
    term_index = int(term_sort) % 10

    if term_index == 1:
        return year * 2

    if term_index == 6:
        return year * 2 + 1

    return None


def max_long_semester_gap(earned_terms: list[int]) -> int:
    ordinals = sorted(
        value
        for value in (term_sort_to_long_ordinal(term) for term in earned_terms)
        if value is not None
    )

    if len(ordinals) < 2:
        return 0

    return max(curr - prev - 1 for prev, curr in zip(ordinals, ordinals[1:]))


def load_student_history(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.copy()

    if "term_sort" not in df.columns:
        raise ValueError(f"{path} is missing required column: term_sort")

    if "student_id" not in df.columns:
        raise ValueError(f"{path} is missing required column: student_id")

    df["term_sort"] = pd.to_numeric(df["term_sort"], errors="coerce")
    df = df[df["term_sort"].notna()].copy()
    df["term_sort"] = df["term_sort"].astype(int)

    if "passed" in df.columns:
        df["earned_for_catalog"] = df["passed"].astype(str).str.upper().eq("TRUE")
    elif "grade" in df.columns:
        df["earned_for_catalog"] = df["grade"].astype(str).str.upper().isin(PASSING_GRADES)
    else:
        raise ValueError(f"{path} must have either passed or grade column")

    return df


def load_activity_history(all_attempts_path: Path, fallback_path: Path) -> pd.DataFrame:
    if all_attempts_path.exists():
        return load_student_history(all_attempts_path)

    return load_student_history(fallback_path)


def load_catalog_years(requirements_path: Path) -> list[str]:
    requirements = pd.read_csv(requirements_path, dtype=str)

    if "catalog_year" not in requirements.columns:
        raise ValueError(f"{requirements_path} is missing required column: catalog_year")

    return sorted(requirements["catalog_year"].dropna().astype(str).unique())


def build_student_catalog_eligibility(
    earned_history: pd.DataFrame,
    activity_history: pd.DataFrame,
    catalog_years: list[str],
) -> pd.DataFrame:
    rows = []

    students = sorted(
        set(earned_history["student_id"].dropna().astype(str))
        | set(activity_history["student_id"].dropna().astype(str))
    )

    earned_only = earned_history[earned_history["earned_for_catalog"] == True].copy()

    for student_id in students:
        student_earned = earned_only[earned_only["student_id"].astype(str).eq(student_id)]
        student_activity = activity_history[activity_history["student_id"].astype(str).eq(student_id)]

        earned_terms = sorted(student_earned["term_sort"].dropna().astype(int).unique())
        activity_terms = sorted(student_activity["term_sort"].dropna().astype(int).unique())

        first_earned = min(earned_terms) if earned_terms else None
        latest_earned = max(earned_terms) if earned_terms else None
        latest_activity = max(activity_terms) if activity_terms else None
        long_gap = max_long_semester_gap(earned_terms)
        continuity_break = long_gap >= 2

        for catalog_year in catalog_years:
            start_term = catalog_start_term_sort(catalog_year)
            year_end_term = catalog_year_end_term_sort(catalog_year)
            life_end_term = catalog_life_end_term_sort(catalog_year)

            earned_in_catalog_year = any(
                start_term <= term <= year_end_term for term in earned_terms
            )

            has_activity_after_life = (
                latest_activity is not None and latest_activity > life_end_term
            )

            reasons = []

            if not earned_in_catalog_year:
                reasons.append("NO_EARNED_COURSE_IN_CATALOG_YEAR")

            if has_activity_after_life:
                reasons.append("COURSE_ACTIVITY_AFTER_CATALOG_LIFE")

            if continuity_break:
                reasons.append("CATALOG_CONTINUITY_REVIEW")

            catalog_eligible = (
                earned_in_catalog_year
                and not has_activity_after_life
                and not continuity_break
            )

            rows.append(
                {
                    "student_id": student_id,
                    "catalog_year": catalog_year,
                    "catalog_start_term_sort": start_term,
                    "catalog_year_end_term_sort": year_end_term,
                    "catalog_life_end_term_sort": life_end_term,
                    "earned_course_in_catalog_year": earned_in_catalog_year,
                    "first_earned_term_sort": first_earned,
                    "latest_earned_term_sort": latest_earned,
                    "latest_activity_term_sort": latest_activity,
                    "has_activity_after_catalog_life": has_activity_after_life,
                    "max_missed_long_semesters_between_earned_terms": long_gap,
                    "continuity_break": continuity_break,
                    "catalog_eligible": catalog_eligible,
                    "eligibility_reason": ";".join(reasons) if reasons else "ELIGIBLE",
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--student-history", default=str(DEFAULT_STUDENT_HISTORY))
    parser.add_argument("--all-attempts", default=str(DEFAULT_ALL_ATTEMPTS))
    parser.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    student_history_path = Path(args.student_history)
    all_attempts_path = Path(args.all_attempts)
    requirements_path = Path(args.requirements)
    output_path = Path(args.output)

    earned_history = load_student_history(student_history_path)
    activity_history = load_activity_history(all_attempts_path, student_history_path)
    catalog_years = load_catalog_years(requirements_path)

    eligibility = build_student_catalog_eligibility(
        earned_history=earned_history,
        activity_history=activity_history,
        catalog_years=catalog_years,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    eligibility.to_csv(output_path, index=False)

    print(f"Wrote {output_path}: {len(eligibility)} rows")
    print()
    print(eligibility.groupby(["catalog_year", "catalog_eligible"]).size().to_string())
    print()
    print(eligibility["eligibility_reason"].value_counts().to_string())


if __name__ == "__main__":
    main()
