#!/usr/bin/env python
"""
Build the staged LSCO six-year catalog/audit package.

This is an ASSEMBLY layer, not a parser.

It intentionally does NOT reparse historical catalogs.

Inputs
------
Five-year production baseline:
    data/processed/catalogs/requirements_master_multicatalog.csv
    data/processed/catalogs/requirements_master_multiyear.csv

Controlled 2025 Logistics replacement:
    data/processed/catalogs/controlled_recovery_2025/
        logistics_management_maritime_requirements_overlay.csv
    TEMP_logistics_2025_executable_recovery/
        requirements_master_multiyear_logistics_2025_recovery.csv

Approved staged 2026 catalog:
    data/processed/catalogs/staging_2026/
        requirements_master_2026_staged.csv
        requirements_master_multiyear_2026_staged.csv

Approved staged semantic policies:
    data/processed/catalogs/staging_2026/semantic_policies/

Controlled 2025 Logistics semantic policies:
    data/processed/catalogs/controlled_recovery_2025/

Outputs
-------
    data/processed/catalogs/staging_six_year/
        requirements_master_multicatalog.csv
        requirements_master_multiyear.csv
        semantic_policies/
            ELECTIVE_controlled_semantic_overrides_final.csv
            compound_requirement_alternatives.csv
            alternative_requirement_paths.csv
        runtime_support/
            catalog_academic_course_crosswalk_final.csv
            core_bucket_lookup_multicatalog.csv

Expected integrated package
---------------------------
Source requirements:       6513
Executable option rows:    7132
Credential-years:           520
Elective policy rows:       190
Compound policy rows:        21
Alternative-path rows:       22
Academic crosswalk rows:    2583
Core lookup rows:           2554

The production baseline files are never modified.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

TARGET_2025 = (
    "LOGISTICS_MANAGEMENT_2025"
)

TARGET_2026 = (
    "LOGISTICS_MANAGEMENT_MARITIME_AAS_2026"
)


PROD_SOURCE = Path(
    "data/processed/catalogs/"
    "requirements_master_multicatalog.csv"
)

PROD_EXEC = Path(
    "data/processed/catalogs/"
    "requirements_master_multiyear.csv"
)


REC25_SOURCE = Path(
    "data/processed/catalogs/controlled_recovery_2025/"
    "logistics_management_maritime_requirements_overlay.csv"
)

REC25_EXEC = Path(
    "TEMP_logistics_2025_executable_recovery/"
    "requirements_master_multiyear_logistics_2025_recovery.csv"
)


STAGED26_SOURCE = Path(
    "data/processed/catalogs/staging_2026/"
    "requirements_master_2026_staged.csv"
)

STAGED26_EXEC = Path(
    "data/processed/catalogs/staging_2026/"
    "requirements_master_multiyear_2026_staged.csv"
)


STAGED26_POLICY_DIR = Path(
    "data/processed/catalogs/staging_2026/"
    "semantic_policies"
)

STAGED26_ELECTIVE = (
    STAGED26_POLICY_DIR
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

STAGED26_COMPOUND = (
    STAGED26_POLICY_DIR
    / "compound_requirement_alternatives.csv"
)

STAGED26_PATHS = (
    STAGED26_POLICY_DIR
    / "alternative_requirement_paths.csv"
)


REC25_POLICY_DIR = Path(
    "data/processed/catalogs/"
    "controlled_recovery_2025"
)

REC25_ELECTIVE = (
    REC25_POLICY_DIR
    / "logistics_management_maritime_"
    "elective_runtime_overlay.csv"
)

REC25_COMPOUND = (
    REC25_POLICY_DIR
    / "logistics_management_maritime_"
    "compound_requirement_alternatives.csv"
)

REC25_PATHS = (
    REC25_POLICY_DIR
    / "logistics_management_maritime_"
    "alternative_requirement_paths.csv"
)


HISTORICAL_ACADEMIC_CROSSWALK = Path(
    "config/"
    "catalog_academic_course_crosswalk_final.csv"
)

STAGED26_ACADEMIC_CROSSWALK = Path(
    "data/processed/catalogs/staging_2026/"
    "catalog_academic_course_crosswalk_2026_staged.csv"
)

HISTORICAL_CORE_LOOKUP = Path(
    "config/"
    "core_bucket_lookup_multicatalog.csv"
)

STAGED26_CORE_LOOKUP = Path(
    "data/processed/catalogs/staging_2026/"
    "core_bucket_lookup_2026_staged.csv"
)


OUTPUT_DIR = Path(
    "data/processed/catalogs/"
    "staging_six_year"
)

OUTPUT_POLICY_DIR = (
    OUTPUT_DIR
    / "semantic_policies"
)

OUTPUT_RUNTIME_SUPPORT_DIR = (
    OUTPUT_DIR
    / "runtime_support"
)

OUT_ACADEMIC_CROSSWALK = (
    OUTPUT_RUNTIME_SUPPORT_DIR
    / "catalog_academic_course_crosswalk_final.csv"
)

OUT_CORE_LOOKUP = (
    OUTPUT_RUNTIME_SUPPORT_DIR
    / "core_bucket_lookup_multicatalog.csv"
)

OUT_SOURCE = (
    OUTPUT_DIR
    / "requirements_master_multicatalog.csv"
)

OUT_EXEC = (
    OUTPUT_DIR
    / "requirements_master_multiyear.csv"
)

OUT_ELECTIVE = (
    OUTPUT_POLICY_DIR
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

OUT_COMPOUND = (
    OUTPUT_POLICY_DIR
    / "compound_requirement_alternatives.csv"
)

OUT_PATHS = (
    OUTPUT_POLICY_DIR
    / "alternative_requirement_paths.csv"
)


# ============================================================
# EXPECTED PACKAGE
# ============================================================

EXPECTED_PROD_SOURCE_ROWS = 4849
EXPECTED_PROD_EXEC_ROWS = 5283

EXPECTED_OLD_2025_SOURCE_ROWS = 10
EXPECTED_OLD_2025_EXEC_ROWS = 10

EXPECTED_REC25_SOURCE_ROWS = 26
EXPECTED_REC25_EXEC_ROWS = 34

EXPECTED_2026_SOURCE_ROWS = 1648
EXPECTED_2026_EXEC_ROWS = 1825

EXPECTED_SOURCE_ROWS = 6513
EXPECTED_EXEC_ROWS = 7132
EXPECTED_CREDENTIAL_YEARS = 520

EXPECTED_ELECTIVE_ROWS = 190
EXPECTED_COMPOUND_ROWS = 21
EXPECTED_PATH_ROWS = 22

EXPECTED_HISTORICAL_ACADEMIC_ROWS = 1999
EXPECTED_2026_ACADEMIC_ROWS = 584
EXPECTED_ACADEMIC_ROWS = 2583

EXPECTED_HISTORICAL_CORE_ROWS = 2070
EXPECTED_2026_CORE_ROWS = 484
EXPECTED_CORE_ROWS = 2554

EXPECTED_LOGISTICS_SOURCE_ROWS = 26
EXPECTED_LOGISTICS_EXEC_ROWS = 34
EXPECTED_LOGISTICS_ELECTIVE_ROWS = 1
EXPECTED_LOGISTICS_COMPOUND_ROWS = 7
EXPECTED_LOGISTICS_PATH_ROWS = 11


# ============================================================
# HELPERS
# ============================================================

def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path) -> None:
    if not path.exists():
        fail(
            f"Required file not found: {path}"
        )


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


def file_hash(path: Path) -> str:
    return sha256(
        path.read_bytes()
    ).hexdigest()


def require_same_schema(
    left: pd.DataFrame,
    right: pd.DataFrame,
    label: str,
) -> None:

    if list(left.columns) != list(
        right.columns
    ):
        fail(
            f"{label} schema mismatch."
        )


def credential_year_count(
    frame: pd.DataFrame,
) -> int:

    return (
        frame[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )


def replace_credential_in_place(
    baseline: pd.DataFrame,
    replacement: pd.DataFrame,
    credential_id: str,
    expected_old_rows: int,
    expected_new_rows: int,
    label: str,
) -> pd.DataFrame:
    """
    Replace one contiguous credential block while preserving
    the existing historical row order around it.
    """

    mask = (
        baseline[
            "credential_id"
        ].eq(
            credential_id
        )
    )

    positions = [
        i
        for i, value in enumerate(
            mask.tolist()
        )
        if value
    ]

    if len(positions) != expected_old_rows:
        fail(
            f"{label}: existing {credential_id} "
            f"rows = {len(positions)}; "
            f"expected {expected_old_rows}."
        )

    if len(replacement) != expected_new_rows:
        fail(
            f"{label}: replacement {credential_id} "
            f"rows = {len(replacement)}; "
            f"expected {expected_new_rows}."
        )

    if set(
        replacement[
            "credential_id"
        ]
    ) != {
        credential_id
    }:
        fail(
            f"{label}: replacement contains "
            "unexpected credential IDs."
        )

    expected_positions = list(
        range(
            min(positions),
            max(positions) + 1,
        )
    )

    if positions != expected_positions:
        fail(
            f"{label}: existing credential block "
            "is not contiguous."
        )

    first = min(
        positions
    )

    last = max(
        positions
    )

    before = baseline.iloc[
        :first
    ].copy()

    after = baseline.iloc[
        last + 1:
    ].copy()

    return pd.concat(
        [
            before,
            replacement,
            after,
        ],
        ignore_index=True,
    )


def check_source_master(
    source: pd.DataFrame,
) -> None:

    if len(source) != EXPECTED_SOURCE_ROWS:
        fail(
            f"Combined source rows = "
            f"{len(source)}; expected "
            f"{EXPECTED_SOURCE_ROWS}."
        )

    if credential_year_count(
        source
    ) != EXPECTED_CREDENTIAL_YEARS:
        fail(
            "Combined source credential-year "
            "count mismatch."
        )

    if source[
        "requirement_id"
    ].astype(str).str.strip().eq(
        ""
    ).any():
        fail(
            "Combined source contains blank "
            "requirement IDs."
        )

    duplicate_ids = source[
        "requirement_id"
    ].duplicated(
        keep=False
    )

    if duplicate_ids.any():
        bad = source.loc[
            duplicate_ids,
            [
                "catalog_year",
                "credential_id",
                "requirement_id",
            ],
        ]

        fail(
            "Combined source contains duplicate "
            "requirement IDs:\n"
            + bad.to_string(
                index=False
            )
        )


def check_exec_master(
    executable: pd.DataFrame,
) -> None:

    if len(
        executable
    ) != EXPECTED_EXEC_ROWS:
        fail(
            f"Combined executable rows = "
            f"{len(executable)}; expected "
            f"{EXPECTED_EXEC_ROWS}."
        )

    if credential_year_count(
        executable
    ) != EXPECTED_CREDENTIAL_YEARS:
        fail(
            "Combined executable credential-year "
            "count mismatch."
        )

    for column in [
        "requirement_id",
        "option_value",
    ]:
        if executable[
            column
        ].astype(str).str.strip().eq(
            ""
        ).any():
            fail(
                "Combined executable contains "
                f"blank {column} values."
            )

    key = [
        "catalog_year",
        "credential_id",
        "requirement_id",
        "option_type",
        "option_value",
    ]

    duplicate_options = executable.duplicated(
        subset=key,
        keep=False,
    )

    if duplicate_options.any():
        bad = executable.loc[
            duplicate_options,
            key,
        ]

        fail(
            "Combined executable contains duplicate "
            "option rows:\n"
            + bad.to_string(
                index=False
            )
        )


def check_logistics_package(
    source: pd.DataFrame,
    executable: pd.DataFrame,
    elective: pd.DataFrame,
    compound: pd.DataFrame,
    paths: pd.DataFrame,
    catalog_year: str,
    credential_id: str,
) -> None:

    source_rows = source.loc[
        source[
            "catalog_year"
        ].eq(
            catalog_year
        )
        & source[
            "credential_id"
        ].eq(
            credential_id
        )
    ]

    exec_rows = executable.loc[
        executable[
            "catalog_year"
        ].eq(
            catalog_year
        )
        & executable[
            "credential_id"
        ].eq(
            credential_id
        )
    ]

    elective_rows = elective.loc[
        elective[
            "catalog_year"
        ].eq(
            catalog_year
        )
        & elective[
            "credential_id"
        ].eq(
            credential_id
        )
    ]

    compound_rows = compound.loc[
        compound[
            "catalog_year"
        ].eq(
            catalog_year
        )
        & compound[
            "credential_id"
        ].eq(
            credential_id
        )
    ]

    path_rows = paths.loc[
        paths[
            "catalog_year"
        ].eq(
            catalog_year
        )
        & paths[
            "credential_id"
        ].eq(
            credential_id
        )
    ]

    checks = {
        "source":
            (
                len(source_rows),
                EXPECTED_LOGISTICS_SOURCE_ROWS,
            ),

        "executable":
            (
                len(exec_rows),
                EXPECTED_LOGISTICS_EXEC_ROWS,
            ),

        "elective":
            (
                len(elective_rows),
                EXPECTED_LOGISTICS_ELECTIVE_ROWS,
            ),

        "compound":
            (
                len(compound_rows),
                EXPECTED_LOGISTICS_COMPOUND_ROWS,
            ),

        "paths":
            (
                len(path_rows),
                EXPECTED_LOGISTICS_PATH_ROWS,
            ),
    }

    for label, (
        actual,
        expected,
    ) in checks.items():

        if actual != expected:
            fail(
                f"{credential_id}: {label} rows "
                f"= {actual}; expected {expected}."
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    inputs = [
        PROD_SOURCE,
        PROD_EXEC,
        REC25_SOURCE,
        REC25_EXEC,
        STAGED26_SOURCE,
        STAGED26_EXEC,
        STAGED26_ELECTIVE,
        STAGED26_COMPOUND,
        STAGED26_PATHS,
        REC25_ELECTIVE,
        REC25_COMPOUND,
        REC25_PATHS,
        HISTORICAL_ACADEMIC_CROSSWALK,
        STAGED26_ACADEMIC_CROSSWALK,
        HISTORICAL_CORE_LOOKUP,
        STAGED26_CORE_LOOKUP,
    ]

    for path in inputs:
        require_file(
            path
        )

    prod_hashes_before = {
        PROD_SOURCE:
            file_hash(
                PROD_SOURCE
            ),
        PROD_EXEC:
            file_hash(
                PROD_EXEC
            ),
        HISTORICAL_ACADEMIC_CROSSWALK:
            file_hash(
                HISTORICAL_ACADEMIC_CROSSWALK
            ),
        HISTORICAL_CORE_LOOKUP:
            file_hash(
                HISTORICAL_CORE_LOOKUP
            ),
    }

    prod_source = read_csv(
        PROD_SOURCE
    )

    prod_exec = read_csv(
        PROD_EXEC
    )

    rec25_source = read_csv(
        REC25_SOURCE
    )

    rec25_exec = read_csv(
        REC25_EXEC
    )

    source26 = read_csv(
        STAGED26_SOURCE
    )

    exec26 = read_csv(
        STAGED26_EXEC
    )

    staged_elective = read_csv(
        STAGED26_ELECTIVE
    )

    staged_compound = read_csv(
        STAGED26_COMPOUND
    )

    staged_paths = read_csv(
        STAGED26_PATHS
    )

    rec25_elective = read_csv(
        REC25_ELECTIVE
    )

    rec25_compound = read_csv(
        REC25_COMPOUND
    )

    rec25_paths = read_csv(
        REC25_PATHS
    )

    historical_academic = read_csv(
        HISTORICAL_ACADEMIC_CROSSWALK
    )

    academic26 = read_csv(
        STAGED26_ACADEMIC_CROSSWALK
    )

    historical_core = read_csv(
        HISTORICAL_CORE_LOOKUP
    )

    core26 = read_csv(
        STAGED26_CORE_LOOKUP
    )


    # --------------------------------------------------------
    # Baseline guards
    # --------------------------------------------------------

    if len(
        prod_source
    ) != EXPECTED_PROD_SOURCE_ROWS:
        fail(
            f"Production source rows = "
            f"{len(prod_source)}; expected "
            f"{EXPECTED_PROD_SOURCE_ROWS}."
        )

    if len(
        prod_exec
    ) != EXPECTED_PROD_EXEC_ROWS:
        fail(
            f"Production executable rows = "
            f"{len(prod_exec)}; expected "
            f"{EXPECTED_PROD_EXEC_ROWS}."
        )

    if "2026-2027" in set(
        prod_source[
            "catalog_year"
        ]
    ):
        fail(
            "Production source already contains "
            "2026-2027."
        )

    if "2026-2027" in set(
        prod_exec[
            "catalog_year"
        ]
    ):
        fail(
            "Production executable already contains "
            "2026-2027."
        )


    # --------------------------------------------------------
    # Schema guards
    # --------------------------------------------------------

    require_same_schema(
        prod_source,
        rec25_source,
        "2025 source recovery",
    )

    require_same_schema(
        prod_source,
        source26,
        "2026 staged source",
    )

    require_same_schema(
        prod_exec,
        rec25_exec,
        "2025 executable recovery",
    )

    require_same_schema(
        prod_exec,
        exec26,
        "2026 staged executable",
    )

    require_same_schema(
        staged_elective,
        rec25_elective,
        "2025 elective policy",
    )

    require_same_schema(
        staged_compound,
        rec25_compound,
        "2025 compound policy",
    )

    require_same_schema(
        staged_paths,
        rec25_paths,
        "2025 alternative-path policy",
    )


    # --------------------------------------------------------
    # Input count guards
    # --------------------------------------------------------

    if len(
        rec25_source
    ) != EXPECTED_REC25_SOURCE_ROWS:
        fail(
            "2025 recovered source row count changed."
        )

    if len(
        rec25_exec
    ) != EXPECTED_REC25_EXEC_ROWS:
        fail(
            "2025 recovered executable row count changed."
        )

    if len(
        source26
    ) != EXPECTED_2026_SOURCE_ROWS:
        fail(
            "2026 staged source row count changed."
        )

    if len(
        exec26
    ) != EXPECTED_2026_EXEC_ROWS:
        fail(
            "2026 staged executable row count changed."
        )

    if set(
        source26[
            "catalog_year"
        ]
    ) != {
        "2026-2027"
    }:
        fail(
            "2026 staged source contains "
            "unexpected catalog years."
        )

    if set(
        exec26[
            "catalog_year"
        ]
    ) != {
        "2026-2027"
    }:
        fail(
            "2026 staged executable contains "
            "unexpected catalog years."
        )

    require_same_schema(
        historical_academic,
        academic26,
        "2026 academic crosswalk",
    )

    require_same_schema(
        historical_core,
        core26,
        "2026 core lookup",
    )

    if len(
        historical_academic
    ) != EXPECTED_HISTORICAL_ACADEMIC_ROWS:
        fail(
            "Historical academic crosswalk row "
            "count changed."
        )

    if len(
        academic26
    ) != EXPECTED_2026_ACADEMIC_ROWS:
        fail(
            "2026 academic crosswalk row "
            "count changed."
        )

    if len(
        historical_core
    ) != EXPECTED_HISTORICAL_CORE_ROWS:
        fail(
            "Historical core lookup row "
            "count changed."
        )

    if len(
        core26
    ) != EXPECTED_2026_CORE_ROWS:
        fail(
            "2026 core lookup row "
            "count changed."
        )

    historical_years = {
        "2021-2022",
        "2022-2023",
        "2023-2024",
        "2024-2025",
        "2025-2026",
    }

    if set(
        historical_academic[
            "catalog_year"
        ]
    ) != historical_years:
        fail(
            "Historical academic crosswalk "
            "catalog-year universe changed."
        )

    if set(
        academic26[
            "catalog_year"
        ]
    ) != {
        "2026-2027"
    }:
        fail(
            "2026 academic crosswalk contains "
            "unexpected catalog years."
        )

    if set(
        historical_core[
            "catalog_year"
        ]
    ) != historical_years:
        fail(
            "Historical core lookup "
            "catalog-year universe changed."
        )

    if set(
        core26[
            "catalog_year"
        ]
    ) != {
        "2026-2027"
    }:
        fail(
            "2026 core lookup contains "
            "unexpected catalog years."
        )


    # --------------------------------------------------------
    # Replace defective 2025 Logistics in-place
    # --------------------------------------------------------

    source_repaired = (
        replace_credential_in_place(
            prod_source,
            rec25_source,
            TARGET_2025,
            EXPECTED_OLD_2025_SOURCE_ROWS,
            EXPECTED_REC25_SOURCE_ROWS,
            "Source master",
        )
    )

    exec_repaired = (
        replace_credential_in_place(
            prod_exec,
            rec25_exec,
            TARGET_2025,
            EXPECTED_OLD_2025_EXEC_ROWS,
            EXPECTED_REC25_EXEC_ROWS,
            "Executable master",
        )
    )


    # --------------------------------------------------------
    # Append independent 2026 snapshot
    # --------------------------------------------------------

    source = pd.concat(
        [
            source_repaired,
            source26,
        ],
        ignore_index=True,
    )

    executable = pd.concat(
        [
            exec_repaired,
            exec26,
        ],
        ignore_index=True,
    )


    # --------------------------------------------------------
    # Semantic policies
    #
    # staging_2026 already contains all historical policies
    # plus all approved 2026 additions.
    #
    # Add only the newly recovered 2025 Logistics policies.
    # --------------------------------------------------------

    elective = pd.concat(
        [
            staged_elective,
            rec25_elective,
        ],
        ignore_index=True,
    )

    compound = pd.concat(
        [
            staged_compound,
            rec25_compound,
        ],
        ignore_index=True,
    )

    paths = pd.concat(
        [
            staged_paths,
            rec25_paths,
        ],
        ignore_index=True,
    )

    academic_crosswalk = pd.concat(
        [
            historical_academic,
            academic26,
        ],
        ignore_index=True,
    )

    core_lookup = pd.concat(
        [
            historical_core,
            core26,
        ],
        ignore_index=True,
    )


    # --------------------------------------------------------
    # Master validation
    # --------------------------------------------------------

    check_source_master(
        source
    )

    check_exec_master(
        executable
    )

    source_universe = set(
        map(
            tuple,
            source[
                [
                    "catalog_year",
                    "credential_id",
                ]
            ]
            .drop_duplicates()
            .values,
        )
    )

    exec_universe = set(
        map(
            tuple,
            executable[
                [
                    "catalog_year",
                    "credential_id",
                ]
            ]
            .drop_duplicates()
            .values,
        )
    )

    if (
        source_universe
        != exec_universe
    ):
        fail(
            "Source and executable credential-year "
            "universes differ."
        )


    # --------------------------------------------------------
    # Policy validation
    # --------------------------------------------------------

    if len(
        elective
    ) != EXPECTED_ELECTIVE_ROWS:
        fail(
            f"Elective rows = {len(elective)}; "
            f"expected {EXPECTED_ELECTIVE_ROWS}."
        )

    if len(
        compound
    ) != EXPECTED_COMPOUND_ROWS:
        fail(
            f"Compound rows = {len(compound)}; "
            f"expected {EXPECTED_COMPOUND_ROWS}."
        )

    if len(
        paths
    ) != EXPECTED_PATH_ROWS:
        fail(
            f"Path rows = {len(paths)}; "
            f"expected {EXPECTED_PATH_ROWS}."
        )

    if elective[
        "requirement_id"
    ].astype(str).str.strip().duplicated().any():
        fail(
            "Elective policies contain duplicate "
            "requirement IDs."
        )

    if compound.duplicated().any():
        fail(
            "Compound policies contain duplicate rows."
        )

    if paths.duplicated().any():
        fail(
            "Alternative-path policies contain "
            "duplicate rows."
        )

    executable_requirement_ids = set(
        executable[
            "requirement_id"
        ]
        .astype(str)
        .str.strip()
    )

    for label, frame in [
        (
            "elective",
            elective,
        ),
        (
            "compound",
            compound,
        ),
        (
            "path",
            paths,
        ),
    ]:

        dangling = sorted(
            set(
                frame[
                    "requirement_id"
                ]
                .astype(str)
                .str.strip()
            )
            - executable_requirement_ids
        )

        if dangling:
            fail(
                f"{label} policies contain dangling "
                f"requirement IDs: {dangling[:20]}"
            )


    # --------------------------------------------------------
    # Runtime-support validation
    # --------------------------------------------------------

    if len(
        academic_crosswalk
    ) != EXPECTED_ACADEMIC_ROWS:
        fail(
            f"Academic crosswalk rows = "
            f"{len(academic_crosswalk)}; expected "
            f"{EXPECTED_ACADEMIC_ROWS}."
        )

    if len(
        core_lookup
    ) != EXPECTED_CORE_ROWS:
        fail(
            f"Core lookup rows = "
            f"{len(core_lookup)}; expected "
            f"{EXPECTED_CORE_ROWS}."
        )

    if academic_crosswalk.duplicated().any():
        fail(
            "Academic crosswalk contains duplicate "
            "full rows."
        )

    if core_lookup.duplicated().any():
        fail(
            "Core lookup contains duplicate full rows."
        )

    expected_years = {
        "2021-2022",
        "2022-2023",
        "2023-2024",
        "2024-2025",
        "2025-2026",
        "2026-2027",
    }

    if set(
        academic_crosswalk[
            "catalog_year"
        ]
    ) != expected_years:
        fail(
            "Academic crosswalk does not contain "
            "exactly six catalog years."
        )

    if set(
        core_lookup[
            "catalog_year"
        ]
    ) != expected_years:
        fail(
            "Core lookup does not contain "
            "exactly six catalog years."
        )


    # --------------------------------------------------------
    # Both Logistics snapshots must be structurally complete
    # --------------------------------------------------------

    check_logistics_package(
        source,
        executable,
        elective,
        compound,
        paths,
        "2025-2026",
        TARGET_2025,
    )

    check_logistics_package(
        source,
        executable,
        elective,
        compound,
        paths,
        "2026-2027",
        TARGET_2026,
    )


    # --------------------------------------------------------
    # Write staging only
    # --------------------------------------------------------

    OUTPUT_POLICY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_RUNTIME_SUPPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    source.to_csv(
        OUT_SOURCE,
        index=False,
    )

    executable.to_csv(
        OUT_EXEC,
        index=False,
    )

    elective.to_csv(
        OUT_ELECTIVE,
        index=False,
    )

    compound.to_csv(
        OUT_COMPOUND,
        index=False,
    )

    paths.to_csv(
        OUT_PATHS,
        index=False,
    )

    academic_crosswalk.to_csv(
        OUT_ACADEMIC_CROSSWALK,
        index=False,
    )

    core_lookup.to_csv(
        OUT_CORE_LOOKUP,
        index=False,
    )


    # --------------------------------------------------------
    # Confirm production immutability
    # --------------------------------------------------------

    prod_hashes_after = {
        PROD_SOURCE:
            file_hash(
                PROD_SOURCE
            ),
        PROD_EXEC:
            file_hash(
                PROD_EXEC
            ),
        HISTORICAL_ACADEMIC_CROSSWALK:
            file_hash(
                HISTORICAL_ACADEMIC_CROSSWALK
            ),
        HISTORICAL_CORE_LOOKUP:
            file_hash(
                HISTORICAL_CORE_LOOKUP
            ),
    }

    changed = [
        str(path)
        for path in prod_hashes_before
        if (
            prod_hashes_before[path]
            != prod_hashes_after[path]
        )
    ]

    if changed:
        fail(
            "Production baseline changed: "
            + ", ".join(
                changed
            )
        )


    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print("=" * 80)
    print(
        "SIX-YEAR CATALOG PACKAGE ? STAGED ASSEMBLY"
    )
    print("=" * 80)

    print()
    print(
        "SOURCE ROWS:",
        len(source),
    )
    print(
        "EXECUTABLE ROWS:",
        len(executable),
    )
    print(
        "CREDENTIAL-YEARS:",
        credential_year_count(
            source
        ),
    )

    print()
    print(
        "ELECTIVE POLICY ROWS:",
        len(elective),
    )
    print(
        "COMPOUND POLICY ROWS:",
        len(compound),
    )
    print(
        "ALTERNATIVE PATH ROWS:",
        len(paths),
    )

    print()
    print(
        "ACADEMIC CROSSWALK ROWS:",
        len(academic_crosswalk),
    )
    print(
        "CORE LOOKUP ROWS:",
        len(core_lookup),
    )

    print()
    print(
        "PASS: 2025 Logistics replaced in-place"
    )
    print(
        "PASS: 2026 independent snapshot appended"
    )
    print(
        "PASS: source requirement IDs unique"
    )
    print(
        "PASS: executable option rows unique"
    )
    print(
        "PASS: credential-year universes match"
    )
    print(
        "PASS: semantic policies resolve to "
        "executable requirements"
    )
    print(
        "PASS: 2025 Logistics semantic package complete"
    )
    print(
        "PASS: 2026 Logistics semantic package complete"
    )
    print(
        "PASS: six-year academic crosswalk assembled"
    )
    print(
        "PASS: six-year core lookup assembled"
    )
    print(
        "PASS: production masters byte-identical"
    )

    print()
    print(
        "WROTE:",
        OUT_SOURCE,
    )
    print(
        "WROTE:",
        OUT_EXEC,
    )
    print(
        "WROTE:",
        OUT_ELECTIVE,
    )
    print(
        "WROTE:",
        OUT_COMPOUND,
    )
    print(
        "WROTE:",
        OUT_PATHS,
    )
    print(
        "WROTE:",
        OUT_ACADEMIC_CROSSWALK,
    )
    print(
        "WROTE:",
        OUT_CORE_LOOKUP,
    )

    print()
    print(
        "PRODUCTION FILES MODIFIED: NO"
    )


if __name__ == "__main__":
    main()
