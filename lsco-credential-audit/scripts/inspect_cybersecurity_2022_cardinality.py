from pathlib import Path
import pandas as pd

REQ_PATH = Path(
    r"data\processed\catalogs\requirements_master_multiyear.csv"
)
DETAIL_PATH = Path(
    r"data\processed\full_actual_audit\full_actual_audit_results.csv"
)

CATALOG_YEAR = "2022-2023"
CREDENTIAL_ID = "CYBERSECURITY_SPECIALIST_2022"

req = pd.read_csv(
    REQ_PATH,
    dtype=str,
    keep_default_na=False,
)

target_req = req[
    req["catalog_year"].eq(CATALOG_YEAR)
    & req["credential_id"].eq(CREDENTIAL_ID)
].copy()

print("=" * 100)
print("MASTER REQUIREMENT INVENTORY")
print("=" * 100)

print("Source option rows:", len(target_req))
print(
    "Distinct requirement IDs:",
    target_req["requirement_id"].nunique()
)

inventory_columns = [
    column
    for column in [
        "catalog_year",
        "credential_id",
        "requirement_id",
        "requirement_text",
        "rule_type",
        "required_count",
        "credit_hours",
        "option_type",
        "option_value",
    ]
    if column in target_req.columns
]

print()
print(
    target_req[inventory_columns]
    .sort_values(
        ["requirement_id", "option_type", "option_value"]
    )
    .to_string(index=False)
)

master_ids = set(target_req["requirement_id"])

print()
print("=" * 100)
print("EXECUTED DETAIL REQUIREMENT INVENTORY")
print("=" * 100)

executed_ids = set()
executed_samples = []

for chunk in pd.read_csv(
    DETAIL_PATH,
    dtype=str,
    keep_default_na=False,
    usecols=[
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "rule_type",
        "status",
        "required_options",
        "option_types",
    ],
    chunksize=500_000,
):
    target = chunk[
        chunk["catalog_year"].eq(CATALOG_YEAR)
        & chunk["credential_id"].eq(CREDENTIAL_ID)
    ]

    if target.empty:
        continue

    executed_ids.update(target["requirement_id"])

    if not executed_samples:
        first_student = target["student_id"].iloc[0]

        executed_samples.append(
            target[
                target["student_id"].eq(first_student)
            ].copy()
        )

print("Distinct executed requirement IDs:", len(executed_ids))

missing_ids = sorted(master_ids - executed_ids)
unexpected_ids = sorted(executed_ids - master_ids)

print("Missing from execution:", len(missing_ids))
print(missing_ids)

print("Unexpected in execution:", len(unexpected_ids))
print(unexpected_ids)

if executed_samples:
    sample = pd.concat(executed_samples, ignore_index=True)

    print()
    print("One student's executed requirements:")
    print(
        sample.sort_values("requirement_id")
        .to_string(index=False)
    )

if missing_ids:
    print()
    print("=" * 100)
    print("MISSING REQUIREMENT SOURCE ROWS")
    print("=" * 100)

    missing_rows = target_req[
        target_req["requirement_id"].isin(missing_ids)
    ]

    print(
        missing_rows[inventory_columns]
        .sort_values(
            ["requirement_id", "option_type", "option_value"]
        )
        .to_string(index=False)
    )

    evidence_path = Path(
        r"data\processed\full_actual_audit\evidence"
        r"\cybersecurity_specialist_2022_missing_requirement.csv"
    )

    missing_rows.to_csv(
        evidence_path,
        index=False,
    )

    print()
    print("Wrote:", evidence_path)
