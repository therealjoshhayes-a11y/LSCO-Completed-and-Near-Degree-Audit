from pathlib import Path
import pandas as pd

SUMMARY_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_credential_summary.csv"
)

OUTPUT_PATH = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\completion_snapshot_before_r5_repair.csv"
)

summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    keep_default_na=False,
)

summary["catalog_year"] = summary["catalog_year"].str.strip()
summary["audit_status"] = summary["audit_status"].str.strip().str.upper()

snapshot = (
    summary.groupby(
        ["catalog_year", "audit_status"],
        dropna=False,
    )
    .size()
    .unstack(
        fill_value=0,
    )
    .reset_index()
)

for column in [
    "COMPLETE",
    "NEAR_COMPLETE",
    "INCOMPLETE",
]:
    if column not in snapshot.columns:
        snapshot[column] = 0

snapshot["TOTAL_AUDITS"] = (
    snapshot["COMPLETE"]
    + snapshot["NEAR_COMPLETE"]
    + snapshot["INCOMPLETE"]
)

snapshot = snapshot[
    [
        "catalog_year",
        "COMPLETE",
        "NEAR_COMPLETE",
        "INCOMPLETE",
        "TOTAL_AUDITS",
    ]
].sort_values("catalog_year")

print("=" * 90)
print("PRE-REPAIR COMPLETION SNAPSHOT BY CATALOG YEAR")
print("=" * 90)
print(snapshot.to_string(index=False))

print()
print("Overall totals:")
print(
    summary["audit_status"]
    .value_counts()
    .to_string()
)

target = summary[
    summary["catalog_year"].eq("2022-2023")
    & summary["credential_id"].eq(
        "CYBERSECURITY_SPECIALIST_2022"
    )
]

print()
print("=" * 90)
print("TARGET CREDENTIAL — CURRENT STATUS")
print("=" * 90)
print(
    target["audit_status"]
    .value_counts()
    .to_string()
)

print()
print("Current requirements_total values:")
print(
    target["requirements_total"]
    .value_counts()
    .sort_index()
    .to_string()
)

OUTPUT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)

snapshot.to_csv(
    OUTPUT_PATH,
    index=False,
)

print()
print("Wrote:")
print(OUTPUT_PATH)
