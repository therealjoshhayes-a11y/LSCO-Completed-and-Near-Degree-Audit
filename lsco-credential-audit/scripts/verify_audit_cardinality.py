from pathlib import Path
import pandas as pd

REQ_PATH = Path(
    r"data\processed\catalogs\requirements_master_multiyear.csv"
)
DETAIL_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_audit_results.csv"
)
SUMMARY_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_credential_summary.csv"
)

CHUNK_SIZE = 500_000

print("=" * 100)
print("GATE D - AUDIT CARDINALITY RECONCILIATION")
print("=" * 100)

req = pd.read_csv(
    REQ_PATH,
    dtype=str,
    keep_default_na=False,
)

detail_header = pd.read_csv(DETAIL_PATH, nrows=0)
summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    keep_default_na=False,
)

required_req_cols = {
    "catalog_year",
    "credential_id",
    "requirement_id",
}

missing = required_req_cols - set(req.columns)
if missing:
    raise RuntimeError(
        f"Requirements file is missing columns: {sorted(missing)}"
    )

# One expected detail row per distinct requirement, for every audited
# student/catalog/credential combination.
req_inventory = (
    req[
        ["catalog_year", "credential_id", "requirement_id"]
    ]
    .drop_duplicates()
)

requirements_per_credential = (
    req_inventory
    .groupby(["catalog_year", "credential_id"])
    .size()
    .rename("expected_requirements")
    .reset_index()
)

duplicate_requirement_rows = (
    req.groupby(
        ["catalog_year", "credential_id", "requirement_id"]
    )
    .size()
    .reset_index(name="source_rows")
)

duplicate_requirement_ids = duplicate_requirement_rows[
    duplicate_requirement_rows["source_rows"] > 1
]

print("Distinct credential-years in requirements:",
      f"{len(requirements_per_credential):,}")
print("Distinct requirements:",
      f"{len(req_inventory):,}")
print("Repeated source rows per requirement_id:",
      f"{len(duplicate_requirement_ids):,}")

print()
print("Summary rows:", f"{len(summary):,}")
print(
    "Unique students:",
    f"{summary['student_id'].nunique():,}"
)

duplicate_summary_keys = (
    summary.groupby(
        ["student_id", "catalog_year", "credential_id"]
    )
    .size()
    .reset_index(name="rows")
)

duplicate_summary_keys = duplicate_summary_keys[
    duplicate_summary_keys["rows"] > 1
]

print(
    "Duplicate summary audit keys:",
    f"{len(duplicate_summary_keys):,}"
)

summary_check = summary.merge(
    requirements_per_credential,
    on=["catalog_year", "credential_id"],
    how="left",
    validate="many_to_one",
)

missing_requirement_inventory = summary_check[
    summary_check["expected_requirements"].isna()
]

print(
    "Summary rows without requirement inventory:",
    f"{len(missing_requirement_inventory):,}"
)

summary_check["requirements_total_num"] = pd.to_numeric(
    summary_check["requirements_total"],
    errors="coerce",
)

summary_check["expected_requirements_num"] = pd.to_numeric(
    summary_check["expected_requirements"],
    errors="coerce",
)

summary_total_mismatch = summary_check[
    summary_check["requirements_total_num"]
    != summary_check["expected_requirements_num"]
]

print(
    "Summary requirements_total mismatches:",
    f"{len(summary_total_mismatch):,}"
)

expected_detail_rows = int(
    summary_check["expected_requirements_num"].sum()
)

print()
print(
    "Expected detail rows from summary × requirement inventory:",
    f"{expected_detail_rows:,}"
)

actual_detail_rows = 0
actual_counts = {}

for chunk_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        keep_default_na=False,
        usecols=[
            "student_id",
            "catalog_year",
            "credential_id",
        ],
        chunksize=CHUNK_SIZE,
    ),
    start=1,
):
    actual_detail_rows += len(chunk)

    grouped = (
        chunk.groupby(
            ["student_id", "catalog_year", "credential_id"]
        )
        .size()
    )

    for key, count in grouped.items():
        actual_counts[key] = (
            actual_counts.get(key, 0) + int(count)
        )

    if chunk_number % 20 == 0:
        print(
            f"Read detail chunks: {chunk_number:,} "
            f"| rows: {actual_detail_rows:,}"
        )

print()
print("Actual detail rows:", f"{actual_detail_rows:,}")
print(
    "Expected minus actual:",
    f"{expected_detail_rows - actual_detail_rows:,}"
)

actual_count_df = pd.DataFrame(
    [
        {
            "student_id": key[0],
            "catalog_year": key[1],
            "credential_id": key[2],
            "actual_requirements": count,
        }
        for key, count in actual_counts.items()
    ]
)

audit_count_check = summary_check.merge(
    actual_count_df,
    on=["student_id", "catalog_year", "credential_id"],
    how="left",
    validate="one_to_one",
)

audit_count_check["actual_requirements"] = (
    audit_count_check["actual_requirements"]
    .fillna(0)
    .astype(int)
)

audit_count_check["expected_requirements_num"] = (
    audit_count_check["expected_requirements_num"]
    .fillna(-1)
    .astype(int)
)

audit_count_check["row_delta"] = (
    audit_count_check["actual_requirements"]
    - audit_count_check["expected_requirements_num"]
)

audit_mismatches = audit_count_check[
    audit_count_check["row_delta"] != 0
].copy()

print(
    "Student/catalog/credential audits with row-count mismatch:",
    f"{len(audit_mismatches):,}"
)

if len(audit_mismatches):
    print()
    print("Mismatch totals by catalog year:")
    print(
        audit_mismatches.groupby("catalog_year")
        .agg(
            affected_audits=("credential_id", "size"),
            net_row_delta=("row_delta", "sum"),
        )
        .to_string()
    )

    print()
    print("Mismatch totals by credential:")
    print(
        audit_mismatches.groupby(
            ["catalog_year", "credential_id"]
        )
        .agg(
            affected_audits=("student_id", "size"),
            expected=("expected_requirements_num", "first"),
            actual=("actual_requirements", "first"),
            net_row_delta=("row_delta", "sum"),
        )
        .sort_values(
            ["catalog_year", "credential_id"]
        )
        .head(100)
        .to_string()
    )

    evidence_path = Path(
        r"data\processed\full_actual_audit\evidence"
        r"\audit_cardinality_mismatches.csv"
    )
    evidence_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_mismatches.to_csv(
        evidence_path,
        index=False,
    )

    print()
    print("Wrote:", evidence_path)

print()
print("=" * 100)

if (
    len(duplicate_summary_keys) == 0
    and len(missing_requirement_inventory) == 0
    and len(summary_total_mismatch) == 0
    and expected_detail_rows == actual_detail_rows
    and len(audit_mismatches) == 0
):
    print("GATE D RESULT: PASS")
else:
    print("GATE D RESULT: REVIEW REQUIRED")
