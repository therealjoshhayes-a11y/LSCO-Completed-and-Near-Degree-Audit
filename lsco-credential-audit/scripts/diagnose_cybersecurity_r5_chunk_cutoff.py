from pathlib import Path
import re
import pandas as pd

# -------------------------------------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------------------------------------

CHUNK_DIR = Path(
    r"data\processed\full_actual_audit\chunks"
)

DETAIL_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_audit_results.csv"
)

SUMMARY_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_credential_summary.csv"
)

OUTPUT_DIR = Path(
    r"data\processed\full_actual_audit\evidence"
)

CHUNK_OUTPUT_PATH = (
    OUTPUT_DIR
    / "cybersecurity_2022_r5_chunk_distribution.csv"
)

STUDENT_OUTPUT_PATH = (
    OUTPUT_DIR
    / "cybersecurity_2022_r5_student_chunk_reconciliation.csv"
)

CATALOG_YEAR = "2022-2023"
CREDENTIAL_ID = "CYBERSECURITY_SPECIALIST_2022"
REQUIREMENT_ID = "CYBERSECURITY_SPECIALIST_2022_R5"

DETAIL_READ_CHUNK_SIZE = 500_000


# -------------------------------------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------------------------------------

def extract_chunk_number(path):
    match = re.search(
        r"chunk_(\d+)",
        path.name,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    return int(match.group(1))


def fail_if_duplicate_key(df, key, label):
    duplicate_mask = df.duplicated(
        subset=[key],
        keep=False,
    )

    duplicate_count = int(
        duplicate_mask.sum()
    )

    if duplicate_count:
        print()
        print(f"Duplicate {label} rows:")
        print(
            df.loc[duplicate_mask]
            .sort_values(key)
            .head(100)
            .to_string(index=False)
        )

        raise RuntimeError(
            f"{label} contains {duplicate_count:,} rows "
            f"with duplicated {key} values."
        )


# -------------------------------------------------------------------------------------------------
# VALIDATE PATHS
# -------------------------------------------------------------------------------------------------

print("=" * 100)
print("CYBERSECURITY SPECIALIST 2022 — R5 CHUNK-CUTOFF DIAGNOSTIC")
print("=" * 100)

for required_path, label in [
    (CHUNK_DIR, "chunk directory"),
    (DETAIL_PATH, "combined detail file"),
    (SUMMARY_PATH, "combined summary file"),
]:
    if not required_path.exists():
        raise FileNotFoundError(
            f"Required {label} not found:\n{required_path}"
        )

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# -------------------------------------------------------------------------------------------------
# BUILD STUDENT-TO-CHUNK MAP
# -------------------------------------------------------------------------------------------------

history_files = sorted(
    CHUNK_DIR.glob(
        "chunk_*_student_course_history.csv"
    )
)

if not history_files:
    raise RuntimeError(
        f"No chunk history files found in:\n{CHUNK_DIR}"
    )

student_chunk_parts = []

for file_number, path in enumerate(
    history_files,
    start=1,
):
    chunk_number = extract_chunk_number(path)

    if chunk_number is None:
        print(
            "Skipping file without a readable chunk number:",
            path,
        )
        continue

    header = pd.read_csv(
        path,
        nrows=0,
    )

    if "student_id" not in header.columns:
        raise RuntimeError(
            f"student_id is missing from:\n{path}"
        )

    students = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        usecols=["student_id"],
    )

    students["student_id"] = (
        students["student_id"]
        .str.strip()
    )

    students = (
        students.loc[
            students["student_id"].ne(""),
            ["student_id"],
        ]
        .drop_duplicates()
    )

    students["chunk_number"] = chunk_number
    students["chunk_history_file"] = str(path)
    students["chunk_history_modified"] = (
        path.stat().st_mtime
    )

    student_chunk_parts.append(students)

    if file_number % 100 == 0:
        print(
            f"Mapped chunk files: {file_number:,}"
        )

student_chunk = pd.concat(
    student_chunk_parts,
    ignore_index=True,
)

duplicate_student_chunk = (
    student_chunk.groupby("student_id")
    .size()
    .reset_index(name="chunk_count")
)

duplicate_student_chunk = duplicate_student_chunk[
    duplicate_student_chunk["chunk_count"] > 1
]

print()
print("Chunk history files:", f"{len(history_files):,}")
print(
    "Mapped students:",
    f"{student_chunk['student_id'].nunique():,}",
)
print(
    "Students mapped to multiple chunks:",
    f"{len(duplicate_student_chunk):,}",
)

if len(duplicate_student_chunk):
    print(
        duplicate_student_chunk
        .head(100)
        .to_string(index=False)
    )

    raise RuntimeError(
        "At least one student is mapped to multiple chunks."
    )

fail_if_duplicate_key(
    student_chunk,
    "student_id",
    "student-to-chunk map",
)


# -------------------------------------------------------------------------------------------------
# LOAD TARGET SUMMARY AUDITS
# -------------------------------------------------------------------------------------------------

summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    keep_default_na=False,
    usecols=[
        "student_id",
        "catalog_year",
        "credential_id",
        "requirements_total",
        "requirements_met",
        "requirements_missing",
        "requirements_unresolved",
        "audit_status",
    ],
)

for column in [
    "student_id",
    "catalog_year",
    "credential_id",
]:
    summary[column] = summary[column].str.strip()

target_summary = summary[
    summary["catalog_year"].eq(CATALOG_YEAR)
    & summary["credential_id"].eq(CREDENTIAL_ID)
].copy()

print()
print(
    "Target summary audits:",
    f"{len(target_summary):,}",
)

fail_if_duplicate_key(
    target_summary,
    "student_id",
    "target summary",
)


# -------------------------------------------------------------------------------------------------
# READ TARGET DETAIL ROWS
# -------------------------------------------------------------------------------------------------

r5_parts = []
target_detail_counts = {}

rows_scanned = 0

for read_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        keep_default_na=False,
        usecols=[
            "student_id",
            "catalog_year",
            "credential_id",
            "requirement_id",
            "status",
            "matched_options",
            "matched_grades",
        ],
        chunksize=DETAIL_READ_CHUNK_SIZE,
    ),
    start=1,
):
    rows_scanned += len(chunk)

    for column in [
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
    ]:
        chunk[column] = chunk[column].str.strip()

    target_detail = chunk[
        chunk["catalog_year"].eq(CATALOG_YEAR)
        & chunk["credential_id"].eq(CREDENTIAL_ID)
    ].copy()

    if not target_detail.empty:
        student_counts = (
            target_detail.groupby("student_id")
            .size()
        )

        for student_id, count in student_counts.items():
            target_detail_counts[student_id] = (
                target_detail_counts.get(
                    student_id,
                    0,
                )
                + int(count)
            )

        r5 = target_detail[
            target_detail["requirement_id"].eq(
                REQUIREMENT_ID
            )
        ].copy()

        if not r5.empty:
            r5_parts.append(r5)

    if read_number % 20 == 0:
        print(
            f"Read combined-detail chunks: {read_number:,} "
            f"| rows scanned: {rows_scanned:,}"
        )

if r5_parts:
    r5_rows = pd.concat(
        r5_parts,
        ignore_index=True,
    )
else:
    r5_rows = pd.DataFrame(
        columns=[
            "student_id",
            "catalog_year",
            "credential_id",
            "requirement_id",
            "status",
            "matched_options",
            "matched_grades",
        ]
    )

r5_student_counts = (
    r5_rows.groupby("student_id")
    .size()
    .reset_index(name="r5_row_count")
)

duplicate_r5_students = r5_student_counts[
    r5_student_counts["r5_row_count"] > 1
]

if len(duplicate_r5_students):
    print()
    print("Students with multiple R5 rows:")
    print(
        duplicate_r5_students
        .head(100)
        .to_string(index=False)
    )

    raise RuntimeError(
        "Some students have multiple R5 detail rows."
    )

r5_students = set(
    r5_rows["student_id"]
)

print()
print(
    "Students with an R5 detail row:",
    f"{len(r5_students):,}",
)
print(
    "Students without an R5 detail row:",
    f"{len(target_summary) - len(r5_students):,}",
)


# -------------------------------------------------------------------------------------------------
# MERGE TARGET AUDITS WITH CHUNK MAP
# -------------------------------------------------------------------------------------------------

target = target_summary.merge(
    student_chunk[
        [
            "student_id",
            "chunk_number",
            "chunk_history_file",
            "chunk_history_modified",
        ]
    ],
    on="student_id",
    how="left",
)

if len(target) != len(target_summary):
    raise RuntimeError(
        "The chunk-map merge changed the number of target summary rows."
    )

target["has_r5_row"] = (
    target["student_id"]
    .isin(r5_students)
)

target["actual_detail_rows"] = (
    target["student_id"]
    .map(target_detail_counts)
    .fillna(0)
    .astype(int)
)

target["chunk_number"] = pd.to_numeric(
    target["chunk_number"],
    errors="coerce",
).astype("Int64")

target["requirements_total_num"] = pd.to_numeric(
    target["requirements_total"],
    errors="coerce",
)

missing_chunk_map = int(
    target["chunk_number"].isna().sum()
)

print()
print(
    "Target students without a chunk mapping:",
    f"{missing_chunk_map:,}",
)

if missing_chunk_map:
    print()
    print("Students without chunk mappings:")
    print(
        target.loc[
            target["chunk_number"].isna(),
            [
                "student_id",
                "requirements_total",
                "audit_status",
            ],
        ]
        .head(100)
        .to_string(index=False)
    )


# -------------------------------------------------------------------------------------------------
# BUILD CHUNK SUMMARY
# -------------------------------------------------------------------------------------------------

chunk_summary = (
    target.groupby(
        "chunk_number",
        dropna=False,
    )
    .agg(
        audited_students=(
            "student_id",
            "nunique",
        ),
        students_with_r5=(
            "has_r5_row",
            "sum",
        ),
        minimum_detail_rows=(
            "actual_detail_rows",
            "min",
        ),
        maximum_detail_rows=(
            "actual_detail_rows",
            "max",
        ),
        summary_total_min=(
            "requirements_total_num",
            "min",
        ),
        summary_total_max=(
            "requirements_total_num",
            "max",
        ),
        first_history_file=(
            "chunk_history_file",
            "first",
        ),
        history_modified=(
            "chunk_history_modified",
            "first",
        ),
    )
    .reset_index()
)

chunk_summary["students_with_r5"] = (
    chunk_summary["students_with_r5"]
    .astype(int)
)

chunk_summary["students_without_r5"] = (
    chunk_summary["audited_students"]
    - chunk_summary["students_with_r5"]
)

chunk_summary["all_students_have_r5"] = (
    chunk_summary["students_without_r5"].eq(0)
)

chunk_summary["no_students_have_r5"] = (
    chunk_summary["students_with_r5"].eq(0)
)

chunk_summary = chunk_summary.sort_values(
    "chunk_number",
    na_position="last",
)

print()
print("=" * 100)
print("CHUNK DISTRIBUTION")
print("=" * 100)

print(
    chunk_summary[
        [
            "chunk_number",
            "audited_students",
            "students_with_r5",
            "students_without_r5",
            "minimum_detail_rows",
            "maximum_detail_rows",
            "summary_total_min",
            "summary_total_max",
        ]
    ].to_string(index=False)
)


# -------------------------------------------------------------------------------------------------
# CUTOFF ANALYSIS
# -------------------------------------------------------------------------------------------------

chunks_with_r5 = (
    chunk_summary.loc[
        chunk_summary["students_with_r5"] > 0,
        "chunk_number",
    ]
    .dropna()
    .astype(int)
)

chunks_missing_r5 = (
    chunk_summary.loc[
        chunk_summary["students_without_r5"] > 0,
        "chunk_number",
    ]
    .dropna()
    .astype(int)
)

mixed_chunks = chunk_summary[
    (chunk_summary["students_with_r5"] > 0)
    & (chunk_summary["students_without_r5"] > 0)
].copy()

fully_good_chunks = chunk_summary[
    chunk_summary["all_students_have_r5"]
].copy()

fully_bad_chunks = chunk_summary[
    chunk_summary["no_students_have_r5"]
].copy()

print()
print("=" * 100)
print("CUTOFF ANALYSIS")
print("=" * 100)

if len(chunks_with_r5):
    first_chunk_with_r5 = int(
        chunks_with_r5.min()
    )
    last_chunk_with_r5 = int(
        chunks_with_r5.max()
    )

    print(
        "First chunk containing R5:",
        first_chunk_with_r5,
    )
    print(
        "Last chunk containing R5:",
        last_chunk_with_r5,
    )
else:
    first_chunk_with_r5 = None
    last_chunk_with_r5 = None

    print("No chunks contain R5.")

if len(chunks_missing_r5):
    first_chunk_missing_r5 = int(
        chunks_missing_r5.min()
    )
    last_chunk_missing_r5 = int(
        chunks_missing_r5.max()
    )

    print(
        "First chunk missing R5:",
        first_chunk_missing_r5,
    )
    print(
        "Last chunk missing R5:",
        last_chunk_missing_r5,
    )
else:
    first_chunk_missing_r5 = None
    last_chunk_missing_r5 = None

    print("No chunks are missing R5.")

print(
    "Fully good chunks:",
    f"{len(fully_good_chunks):,}",
)
print(
    "Fully bad chunks:",
    f"{len(fully_bad_chunks):,}",
)
print(
    "Mixed chunks:",
    f"{len(mixed_chunks):,}",
)

if len(mixed_chunks):
    print()
    print("Mixed chunk details:")
    print(
        mixed_chunks[
            [
                "chunk_number",
                "audited_students",
                "students_with_r5",
                "students_without_r5",
                "minimum_detail_rows",
                "maximum_detail_rows",
                "summary_total_min",
                "summary_total_max",
            ]
        ].to_string(index=False)
    )


# -------------------------------------------------------------------------------------------------
# WRITE EVIDENCE
# -------------------------------------------------------------------------------------------------

chunk_summary.to_csv(
    CHUNK_OUTPUT_PATH,
    index=False,
)

target.sort_values(
    [
        "chunk_number",
        "student_id",
    ],
    na_position="last",
).to_csv(
    STUDENT_OUTPUT_PATH,
    index=False,
)

print()
print("Wrote:")
print(CHUNK_OUTPUT_PATH)
print(STUDENT_OUTPUT_PATH)


# -------------------------------------------------------------------------------------------------
# INTERPRET RESULT
# -------------------------------------------------------------------------------------------------

print()
print("=" * 100)
print("DIAGNOSTIC RESULT")
print("=" * 100)

clean_forward_cutoff = False
clean_reverse_cutoff = False

if (
    len(mixed_chunks) == 0
    and len(fully_good_chunks) > 0
    and len(fully_bad_chunks) > 0
):
    good_numbers = set(
        fully_good_chunks["chunk_number"]
        .dropna()
        .astype(int)
    )

    bad_numbers = set(
        fully_bad_chunks["chunk_number"]
        .dropna()
        .astype(int)
    )

    last_good = max(good_numbers)
    first_good = min(good_numbers)
    last_bad = max(bad_numbers)
    first_bad = min(bad_numbers)

    clean_forward_cutoff = (
        max(good_numbers) < min(bad_numbers)
        and last_good + 1 == first_bad
    )

    clean_reverse_cutoff = (
        max(bad_numbers) < min(good_numbers)
        and last_bad + 1 == first_good
    )

if clean_forward_cutoff:
    print("CLEAN FORWARD CHUNK CUTOFF CONFIRMED.")
    print(
        "Last fully good chunk:",
        max(
            fully_good_chunks["chunk_number"]
            .dropna()
            .astype(int)
        ),
    )
    print(
        "First fully bad chunk:",
        min(
            fully_bad_chunks["chunk_number"]
            .dropna()
            .astype(int)
        ),
    )
    print()
    print(
        "R5 was present in earlier chunks and absent from all "
        "students in later chunks."
    )
    print(
        "The defect is tied to chunk execution state rather than "
        "student course history."
    )

elif clean_reverse_cutoff:
    print("CLEAN REVERSE CHUNK CUTOFF CONFIRMED.")
    print(
        "Last fully bad chunk:",
        max(
            fully_bad_chunks["chunk_number"]
            .dropna()
            .astype(int)
        ),
    )
    print(
        "First fully good chunk:",
        min(
            fully_good_chunks["chunk_number"]
            .dropna()
            .astype(int)
        ),
    )
    print()
    print(
        "R5 was absent from earlier chunks and present in all "
        "students in later chunks."
    )
    print(
        "The defect is tied to chunk execution state rather than "
        "student course history."
    )

else:
    print(
        "A single clean sequential cutoff was not confirmed."
    )
    print(
        "Review the chunk-distribution CSV to identify whether "
        "missing R5 rows cluster by chunk, occur in mixed chunks, "
        "or follow another execution pattern."
    )
