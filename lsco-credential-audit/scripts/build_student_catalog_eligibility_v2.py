"""Build student catalog-year eligibility SETS, segmented by real enrollment gaps.

Policy this implements (agreed 2026-07-16, revised same day):
    1. Each continuous-enrollment segment is eligible under its ANCHOR
       catalog (the catalog in effect at the segment's first in-window
       term of activity, any grade including W/F/I/Q/blank -- a Q is an
       enrollment, per user decision 2026-07-16) AND every later catalog
       that took effect during the segment. Standard catalog-choice: a
       continuously enrolled student may complete under any catalog
       published while enrolled.
    2. Coursework does not expire. There is no cutoff based on how long ago
       a catalog started, and completion checking (downstream) uses the
       student's FULL course history regardless of when courses were taken.
       "Course records are eternal; the only temporal object is the catalog
       and its children."
    3. A reset is triggered by a gap of two consecutive missed long
       semesters (Fall/Spring; Summer does not count) with ZERO course
       activity at LSCO. After a reset, the next segment gets its own
       catalog set anchored at its own first term.
    4. Review window: only activity at or after the earliest registered
       catalog's start term participates in segmentation/anchoring.
       Pre-window activity is invisible to catalog assignment but still
       counts toward completion downstream.

Grain note: catalog sets are keyed per student_id, not per
(student_id, major). Under the maximum-awards sweep this is correct by
construction: the audit engine tests every student against every
credential in every eligible catalog, so major-change timing cannot hide
an award.

Award selection (one countable award per credential lineage, LATEST
completing catalog wins, per user decision 2026-07-16) is NOT this
script's job -- this script answers "which catalogs may this student be
audited under"; the report layer picks the single countable award per
(student, lineage).
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


def assign_catalog_set_for_segment(
    segment_start_term: int,
    segment_end_term: int,
    catalog_start_terms: list[tuple[str, int]],
) -> list[str]:
    """All catalogs a continuously-enrolled segment is eligible under:

    1. The anchor catalog -- the catalog in effect at the segment's first
       term of activity.
    2. Every later catalog whose effective (start) term falls at or before
       the segment's last term of activity. Standard catalog-choice: a
       continuously enrolled student may elect any catalog published
       during their enrollment.

    Returns catalog years in ascending order. Empty if the segment
    predates every registered catalog (should not occur once activity is
    window-filtered, but kept defensive)."""
    anchor = assign_catalog_for_anchor(segment_start_term, catalog_start_terms)

    if anchor is None:
        return []

    catalogs = [anchor]

    anchor_start = dict(catalog_start_terms)[anchor]

    for year, start in catalog_start_terms:
        if anchor_start < start <= segment_end_term:
            catalogs.append(year)

    return catalogs


def build_student_catalog_eligibility(
    activity_history: pd.DataFrame,
    catalog_years: list[str],
) -> pd.DataFrame:
    catalog_start_terms = sorted(
        ((year, catalog_start_term_sort(year)) for year in catalog_years),
        key=lambda pair: pair[1],
    )

    activity_history = activity_history.copy()
    activity_history["student_id"] = activity_history["student_id"].astype(str)

    # Review-window floor: the earliest term any registered catalog governs.
    # Pre-window activity is real (course records are eternal), but it is not
    # relevant to WHICH catalog governs a student -- only the catalog and its
    # children are temporal. Filtering here, uniformly, for every student,
    # means a student whose true history starts before the window simply
    # anchors to their first in-window term instead of being dropped, and a
    # student who already started inside the window is completely unaffected.
    window_start_term_sort = min(start for _, start in catalog_start_terms)

    rows = []

    # groupby does one pass to bucket rows by student, instead of
    # re-scanning + re-casting the full table once per student (which is
    # what made the original loop O(students x rows) instead of O(rows)).
    grouped = activity_history.groupby("student_id")[["term_sort", "is_passing"]]

    for student_id, student_df in grouped:
        all_terms = sorted(student_df["term_sort"].dropna().astype(int).unique())
        activity_terms = [term for term in all_terms if term >= window_start_term_sort]

        # A term_sort counts as "earned" if any row for that term was a
        # passing grade -- multiple attempts/courses can share a term_sort.
        earned_lookup = (
            student_df[student_df["term_sort"] >= window_start_term_sort]
            .groupby("term_sort")["is_passing"]
            .any()
        )

        segments = build_segments(activity_terms)

        assigned_catalogs: dict[str, dict] = {}

        for segment_index, segment_terms in enumerate(segments):
            anchor_term = min(segment_terms)
            segment_end = max(segment_terms)
            assigned_set = assign_catalog_set_for_segment(
                anchor_term, segment_end, catalog_start_terms
            )

            for assigned in assigned_set:
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

                segment_terms_all = [
                    term
                    for idx in record["segment_indexes"]
                    for term in segments[idx]
                ]
                earned_terms_in_segments = [
                    term for term in segment_terms_all if earned_lookup.get(term, False)
                ]

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
                        # Preserved for build_credential_completion_report.py,
                        # which expects these three names specifically.
                        "first_earned_term_sort": min(earned_terms_in_segments) if earned_terms_in_segments else "",
                        "latest_earned_term_sort": max(earned_terms_in_segments) if earned_terms_in_segments else "",
                        "latest_activity_term_sort": max(record["segment_ends"]),
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
                        "first_earned_term_sort": "",
                        "latest_earned_term_sort": "",
                        "latest_activity_term_sort": "",
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
