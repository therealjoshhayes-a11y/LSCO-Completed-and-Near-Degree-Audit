from pathlib import Path
from datetime import datetime
import os
import shutil
import pandas as pd
from openpyxl import load_workbook

ROOT = Path.cwd()

MODELED = (
    ROOT / "data/processed/full_actual_audit/president_report/"
    "complete_rows_with_canonical_lineage.csv"
)

CROSSWALK = (
    ROOT / "data/interim/institutional_awards/"
    "award_program_crosswalk_curated.xlsx"
)

TARGET = "SAFETY_HEALTH_AND_ENVIRONMENT_AAS"
OLD = "INDUSTRIAL_TECHNOLOGY"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def norm(v):
    if v is None or pd.isna(v):
        return ""
    return str(v).strip().upper()


def fail(msg):
    raise RuntimeError(msg)


print("=" * 110)
print("INDUSTRIAL TECHNOLOGY -> SAFETY, HEALTH & ENVIRONMENT AAS LINEAGE REPAIR")
print("=" * 110)


# =============================================================================
# MODELED LINEAGE
# =============================================================================

df = pd.read_csv(MODELED, dtype=str, low_memory=False).fillna("")

mask = (
    df["canonical_lineage"].map(norm).eq(OLD)
    & df["catalog_year"].eq("2021-2022")
)

before = (
    df.loc[
        mask,
        [
            "catalog_year",
            "credential_id",
            "mechanical_lineage",
            "canonical_lineage",
        ],
    ]
    .drop_duplicates()
)

print("\nMODELED GENERATION BEFORE REPAIR")
print(before.to_string(index=False))

if before.empty:
    fail("No 2021-2022 INDUSTRIAL_TECHNOLOGY modeled rows found.")

# Guard: this should be the historical AAS, not some certificate.
bad = before[
    ~before["credential_id"]
    .str.upper()
    .str.contains("INDUSTRIAL_TECHNOLOGY", na=False)
]

if not bad.empty:
    fail("Unexpected rows inside Industrial Technology target set.")

df.loc[mask, "canonical_lineage"] = TARGET


# =============================================================================
# CROSSWALK
# =============================================================================

wb = load_workbook(CROSSWALK)

ws = wb["Crosswalk Draft"]

headers = {
    norm(c.value): c.column
    for c in ws[1]
    if c.value is not None
}

for needed in [
    "CURR1PROGRAMCODE",
    "MAJOR1CODE",
    "DEGREECODE",
    "MAJORDESC",
    "CANONICAL_LINEAGE",
    "RECONCILIATION_KEY",
]:
    if needed not in headers:
        fail(f"Missing crosswalk column: {needed}")

updates = []

for r in range(2, ws.max_row + 1):

    degree = norm(
        ws.cell(r, headers["DEGREECODE"]).value
    )

    major_desc = norm(
        ws.cell(r, headers["MAJORDESC"]).value
    )

    lineage = norm(
        ws.cell(r, headers["CANONICAL_LINEAGE"]).value
    )

    # Only the AAS historical identity.
    if (
        degree == "AAS"
        and lineage == OLD
    ):
        updates.append({
            "row": r,
            "program": norm(
                ws.cell(
                    r,
                    headers["CURR1PROGRAMCODE"]
                ).value
            ),
            "major": norm(
                ws.cell(
                    r,
                    headers["MAJOR1CODE"]
                ).value
            ),
            "degree": degree,
            "major_desc": major_desc,
            "old_lineage": lineage,
        })

        ws.cell(
            r,
            headers["CANONICAL_LINEAGE"]
        ).value = TARGET

        ws.cell(
            r,
            headers["RECONCILIATION_KEY"]
        ).value = TARGET


print("\nOFFICIAL-AWARD CROSSWALK ROWS TO REPAIR")

if updates:
    print(pd.DataFrame(updates).to_string(index=False))
else:
    print(
        "No official crosswalk row currently uses "
        "INDUSTRIAL_TECHNOLOGY. "
        "This is okay if historical awards use SHED only."
    )


# =============================================================================
# MODELED INVENTORY TAB
# =============================================================================

inventory_updates = 0

if "Modeled Inventory" in wb.sheetnames:

    inv = wb["Modeled Inventory"]

    ih = {
        norm(c.value): c.column
        for c in inv[1]
        if c.value is not None
    }

    if {
        "CREDENTIAL_ID",
        "CANONICAL_LINEAGE",
    }.issubset(ih):

        for r in range(2, inv.max_row + 1):

            cred = norm(
                inv.cell(
                    r,
                    ih["CREDENTIAL_ID"]
                ).value
            )

            lin = norm(
                inv.cell(
                    r,
                    ih["CANONICAL_LINEAGE"]
                ).value
            )

            if (
                lin == OLD
                and "INDUSTRIAL_TECHNOLOGY" in cred
            ):
                inv.cell(
                    r,
                    ih["CANONICAL_LINEAGE"]
                ).value = TARGET

                inventory_updates += 1


# =============================================================================
# BACKUP
# =============================================================================

m_backup = MODELED.with_name(
    MODELED.stem
    + "_PRE_INDUSTRIAL_TO_SHE_AAS_FIX_"
    + STAMP
    + MODELED.suffix
)

x_backup = CROSSWALK.with_name(
    CROSSWALK.stem
    + "_PRE_INDUSTRIAL_TO_SHE_AAS_FIX_"
    + STAMP
    + CROSSWALK.suffix
)

shutil.copy2(MODELED, m_backup)
shutil.copy2(CROSSWALK, x_backup)


# =============================================================================
# ATOMIC WRITES
# =============================================================================

tmp_csv = MODELED.with_suffix(".tmp.csv")
df.to_csv(tmp_csv, index=False)
os.replace(tmp_csv, MODELED)

tmp_xlsx = CROSSWALK.with_name(
    CROSSWALK.stem + ".tmp.xlsx"
)
wb.save(tmp_xlsx)
os.replace(tmp_xlsx, CROSSWALK)


# =============================================================================
# VALIDATE
# =============================================================================

chk = pd.read_csv(
    MODELED,
    dtype=str,
    low_memory=False,
).fillna("")

remaining = chk[
    chk["catalog_year"].eq("2021-2022")
    & chk["canonical_lineage"].map(norm).eq(OLD)
]

if not remaining.empty:
    fail(
        "2021-2022 Industrial Technology rows "
        "remain on old canonical lineage."
    )

after = (
    chk[
        chk["credential_id"]
        .str.upper()
        .str.contains(
            "INDUSTRIAL_TECHNOLOGY",
            na=False
        )
    ][
        [
            "catalog_year",
            "credential_id",
            "mechanical_lineage",
            "canonical_lineage",
        ]
    ]
    .drop_duplicates()
)

print("\nAFTER REPAIR")
print(after.to_string(index=False))

print()
print("Modeled COMPLETE rows updated:", int(mask.sum()))
print("Crosswalk rows updated:", len(updates))
print("Modeled Inventory rows updated:", inventory_updates)
print("Canonical AAS lineage:", TARGET)

print("\nBACKUPS")
print(m_backup)
print(x_backup)

print()
print(
    "PASS — 2021-2022 Industrial Technology AAS "
    "now continues into Safety, Health, and Environment AAS."
)
