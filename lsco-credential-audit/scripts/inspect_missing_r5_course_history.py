from pathlib import Path
import pandas as pd

EVIDENCE_PATH = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\cybersecurity_specialist_2022_student_reconciliation.csv"
)

SEARCH_ROOTS = [
    Path(r"data\processed"),
    Path(r"data\interim"),
]

TARGET_COURSE = "ITNW 1313"

affected = pd.read_csv(
    EVIDENCE_PATH,
    dtype=str,
    keep_default_na=False,
)

affected_ids = set(affected["student_id"])

print("=" * 100)
print("LOCATING COURSE-HISTORY INPUT")
print("=" * 100)

candidates = []

for root in SEARCH_ROOTS:
    if not root.exists():
        continue

    for path in root.rglob("*.csv"):
        name = path.name.lower()

        if any(
            token in name
            for token in [
                "course",
                "history",
                "student",
                "passed",
                "banner",
                "normalized",
            ]
        ):
            candidates.append(path)

for index, path in enumerate(candidates, start=1):
    print(f"{index:3d}. {path}")

print()
print("Testing candidate files for student/course columns...")

matches = []

student_candidates = [
    "student_id",
    "student",
    "banner_id",
    "pidm",
]

course_candidates = [
    "course_code",
    "normalized_course_code",
    "course",
    "subject_course",
]

grade_candidates = [
    "grade",
    "final_grade",
    "grade_code",
]

term_candidates = [
    "term",
    "term_code",
    "term_taken",
    "term_sort",
]

for path in candidates:
    try:
        header = pd.read_csv(path, nrows=0)
    except Exception:
        continue

    normalized = {
        str(column).strip().lower(): column
        for column in header.columns
    }

    student_col = next(
        (
            normalized[name]
            for name in student_candidates
            if name in normalized
        ),
        None,
    )

    course_col = next(
        (
            normalized[name]
            for name in course_candidates
            if name in normalized
        ),
        None,
    )

    if student_col and course_col:
        grade_col = next(
            (
                normalized[name]
                for name in grade_candidates
                if name in normalized
            ),
            None,
        )

        term_col = next(
            (
                normalized[name]
                for name in term_candidates
                if name in normalized
            ),
            None,
        )

        matches.append(
            {
                "path": path,
                "student_col": student_col,
                "course_col": course_col,
                "grade_col": grade_col,
                "term_col": term_col,
            }
        )

print()
print("Usable course-history candidates:")

for index, match in enumerate(matches, start=1):
    print(
        f"{index:3d}. {match['path']}\n"
        f"     student={match['student_col']} "
        f"course={match['course_col']} "
        f"grade={match['grade_col']} "
        f"term={match['term_col']}"
    )

if not matches:
    raise RuntimeError(
        "No course-history file was identified automatically."
    )

# Prefer the largest usable file because it is most likely the complete
# normalized student-history input.
selected = max(
    matches,
    key=lambda item: item["path"].stat().st_size,
)

path = selected["path"]
student_col = selected["student_col"]
course_col = selected["course_col"]
grade_col = selected["grade_col"]
term_col = selected["term_col"]

print()
print("=" * 100)
print("SELECTED COURSE-HISTORY FILE")
print("=" * 100)
print(path)

usecols = [
    column
    for column in [
        student_col,
        course_col,
        grade_col,
        term_col,
    ]
    if column is not None
]

target_rows = []

for chunk in pd.read_csv(
    path,
    dtype=str,
    keep_default_na=False,
    usecols=usecols,
    chunksize=250_000,
):
    course_values = (
        chunk[course_col]
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    target = chunk[
        chunk[student_col].isin(affected_ids)
        & course_values.eq(TARGET_COURSE)
    ].copy()

    if not target.empty:
        target_rows.append(target)

if target_rows:
    history = pd.concat(target_rows, ignore_index=True)
else:
    history = pd.DataFrame(columns=usecols)

print()
print("=" * 100)
print("AFFECTED STUDENT ITNW 1313 HISTORY")
print("=" * 100)

students_with_any_attempt = set(history[student_col])

print("Affected students:", len(affected_ids))
print(
    "Affected students with any ITNW 1313 attempt:",
    len(students_with_any_attempt),
)
print(
    "Affected students with no ITNW 1313 attempt:",
    len(affected_ids - students_with_any_attempt),
)
print("ITNW 1313 attempt rows:", len(history))

if grade_col is not None and len(history):
    print()
    print("Grade distribution:")
    print(
        history[grade_col]
        .replace("", "<BLANK>")
        .value_counts(dropna=False)
        .to_string()
    )

if term_col is not None and len(history):
    print()
    print("Attempt counts by term:")
    print(
        history[term_col]
        .replace("", "<BLANK>")
        .value_counts()
        .sort_index()
        .to_string()
    )

attempt_counts = (
    history.groupby(student_col)
    .size()
    .rename("itnw_1313_attempt_rows")
    .reset_index()
)

reconciliation = affected.merge(
    attempt_counts,
    left_on="student_id",
    right_on=student_col,
    how="left",
)

reconciliation["itnw_1313_attempt_rows"] = (
    reconciliation["itnw_1313_attempt_rows"]
    .fillna(0)
    .astype(int)
)

output_path = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\cybersecurity_2022_missing_r5_course_history.csv"
)

reconciliation.to_csv(
    output_path,
    index=False,
)

if len(history):
    history_path = Path(
        r"data\processed\full_actual_audit\evidence"
        r"\cybersecurity_2022_missing_r5_attempts.csv"
    )

    history.to_csv(
        history_path,
        index=False,
    )

    print()
    print("Wrote attempt details:", history_path)

print("Wrote reconciliation:", output_path)

print()
print("=" * 100)

if len(students_with_any_attempt) == 1200:
    print(
        "HYPOTHESIS CONFIRMED: every omitted R5 row belongs to a "
        "student with an ITNW 1313 attempt."
    )
elif len(students_with_any_attempt) > 0:
    print(
        "HYPOTHESIS PARTIALLY CONFIRMED: omitted rows are associated "
        "with ITNW 1313 attempts for some affected students."
    )
else:
    print(
        "HYPOTHESIS NOT CONFIRMED: affected students have no ITNW 1313 "
        "attempts in the selected history file."
    )
