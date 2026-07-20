from pathlib import Path
import pandas as pd

SOURCE_PATH = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\best_student_credential_family_audit.csv"
)

OUTPUT_PATH = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\lineage_deduped_complete_by_last_catalog_before_r5_repair.csv"
)


def find_column(columns, candidates):
    normalized = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]

    return None


def catalog_sort_value(value):
    text = str(value).strip()

    if not text:
        return -1

    try:
        return int(text.split("-")[0])
    except (ValueError, IndexError):
        return -1


print("=" * 100)
print("LINEAGE-DEDUPED COMPLETIONS BY LAST CATALOG ASSIGNED")
print("=" * 100)

if not SOURCE_PATH.exists():
    raise FileNotFoundError(
        f"Source file not found:\n{SOURCE_PATH}"
    )

df = pd.read_csv(
    SOURCE_PATH,
    dtype=str,
    keep_default_na=False,
)

print("Source:")
print(SOURCE_PATH)

print()
print("Columns:")
print(list(df.columns))

student_col = find_column(
    df.columns,
    [
        "student_id",
        "banner_id",
        "pidm",
    ],
)

lineage_col = find_column(
    df.columns,
    [
        "credential_family",
        "credential_lineage",
        "lineage_id",
        "credential_family_id",
        "family_id",
        "credential_group",
    ],
)

catalog_col = find_column(
    df.columns,
    [
        "catalog_year",
        "assigned_catalog_year",
        "best_catalog_year",
    ],
)

status_col = find_column(
    df.columns,
    [
        "audit_status",
        "status",
        "best_audit_status",
    ],
)

credential_col = find_column(
    df.columns,
    [
        "credential_id",
        "best_credential_id",
    ],
)

status_rank_col = find_column(
    df.columns,
    [
        "status_rank",
    ],
)

print()
print("Resolved columns:")
print("  student:    ", student_col)
print("  lineage:    ", lineage_col)
print("  catalog:    ", catalog_col)
print("  status:     ", status_col)
print("  credential: ", credential_col)
print("  status rank:", status_rank_col)

required = {
    "student": student_col,
    "lineage": lineage_col,
    "catalog": catalog_col,
    "status": status_col,
}

missing = [
    label
    for label, column in required.items()
    if column is None
]

if missing:
    raise RuntimeError(
        "Could not identify required columns: "
        + ", ".join(missing)
    )

for column in [
    student_col,
    lineage_col,
    catalog_col,
    status_col,
]:
    df[column] = df[column].str.strip()

df[status_col] = df[status_col].str.upper()

df = df[
    df[student_col].ne("")
    & df[lineage_col].ne("")
    & df[catalog_col].ne("")
].copy()

df["_catalog_sort"] = df[catalog_col].map(
    catalog_sort_value
)

if status_rank_col is not None:
    df["_status_priority"] = pd.to_numeric(
        df[status_rank_col],
        errors="coerce",
    ).fillna(0)
else:
    df["_status_priority"] = (
        df[status_col]
        .map(
            {
                "COMPLETE": 3,
                "NEAR_COMPLETE": 2,
                "INCOMPLETE": 1,
            }
        )
        .fillna(0)
    )

sort_columns = [
    student_col,
    lineage_col,
    "_catalog_sort",
    "_status_priority",
]

ascending = [
    True,
    True,
    False,
    False,
]

latest = (
    df.sort_values(
        sort_columns,
        ascending=ascending,
    )
    .drop_duplicates(
        subset=[
            student_col,
            lineage_col,
        ],
        keep="first",
    )
    .copy()
)

complete = latest[
    latest[status_col].eq("COMPLETE")
].copy()

by_catalog = (
    complete.groupby(
        catalog_col,
        dropna=False,
    )
    .agg(
        lineage_awards=(lineage_col, "size"),
        distinct_students=(student_col, "nunique"),
        distinct_lineages=(lineage_col, "nunique"),
    )
    .reset_index()
)

by_catalog["_catalog_sort"] = by_catalog[catalog_col].map(
    catalog_sort_value
)

by_catalog = (
    by_catalog.sort_values("_catalog_sort")
    .drop(columns="_catalog_sort")
    .reset_index(drop=True)
)

print()
print("=" * 100)
print("COMPLETE — ONE ROW PER STUDENT + LINEAGE, LATEST CATALOG")
print("=" * 100)

if len(by_catalog):
    print(by_catalog.to_string(index=False))
else:
    print("No COMPLETE rows found after lineage deduplication.")

print()
print(
    "Overall lineage-deduped COMPLETE awards:",
    f"{len(complete):,}",
)

print(
    "Distinct students with at least one COMPLETE lineage:",
    f"{complete[student_col].nunique():,}",
)

print(
    "Distinct credential lineages represented:",
    f"{complete[lineage_col].nunique():,}",
)

print()
print("Selected latest-catalog status totals:")
print(
    latest[status_col]
    .value_counts(dropna=False)
    .to_string()
)

OUTPUT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)

by_catalog.to_csv(
    OUTPUT_PATH,
    index=False,
)

detail_output = OUTPUT_PATH.with_name(
    "lineage_deduped_complete_detail_before_r5_repair.csv"
)

complete.to_csv(
    detail_output,
    index=False,
)

print()
print("Wrote:")
print(OUTPUT_PATH)
print(detail_output)
