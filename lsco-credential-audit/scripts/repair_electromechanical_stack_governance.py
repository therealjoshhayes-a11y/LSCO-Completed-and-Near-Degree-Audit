from pathlib import Path
from datetime import datetime
import shutil
import pandas as pd

ROOT = Path.cwd()

p = (
    ROOT
    / "data/interim/institutional_awards"
    / "governed_lineage_relationships_final.csv"
)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

backup = p.with_name(
    f"{p.stem}_PRE_ELECTROMECH_STACK_FIX_{stamp}{p.suffix}"
)

shutil.copy2(p, backup)

df = pd.read_csv(
    p,
    dtype=str,
).fillna("")

required = {
    "detected_lineage",
    "institutional_lineage",
    "relationship_type",
    "awarded_represents_detected",
    "detected_remains_additional_award",
    "governance_status",
    "governance_note",
    "governance_source",
}

missing = required - set(df.columns)

if missing:
    raise RuntimeError(
        f"Missing governance columns: {sorted(missing)}"
    )

mask = (
    df["detected_lineage"].eq(
        "ELECTROMECHANICAL_TECHNOLOGY_BASIC"
    )
    & df["institutional_lineage"].eq(
        "ELECTROMECHANICAL_TECHNOLOGY"
    )
    & df["awarded_represents_detected"]
        .str.strip()
        .str.lower()
        .eq("true")
    & df["detected_remains_additional_award"]
        .str.strip()
        .str.lower()
        .eq("false")
)

if mask.sum() != 1:
    raise RuntimeError(
        "Expected exactly one stale consuming "
        f"Electromechanical Basic rule; found {mask.sum()}."
    )

print("=" * 110)
print("OLD GOVERNANCE RULE")
print("=" * 110)
print(df.loc[mask].to_string(index=False))

# The full certificate is the direct catalog parent of Basic.
# It is a stackable relationship, but the parent award does NOT
# represent or consume the separately awardable Basic certificate.
df.loc[
    mask,
    "institutional_lineage"
] = "ELECTROMECHANICAL_TECHNOLOGY_CERTIFICATE"

df.loc[
    mask,
    "relationship_type"
] = "PARENT_CHILD_STACK"

df.loc[
    mask,
    "awarded_represents_detected"
] = "False"

df.loc[
    mask,
    "detected_remains_additional_award"
] = "True"

df.loc[
    mask,
    "governance_status"
] = "GOVERNED"

df.loc[
    mask,
    "governance_note"
] = (
    "Catalog-validated stackable relationship. "
    "Electromechanical Technology Basic is separately published "
    "and separately awardable from the full Electromechanical "
    "Technology Certificate; the parent certificate does not "
    "represent or consume the Basic award."
)

df.loc[
    mask,
    "governance_source"
] = "CATALOG_REVIEW_20260811"

df.to_csv(
    p,
    index=False,
)

check = (
    df["detected_lineage"].eq(
        "ELECTROMECHANICAL_TECHNOLOGY_BASIC"
    )
    & df["institutional_lineage"].eq(
        "ELECTROMECHANICAL_TECHNOLOGY_CERTIFICATE"
    )
)

print()
print("=" * 110)
print("NEW GOVERNANCE RULE")
print("=" * 110)
print(df.loc[check].to_string(index=False))

print()
print("Backup:")
print(backup)
print()
print("PASS")
