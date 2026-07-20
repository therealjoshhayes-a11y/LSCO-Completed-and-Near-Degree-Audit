from pathlib import Path
import pandas as pd

DETAIL_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_audit_results.csv"
)
SUMMARY_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_credential_summary.csv"
)

CHUNK_SIZE = 500_000

FAILURE_TERMS = (
    "UNRESOLVED",
    "ERROR",
    "SKIPPED",
    "UNKNOWN",
    "INVALID",
    "MISSING_RULE",
    "NO_RULE",
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


print("=" * 100)
print("DETAIL OUTPUT RUNTIME-RESOLUTION SCAN")
print("=" * 100)

detail_header = pd.read_csv(DETAIL_PATH, nrows=0)
detail_columns = list(detail_header.columns)

print("Detail columns:")
print(detail_columns)

detail_status_col = find_column(
    detail_columns,
    [
        "requirement_status",
        "status",
        "audit_status",
        "result_status",
        "met_status",
    ],
)

detail_rule_col = find_column(
    detail_columns,
    [
        "rule_type",
        "requirement_rule_type",
    ],
)

detail_option_col = find_column(
    detail_columns,
    [
        "option_type",
        "requirement_option_type",
    ],
)

detail_requirement_col = find_column(
    detail_columns,
    [
        "requirement_id",
        "requirement_key",
    ],
)

detail_student_col = find_column(
    detail_columns,
    [
        "student_id",
        "student_pidm",
        "pidm",
        "banner_id",
    ],
)

print()
print("Resolved detail columns:")
print("  status:", detail_status_col)
print("  rule_type:", detail_rule_col)
print("  option_type:", detail_option_col)
print("  requirement_id:", detail_requirement_col)
print("  student:", detail_student_col)

if detail_status_col is None:
    raise RuntimeError(
        "Could not identify the detail status column. "
        "Review the printed columns and add its name to the candidate list."
    )

detail_rows = 0
blank_status_rows = 0
failure_rows = 0
failure_samples = []
status_counts = {}
rule_status_counts = {}

for chunk_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
    ),
    start=1,
):
    detail_rows += len(chunk)

    statuses = chunk[detail_status_col].str.strip().str.upper()

    blank_mask = statuses.eq("")
    blank_status_rows += int(blank_mask.sum())

    failure_mask = statuses.map(
        lambda value: any(term in value for term in FAILURE_TERMS)
    )
    failure_rows += int(failure_mask.sum())

    for status, count in statuses.value_counts().items():
        status_counts[status] = status_counts.get(status, 0) + int(count)

    if detail_rule_col is not None:
        rules = chunk[detail_rule_col].str.strip().str.upper()

        grouped = (
            pd.DataFrame(
                {
                    "rule_type": rules,
                    "status": statuses,
                }
            )
            .groupby(["rule_type", "status"])
            .size()
        )

        for key, count in grouped.items():
            rule_status_counts[key] = (
                rule_status_counts.get(key, 0) + int(count)
            )

    if failure_mask.any() and len(failure_samples) < 50:
        sample_columns = [
            column
            for column in [
                detail_student_col,
                "catalog_year",
                "credential_id",
                detail_requirement_col,
                detail_rule_col,
                detail_option_col,
                detail_status_col,
            ]
            if column is not None and column in chunk.columns
        ]

        remaining = 50 - len(failure_samples)

        failure_samples.extend(
            chunk.loc[failure_mask, sample_columns]
            .head(remaining)
            .to_dict("records")
        )

    if chunk_number % 20 == 0:
        print(
            f"Read detail chunks: {chunk_number:,} "
            f"| rows: {detail_rows:,}"
        )

print()
print("Detail rows:", f"{detail_rows:,}")
print("Blank detail statuses:", f"{blank_status_rows:,}")
print("Runtime failure statuses:", f"{failure_rows:,}")

print()
print("Detail status counts:")
for status, count in sorted(
    status_counts.items(),
    key=lambda item: (-item[1], item[0]),
):
    print(f"{status or '<BLANK>':30s} {count:>15,}")

if detail_rule_col is not None:
    print()
    print("Status counts by rule type:")
    rule_table = pd.Series(rule_status_counts).rename("rows")
    rule_table.index = pd.MultiIndex.from_tuples(
        rule_table.index,
        names=["rule_type", "status"],
    )
    print(rule_table.to_string())

if failure_samples:
    print()
    print("First runtime failure samples:")
    print(pd.DataFrame(failure_samples).to_string(index=False))


print()
print("=" * 100)
print("SUMMARY OUTPUT STATUS SCAN")
print("=" * 100)

summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    keep_default_na=False,
)

print("Summary rows:", f"{len(summary):,}")
print("Summary columns:")
print(list(summary.columns))

summary_status_col = find_column(
    summary.columns,
    [
        "audit_status",
        "credential_status",
        "status",
    ],
)

if summary_status_col is None:
    raise RuntimeError(
        "Could not identify the summary status column."
    )

summary_statuses = (
    summary[summary_status_col]
    .str.strip()
    .str.upper()
)

summary_blank = int(summary_statuses.eq("").sum())
summary_failure = int(
    summary_statuses.map(
        lambda value: any(term in value for term in FAILURE_TERMS)
    ).sum()
)

print()
print("Summary status column:", summary_status_col)
print("Blank summary statuses:", f"{summary_blank:,}")
print("Summary failure statuses:", f"{summary_failure:,}")

print()
print("Summary status counts:")
print(summary_statuses.value_counts(dropna=False).to_string())

print()
print("=" * 100)

if (
    blank_status_rows == 0
    and failure_rows == 0
    and summary_blank == 0
    and summary_failure == 0
):
    print("GATE C RESULT: PASS")
else:
    print("GATE C RESULT: REVIEW REQUIRED")
