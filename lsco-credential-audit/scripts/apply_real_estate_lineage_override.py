from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd


SELECTOR = Path("scripts/select_maximum_awards.py")
CROSSWALK = Path(
    "data/processed/reporting/credential_lineage_crosswalk.csv"
)

OVERRIDE_CREDENTIAL_ID = "REAL_ESTATE_MANAGEMENT_2025"
OVERRIDE_LINEAGE = "BUSINESS_REAL_ESTATE_MANAGEMENT"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def patch_selector() -> None:
    if not SELECTOR.exists():
        raise FileNotFoundError(SELECTOR)

    text = SELECTOR.read_text(encoding="utf-8")

    backup = SELECTOR.with_suffix(
        SELECTOR.suffix + f".before_real_estate_{STAMP}.bak"
    )
    shutil.copy2(SELECTOR, backup)

    old_paths = '''CATALOG_REGISTRY_PATH = Path("config/catalogs.csv")

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
'''

    new_paths = '''CATALOG_REGISTRY_PATH = Path("config/catalogs.csv")
LINEAGE_CROSSWALK_PATH = Path(
    "data/processed/reporting/credential_lineage_crosswalk.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
'''

    if "LINEAGE_CROSSWALK_PATH" not in text:
        if old_paths not in text:
            raise RuntimeError(
                "Could not find the selector path block to patch."
            )
        text = text.replace(old_paths, new_paths, 1)

    old_lineage = '''    combos = complete.merge(eligible_pairs, on=["student_id", "catalog_year"], how="inner")
    combos["credential_lineage"] = combos["credential_id"].map(derive_lineage)
    combos["catalog_rank"] = combos["catalog_year"].map(catalog_sort_key)
'''

    new_lineage = '''    combos = complete.merge(eligible_pairs, on=["student_id", "catalog_year"], how="inner")
    combos["derived_credential_lineage"] = combos["credential_id"].map(derive_lineage)

    if LINEAGE_CROSSWALK_PATH.exists():
        lineage_crosswalk = pd.read_csv(
            LINEAGE_CROSSWALK_PATH,
            dtype=str,
            low_memory=False,
        ).fillna("")

        required_crosswalk_columns = {
            "credential_id",
            "credential_lineage",
        }
        missing_crosswalk_columns = (
            required_crosswalk_columns - set(lineage_crosswalk.columns)
        )
        if missing_crosswalk_columns:
            raise SystemExit(
                "Lineage crosswalk is missing columns: "
                + ", ".join(sorted(missing_crosswalk_columns))
            )

        lineage_crosswalk = (
            lineage_crosswalk[
                ["credential_id", "credential_lineage"]
            ]
            .drop_duplicates(subset=["credential_id"])
        )

        combos = combos.merge(
            lineage_crosswalk,
            on="credential_id",
            how="left",
            validate="many_to_one",
        )

        combos["credential_lineage"] = combos[
            "credential_lineage"
        ].where(
            combos["credential_lineage"]
            .astype(str)
            .str.strip()
            .ne(""),
            combos["derived_credential_lineage"],
        )
    else:
        combos["credential_lineage"] = combos[
            "derived_credential_lineage"
        ]

    combos["catalog_rank"] = combos["catalog_year"].map(catalog_sort_key)
'''

    if "derived_credential_lineage" not in text:
        if old_lineage not in text:
            raise RuntimeError(
                "Could not find the selector lineage block to patch."
            )
        text = text.replace(old_lineage, new_lineage, 1)

    SELECTOR.write_text(text, encoding="utf-8")

    print(f"Patched selector: {SELECTOR}")
    print(f"Selector backup: {backup}")


def upsert_crosswalk() -> None:
    CROSSWALK.parent.mkdir(parents=True, exist_ok=True)

    if CROSSWALK.exists():
        crosswalk = pd.read_csv(
            CROSSWALK,
            dtype=str,
            low_memory=False,
        ).fillna("")
    else:
        crosswalk = pd.DataFrame(
            columns=["credential_id", "credential_lineage"]
        )

    required = {"credential_id", "credential_lineage"}
    missing = required - set(crosswalk.columns)
    if missing:
        raise RuntimeError(
            "Existing lineage crosswalk is missing columns: "
            + ", ".join(sorted(missing))
        )

    if CROSSWALK.exists():
        backup = CROSSWALK.with_suffix(
            CROSSWALK.suffix + f".before_real_estate_{STAMP}.bak"
        )
        shutil.copy2(CROSSWALK, backup)
        print(f"Crosswalk backup: {backup}")

    mask = (
        crosswalk["credential_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq(OVERRIDE_CREDENTIAL_ID)
    )

    if mask.any():
        crosswalk.loc[mask, "credential_lineage"] = OVERRIDE_LINEAGE
    else:
        new_row = {
            column: ""
            for column in crosswalk.columns
        }
        new_row["credential_id"] = OVERRIDE_CREDENTIAL_ID
        new_row["credential_lineage"] = OVERRIDE_LINEAGE
        crosswalk = pd.concat(
            [crosswalk, pd.DataFrame([new_row])],
            ignore_index=True,
        )

    duplicate_ids = crosswalk[
        crosswalk["credential_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        .duplicated(keep=False)
    ]

    if not duplicate_ids.empty:
        duplicates = sorted(
            set(
                duplicate_ids["credential_id"]
                .astype(str)
                .tolist()
            )
        )
        raise RuntimeError(
            "Crosswalk contains duplicate credential IDs: "
            + ", ".join(duplicates)
        )

    crosswalk.to_csv(CROSSWALK, index=False)

    check = crosswalk[
        crosswalk["credential_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq(OVERRIDE_CREDENTIAL_ID)
    ]

    if len(check) != 1:
        raise RuntimeError(
            "Real Estate override was not written exactly once."
        )

    actual = str(
        check.iloc[0]["credential_lineage"]
    ).strip().upper()

    if actual != OVERRIDE_LINEAGE:
        raise RuntimeError(
            f"Override validation failed: {actual!r}"
        )

    print(f"Updated crosswalk: {CROSSWALK}")
    print(
        f"Controlled override: {OVERRIDE_CREDENTIAL_ID} "
        f"-> {OVERRIDE_LINEAGE}"
    )


def validate_selector_syntax() -> None:
    source = SELECTOR.read_text(encoding="utf-8")
    compile(source, str(SELECTOR), "exec")
    print("Selector syntax: PASSED")


def main() -> None:
    print("=" * 100)
    print("APPLY REAL ESTATE CREDENTIAL-LINEAGE OVERRIDE")
    print("=" * 100)

    patch_selector()
    upsert_crosswalk()
    validate_selector_syntax()

    print()
    print("PATCH GATE: PASSED")
    print()
    print("Next command:")
    print("python -u .\\scripts\\select_maximum_awards.py")


if __name__ == "__main__":
    main()
