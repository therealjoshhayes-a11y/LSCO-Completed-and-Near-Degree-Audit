from __future__ import annotations

from pathlib import Path

import pandas as pd

from lsco_audit.paths import PROCESSED_DIR


CREDENTIALS_CSV = PROCESSED_DIR / "credentials.csv"
REQUIREMENTS_MASTER_CSV = PROCESSED_DIR / "requirements_master.csv"
OUTPUT_CSV = PROCESSED_DIR / "requirements_pattern_d.csv"


def req(
    credential_id: str,
    sequence: int,
    rule_type: str,
    group_name: str,
    option_value: str,
    option_type: str,
    source_page: int,
    source_line: int,
    min_required: int = 1,
) -> dict:
    return {
        "requirement_id": f"{credential_id}_R{sequence:03}",
        "credential_id": credential_id,
        "sequence": sequence,
        "rule_type": rule_type,
        "min_required": min_required,
        "group_name": group_name,
        "option_value": option_value,
        "option_type": option_type,
        "source_page": source_page,
        "source_line": source_line,
        "source_file": "requirements_pattern_d.csv",
    }


def welding_fabrication_aas_fix() -> tuple[dict, pd.DataFrame]:
    credential_id = "WELDING_FABRICATION_TECHNOLOGY_AAS_2025"
    source_page = 270

    credential = {
        "credential_id": credential_id,
        "credential_name": "Welding Fabrication Technology",
        "award_type": "Associate of Applied Science Degree",
        "pathway": "",
        "total_hours": 60.0,
        "catalog_year": "2025-2026",
        "source_page": source_page,
        "extraction_issue": "pattern_d_static_fix",
    }

    rows = [
        req(credential_id, 1, "EXACT", "Required Course", "WLDG 1323", "COURSE", source_page, 13),
        req(credential_id, 2, "EXACT", "Required Course", "WLDG 1327", "COURSE", source_page, 14),
        req(credential_id, 3, "EXACT", "Required Course", "WLDG 1428", "COURSE", source_page, 15),

        req(credential_id, 4, "ANY_N", "WLDG 1435 OR PFPB 1450", "WLDG 1435", "COURSE", source_page, 16),
        req(credential_id, 4, "ANY_N", "WLDG 1435 OR PFPB 1450", "PFPB 1450", "COURSE", source_page, 16),

        req(credential_id, 5, "ANY_N", "EDUC 1300 OR BCIS 1305 OR COSC 1301", "EDUC 1300", "COURSE", source_page, 20),
        req(credential_id, 5, "ANY_N", "EDUC 1300 OR BCIS 1305 OR COSC 1301", "BCIS 1305", "COURSE", source_page, 20),
        req(credential_id, 5, "ANY_N", "EDUC 1300 OR BCIS 1305 OR COSC 1301", "COSC 1301", "COURSE", source_page, 21),

        req(credential_id, 6, "EXACT", "Required Course", "WLDG 1417", "COURSE", source_page, 22),

        req(credential_id, 7, "ANY_N", "WLDG 2406 OR PFPB 1408", "WLDG 2406", "COURSE", source_page, 23),
        req(credential_id, 7, "ANY_N", "WLDG 2406 OR PFPB 1408", "PFPB 1408", "COURSE", source_page, 24),

        req(credential_id, 8, "ANY_N", "WLDG 1457 OR WLDG 2489 OR PFPB 1443", "WLDG 1457", "COURSE", source_page, 25),
        req(credential_id, 8, "ANY_N", "WLDG 1457 OR WLDG 2489 OR PFPB 1443", "WLDG 2489", "COURSE", source_page, 26),
        req(credential_id, 8, "ANY_N", "WLDG 1457 OR WLDG 2489 OR PFPB 1443", "PFPB 1443", "COURSE", source_page, 26),

        req(credential_id, 9, "EXACT", "Required Course", "ENGL 1301", "COURSE", source_page, 29),
        req(credential_id, 10, "ANY_N", "Language, Philosophy, and Culture", "Language, Philosophy, and Culture", "CORE_BUCKET", source_page, 30),
        req(credential_id, 11, "EXACT", "Required Course", "WLDG 1453", "COURSE", source_page, 31),

        req(credential_id, 12, "ANY_N", "WLDG 1421 OR WLDG 2488", "WLDG 1421", "COURSE", source_page, 32),
        req(credential_id, 12, "ANY_N", "WLDG 1421 OR WLDG 2488", "WLDG 2488", "COURSE", source_page, 33),

        req(credential_id, 13, "ANY_N", "Social and Behavioral Science", "Social and Behavioral Science", "CORE_BUCKET", source_page, 36),
        req(credential_id, 14, "EXACT", "Required Course", "MATH 1332", "COURSE", source_page, 37),

        req(credential_id, 15, "ANY_N", "WLDG 2453 OR PFPB 2433", "WLDG 2453", "COURSE", source_page, 38),
        req(credential_id, 15, "ANY_N", "WLDG 2453 OR PFPB 2433", "PFPB 2433", "COURSE", source_page, 39),

        req(credential_id, 16, "EXACT", "Required Course", "WLDG 2435", "COURSE", source_page, 40),
        req(credential_id, 17, "ANY_N", "Approved Elective", "Approved Elective", "ELECTIVE", source_page, 41),
    ]

    return credential, pd.DataFrame(rows)


STATIC_CREDENTIAL_FIXES = [
    welding_fabrication_aas_fix,
]


def backup_once(path: Path) -> None:
    backup_path = path.with_suffix(path.suffix + ".bak")
    if not backup_path.exists():
        backup_path.write_bytes(path.read_bytes())


def apply_pattern_d_fixes() -> None:
    backup_once(CREDENTIALS_CSV)
    backup_once(REQUIREMENTS_MASTER_CSV)

    credentials = pd.read_csv(CREDENTIALS_CSV)
    requirements = pd.read_csv(REQUIREMENTS_MASTER_CSV)

    fixed_credentials = []
    fixed_requirements = []

    for fix_factory in STATIC_CREDENTIAL_FIXES:
        credential, requirement_rows = fix_factory()
        fixed_credentials.append(credential)
        fixed_requirements.append(requirement_rows)

        credentials = credentials[
            credentials["credential_id"] != credential["credential_id"]
        ].copy()

        requirements = requirements[
            requirements["credential_id"] != credential["credential_id"]
        ].copy()

    pattern_d_requirements = pd.concat(fixed_requirements, ignore_index=True)

    credentials = pd.concat(
        [credentials, pd.DataFrame(fixed_credentials)],
        ignore_index=True,
    )

    requirements = pd.concat(
        [requirements, pattern_d_requirements],
        ignore_index=True,
    )

    credentials.to_csv(CREDENTIALS_CSV, index=False)
    requirements.to_csv(REQUIREMENTS_MASTER_CSV, index=False)
    pattern_d_requirements.to_csv(OUTPUT_CSV, index=False)

    print("Pattern D fixes applied.")
    print(f"Added/updated credentials: {len(fixed_credentials)}")
    print(f"Added/updated requirement rows: {len(pattern_d_requirements)}")


if __name__ == "__main__":
    apply_pattern_d_fixes()