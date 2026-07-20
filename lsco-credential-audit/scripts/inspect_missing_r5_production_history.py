from pathlib import Path
import pandas as pd

# -------------------------------------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------------------------------------

HISTORY_PATH = Path(
    r"data\processed\student_course_history_normalized_FULL_ACTUAL.csv"
)

AFFECTED_PATH = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\cybersecurity_specialist_2022_student_reconciliation.csv"
)

OUTPUT_DIR = Path(
    r"data\processed\full_actual_audit\evidence"
)

TARGET_COURSE = "ITNW 1313"
CHUNK_SIZE = 250_000

OUTPUT_RECONCILIATION = (
    OUTPUT_DIR
    / "cybersecurity_2022_missing_r5_production_history.csv"
)

OUTPUT_ATTEMPTS = (
    OUTPUT_DIR
    / "cybersecurity_2022_missing_r5_production_attempts.csv"
)


# -------------------------------------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------------------------------------

def find_column(columns, candidates):
    normalized = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]

    return None


def normalize_course_code(series):
    return (
        series.astype(str)
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )


# -------------------------------------------------------------------------------------------------
# VALIDATE INPUTS
# -------------------------------------------------------------------------------------------------

print("=" * 100)
print("CYBERSECURITY SPECIALIST 2022 — R5 PRODUCTION-HISTORY DIAGNOSTIC")
print("=" * 100)

if not HISTORY_PATH.exists():
    raise FileNotFoundError(
        f"Production course-history file not found:\n{HISTORY_PATH}"
    )

if not AFFECTED_PATH.exists():
    raise FileNotFoundError(
        f"Affected-student reconciliation file not found:\n{AFFECTED_PATH}"
    )

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

history_header = pd.read_csv(
    HISTORY_PATH,
    nrows=0,
)

history_columns = list(history_header.columns)

student_col = find_column(
    history_columns,
    [
        "student_id",
        "banner_id",
        "student_pidm",
        "pidm",
    ],
)

course_col = find_column(
    history_columns,
    [
        "course_code",
        "normalized_course_code",
        "subject_course",
        "course",
    ],
)

grade_col = find_column(
    history_columns,
    [
        "grade",
        "final_grade",
        "grade_code",
    ],
)

term_col = find_column(
    history_columns,
    [
        "term_taken",
        "term",
        "term_code",
        "term_sort",
    ],
)

print("Production history file:")
print(HISTORY_PATH)

print()
print("Resolved columns:")
print("  student:", student_col)
print("  course: ", course_col)
print("  grade:  ", grade_col)
print("  term:   ", term_col)

if student_col is None:
    raise RuntimeError(
        "Could not identify the student ID column."
    )

if course_col is None:
    raise RuntimeError(
        "Could not identify the course-code column."
    )

if grade_col is None:
    raise RuntimeError(
        "Could not identify the grade column."
    )


# -------------------------------------------------------------------------------------------------
# LOAD THE 1,200 AFFECTED STUDENTS
# -------------------------------------------------------------------------------------------------

affected = pd.read_csv(
    AFFECTED_PATH,
    dtype=str,
    keep_default_na=False,
)

if "student_id" not in affected.columns:
    raise RuntimeError(
        "Affected-student file does not contain student_id."
    )

affected["student_id"] = affected["student_id"].str.strip()

affected_ids = set(
    affected.loc[
        affected["student_id"].ne(""),
        "student_id",
    ]
)

print()
print("Affected students loaded:", f"{len(affected_ids):,}")

if len(affected_ids) != 1_200:
    print(
        "WARNING: expected 1,200 affected students, "
        f"but loaded {len(affected_ids):,}."
    )


# -------------------------------------------------------------------------------------------------
# READ ONLY ITNW 1313 ATTEMPTS FOR THE AFFECTED STUDENTS
# -------------------------------------------------------------------------------------------------

usecols = [
    student_col,
    course_col,
    grade_col,
]

if term_col is not None:
    usecols.append(term_col)

attempt_parts = []
rows_read = 0

for chunk_number, chunk in enumerate(
    pd.read_csv(
        HISTORY_PATH,
        dtype=str,
        keep_default_na=False,
        usecols=usecols,
        chunksize=CHUNK_SIZE,
    ),
    start=1,
):
    rows_read += len(chunk)

    chunk[student_col] = chunk[student_col].str.strip()

    normalized_courses = normalize_course_code(
        chunk[course_col]
    )

    target = chunk[
        chunk[student_col].isin(affected_ids)
        & normalized_courses.eq(TARGET_COURSE)
    ].copy()

    if not target.empty:
        target["normalized_course_code"] = TARGET_COURSE
        attempt_parts.append(target)

    if chunk_number % 10 == 0:
        print(
            f"Read chunks: {chunk_number:,} "
            f"| rows: {rows_read:,}"
        )

if attempt_parts:
    attempts = pd.concat(
        attempt_parts,
        ignore_index=True,
    )
else:
    attempts = pd.DataFrame(
        columns=usecols + ["normalized_course_code"]
    )


# -------------------------------------------------------------------------------------------------
# SUMMARIZE RESULTS
# -------------------------------------------------------------------------------------------------

students_with_attempt = set(
    attempts[student_col].str.strip()
)

students_without_attempt = (
    affected_ids - students_with_attempt
)

print()
print("=" * 100)
print("PRODUCTION-HISTORY RESULTS")
print("=" * 100)

print("History rows scanned:", f"{rows_read:,}")
print("Affected students:", f"{len(affected_ids):,}")
print(
    "Affected students with ITNW 1313 attempt:",
    f"{len(students_with_attempt):,}",
)
print(
    "Affected students with no ITNW 1313 attempt:",
    f"{len(students_without_attempt):,}",
)
print("ITNW 1313 attempt rows:", f"{len(attempts):,}")

if len(attempts):
    print()
    print("Grade distribution:")
    print(
        attempts[grade_col]
        .replace("", "<BLANK>")
        .value_counts(dropna=False)
        .to_string()
    )

    print()
    print("Attempt-row count per student:")
    print(
        attempts.groupby(student_col)
        .size()
        .value_counts()
        .sort_index()
        .rename_axis("attempt_rows")
        .to_string()
    )

    if term_col is not None:
        print()
        print("Attempt distribution by term:")
        print(
            attempts[term_col]
            .replace("", "<BLANK>")
            .value_counts()
            .sort_index()
            .to_string()
        )


# -------------------------------------------------------------------------------------------------
# BUILD STUDENT-LEVEL RECONCILIATION
# -------------------------------------------------------------------------------------------------

attempt_summary = (
    attempts.groupby(student_col)
    .agg(
        itnw_1313_attempt_rows=(course_col, "size"),
        itnw_1313_grades=(
            grade_col,
            lambda values: "|".join(
                sorted(
                    {
                        str(value).strip()
                        for value in values
                        if str(value).strip()
                    }
                )
            ),
        ),
    )
    .reset_index()
    .rename(
        columns={
            student_col: "student_id",
        }
    )
)

if term_col is not None:
    term_summary = (
        attempts.groupby(student_col)[term_col]
        .agg(
            lambda values: "|".join(
                sorted(
                    {
                        str(value).strip()
                        for value in values
                        if str(value).strip()
                    }
                )
            )
        )
        .rename("itnw_1313_terms")
        .reset_index()
        .rename(
            columns={
                student_col: "student_id",
            }
        )
    )

    attempt_summary = attempt_summary.merge(
        term_summary,
        on="student_id",
        how="left",
        validate="one_to_one",
    )

result = affected.merge(
    attempt_summary,
    on="student_id",
    how="left",
    validate="one_to_one",
)

result["itnw_1313_attempt_rows"] = (
    pd.to_numeric(
        result["itnw_1313_attempt_rows"],
        errors="coerce",
    )
    .fillna(0)
    .astype(int)
)

result["has_itnw_1313_attempt"] = (
    result["itnw_1313_attempt_rows"] > 0
)

for column in [
    "itnw_1313_grades",
    "itnw_1313_terms",
]:
    if column in result.columns:
        result[column] = result[column].fillna("")


# -------------------------------------------------------------------------------------------------
# WRITE EVIDENCE
# -------------------------------------------------------------------------------------------------

result.to_csv(
    OUTPUT_RECONCILIATION,
    index=False,
)

attempts.to_csv(
    OUTPUT_ATTEMPTS,
    index=False,
)

print()
print("Wrote:")
print(OUTPUT_RECONCILIATION)
print(OUTPUT_ATTEMPTS)


# -------------------------------------------------------------------------------------------------
# INTERPRETATION
# -------------------------------------------------------------------------------------------------

print()
print("=" * 100)
print("DIAGNOSTIC RESULT")
print("=" * 100)

with_attempt_count = len(students_with_attempt)

if with_attempt_count == len(affected_ids):
    print(
        "Every omitted R5 row belongs to a student with an "
        "ITNW 1313 history row."
    )
    print(
        "Next target: inspect grade filtering and the EXACT-rule "
        "row-emission branch."
    )

elif with_attempt_count == 0:
    print(
        "None of the omitted R5 rows belongs to a student with an "
        "ITNW 1313 history row."
    )
    print(
        "The defect is not caused by failed ITNW 1313 attempts. "
        "Next target: inspect requirement allocation, filtering, "
        "and row construction."
    )

else:
    print(
        f"{with_attempt_count:,} of {len(affected_ids):,} affected "
        "students have ITNW 1313 history rows."
    )
    print(
        "The omission is not explained by a single attempt-state "
        "condition. Compare the students with and without attempts "
        "against chunk and allocation behavior."
    )
