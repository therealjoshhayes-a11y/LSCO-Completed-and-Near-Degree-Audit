from pathlib import Path
from datetime import datetime
import shutil
import pandas as pd

ROOT = Path.cwd()
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

COMPLETE = (
    ROOT
    / "data/processed/full_actual_audit/president_report"
    / "complete_rows_with_canonical_lineage.csv"
)

GOV = (
    ROOT
    / "data/interim/institutional_awards"
    / "governed_lineage_relationships_final.csv"
)

LINEAGE_CROSSWALK = (
    ROOT
    / "data/processed/reporting"
    / "credential_lineage_crosswalk.csv"
)

OLD = "REAL_ESTATE"
NEW = "REAL_ESTATE_MANAGEMENT"
AAS = "BUSINESS_REAL_ESTATE_MANAGEMENT"


def backup(path: Path, label: str):
    dst = path.with_name(
        f"{path.stem}_PRE_{label}_{STAMP}{path.suffix}"
    )
    shutil.copy2(path, dst)
    return dst


print("=" * 110)
print("REAL ESTATE CERTIFICATE CANONICAL LINEAGE REPAIR")
print("=" * 110)


# =============================================================================
# 1. CURRENT COMPLETION ARTIFACT
# =============================================================================

df = pd.read_csv(
    COMPLETE,
    dtype=str,
    low_memory=False,
).fillna("")

needed = {
    "credential_id",
    "canonical_lineage",
}

missing = needed - set(df.columns)

if missing:
    raise RuntimeError(
        f"Completion file missing: {sorted(missing)}"
    )

cert_mask = (
    df["credential_id"].eq("REAL_ESTATE_2025")
)

if not cert_mask.any():
    raise RuntimeError(
        "REAL_ESTATE_2025 not found in completion artifact."
    )

bad_cert = df.loc[
    cert_mask
    & ~df["canonical_lineage"].isin(
        [OLD, NEW]
    )
]

if not bad_cert.empty:
    raise RuntimeError(
        "Unexpected canonical lineage for REAL_ESTATE_2025:\n"
        + bad_cert[
            [
                "credential_id",
                "canonical_lineage",
            ]
        ]
        .drop_duplicates()
        .to_string(index=False)
    )


# Protect the AAS.
aas_mask = (
    df["credential_id"].eq(
        "REAL_ESTATE_MANAGEMENT_2025"
    )
)

if aas_mask.any():

    bad_aas = df.loc[
        aas_mask
        & ~df["canonical_lineage"].eq(AAS)
    ]

    if not bad_aas.empty:
        raise RuntimeError(
            "STOP: 2025 Real Estate Management AAS "
            "is not mapped to BUSINESS_REAL_ESTATE_MANAGEMENT:\n"
            + bad_aas[
                [
                    "credential_id",
                    "canonical_lineage",
                ]
            ]
            .drop_duplicates()
            .to_string(index=False)
        )


print()
print("BEFORE")
print(
    df.loc[
        cert_mask | aas_mask,
        [
            c for c in [
                "catalog_year",
                "credential_id",
                "mechanical_lineage",
                "canonical_lineage",
            ]
            if c in df.columns
        ],
    ]
    .drop_duplicates()
    .sort_values("credential_id")
    .to_string(index=False)
)

complete_backup = backup(
    COMPLETE,
    "REAL_ESTATE_CERT_FIX"
)

changed = int(
    (
        cert_mask
        & df["canonical_lineage"].eq(OLD)
    ).sum()
)

df.loc[
    cert_mask,
    "canonical_lineage"
] = NEW

df.to_csv(
    COMPLETE,
    index=False,
)


# =============================================================================
# 2. GOVERNANCE
#
# REAL_ESTATE -> REAL_ESTATE_MANAGEMENT is not a relationship anymore.
# They are the SAME certificate identity.
# Normalize the obsolete name and retire any resulting self-pair.
# =============================================================================

gov_backup = backup(
    GOV,
    "REAL_ESTATE_CERT_FIX"
)

g = pd.read_csv(
    GOV,
    dtype=str,
).fillna("")

for col in [
    "detected_lineage",
    "institutional_lineage",
]:
    if col not in g.columns:
        raise RuntimeError(
            f"{col} missing from governance."
        )

g["detected_lineage"] = (
    g["detected_lineage"]
    .replace({OLD: NEW})
)

g["institutional_lineage"] = (
    g["institutional_lineage"]
    .replace({OLD: NEW})
)

self_mask = (
    g["detected_lineage"].eq(NEW)
    & g["institutional_lineage"].eq(NEW)
)

retired = g.loc[self_mask].copy()

if len(retired):

    retired_path = GOV.with_name(
        f"retired_real_estate_alias_governance_{STAMP}.csv"
    )

    retired.to_csv(
        retired_path,
        index=False,
    )

    print()
    print(
        "Redundant Real Estate governance rows retired:",
        len(retired),
    )
    print("Audit:", retired_path)

g = g.loc[
    ~self_mask
].copy()

g.to_csv(
    GOV,
    index=False,
)


# =============================================================================
# 3. PERSISTENT CREDENTIAL-LINEAGE CROSSWALK, IF PRESENT
# =============================================================================

if LINEAGE_CROSSWALK.exists():

    cw_backup = backup(
        LINEAGE_CROSSWALK,
        "REAL_ESTATE_CERT_FIX"
    )

    cw = pd.read_csv(
        LINEAGE_CROSSWALK,
        dtype=str,
    ).fillna("")

    lineage_col = next(
        (
            c for c in [
                "credential_lineage",
                "canonical_lineage",
            ]
            if c in cw.columns
        ),
        None,
    )

    if (
        "credential_id" in cw.columns
        and lineage_col
    ):

        m = cw["credential_id"].eq(
            "REAL_ESTATE_2025"
        )

        if m.any():

            cw.loc[
                m,
                lineage_col
            ] = NEW

        else:

            row = {
                c: ""
                for c in cw.columns
            }

            row["credential_id"] = (
                "REAL_ESTATE_2025"
            )

            row[lineage_col] = NEW

            cw = pd.concat(
                [
                    cw,
                    pd.DataFrame([row]),
                ],
                ignore_index=True,
            )

        cw.to_csv(
            LINEAGE_CROSSWALK,
            index=False,
        )

        print()
        print(
            "Persistent lineage crosswalk updated:"
        )
        print(LINEAGE_CROSSWALK)

    else:
        print()
        print(
            "WARNING: lineage crosswalk exists but "
            "expected columns were not found; left unchanged."
        )


# =============================================================================
# 4. QA
# =============================================================================

check = pd.read_csv(
    COMPLETE,
    dtype=str,
    low_memory=False,
).fillna("")

cert = check[
    check["credential_id"].eq(
        "REAL_ESTATE_2025"
    )
]

if not cert["canonical_lineage"].eq(NEW).all():
    raise RuntimeError(
        "Real Estate certificate repair failed."
    )

aas = check[
    check["credential_id"].eq(
        "REAL_ESTATE_MANAGEMENT_2025"
    )
]

if (
    len(aas)
    and not aas["canonical_lineage"].eq(AAS).all()
):
    raise RuntimeError(
        "AAS lineage was disturbed."
    )

print()
print("Completion rows changed:", changed)

print()
print("AFTER")
print(
    check.loc[
        check["credential_id"].isin(
            [
                "REAL_ESTATE_2025",
                "REAL_ESTATE_MANAGEMENT_2025",
            ]
        ),
        [
            c for c in [
                "catalog_year",
                "credential_id",
                "mechanical_lineage",
                "canonical_lineage",
            ]
            if c in check.columns
        ],
    ]
    .drop_duplicates()
    .sort_values("credential_id")
    .to_string(index=False)
)

print()
print("Completion backup:")
print(complete_backup)

print()
print("Governance backup:")
print(gov_backup)

print()
print("PASS")
