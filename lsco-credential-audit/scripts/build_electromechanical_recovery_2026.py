#!/usr/bin/env python
"""
Controlled source recovery: 2026-2027 Electromechanical Technology.

RATIONALE
---------
The generic DOCX parser cannot safely recover these two credential tables.

Certificate of Completion:
    DOCX table 78 is admitted by the generic parser, but its cell/hour streams
    are structurally damaged. The extracted result is therefore incomplete.

Associate of Applied Science:
    DOCX table 79 uses a First Semester (Fall) structure and also contains
    damaged/truncated cell/hour streams. It is intentionally excluded from
    the generic parser rather than inferred from malformed DOCX content.

AUTHORITY
---------
The rendered 2026-2027 catalog PDF is treated as the controlled recovery
source for these two credential definitions:

    PDF page 199: Electromechanical Technology Certificate of Completion
                  41 SCH = 17 + 15 + 9

    PDF page 200: Electromechanical Technology AAS Degree
                  60 SCH = 17 + 15 + 6 + 12 + 10

This script does NOT modify generic parser output and does NOT merge anything
into production. It writes a deterministic overlay and recovery manifest for
subsequent review and controlled merge.

No AI/inference is used at runtime.
"""

from __future__ import annotations

from pathlib import Path
import csv


CATALOG_YEAR = "2026-2027"

SOURCE_PDF = (
    "data/raw/catalogs/2026-2027/"
    "2026-2027_Catalog.pdf"
)

OUTPUT_DIR = Path(
    "data/processed/catalogs/controlled_recovery_2026"
)

OVERLAY_PATH = OUTPUT_DIR / "electromechanical_requirements_overlay.csv"
MANIFEST_PATH = OUTPUT_DIR / "electromechanical_recovery_manifest.csv"


REQUIREMENT_FIELDS = [
    "catalog_year",
    "credential_id",
    "credential_title",
    "source_table_index",
    "source_row_index",
    "requirement_sequence",
    "semester_label",
    "raw_requirement_text",
    "credit_hours",
    "raw_credit_hours_text",
    "rule_type",
    "course_codes",
    "issue_flags",
]


RECOVERY_FLAG = (
    "CONTROLLED_SOURCE_RECOVERY_2026;"
    "DOCX_TABLE_MALFORMED;"
    "PDF_RENDER_VERIFIED"
)


def exact(
    semester: str,
    code: str,
    title: str,
    hours: int,
) -> dict:
    return {
        "semester": semester,
        "text": f"{code} {title}",
        "hours": hours,
        "rule_type": "EXACT",
        "course_codes": code,
    }


def any_n(
    semester: str,
    codes: list[str],
    text: str,
    hours: int,
) -> dict:
    return {
        "semester": semester,
        "text": text,
        "hours": hours,
        "rule_type": "ANY_N",
        "course_codes": ";".join(codes),
    }


def core_bucket(
    semester: str,
    text: str,
    hours: int,
) -> dict:
    return {
        "semester": semester,
        "text": text,
        "hours": hours,
        "rule_type": "CORE_BUCKET",
        "course_codes": "",
    }


RECOVERIES = [
    {
        "credential_id": "ELECTROMECHANICAL_TECHNOLOGY_2026",
        "credential_title": "Electromechanical Technology",
        "award": "Certificate of Completion",
        "merge_action": "REPLACE_BASE_CREDENTIAL",
        "source_pdf_page": 199,
        "damaged_docx_table_index": 78,
        "expected_program_hours": 41,
        "expected_semester_hours": {
            "First Semester": 17,
            "Second Semester": 15,
            "Third Semester": 9,
        },
        "requirements": [
            exact(
                "First Semester",
                "OSHT 2401",
                "OSHA Regulations – General Industry",
                4,
            ),
            exact(
                "First Semester",
                "ELPT 1411",
                "Basic Electrical Theory",
                4,
            ),
            exact(
                "First Semester",
                "MCHN 1338",
                "Basic Machine Shop I",
                3,
            ),
            exact(
                "First Semester",
                "INMT 2303",
                "Pumps, Compressors and Mechanical Drives",
                3,
            ),
            exact(
                "First Semester",
                "INTC 1358",
                "Flow and Calibration",
                3,
            ),
            exact(
                "Second Semester",
                "INTC 1301",
                "Principles of Industrial Measurements I",
                3,
            ),
            exact(
                "Second Semester",
                "HYDR 1445",
                "Hydraulics and Pneumatics",
                4,
            ),
            exact(
                "Second Semester",
                "RBTC 1401",
                "Programmable Logic Controllers",
                4,
            ),
            exact(
                "Second Semester",
                "INTC 1457",
                "AC/DC Motor Control",
                4,
            ),
            exact(
                "Third Semester",
                "INMT 2345",
                "Industrial Troubleshooting",
                3,
            ),
            exact(
                "Third Semester",
                "INMT 2301",
                "Machinery Installation (Capstone Course)",
                3,
            ),
            exact(
                "Third Semester",
                "PTAC 2314",
                "Principles of Quality",
                3,
            ),
        ],
    },
    {
        "credential_id": "ELECTROMECHANICAL_TECHNOLOGY_AAS_2026",
        "credential_title": "Electromechanical Technology",
        "award": "Associate of Applied Science",
        "merge_action": "APPEND_MISSING_CREDENTIAL",
        "source_pdf_page": 200,
        "damaged_docx_table_index": 79,
        "expected_program_hours": 60,
        "expected_semester_hours": {
            "First Semester (Fall)": 17,
            "Second Semester (Spring)": 15,
            "Third Semester (Summer)": 6,
            "Fourth Semester (Fall)": 12,
            "Fifth Semester (Spring)": 10,
        },
        "requirements": [
            exact(
                "First Semester (Fall)",
                "OSHT 2401",
                "OSHA Regulations – General Industry",
                4,
            ),
            exact(
                "First Semester (Fall)",
                "INTC 1358",
                "Flow and Calibration",
                3,
            ),
            exact(
                "First Semester (Fall)",
                "ELPT 1411",
                "Basic Electrical Theory",
                4,
            ),
            exact(
                "First Semester (Fall)",
                "MCHN 1338",
                "Basic Machine Shop I",
                3,
            ),
            exact(
                "First Semester (Fall)",
                "INMT 2303",
                "Pumps, Compressors, and Mechanical Drives",
                3,
            ),
            exact(
                "Second Semester (Spring)",
                "INTC 1301",
                "Principles of Industrial Measurements I",
                3,
            ),
            exact(
                "Second Semester (Spring)",
                "HYDR 1445",
                "Hydraulics and Pneumatics",
                4,
            ),
            exact(
                "Second Semester (Spring)",
                "RBTC 1401",
                "Programmable Logic Controllers",
                4,
            ),
            exact(
                "Second Semester (Spring)",
                "INTC 1457",
                "AC/DC Motor Control",
                4,
            ),
            exact(
                "Third Semester (Summer)",
                "ENGL 1301",
                "Composition I",
                3,
            ),
            core_bucket(
                "Third Semester (Summer)",
                "SOCIAL AND BEHAVIORAL SCIENCES",
                3,
            ),
            exact(
                "Fourth Semester (Fall)",
                "INMT 2345",
                "Industrial Troubleshooting",
                3,
            ),
            exact(
                "Fourth Semester (Fall)",
                "INMT 2301",
                "Machinery Installation",
                3,
            ),
            exact(
                "Fourth Semester (Fall)",
                "MATH 1332",
                "Contemporary Math (Core Math)",
                3,
            ),
            exact(
                "Fourth Semester (Fall)",
                "PTAC 2314",
                "Principles of Quality",
                3,
            ),
            any_n(
                "Fifth Semester (Spring)",
                ["COSC 1301", "SPCH 1315"],
                "COSC 1301 Introduction to Computing or "
                "SPCH 1315 Public Speaking",
                3,
            ),
            exact(
                "Fifth Semester (Spring)",
                "INTC 2488",
                "Internship Instrumentation Technology/Technician "
                "(Capstone)",
                4,
            ),
            core_bucket(
                "Fifth Semester (Spring)",
                "LANGUAGE, PHILOSOPHY, AND CULTURE or CREATIVE ARTS",
                3,
            ),
        ],
    },
]


def main() -> None:
    output_rows = []
    manifest_rows = []

    for recovery in RECOVERIES:
        semester_actual = {
            semester: 0
            for semester in recovery["expected_semester_hours"]
        }

        for sequence, requirement in enumerate(
            recovery["requirements"],
            start=1,
        ):
            semester_actual[requirement["semester"]] += requirement["hours"]

            output_rows.append(
                {
                    "catalog_year": CATALOG_YEAR,
                    "credential_id": recovery["credential_id"],
                    "credential_title": recovery["credential_title"],
                    "source_table_index": str(
                        recovery["damaged_docx_table_index"]
                    ),
                    "source_row_index": (
                        f"PDF{recovery['source_pdf_page']}_R{sequence:02d}"
                    ),
                    "requirement_sequence": str(sequence),
                    "semester_label": requirement["semester"],
                    "raw_requirement_text": requirement["text"],
                    "credit_hours": str(requirement["hours"]),
                    "raw_credit_hours_text": str(requirement["hours"]),
                    "rule_type": requirement["rule_type"],
                    "course_codes": requirement["course_codes"],
                    "issue_flags": RECOVERY_FLAG,
                }
            )

        actual_program_hours = sum(semester_actual.values())

        semester_match = (
            semester_actual
            == recovery["expected_semester_hours"]
        )
        program_match = (
            actual_program_hours
            == recovery["expected_program_hours"]
        )

        status = (
            "PASS_CONTROLLED_RECOVERY"
            if semester_match and program_match
            else "FAIL_CONTROLLED_RECOVERY"
        )

        manifest_rows.append(
            {
                "catalog_year": CATALOG_YEAR,
                "credential_id": recovery["credential_id"],
                "credential_title": recovery["credential_title"],
                "award": recovery["award"],
                "merge_action": recovery["merge_action"],
                "source_pdf": SOURCE_PDF,
                "source_pdf_page": str(recovery["source_pdf_page"]),
                "damaged_docx_table_index": str(
                    recovery["damaged_docx_table_index"]
                ),
                "recovery_reason": (
                    "Generic DOCX extraction is not authoritative for this "
                    "credential because the source table contains missing or "
                    "truncated course/hour cell streams. Requirements were "
                    "transcribed deterministically from the rendered catalog "
                    "PDF and validated against displayed semester/program totals."
                ),
                "expected_program_hours": str(
                    recovery["expected_program_hours"]
                ),
                "recovered_program_hours": str(actual_program_hours),
                "expected_semester_hours": repr(
                    recovery["expected_semester_hours"]
                ),
                "recovered_semester_hours": repr(semester_actual),
                "requirement_count": str(
                    len(recovery["requirements"])
                ),
                "validation_status": status,
                "runtime_inference": "NONE",
            }
        )

        if status != "PASS_CONTROLLED_RECOVERY":
            raise ValueError(
                f"{recovery['credential_id']} recovery failed validation: "
                f"semester={semester_actual}, "
                f"program={actual_program_hours}"
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with OVERLAY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=REQUIREMENT_FIELDS,
        )
        writer.writeheader()
        writer.writerows(output_rows)

    with MANIFEST_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(manifest_rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(
        f"Wrote {len(output_rows)} recovered requirement rows "
        f"for {len(manifest_rows)} credentials."
    )

    for row in manifest_rows:
        print(
            f"{row['credential_id']}: "
            f"{row['recovered_program_hours']}/"
            f"{row['expected_program_hours']} SCH :: "
            f"{row['validation_status']} :: "
            f"{row['merge_action']}"
        )

    print()
    print("No generic parser output was modified.")
    print("No production master was modified.")


if __name__ == "__main__":
    main()
