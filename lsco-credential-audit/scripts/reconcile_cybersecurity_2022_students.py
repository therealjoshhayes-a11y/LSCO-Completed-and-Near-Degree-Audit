from pathlib import Path
import pandas as pd

DETAIL_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_audit_results.csv"
)
SUMMARY_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_credential_summary.csv"
)

CATALOG_YEAR = "2022-2023"
CREDENTIAL_ID = "CYBERSECURITY_SPECIALIST_2022"

EXPECTED_IDS = {
    f"CYBERSECURITY_SPECIALIST_2022_R{i}"
    for i in range(1, 11)
}

detail_parts = []

for chunk in pd.read_csv(
    DETAIL_PATH,
    dtype=str,
    keep_default_na=False,
    chunksize=500_000,
):
    target = chunk[
        chunk["catalog_year"].eq(CATALOG_YEAR)
        & chunk["credential_id"].eq(CREDENTIAL_ID)
    ].copy()

    if not target.empty:
        detail_parts.append(target)

detail = pd.concat(detail_parts, ignore_index=True)

summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    keep_default_na=False,
)

summary = summary[
    summary["catalog_year"].eq(CATALOG_YEAR)
    & summary["credential_id"].eq(CREDENTIAL_ID)
].copy()

print("=" * 100)
print("CYBERSECURITY SPECIALIST 2022 STUDENT-LEVEL REQUIREMENT RECONCILIATION")
print("=" * 100)

print("Summary audits:", len(summary))
print("Detail rows:", len(detail))
print("Expected detail rows:", len(summary) * 10)
print("Difference:", len(summary) * 10 - len(detail))

print()
print("Rows emitted by requirement ID:")
requirement_counts = (
    detail["requirement_id"]
    .value_counts()
    .sort_index()
)
print(requirement_counts.to_string())

all_students = set(summary["student_id"])

student_requirement_sets = (
    detail.groupby("student_id")["requirement_id"]
    .agg(set)
)

records = []

for student_id in sorted(all_students):
    present = student_requirement_sets.get(student_id, set())
    missing = sorted(EXPECTED_IDS - present)
    unexpected = sorted(present - EXPECTED_IDS)

    records.append(
        {
            "student_id": student_id,
            "detail_row_count": len(present),
            "missing_requirement_ids": "|".join(missing),
            "unexpected_requirement_ids": "|".join(unexpected),
        }
    )

reconciliation = pd.DataFrame(records)

mismatches = reconciliation[
    reconciliation["detail_row_count"] != 10
].copy()

print()
print("Students with fewer than 10 distinct requirements:", len(mismatches))

print()
print("Missing-requirement patterns:")
print(
    mismatches["missing_requirement_ids"]
    .value_counts(dropna=False)
    .to_string()
)

print()
print("R5 status rows that do exist:")
r5 = detail[
    detail["requirement_id"].eq(
        "CYBERSECURITY_SPECIALIST_2022_R5"
    )
].copy()

print("R5 rows:", len(r5))
print(r5["status"].value_counts().to_string())

print()
print("R5 matched-option patterns:")
print(
    r5.groupby(
        [
            "status",
            "matched_options",
            "matched_grades",
        ],
        dropna=False,
    )
    .size()
    .sort_values(ascending=False)
    .head(30)
    .to_string()
)

affected_ids = set(mismatches["student_id"])

other_rows_for_affected = detail[
    detail["student_id"].isin(affected_ids)
].copy()

print()
print("Statuses for affected students across their other nine requirements:")
print(
    other_rows_for_affected.groupby(
        ["requirement_id", "status"]
    )
    .size()
    .to_string()
)

summary_cols = [
    "student_id",
    "requirements_met",
    "requirements_total",
    "requirements_missing",
    "requirements_unresolved",
    "audit_status",
]

mismatch_summary = mismatches.merge(
    summary[summary_cols],
    on="student_id",
    how="left",
    validate="one_to_one",
)

print()
print("Affected-summary status counts:")
print(
    mismatch_summary["audit_status"]
    .value_counts()
    .to_string()
)

print()
print("Affected requirements_total values:")
print(
    mismatch_summary["requirements_total"]
    .value_counts()
    .to_string()
)

print()
print("First 30 affected students:")
print(
    mismatch_summary.head(30)
    .to_string(index=False)
)

evidence_path = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\cybersecurity_specialist_2022_student_reconciliation.csv"
)

mismatch_summary.to_csv(
    evidence_path,
    index=False,
)

print()
print("Wrote:", evidence_path)
