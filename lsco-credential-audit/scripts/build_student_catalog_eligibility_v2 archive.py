"""Build student catalog-year assignment, segmented by real enrollment gaps.

Policy this implements (agreed 2026-07-16):
    1. A student's assigned catalog is the catalog in effect the term they
       FIRST had any course activity (any grade, including W/F/I/Q/blank --
       a blank grade means "current term," i.e. still enrolled) since their
       last reset, or since the start of their record if never reset.
    2. Coursework does not expire. There is no cutoff based on how long ago
       a catalog started.
    3. A reset is triggered by a gap of two consecutive missed long
       semesters (Fall/Spring; Summer does not count) with ZERO course
       activity at LSCO -- not zero passing grades, zero activity of any
       kind. On a reset, the student is re-anchored to the catalog in
       effect at their next term of activity.

FLAGGED ASSUMPTION (not yet confirmed): W, F, I, Q/QL, and blank
current-term rows are all treated as "enrollment activity" for gap
detection, since each represents a registration record in Banner. If LSCO
wants Q/QL (a drop, possibly pre-census) excluded from counting as
"enrolled," that changes segment boundaries and should be confirmed before
this is trusted for a live run.

FLAGGED SCOPE NOTE (not yet decided): this script assigns one catalog
timeline per student_id, matching the grain of the file it replaces. It
does NOT yet assign catalog year per (student, major) even though
`student_major` is available in the input and the agreed policy is
phrased in terms of "first enrolled in THAT major." A student who changes
majors without any enrollment gap would, under this script, keep the
catalog anchored to their original enrollment -- not get a new catalog
tied to the major-change date. Confirm whether that's intended before
this feeds a live run; if not, this needs to re-key on
(student_id, student_major) instead of student_id alone.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_ALL_ATTEMPTS = Path("data") / "processed" / "all_student_course_attempts_normalized.csv"
DEFAULT_REQUIREMENTS = Path("data") / "processed" / "catalogs" / "requirements_master_multiyear.csv"
DEFAULT_OUTPUT = Path("data") / "processed" / "student_catalog_eligibility.csv"

PASSING_GRADES = {"A", "B", "C", "D", "S", "P", "CR", "T", "TA", "TB", "TC", "TD", "TS"}


def parse_catalog_start_year(catalog_year: str) -> int:
    return int(str(catalog_year).split("-")[0])


def catalog_start_term_sort(catalog_year: str) -> int:
    """Fall opening term for the catalog year."""
    start_year = parse_catalog_start_year(catalog_year)
    return start_year * 100 + 90


def term_sort_to_long_ordinal(term_sort: int) -> int | None:
    """Map LSCO six-digit Banner terms to long-semester order.

    Spring-family suffixes: 10, 13, 15
    Fall-family suffixes:   90, 91, 92, 95
    Summer-family suffixes: 60, 64 and do not count as long semesters --
    a summer-only gap is not a break, and summer activity alone does not
    close a gap between the surrounding long semesters.
    """
    value = int(term_sort)
    year = value // 100
    suffix = value % 100

    if suffix in {10, 13, 15}:
        return year * 2

    if suffix in {90, 91, 92, 95}:
        return year * 2 + 1

    return None


def load_activity_history(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.copy()

    for required in ("student_id", "term_sort"):
        if required not in df.columns:
            raise ValueError(f"{path} is missing required column: {required}")

    df["term_sort"] = pd.to_numeric(df["term_sort"], errors="coerce")
    df = df[df["term_sort"].notna()].copy()
    df["term_sort"] = df["term_sort"].astype(int)

    if "final_grade" in df.columns:
        df["is_passing"] = df["final_grade"].astype(str).str.upper().isin(PASSING_GRADES)
    elif "grade" in df.columns:
        df["is_passing"] = df["grade"].astype(str).str.upper().isin(PASSING_GRADES)
    else:
        df["is_passing"] = False

    return df


def load_catalog_years(requirements_path: Path) -> list[str]:
    requirements = pd.read_csv(requirements_path, dtype=str)

    if "catalog_year" not in requirements.columns:
        raise ValueError(f"{requirements_path} is missing required column: catalog_year")

    return sorted(requirements["catalog_year"].dropna().astype(str).unique())


def build_segments(activity_terms: list[int]) -> list[list[int]]:
    """Split a sorted, deduplicated list of term_sort values into
    continuous-enrollment segments, breaking wherever two or more
    consecutive long semesters have zero activity in between."""
    if not activity_terms:
        return []

    ordinal_pairs = sorted(
        (term_sort_to_long_ordinal(term), term)
        for term in activity_terms
        if term_sort_to_long_ordinal(term) is not None
    )

    if not ordinal_pairs:
        return []

    segments: list[list[int]] = [[ordinal_pairs[0][1]]]

    for (prev_ordinal, _prev_term), (curr_ordinal, curr_term) in zip(ordinal_pairs, ordinal_pairs[1:]):
        missed_long_semesters = curr_ordinal - prev_ordinal - 1

        if missed_long_semesters >= 2:
            segments.append([curr_term])
        else:
            segments[-1].append(curr_term)

    return segments


def assign_catalog_for_anchor(anchor_term: int, catalog_start_terms: list[tuple[str, int]]) -> str | None:
    """The catalog in effect is the latest catalog whose start term is
    at or before the anchor term. catalog_start_terms is a list of
    (catalog_year, start_term_sort), sorted ascending by start_term_sort."""
    eligible = [year for year, start in catalog_start_terms if start <= anchor_term]

    if not eligible:
        return None

    return eligible[-1]


def build_student_catalog_eligibility(
    activity_history: pd.DataFrame,
    catalog_years: list[str],
) -> pd.DataFrame:
    catalog_start_terms = sorted(
        ((year, catalog_start_term_sort(year)) for year in catalog_years),
        key=lambda pair: pair[1],
    )

    rows = []
    students = sorted(activity_history["student_id"].dropna().astype(str).unique())

    for student_id in students:
        student_activity = activity_history[activity_history["student_id"].astype(str).eq(student_id)]
        activity_terms = sorted(student_activity["term_sort"].dropna().astype(int).unique())

        segments = build_segments(activity_terms)

        assigned_catalogs: dict[str, dict] = {}

        for segment_index, segment_terms in enumerate(segments):
            anchor_term = min(segment_terms)
            segment_end = max(segment_terms)
            assigned = assign_catalog_for_anchor(anchor_term, catalog_start_terms)

            if assigned is None:
                continue

            record = assigned_catalogs.setdefault(
                assigned,
                {
                    "segment_indexes": [],
                    "anchor_terms": [],
                    "segment_ends": [],
                },
            )
            record["segment_indexes"].append(segment_index)
            record["anchor_terms"].append(anchor_term)
            record["segment_ends"].append(segment_end)

        for catalog_year in catalog_years:
            if catalog_year in assigned_catalogs:
                record = assigned_catalogs[catalog_year]
                rows.append(
                    {
                        "student_id": student_id,
                        "catalog_year": catalog_year,
                        "catalog_start_term_sort": catalog_start_term_sort(catalog_year),
                        "catalog_eligible": True,
                        "eligibility_reason": "ELIGIBLE",
                        "assigned_segment_count": len(record["segment_indexes"]),
                        "first_activity_term_sort": min(record["anchor_terms"]),
                        "last_activity_term_sort_in_segment": max(record["segment_ends"]),
                        "total_segments_for_student": len(segments),
                    }
                )
            else:
                rows.append(
                    {
                        "student_id": student_id,
                        "catalog_year": catalog_year,
                        "catalog_start_term_sort": catalog_start_term_sort(catalog_year),
                        "catalog_eligible": False,
                        "eligibility_reason": "NOT_ASSIGNED_TO_THIS_CATALOG_YEAR",
                        "assigned_segment_count": 0,
                        "first_activity_term_sort": None,
                        "last_activity_term_sort_in_segment": None,
                        "total_segments_for_student": len(segments),
                    }
                )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-attempts", default=str(DEFAULT_ALL_ATTEMPTS))
    parser.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    activity_history = load_activity_history(Path(args.all_attempts))
    catalog_years = load_catalog_years(Path(args.requirements))

    eligibility = build_student_catalog_eligibility(
        activity_history=activity_history,
        catalog_years=catalog_years,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    eligibility.to_csv(output_path, index=False)

    print(f"Wrote {output_path}: {len(eligibility)} rows")
    print()
    print(eligibility.groupby(["catalog_year", "catalog_eligible"]).size().to_string())
    print()
    students_with_reset = eligibility.groupby("student_id")["total_segments_for_student"].first().gt(1).sum()
    print(f"Students with more than one enrollment segment (real gap + reset): {students_with_reset}")


if __name__ == "__main__":
    main()
