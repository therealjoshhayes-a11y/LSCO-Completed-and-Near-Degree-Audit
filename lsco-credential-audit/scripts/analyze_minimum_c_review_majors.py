from __future__ import annotations

from pathlib import Path
import pandas as pd


ROOT = Path.cwd()

AWARDABILITY = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "evidence"
    / "awardability"
    / "selected_awards_awardability_screen.csv"
)

ATTEMPTS = (
    ROOT
    / "data"
    / "processed"
    / "all_student_course_attempts_normalized.csv"
)

OUT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "evidence"
    / "awardability"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

DETAIL_OUT = OUT_DIR / "minimum_c_review_last_two_majors.csv"
PAIR_DIST_OUT = OUT_DIR / "minimum_c_review_major_pair_distribution.csv"
MAJOR_DIST_OUT = OUT_DIR / "minimum_c_review_individual_major_distribution.csv"
CREDENTIAL_DIST_OUT = OUT_DIR / "minimum_c_review_credential_distribution.csv"


def clean_major(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.upper() in {"NAN", "NONE", "NULL"}:
        return ""
    return text


for path in [AWARDABILITY, ATTEMPTS]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

awards = pd.read_csv(AWARDABILITY, dtype=str, low_memory=False)
attempts = pd.read_csv(
    ATTEMPTS,
    dtype=str,
    usecols=[
        "student_id",
        "student_major",
        "course_code",
        "final_grade",
        "term_taken",
        "term_sort",
    ],
    low_memory=False,
)

awards["student_id"] = awards["student_id"].astype(str)
attempts["student_id"] = attempts["student_id"].astype(str)

review = awards[
    awards["minimum_c_status"].astype(str).str.upper() == "REVIEW"
].copy()

review_students = set(review["student_id"])
student_attempts = attempts[attempts["student_id"].isin(review_students)].copy()

student_attempts["student_major_clean"] = student_attempts["student_major"].map(
    clean_major
)
student_attempts["term_sort_numeric"] = pd.to_numeric(
    student_attempts["term_sort"],
    errors="coerce",
)

# One major observation per student and term. If a student has conflicting majors
# within the same term, preserve all distinct values joined together for review.
term_majors = (
    student_attempts[
        student_attempts["student_major_clean"].ne("")
    ]
    .groupby(
        ["student_id", "term_sort_numeric", "term_taken"],
        dropna=False,
    )["student_major_clean"]
    .agg(lambda values: " | ".join(sorted(set(values))))
    .reset_index(name="major_at_term")
)

term_majors = term_majors.sort_values(
    ["student_id", "term_sort_numeric", "term_taken"],
    ascending=[True, False, False],
)

last_two_rows = []

for student_id in sorted(review_students):
    history = term_majors[term_majors["student_id"] == student_id].head(2)

    last_major = ""
    last_major_term = ""
    prior_major = ""
    prior_major_term = ""

    if len(history) >= 1:
        last_major = history.iloc[0]["major_at_term"]
        last_major_term = history.iloc[0]["term_taken"]

    if len(history) >= 2:
        prior_major = history.iloc[1]["major_at_term"]
        prior_major_term = history.iloc[1]["term_taken"]

    last_two_rows.append(
        {
            "student_id": student_id,
            "last_major": last_major,
            "last_major_term": last_major_term,
            "prior_major": prior_major,
            "prior_major_term": prior_major_term,
            "major_pair": (
                f"{last_major} <- {prior_major}"
                if prior_major
                else last_major
            ),
        }
    )

last_two = pd.DataFrame(last_two_rows)

detail = review.merge(
    last_two,
    on="student_id",
    how="left",
    validate="many_to_one",
)

detail.to_csv(DETAIL_OUT, index=False)

pair_dist = (
    detail["major_pair"]
    .fillna("")
    .replace("", "NO_MAJOR_FOUND")
    .value_counts(dropna=False)
    .rename_axis("major_pair")
    .reset_index(name="award_count")
)
pair_dist["percent_of_262"] = (
    pair_dist["award_count"] / len(detail) * 100
).round(2)
pair_dist.to_csv(PAIR_DIST_OUT, index=False)

individual = pd.concat(
    [
        detail[["student_id", "credential_id", "last_major"]]
        .rename(columns={"last_major": "major"})
        .assign(position="LAST"),
        detail[["student_id", "credential_id", "prior_major"]]
        .rename(columns={"prior_major": "major"})
        .assign(position="PRIOR"),
    ],
    ignore_index=True,
)

individual["major"] = individual["major"].fillna("").replace("", "NO_MAJOR_FOUND")

major_dist = (
    individual.groupby(["position", "major"], dropna=False)
    .size()
    .reset_index(name="award_count")
    .sort_values(["position", "award_count"], ascending=[True, False])
)
major_dist.to_csv(MAJOR_DIST_OUT, index=False)

credential_dist = (
    detail.groupby(
        [
            "catalog_year",
            "credential_id",
            "credential_title",
            "program_hours",
            "credential_type",
        ],
        dropna=False,
    )
    .size()
    .reset_index(name="review_award_count")
    .sort_values("review_award_count", ascending=False)
)
credential_dist.to_csv(CREDENTIAL_DIST_OUT, index=False)

print("=" * 110)
print("MINIMUM-C REVIEW: LAST TWO STUDENT MAJORS")
print("=" * 110)
print(f"Review awards: {len(detail):,}")
print(f"Distinct students: {detail['student_id'].nunique():,}")

print("\nTop major pairs:")
print(pair_dist.head(30).to_string(index=False))

print("\nLast-major distribution:")
print(
    major_dist[major_dist["position"] == "LAST"]
    .head(30)
    .to_string(index=False)
)

print("\nTop credentials among the 262 reviews:")
print(credential_dist.head(30).to_string(index=False))

print("\nOutputs:")
print(DETAIL_OUT)
print(PAIR_DIST_OUT)
print(MAJOR_DIST_OUT)
print(CREDENTIAL_DIST_OUT)
