#!/usr/bin/env python
"""
Controlled source recovery: Logistics Management (Maritime) AAS.

RATIONALE
---------
The published curriculum uses a multi-column fourth-semester structure with
two mutually alternative paths. Flattening the table into independent
requirements destroys the catalog semantics.

The generic DOCX parser therefore does not execute this credential.

AUTHORITY
---------
Rendered catalog PDF for the selected catalog year, confirmed by human catalog review.

Published structure:

    Semesters 1-3 common requirements: 46 applied SCH

    Fourth Semester - choose one path:

        Path A, Logistics/CDL: 14 applied SCH

        OR

        Path B, Ordinary Seaman:
            12 applied SCH from the four Ordinary Seaman courses not already
            represented by EDUC 1300 in the common AAS requirements,
            plus one approved supplemental alternative carrying 2 applied SCH.

The supplemental alternatives all represent at least 3 earned SCH. The
catalog nevertheless assigns the requirement 2 SCH so that the published
AAS remains 60 applied SCH. Earned transcript SCH are not altered.

No AI/inference is used at runtime.

This script DOES NOT:
- modify generic parser output;
- modify production requirement masters;
- modify global semantic-policy files;
- modify the audit engine.

It writes controlled candidate artifacts for review and later merge.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import csv


RECOVERY_CONFIGS = {
    "2025-2026": {
        "catalog_year_start": "2025",
        "credential_id": "LOGISTICS_MANAGEMENT_2025",
        "credential_title": "Logistics Management (Maritime)",
        "credential_family": "LOGISTICS_MANAGEMENT",
        "source_file": "2025-2026 Catalog.pdf",
        "source_page": "192",
        "source_table_index": "76",
        "output_dir": (
            "data/processed/catalogs/controlled_recovery_2025"
        ),
        "merge_action": "REPLACE_BASE_CREDENTIAL",
        "recovery_flag": "CONTROLLED_SOURCE_RECOVERY_2025",
    },
    "2026-2027": {
        "catalog_year_start": "2026",
        "credential_id": "LOGISTICS_MANAGEMENT_MARITIME_AAS_2026",
        "credential_title": "Logistics Management (Maritime)",
        "credential_family": "LOGISTICS_MANAGEMENT_MARITIME",
        "source_file": "2026-2027_Catalog.pdf",
        "source_page": "209",
        "source_table_index": "88",
        "output_dir": (
            "data/processed/catalogs/controlled_recovery_2026"
        ),
        "merge_action": "APPEND_MISSING_CREDENTIAL",
        "recovery_flag": "CONTROLLED_SOURCE_RECOVERY_2026",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build controlled Logistics Management "
            "(Maritime) recovery artifacts."
        )
    )
    parser.add_argument(
        "--catalog-year",
        choices=sorted(RECOVERY_CONFIGS),
        default="2026-2027",
        help=(
            "Catalog snapshot to build. Default preserves "
            "the original 2026-2027 behavior."
        ),
    )
    return parser.parse_args()


ARGS = parse_args()
CONFIG = RECOVERY_CONFIGS[ARGS.catalog_year]

CATALOG_YEAR = ARGS.catalog_year
CATALOG_YEAR_START = CONFIG["catalog_year_start"]

CREDENTIAL_ID = CONFIG["credential_id"]
CREDENTIAL_TITLE = CONFIG["credential_title"]
CREDENTIAL_FAMILY = CONFIG["credential_family"]

SOURCE_FILE = CONFIG["source_file"]
SOURCE_PAGE = CONFIG["source_page"]
SOURCE_TABLE_INDEX = CONFIG["source_table_index"]

OUTPUT_DIR = Path(CONFIG["output_dir"])
MERGE_ACTION = CONFIG["merge_action"]

OVERLAY_PATH = OUTPUT_DIR / "logistics_management_maritime_requirements_overlay.csv"
MANIFEST_PATH = OUTPUT_DIR / "logistics_management_maritime_recovery_manifest.csv"

PATH_POLICY_PATH = (
    OUTPUT_DIR / "logistics_management_maritime_alternative_requirement_paths.csv"
)

COMPOUND_POLICY_PATH = (
    OUTPUT_DIR / "logistics_management_maritime_compound_requirement_alternatives.csv"
)

ELECTIVE_POLICY_PATH = (
    OUTPUT_DIR / "logistics_management_maritime_elective_policy.csv"
)


MASTER_COLUMNS = [
    "requirement_id",
    "catalog_year",
    "catalog_year_start",
    "credential_family",
    "credential_id",
    "credential_title",
    "requirement_sequence",
    "semester_label",
    "rule_type",
    "original_rule_type",
    "credit_hours",
    "correction_note",
    "course_codes",
    "raw_requirement_text",
    "source_table_index",
    "source_row_index",
    "raw_credit_hours_text",
    "issue_flags",
    "source_file",
    "validation_rows",
    "validation_statuses",
    "validation_notes",
]


RECOVERY_FLAGS = (
    f"{CONFIG['recovery_flag']};"
    "MULTI_PATH_TABLE_UNSUPPORTED;"
    "PDF_RENDER_VERIFIED;"
    "HUMAN_REVIEW_CONFIRMED"
)


CORRECTION_NOTE = (
    "CONTROLLED RECOVERY: rendered catalog page "
    f"{SOURCE_PAGE} contains a mutually alternative fourth-semester "
    "path structure that cannot be represented safely by the generic "
    "flattened DOCX parser."
)


VALIDATION_NOTE = (
    "Human review confirmed 46 common applied SCH plus either "
    "14-SCH fourth-semester path = published 60-SCH AAS."
)


def rid(sequence: int) -> str:
    return f"{CREDENTIAL_ID}_R{sequence}"


def requirement(
    sequence: int,
    semester: str,
    rule_type: str,
    hours: int,
    text: str,
    course_codes: str = "",
) -> dict[str, str]:
    return {
        "requirement_id": rid(sequence),
        "catalog_year": CATALOG_YEAR,
        "catalog_year_start": CATALOG_YEAR_START,
        "credential_family": CREDENTIAL_FAMILY,
        "credential_id": CREDENTIAL_ID,
        "credential_title": CREDENTIAL_TITLE,
        "requirement_sequence": str(sequence),
        "semester_label": semester,
        "rule_type": rule_type,
        "original_rule_type": rule_type,
        "credit_hours": str(hours),
        "correction_note": CORRECTION_NOTE,
        "course_codes": course_codes,
        "raw_requirement_text": text,
        "source_table_index": SOURCE_TABLE_INDEX,
        "source_row_index": f"PDF{SOURCE_PAGE}_R{sequence:02d}",
        "raw_credit_hours_text": str(hours),
        "issue_flags": RECOVERY_FLAGS,
        "source_file": SOURCE_FILE,
        "validation_rows": "",
        "validation_statuses": "",
        "validation_notes": "",
    }


REQUIREMENTS = [
    # ------------------------------------------------------------
    # COMMON REQUIREMENTS: FIRST THREE SEMESTERS = 46 SCH
    # ------------------------------------------------------------

    requirement(
        1,
        "First Semester",
        "EXACT",
        3,
        "EDUC 1300 Learning Framework",
        "EDUC 1300",
    ),
    requirement(
        2,
        "First Semester",
        "EXACT",
        3,
        "LMGT 1319 Intro to Business Logistics",
        "LMGT 1319",
    ),
    requirement(
        3,
        "First Semester",
        "EXACT",
        3,
        "LMGT 1321 Intro to Materials Handling",
        "LMGT 1321",
    ),
    requirement(
        4,
        "First Semester",
        "EXACT",
        3,
        "ENGL 1301 Composition I",
        "ENGL 1301",
    ),
    requirement(
        5,
        "First Semester",
        "EXACT",
        3,
        "LMGT 1345 Economics of Transportation and Distribution",
        "LMGT 1345",
    ),

    requirement(
        6,
        "Second Semester",
        "EXACT",
        3,
        "LMGT 2334 Principles of Traffic Management",
        "LMGT 2334",
    ),
    requirement(
        7,
        "Second Semester",
        "EXACT",
        3,
        "LMGT 1325 Warehouse Distribution Management",
        "LMGT 1325",
    ),
    requirement(
        8,
        "Second Semester",
        "EXACT",
        3,
        "LMGT 1323 Domestic and International Transportation Management",
        "LMGT 1323",
    ),
    requirement(
        9,
        "Second Semester",
        "EXACT",
        3,
        "BMGT 1309 Information and Project Management",
        "BMGT 1309",
    ),
    requirement(
        10,
        "Second Semester",
        "EXACT",
        3,
        "LMGT 2388 Internship",
        "LMGT 2388",
    ),

    requirement(
        11,
        "Third Semester",
        "EXACT",
        4,
        "OSHT 2401 OSHA Regulations - General Industry",
        "OSHT 2401",
    ),
    requirement(
        12,
        "Third Semester",
        "EXACT",
        3,
        "BUSI 2301 Business Law",
        "BUSI 2301",
    ),
    requirement(
        13,
        "Third Semester",
        "CORE_BUCKET",
        3,
        "SOCIAL AND BEHAVIORAL SCIENCES",
    ),
    requirement(
        14,
        "Third Semester",
        "CORE_BUCKET",
        3,
        "LANGUAGE, PHILOSOPHY, CULTURE or CREATIVE ARTS",
    ),
    requirement(
        15,
        "Third Semester",
        "ANY_N",
        3,
        (
            "MATH 1314 College Algebra or MATH 1332 Contemporary "
            "Mathematics or MATH 1342 Elementary Statistical Methods"
        ),
        "MATH 1314;MATH 1332;MATH 1342",
    ),

    # ------------------------------------------------------------
    # FOURTH SEMESTER PATH A: LOGISTICS / CDL = 14 APPLIED SCH
    # ------------------------------------------------------------

    requirement(
        16,
        "Fourth Semester - Logistics/CDL Path",
        "EXACT",
        3,
        "BUSI 1301 Business Principles",
        "BUSI 1301",
    ),
    requirement(
        17,
        "Fourth Semester - Logistics/CDL Path",
        "EXACT",
        1,
        "CVOP 1145 Commercial Driver License Overview",
        "CVOP 1145",
    ),
    requirement(
        18,
        "Fourth Semester - Logistics/CDL Path",
        "EXACT",
        2,
        "CVOP 1201 Commercial Driver License Driving Skills",
        "CVOP 1201",
    ),
    requirement(
        19,
        "Fourth Semester - Logistics/CDL Path",
        "ELECTIVE",
        2,
        "BUSI Elective",
    ),
    requirement(
        20,
        "Fourth Semester - Logistics/CDL Path",
        "EXACT",
        3,
        "COSC 1301 Introduction to Computing",
        "COSC 1301",
    ),
    requirement(
        21,
        "Fourth Semester - Logistics/CDL Path",
        "EXACT",
        3,
        "BMGT 2341 Strategic Management",
        "BMGT 2341",
    ),

    # ------------------------------------------------------------
    # FOURTH SEMESTER PATH B: ORDINARY SEAMAN = 14 APPLIED SCH
    #
    # The catalog labels "Ordinary Seaman I Cert" as 12 SCH within
    # this AAS. Human review confirms that EDUC 1300 is already a
    # common AAS requirement, so the four remaining 3-SCH Ordinary
    # Seaman courses constitute the 12-SCH component.
    # ------------------------------------------------------------

    requirement(
        22,
        "Fourth Semester - Ordinary Seaman Path",
        "EXACT",
        3,
        "NAUT 1343 Introduction to Tugs and Towing",
        "NAUT 1343",
    ),
    requirement(
        23,
        "Fourth Semester - Ordinary Seaman Path",
        "EXACT",
        3,
        "NAUT 1315 Basic Safety",
        "NAUT 1315",
    ),
    requirement(
        24,
        "Fourth Semester - Ordinary Seaman Path",
        "EXACT",
        3,
        "NAUT 1305 Introduction to Ships and Shipping",
        "NAUT 1305",
    ),
    requirement(
        25,
        "Fourth Semester - Ordinary Seaman Path",
        "EXACT",
        3,
        "NAUT 1320 Seamanship I",
        "NAUT 1320",
    ),

    # Applied-hour requirement: catalog says "Choose 2 SCH".
    # Every listed satisfying alternative represents >=3 earned SCH.
    # credit_hours=2 therefore means APPLIED credential hours and
    # does not modify the transcript SCH of the satisfying course(s).
    requirement(
        26,
        "Fourth Semester - Ordinary Seaman Path",
        "ANY_N",
        2,
        (
            "Choose 2 SCH from BUSI 1301; CVOP 1145 and CVOP 1201; "
            "COSC 1301; BMGT 2341; BMGT 1301; BMGT 1327"
        ),
        (
            "BUSI 1301;CVOP 1145;CVOP 1201;COSC 1301;"
            "BMGT 2341;BMGT 1301;BMGT 1327"
        ),
    ),
]


COMMON_IDS = {rid(i) for i in range(1, 16)}
PATH_A_IDS = {rid(i) for i in range(16, 22)}
PATH_B_IDS = {rid(i) for i in range(22, 27)}


PATH_POLICY_ROWS = []

for requirement_id in sorted(
    PATH_A_IDS,
    key=lambda value: int(value.rsplit("R", 1)[1]),
):
    PATH_POLICY_ROWS.append(
        {
            "catalog_year": CATALOG_YEAR,
            "credential_id": CREDENTIAL_ID,
            "path_group_id": "FOURTH_SEMESTER",
            "path_id": "LOGISTICS_CDL",
            "path_label": "Logistics/CDL Path",
            "path_order": "1",
            "requirement_id": requirement_id,
            "path_expected_applied_hours": "14",
            "policy_status": "AUTHORIZED_FROM_CATALOG_TEXT_AND_HUMAN_REVIEW",
            "policy_note": (
                "Fourth Semester explicitly says choose one path from below."
            ),
        }
    )

for requirement_id in sorted(
    PATH_B_IDS,
    key=lambda value: int(value.rsplit("R", 1)[1]),
):
    PATH_POLICY_ROWS.append(
        {
            "catalog_year": CATALOG_YEAR,
            "credential_id": CREDENTIAL_ID,
            "path_group_id": "FOURTH_SEMESTER",
            "path_id": "ORDINARY_SEAMAN",
            "path_label": "Ordinary Seaman Path",
            "path_order": "2",
            "requirement_id": requirement_id,
            "path_expected_applied_hours": "14",
            "policy_status": "AUTHORIZED_FROM_CATALOG_TEXT_AND_HUMAN_REVIEW",
            "policy_note": (
                "Ordinary Seaman component contributes 12 applied SCH; "
                "supplemental requirement contributes 2 applied SCH."
            ),
        }
    )


ELECTIVE_POLICY_ROWS = [
    {
        "requirement_id": rid(19),
        "catalog_year": CATALOG_YEAR,
        "credential_id": CREDENTIAL_ID,
        "credential_title": CREDENTIAL_TITLE,
        "semester_label": "Fourth Semester - Logistics/CDL Path",
        "credit_hours": "2",
        "raw_requirement_text": "BUSI Elective",
        "resolver_type": "RUBRIC_ELECTIVE",
        "allowed_rubrics": "BUSI",
        "resolution_note": (
            "Human catalog review confirmed that BUSI Elective means "
            "a course carrying the BUSI rubric only. Do not expand to "
            "a broader business-subject elective pool."
        ),
        "policy_status": "AUTHORIZED_FROM_CATALOG_TEXT_AND_HUMAN_REVIEW",
    }
]


COMPOUND_POLICY_ROWS = []


def compound_row(
    alternative_group: int,
    course_order: int,
    option_value: str,
    courses_required: int,
    note: str,
) -> dict[str, str]:
    return {
        "catalog_year": CATALOG_YEAR,
        "credential_id": CREDENTIAL_ID,
        "requirement_id": rid(26),
        "alternative_group": str(alternative_group),
        "alternative_course_order": str(course_order),
        "option_type": "COURSE",
        "option_value": option_value,
        "courses_required_in_group": str(courses_required),
        "credit_hours_required": "2",
        "policy_status": "AUTHORIZED_FROM_CATALOG_TEXT_AND_HUMAN_REVIEW",
        "policy_note": note,
    }


COMPOUND_POLICY_ROWS.extend(
    [
        compound_row(
            1,
            1,
            "BUSI 1301",
            1,
            "BUSI 1301 is one complete supplemental alternative.",
        ),
        compound_row(
            2,
            1,
            "CVOP 1145",
            2,
            (
                "CVOP 1145 and CVOP 1201 are printed together as one "
                "supplemental alternative."
            ),
        ),
        compound_row(
            2,
            2,
            "CVOP 1201",
            2,
            (
                "CVOP 1145 and CVOP 1201 are printed together as one "
                "supplemental alternative."
            ),
        ),
        compound_row(
            3,
            1,
            "COSC 1301",
            1,
            "COSC 1301 is one complete supplemental alternative.",
        ),
        compound_row(
            4,
            1,
            "BMGT 2341",
            1,
            "BMGT 2341 is one complete supplemental alternative.",
        ),
        compound_row(
            5,
            1,
            "BMGT 1301",
            1,
            "BMGT 1301 is one complete supplemental alternative.",
        ),
        compound_row(
            6,
            1,
            "BMGT 1327",
            1,
            "BMGT 1327 is one complete supplemental alternative.",
        ),
    ]
)


def hours_for(ids: set[str]) -> int:
    return sum(
        int(row["credit_hours"])
        for row in REQUIREMENTS
        if row["requirement_id"] in ids
    )


def main() -> None:
    requirement_ids = [
        row["requirement_id"]
        for row in REQUIREMENTS
    ]

    if len(REQUIREMENTS) != 26:
        raise ValueError(
            f"Expected 26 requirements; found {len(REQUIREMENTS)}"
        )

    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("Duplicate Logistics Management (Maritime) requirement IDs")

    common_hours = hours_for(COMMON_IDS)
    path_a_hours = hours_for(PATH_A_IDS)
    path_b_hours = hours_for(PATH_B_IDS)

    if common_hours != 46:
        raise ValueError(
            f"Common requirement hours must equal 46; found {common_hours}"
        )

    if path_a_hours != 14:
        raise ValueError(
            f"Path A hours must equal 14; found {path_a_hours}"
        )

    if path_b_hours != 14:
        raise ValueError(
            f"Path B hours must equal 14; found {path_b_hours}"
        )

    if common_hours + path_a_hours != 60:
        raise ValueError("Path A does not reconcile to 60 applied SCH")

    if common_hours + path_b_hours != 60:
        raise ValueError("Path B does not reconcile to 60 applied SCH")

    mapped_path_ids = {
        row["requirement_id"]
        for row in PATH_POLICY_ROWS
    }

    if mapped_path_ids != PATH_A_IDS | PATH_B_IDS:
        raise ValueError(
            "Alternative-path policy does not map exactly the branch requirements"
        )

    groups: dict[str, list[str]] = {}

    for row in COMPOUND_POLICY_ROWS:
        groups.setdefault(
            row["alternative_group"],
            [],
        ).append(row["option_value"])

    expected_groups = {
        "1": ["BUSI 1301"],
        "2": ["CVOP 1145", "CVOP 1201"],
        "3": ["COSC 1301"],
        "4": ["BMGT 2341"],
        "5": ["BMGT 1301"],
        "6": ["BMGT 1327"],
    }

    if groups != expected_groups:
        raise ValueError(
            f"Supplemental alternatives changed: {groups}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OVERLAY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=MASTER_COLUMNS,
        )
        writer.writeheader()
        writer.writerows(REQUIREMENTS)

    path_fields = list(PATH_POLICY_ROWS[0].keys())

    with PATH_POLICY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=path_fields,
        )
        writer.writeheader()
        writer.writerows(PATH_POLICY_ROWS)

    elective_fields = list(
        ELECTIVE_POLICY_ROWS[0].keys()
    )

    with ELECTIVE_POLICY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=elective_fields,
        )
        writer.writeheader()
        writer.writerows(ELECTIVE_POLICY_ROWS)

    compound_fields = list(
        COMPOUND_POLICY_ROWS[0].keys()
    )

    with COMPOUND_POLICY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=compound_fields,
        )
        writer.writeheader()
        writer.writerows(COMPOUND_POLICY_ROWS)

    manifest = {
        "catalog_year": CATALOG_YEAR,
        "credential_id": CREDENTIAL_ID,
        "credential_title": CREDENTIAL_TITLE,
        "award": "Associate of Applied Science",
        "merge_action": MERGE_ACTION,
        "source_pdf": SOURCE_FILE,
        "source_pdf_page": SOURCE_PAGE,
        "source_docx_table_index": SOURCE_TABLE_INDEX,
        "common_applied_hours": str(common_hours),
        "path_a_applied_hours": str(path_a_hours),
        "path_b_applied_hours": str(path_b_hours),
        "path_a_program_hours": str(
            common_hours + path_a_hours
        ),
        "path_b_program_hours": str(
            common_hours + path_b_hours
        ),
        "published_program_hours": "60",
        "requirement_rows": str(
            len(REQUIREMENTS)
        ),
        "path_policy_rows": str(
            len(PATH_POLICY_ROWS)
        ),
        "compound_policy_rows": str(
            len(COMPOUND_POLICY_ROWS)
        ),
        "elective_policy_rows": str(
            len(ELECTIVE_POLICY_ROWS)
        ),
        "supplemental_applied_hours": "2",
        "supplemental_minimum_earned_hours": "3",
        "human_review_status": "CONFIRMED",
        "runtime_inference": "NONE",
        "validation_status": "PASS_CONTROLLED_RECOVERY",
        "recovery_reason": (
            "Published curriculum contains mutually alternative "
            "fourth-semester paths. Generic flattening would change "
            "credential semantics."
        ),
    }

    with MANIFEST_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(manifest.keys()),
        )
        writer.writeheader()
        writer.writerow(manifest)

    print(
        f"Wrote {len(REQUIREMENTS)} Logistics Management (Maritime) requirement rows."
    )
    print(
        f"Common requirements: {common_hours} SCH"
    )
    print(
        f"Path A: {path_a_hours} SCH -> "
        f"{common_hours + path_a_hours}/60"
    )
    print(
        f"Path B: {path_b_hours} SCH -> "
        f"{common_hours + path_b_hours}/60"
    )
    print(
        f"Alternative-path policy rows: "
        f"{len(PATH_POLICY_ROWS)}"
    )
    print(
        f"Compound supplemental rows: "
        f"{len(COMPOUND_POLICY_ROWS)}"
    )
    print(
        f"Elective policy rows: "
        f"{len(ELECTIVE_POLICY_ROWS)}"
    )
    print("BUSI Elective scope: BUSI RUBRIC ONLY")
    print("HUMAN REVIEW: CONFIRMED")
    print("No production files were modified.")
    print("No audit-engine code was modified.")


if __name__ == "__main__":
    main()
