#!/usr/bin/env python
"""
Build isolated staged semantic-policy files for LSCO 2026-2027.

This script DOES NOT modify production semantic-policy files.

Inputs:
- historical compound_requirement_alternatives.csv
- 2026 Logistics Management (Maritime) compound overlay
- 2026 Logistics Management (Maritime) alternative-path policy
- historical controlled elective rules
- 2026 Logistics Management (Maritime) elective runtime overlay
- staged 2026 executable requirements

Outputs:
    data/processed/catalogs/staging_2026/semantic_policies/
        compound_requirement_alternatives.csv
        alternative_requirement_paths.csv
        ELECTIVE_controlled_semantic_overrides_final.csv

Expected:
- compound rows: 14
- alternative-path rows: 11
- elective rows: 189
- no requirement-ID collisions during merges
- no duplicate policy rows
- no dangling 2026 Logistics requirement IDs
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


LOGISTICS_CREDENTIAL = (
    "LOGISTICS_MANAGEMENT_MARITIME_AAS_2026"
)

STAGED_EXECUTABLE = Path(
    "data/processed/catalogs/staging_2026/"
    "requirements_master_multiyear_2026_staged.csv"
)

GLOBAL_COMPOUND = Path(
    "data/processed/catalogs/semantic_policies/"
    "compound_requirement_alternatives.csv"
)

NEW_COMPOUND = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_"
    "compound_requirement_alternatives.csv"
)

NEW_PATHS = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_"
    "alternative_requirement_paths.csv"
)

GLOBAL_ELECTIVE = Path(
    "data/processed/full_actual_audit/evidence/"
    "rule_logic_review/"
    "ELECTIVE_controlled_semantic_overrides_final.csv"
)

NEW_ELECTIVE = Path(
    "data/processed/catalogs/controlled_recovery_2026/"
    "logistics_management_maritime_"
    "elective_runtime_overlay.csv"
)

OUTPUT_DIR = Path(
    "data/processed/catalogs/staging_2026/"
    "semantic_policies"
)

OUT_COMPOUND = (
    OUTPUT_DIR
    / "compound_requirement_alternatives.csv"
)

OUT_PATHS = (
    OUTPUT_DIR
    / "alternative_requirement_paths.csv"
)

OUT_ELECTIVE = (
    OUTPUT_DIR
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

EXPECTED_COMPOUND_ROWS = 14
EXPECTED_PATH_ROWS = 11
EXPECTED_ELECTIVE_ROWS = 189


def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path) -> None:
    if not path.exists():
        fail(f"Required file not found: {path}")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


def require_column(
    frame: pd.DataFrame,
    column: str,
    label: str,
) -> None:
    if column not in frame.columns:
        fail(
            f"{label} missing required column: "
            f"{column}"
        )


def normalized_ids(
    frame: pd.DataFrame,
) -> set[str]:
    return set(
        frame["requirement_id"]
        .astype(str)
        .str.strip()
    )


def check_no_blank_ids(
    frame: pd.DataFrame,
    label: str,
) -> None:
    blank = (
        frame["requirement_id"]
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    if blank:
        fail(
            f"{label} contains {blank} blank "
            "requirement IDs."
        )



INHERITED_DIAGNOSTIC_FIELDS = [
    "unresolved_rows_rechecked",
    "distinct_students",
    "safe_now_satisfied",
    "permissive_now_satisfied",
    "still_unmet_or_semantic_review",
    "maximum_eligible_course_count",
    "average_eligible_course_count",
    "review_text",
    "review_priority",
    "unresolved_rows_rechecked_num",
    "safe_now_satisfied_num",
]


PLANT_REQUIREMENT_ID = (
    "PLANT_SCIENCE_MANAGEMENT_2026_R4_3"
)

ANIMAL_REQUIREMENT_ID = (
    "ANIMAL_SCIENCE_MANAGEMENT_2026_R4_3"
)

LOGISTICS_ELECTIVE_REQUIREMENT_ID = (
    f"{LOGISTICS_CREDENTIAL}_R19"
)

PLANT_APPROVED_RUBRICS = (
    "ACCT | ACNT | AGAH | AGCR | AGMG | "
    "BMGT | BUSG | BUSI | MRKG"
)

PLANT_OVERRIDE_REASON = (
    "Human review approved the literal union of Business, "
    "Animal Science, and Agribusiness elective rubrics for "
    "Plant Science Management: "
    "ACCT | ACNT | AGAH | AGCR | AGMG | BMGT | BUSG | "
    "BUSI | MRKG."
)


def build_2026_inherited_elective_rows(
    executable: pd.DataFrame,
    historical_elective: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    current = executable.loc[
        executable["catalog_year"].eq(
            "2026-2027"
        )
        & executable["rule_type"].eq(
            "ELECTIVE"
        )
    ].copy()

    if len(current) != 31:
        fail(
            "Staged executable contains "
            f"{len(current)} 2026 elective rows; expected 31."
        )

    if current["requirement_id"].duplicated().any():
        fail(
            "Staged executable contains duplicate "
            "2026 elective requirement IDs."
        )

    inherited_rows = []

    for _, source_row in current.iterrows():

        requirement_id = str(
            source_row["requirement_id"]
        ).strip()

        if requirement_id in {
            LOGISTICS_ELECTIVE_REQUIREMENT_ID,
            PLANT_REQUIREMENT_ID,
        }:
            continue

        credential_id = str(
            source_row["credential_id"]
        ).strip()

        if not credential_id.endswith(
            "_2026"
        ):
            fail(
                "Cannot derive 2025 elective predecessor "
                f"for credential {credential_id}."
            )

        if not requirement_id.startswith(
            credential_id
        ):
            fail(
                "Requirement ID does not begin with "
                f"credential ID: {requirement_id}"
            )

        predecessor_credential = (
            credential_id[:-5]
            + "_2025"
        )

        requirement_suffix = requirement_id[
            len(credential_id):
        ]

        predecessor_requirement = (
            predecessor_credential
            + requirement_suffix
        )

        predecessor = historical_elective.loc[
            historical_elective[
                "requirement_id"
            ].astype(str).str.strip().eq(
                predecessor_requirement
            )
        ]

        if len(predecessor) != 1:
            fail(
                "Expected exactly one 2025 elective "
                "predecessor for "
                f"{requirement_id}; found {len(predecessor)}."
            )

        prior = predecessor.iloc[0].copy()

        if str(
            prior["credential_title"]
        ).strip() != str(
            source_row["credential_title"]
        ).strip():
            fail(
                "Credential-title continuity failed for "
                f"{requirement_id}."
            )

        if str(
            prior["source_requirement_text"]
        ).strip() != str(
            source_row["source_requirement_text"]
        ).strip():
            fail(
                "Source elective wording changed for "
                f"{requirement_id}."
            )

        try:
            prior_hours = float(
                str(
                    prior["credit_hours_values"]
                ).strip()
            )

            current_hours = float(
                str(
                    source_row["credit_hours"]
                ).strip()
            )

        except ValueError as exc:
            fail(
                "Non-numeric elective credit hours for "
                f"{requirement_id}: {exc}"
            )

        if prior_hours != current_hours:
            fail(
                "Elective credit-hour continuity failed for "
                f"{requirement_id}: "
                f"{prior_hours} != {current_hours}."
            )

        if str(
            prior["rule_type"]
        ).strip() != "ELECTIVE":
            fail(
                "Historical predecessor is not ELECTIVE: "
                f"{predecessor_requirement}"
            )

        inherited = prior.copy()

        inherited["catalog_year"] = (
            "2026-2027"
        )

        inherited["credential_id"] = (
            credential_id
        )

        inherited["credential_title"] = (
            str(
                source_row[
                    "credential_title"
                ]
            ).strip()
        )

        inherited["requirement_id"] = (
            requirement_id
        )

        for field in (
            INHERITED_DIAGNOSTIC_FIELDS
        ):
            if field not in inherited.index:
                fail(
                    "Historical elective schema missing "
                    f"diagnostic field {field}."
                )

            inherited[field] = ""

        inherited_rows.append(
            inherited
        )

    if len(inherited_rows) != 29:
        fail(
            "Inherited 2026 elective row count is "
            f"{len(inherited_rows)}; expected 29."
        )

    inherited = pd.DataFrame(
        inherited_rows,
        columns=historical_elective.columns,
    )

    if inherited[
        "requirement_id"
    ].duplicated().any():
        fail(
            "Inherited 2026 elective policies contain "
            "duplicate requirement IDs."
        )

    animal = inherited.loc[
        inherited[
            "requirement_id"
        ].eq(
            ANIMAL_REQUIREMENT_ID
        )
    ]

    if len(animal) != 1:
        fail(
            "Expected exactly one inherited 2026 "
            "Animal Science policy."
        )

    plant_source = current.loc[
        current[
            "requirement_id"
        ].eq(
            PLANT_REQUIREMENT_ID
        )
    ]

    if len(plant_source) != 1:
        fail(
            "Expected exactly one 2026 Plant Science "
            "elective requirement."
        )

    animal = animal.iloc[0]
    plant_source = plant_source.iloc[0]

    if str(
        animal["source_requirement_text"]
    ).strip() != str(
        plant_source[
            "source_requirement_text"
        ]
    ).strip():
        fail(
            "Plant Science and Animal Science "
            "elective wording no longer matches."
        )

    try:
        animal_hours = float(
            str(
                animal[
                    "credit_hours_values"
                ]
            ).strip()
        )

        plant_hours = float(
            str(
                plant_source[
                    "credit_hours"
                ]
            ).strip()
        )

    except ValueError as exc:
        fail(
            "Invalid Plant/Animal elective hours: "
            f"{exc}"
        )

    if animal_hours != plant_hours:
        fail(
            "Plant Science and Animal Science "
            "elective hours no longer match."
        )

    if str(
        animal[
            "allowed_rubrics_override"
        ]
    ).strip() != PLANT_APPROVED_RUBRICS:
        fail(
            "Inherited Animal Science rubric policy "
            "no longer matches the human-approved "
            "Plant Science literal union."
        )

    if str(
        animal[
            "controlled_class"
        ]
    ).strip() != "RUBRIC_RESTRICTED":
        fail(
            "Inherited Animal Science controlled class "
            "changed unexpectedly."
        )

    if str(
        animal[
            "resolution_policy"
        ]
    ).strip() != (
        "COUNT_UNUSED_PASSED_ALLOWED_RUBRIC"
    ):
        fail(
            "Inherited Animal Science resolution "
            "policy changed unexpectedly."
        )

    plant = animal.copy()

    plant["catalog_year"] = (
        "2026-2027"
    )

    plant["credential_id"] = str(
        plant_source[
            "credential_id"
        ]
    ).strip()

    plant["credential_title"] = str(
        plant_source[
            "credential_title"
        ]
    ).strip()

    plant["requirement_id"] = (
        PLANT_REQUIREMENT_ID
    )

    plant["elective_class"] = (
        "RUBRIC_RESTRICTED"
    )

    plant["issue_flags"] = (
        "HUMAN_REVIEW_CONFIRMED_2026;"
        "NEW_CREDENTIAL_ELECTIVE_POLICY"
    )

    plant[
        "classification_confidence"
    ] = "HIGH"

    plant["override_reason"] = (
        PLANT_OVERRIDE_REASON
    )

    plant_frame = pd.DataFrame(
        [plant],
        columns=historical_elective.columns,
    )

    return (
        inherited,
        plant_frame,
    )


def main() -> None:
    for path in [
        STAGED_EXECUTABLE,
        GLOBAL_COMPOUND,
        NEW_COMPOUND,
        NEW_PATHS,
        GLOBAL_ELECTIVE,
        NEW_ELECTIVE,
    ]:
        require_file(path)

    executable = read_csv(
        STAGED_EXECUTABLE
    )

    historical_compound = read_csv(
        GLOBAL_COMPOUND
    )

    new_compound = read_csv(
        NEW_COMPOUND
    )

    new_paths = read_csv(
        NEW_PATHS
    )

    historical_elective = read_csv(
        GLOBAL_ELECTIVE
    )

    new_elective = read_csv(
        NEW_ELECTIVE
    )

    for label, frame in [
        (
            "staged executable",
            executable,
        ),
        (
            "historical compound",
            historical_compound,
        ),
        (
            "new compound",
            new_compound,
        ),
        (
            "new alternative paths",
            new_paths,
        ),
        (
            "historical elective",
            historical_elective,
        ),
        (
            "new elective",
            new_elective,
        ),
    ]:
        require_column(
            frame,
            "requirement_id",
            label,
        )

        check_no_blank_ids(
            frame,
            label,
        )

    if list(
        historical_compound.columns
    ) != list(
        new_compound.columns
    ):
        fail(
            "Compound policy schema mismatch."
        )

    if list(
        historical_elective.columns
    ) != list(
        new_elective.columns
    ):
        fail(
            "Elective policy schema mismatch."
        )

    compound_collisions = sorted(
        normalized_ids(
            historical_compound
        )
        & normalized_ids(
            new_compound
        )
    )

    if compound_collisions:
        fail(
            "Compound requirement-ID collisions: "
            f"{compound_collisions}"
        )

    elective_collisions = sorted(
        normalized_ids(
            historical_elective
        )
        & normalized_ids(
            new_elective
        )
    )

    if elective_collisions:
        fail(
            "Elective requirement-ID collisions: "
            f"{elective_collisions}"
        )

    compound = pd.concat(
        [
            historical_compound,
            new_compound,
        ],
        ignore_index=True,
    )

    (
        inherited_elective,
        plant_elective,
    ) = build_2026_inherited_elective_rows(
        executable,
        historical_elective,
    )

    elective = pd.concat(
        [
            historical_elective,
            new_elective,
            inherited_elective,
            plant_elective,
        ],
        ignore_index=True,
    )

    paths = new_paths.copy()

    if len(compound) != EXPECTED_COMPOUND_ROWS:
        fail(
            f"Compound staged row count is "
            f"{len(compound)}; expected "
            f"{EXPECTED_COMPOUND_ROWS}."
        )

    if len(paths) != EXPECTED_PATH_ROWS:
        fail(
            f"Alternative-path staged row count is "
            f"{len(paths)}; expected "
            f"{EXPECTED_PATH_ROWS}."
        )

    if len(elective) != EXPECTED_ELECTIVE_ROWS:
        fail(
            f"Elective staged row count is "
            f"{len(elective)}; expected "
            f"{EXPECTED_ELECTIVE_ROWS}."
        )

    elective_requirement_duplicates = (
        elective[
            "requirement_id"
        ]
        .astype(str)
        .str.strip()
        .duplicated()
        .sum()
    )

    if elective_requirement_duplicates:
        fail(
            "Elective staged policy contains "
            f"{elective_requirement_duplicates} duplicate "
            "requirement IDs."
        )

    source_2026_elective_ids = set(
        executable.loc[
            executable[
                "catalog_year"
            ].eq(
                "2026-2027"
            )
            & executable[
                "rule_type"
            ].eq(
                "ELECTIVE"
            ),
            "requirement_id",
        ]
        .astype(str)
        .str.strip()
    )

    staged_2026_elective_ids = set(
        elective.loc[
            elective[
                "catalog_year"
            ].eq(
                "2026-2027"
            ),
            "requirement_id",
        ]
        .astype(str)
        .str.strip()
    )

    if len(
        source_2026_elective_ids
    ) != 31:
        fail(
            "Staged executable 2026 elective universe "
            f"contains {len(source_2026_elective_ids)} "
            "requirement IDs; expected 31."
        )

    if (
        staged_2026_elective_ids
        != source_2026_elective_ids
    ):
        missing = sorted(
            source_2026_elective_ids
            - staged_2026_elective_ids
        )

        extra = sorted(
            staged_2026_elective_ids
            - source_2026_elective_ids
        )

        fail(
            "2026 elective policy coverage mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    compound_duplicate_rows = (
        compound.duplicated().sum()
    )

    if compound_duplicate_rows:
        fail(
            "Compound staged policy contains "
            f"{compound_duplicate_rows} duplicate rows."
        )

    path_duplicate_rows = (
        paths.duplicated().sum()
    )

    if path_duplicate_rows:
        fail(
            "Alternative-path staged policy contains "
            f"{path_duplicate_rows} duplicate rows."
        )

    elective_duplicate_rows = (
        elective.duplicated().sum()
    )

    if elective_duplicate_rows:
        fail(
            "Elective staged policy contains "
            f"{elective_duplicate_rows} duplicate rows."
        )

    new_compound_ids = normalized_ids(
        new_compound
    )

    new_path_ids = normalized_ids(
        new_paths
    )

    new_elective_ids = normalized_ids(
        new_elective
    )

    expected_path_ids = {
        f"{LOGISTICS_CREDENTIAL}_R{i}"
        for i in range(16, 27)
    }

    if new_path_ids != expected_path_ids:
        fail(
            "Alternative-path membership is not "
            "exactly Logistics R16-R26."
        )

    if new_compound_ids != {
        f"{LOGISTICS_CREDENTIAL}_R26"
    }:
        fail(
            "New compound policy is not isolated "
            "to Logistics R26."
        )

    if new_elective_ids != {
        f"{LOGISTICS_CREDENTIAL}_R19"
    }:
        fail(
            "New elective policy is not isolated "
            "to Logistics R19."
        )

    executable_logistics_ids = set(
        executable.loc[
            executable["credential_id"].eq(
                LOGISTICS_CREDENTIAL
            ),
            "requirement_id",
        ]
        .astype(str)
        .str.strip()
    )

    all_new_policy_ids = (
        new_compound_ids
        | new_path_ids
        | new_elective_ids
    )

    dangling = sorted(
        all_new_policy_ids
        - executable_logistics_ids
    )

    if dangling:
        fail(
            "2026 Logistics semantic policies "
            "contain dangling requirement IDs: "
            f"{dangling}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    compound.to_csv(
        OUT_COMPOUND,
        index=False,
    )

    paths.to_csv(
        OUT_PATHS,
        index=False,
    )

    elective.to_csv(
        OUT_ELECTIVE,
        index=False,
    )

    print(
        f"Wrote staged compound policy: "
        f"{OUT_COMPOUND}"
    )
    print(
        "ROWS:",
        len(compound),
    )

    print()
    print(
        f"Wrote staged alternative-path policy: "
        f"{OUT_PATHS}"
    )
    print(
        "ROWS:",
        len(paths),
    )

    print()
    print(
        f"Wrote staged elective policy: "
        f"{OUT_ELECTIVE}"
    )
    print(
        "ROWS:",
        len(elective),
    )

    print()
    print(
        "PASS: compound schemas identical"
    )
    print(
        "PASS: elective schemas identical"
    )
    print(
        "PASS: inherited 2026 elective policies = 29"
    )
    print(
        "PASS: Plant Science human-reviewed policy = 1"
    )
    print(
        "PASS: 2026 elective policy coverage = 31/31"
    )
    print(
        "PASS: no merge requirement-ID collisions"
    )
    print(
        "PASS: no duplicate policy rows"
    )
    print(
        "PASS: Logistics path membership = R16-R26"
    )
    print(
        "PASS: Logistics compound policy = R26"
    )
    print(
        "PASS: Logistics elective policy = R19"
    )
    print(
        "PASS: no dangling Logistics policy IDs"
    )

    print()
    print(
        "PRODUCTION SEMANTIC POLICIES MODIFIED: NO"
    )


if __name__ == "__main__":
    main()