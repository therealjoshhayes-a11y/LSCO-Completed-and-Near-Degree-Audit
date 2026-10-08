from pathlib import Path
from datetime import datetime
import shutil
import pandas as pd

ROOT = Path.cwd()

PATH = (
    ROOT
    / "data/interim/institutional_awards"
    / "governed_lineage_relationships_final.csv"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = PATH.with_name(
    f"{PATH.stem}_PRE_NONCONSUMING_STACK_FIX_{STAMP}{PATH.suffix}"
)

shutil.copy2(PATH, BACKUP)

df = pd.read_csv(
    PATH,
    dtype=str,
).fillna("")


# =============================================================================
# Catalog-proven separately awardable relationships.
#
# Existing award may demonstrate curricular progression, but it DOES NOT
# represent the separately published detected credential.
# =============================================================================

FIXES = {

    (
        "CRIMINAL_JUSTICE_LAW_ENFORCEMENT",
        "CRIMINAL_JUSTICE_CERTIFICATE_OF_COMPLETION",
    ): (
        "STACKABLE_NONCONSUMING",
        "Catalog publishes Criminal Justice Law Enforcement as a separate "
        "certificate and states its coursework may apply toward the larger "
        "Criminal Justice certificate. Both remain separately awardable."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "BIOLOGY_MEDICAL_PROFESSIONS_EMPHASIS",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an academic associate does not represent the certificate."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "BUSINESS",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an academic associate does not represent the certificate."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "COMPUTER_SCIENCE",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an academic associate does not represent the certificate."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "LIBERAL_ARTS",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an academic associate does not represent the certificate."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "SOCIOLOGY",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an academic associate does not represent the certificate."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "TEACHING_AAT1",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an AAT does not represent the certificate."
    ),

    (
        "GENERAL_STUDIES_CORE_CURRICULUM",
        "TEACHING_AAT2",
    ): (
        "EMBEDDED_SEPARATELY_AWARDABLE",
        "General Studies Core Curriculum is a separately published certificate. "
        "Completion of an AAT does not represent the certificate."
    ),

    (
        "INSTRUMENTATION_BASIC",
        "INSTRUMENTATION_AAS",
    ): (
        "STACKABLE_NONCONSUMING",
        "Instrumentation Basic is a separately published 15-SCH certificate "
        "nested in the Instrumentation pathway. The AAS does not consume it."
    ),

    (
        "INSTRUMENTATION_BASIC",
        "INSTRUMENTATION_CERTIFICATE_OF_COMPLETION",
    ): (
        "STACKABLE_NONCONSUMING",
        "Instrumentation Basic and the full Instrumentation certificate are "
        "concurrently published, separately awardable stackable credentials."
    ),

    (
        "PHARMACY_TECHNOLOGY_BASIC",
        "HOSPITAL_PHARMACY_TECHNOLOGY",
    ): (
        "STACKABLE_NONCONSUMING",
        "Pharmacy Technology Basic is explicitly published as a stackable "
        "certificate. The full Hospital Pharmacy Technology certificate does "
        "not consume the Basic certificate."
    ),

    (
        "REAL_ESTATE",
        "REAL_ESTATE_MANAGEMENT",
    ): (
        "STACKABLE_NONCONSUMING",
        "Real Estate is a separately published Certificate of Completion and "
        "Real Estate Management is the associated degree pathway. The degree "
        "does not represent the certificate."
    ),

    (
        "SAFETY_HEALTH_AND_ENVIRONMENT",
        "SAFETY_HEALTH_AND_ENVIRONMENT_AAS",
    ): (
        "STACKABLE_NONCONSUMING",
        "Safety, Health and Environment Certificate and AAS are separately "
        "published credentials. The AAS does not consume the certificate."
    ),
}


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
        f"Governance file missing columns: {sorted(missing)}"
    )


print("=" * 110)
print("CATALOG-PROVEN NON-CONSUMING GOVERNANCE REPAIR")
print("=" * 110)

changed = []

for (detected, institutional), (rel_type, note) in FIXES.items():

    mask = (
        df["detected_lineage"].eq(detected)
        & df["institutional_lineage"].eq(institutional)
    )

    n = int(mask.sum())

    if n != 1:
        raise RuntimeError(
            f"Expected exactly one governance row for "
            f"{detected} -> {institutional}; found {n}"
        )

    old_rep = (
        df.loc[
            mask,
            "awarded_represents_detected"
        ]
        .iloc[0]
        .strip()
        .lower()
    )

    old_remains = (
        df.loc[
            mask,
            "detected_remains_additional_award"
        ]
        .iloc[0]
        .strip()
        .lower()
    )

    if old_rep != "true" or old_remains != "false":
        raise RuntimeError(
            f"{detected} -> {institutional} is not currently "
            f"the expected consuming rule "
            f"(represents={old_rep}, remains={old_remains})."
        )

    df.loc[
        mask,
        "relationship_type"
    ] = rel_type

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
    ] = note

    df.loc[
        mask,
        "governance_source"
    ] = "CATALOG_REVIEW_20260811"

    changed.append(
        (
            detected,
            institutional,
            rel_type,
        )
    )


df.to_csv(
    PATH,
    index=False,
)


# =============================================================================
# QA — none of the 13 repaired pairs may still consume the detected award.
# =============================================================================

check = pd.read_csv(
    PATH,
    dtype=str,
).fillna("")

bad = []

for detected, institutional in FIXES:

    mask = (
        check["detected_lineage"].eq(detected)
        & check["institutional_lineage"].eq(institutional)
    )

    row = check.loc[mask].iloc[0]

    if (
        str(row["awarded_represents_detected"]).strip().lower() != "false"
        or
        str(row["detected_remains_additional_award"]).strip().lower() != "true"
    ):
        bad.append(
            f"{detected} -> {institutional}"
        )

if bad:
    raise RuntimeError(
        "Post-write validation failed:\n"
        + "\n".join(bad)
    )


print()
print("Relationships repaired:", len(changed))

for detected, institutional, rel_type in changed:
    print(
        f"  {detected} -> {institutional} "
        f"[{rel_type}]"
    )

print()
print("Backup:")
print(BACKUP)

print()
print("PASS")
