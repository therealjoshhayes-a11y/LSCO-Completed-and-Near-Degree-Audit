"""
Synthetic FERPA-free tests for the 2026 Logistics Management
(Maritime) alternative-path semantics.

This harness:
- imports the path-aware audit candidate only;
- reads the isolated controlled-recovery artifacts;
- does not modify production masters or semantic-policy files;
- creates no student records;
- uses synthetic course histories only.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

SRC_DIR = ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


CANDIDATE_PATH = (
    ROOT
    / "src"
    / "lsco_audit"
    / "audit_multiyear_sample_path_candidate.py"
)

AUDIT_BUILDER_PATH = (
    ROOT
    / "scripts"
    / "build_audit_requirements_multiyear.py"
)

RECOVERY_DIR = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "controlled_recovery_2026"
)

SOURCE_REQUIREMENTS_PATH = (
    RECOVERY_DIR
    / "logistics_management_maritime_requirements_overlay.csv"
)

PATH_POLICY_PATH = (
    RECOVERY_DIR
    / "logistics_management_maritime_alternative_requirement_paths.csv"
)

COMPOUND_POLICY_PATH = (
    RECOVERY_DIR
    / "logistics_management_maritime_compound_requirement_alternatives.csv"
)

ELECTIVE_POLICY_PATH = (
    RECOVERY_DIR
    / "logistics_management_maritime_elective_policy.csv"
)

CATALOG_YEAR = "2026-2027"

CREDENTIAL_ID = (
    "LOGISTICS_MANAGEMENT_MARITIME_AAS_2026"
)

PATH_A = "LOGISTICS_CDL"
PATH_B = "ORDINARY_SEAMAN"


def load_module(
    name: str,
    path: Path,
):
    if not path.exists():
        raise FileNotFoundError(
            path
        )

    spec = (
        importlib.util.spec_from_file_location(
            name,
            path,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            f"Could not load module: {path}"
        )

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


audit = load_module(
    "audit_multiyear_sample_path_candidate",
    CANDIDATE_PATH,
)

builder = load_module(
    "build_audit_requirements_multiyear_test_import",
    AUDIT_BUILDER_PATH,
)


def require_file(
    path: Path,
) -> None:
    if not path.exists():
        raise FileNotFoundError(
            path
        )


for required_path in [
    SOURCE_REQUIREMENTS_PATH,
    PATH_POLICY_PATH,
    COMPOUND_POLICY_PATH,
    ELECTIVE_POLICY_PATH,
]:
    require_file(
        required_path
    )


source_requirements = pd.read_csv(
    SOURCE_REQUIREMENTS_PATH,
    dtype=str,
    keep_default_na=False,
)

executable_requirements = pd.DataFrame(
    builder.build_rows(
        source_requirements
    )
)

if executable_requirements.empty:
    raise RuntimeError(
        "Executable synthetic requirement set is empty"
    )


# ------------------------------------------------------------
# Load the isolated semantic sidecars through the candidate's
# real loaders. Only module constants are redirected in memory.
# No files are copied or changed.
# ------------------------------------------------------------

audit.ALTERNATIVE_REQUIREMENT_PATHS = (
    PATH_POLICY_PATH
)

audit.COMPOUND_REQUIREMENT_ALTERNATIVES = (
    COMPOUND_POLICY_PATH
)

audit.ELECTIVE_RULES = (
    ELECTIVE_POLICY_PATH
)

alternative_paths = (
    audit.load_alternative_requirement_paths()
)

audit.validate_alternative_requirement_paths(
    alternative_paths,
    executable_requirements,
)

alternative_path_lookup = (
    audit.build_alternative_path_lookup(
        alternative_paths
    )
)

compound_alternatives = (
    audit.load_compound_requirement_alternatives()
)

elective_rules = (
    audit.load_elective_rules()
)


# ------------------------------------------------------------
# Synthetic core lookup.
#
# Only the two core slots in this credential are needed.
# These are synthetic test satisfiers, not a production 2026
# core crosswalk.
# ------------------------------------------------------------

core_lookup = {
    (
        CATALOG_YEAR,
        "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE",
    ): {
        "PSYC 2301",
    },
    (
        CATALOG_YEAR,
        "LANGUAGE_PHILOSOPHY_AND_CULTURE_OR_CREATIVE_ARTS",
    ): {
        "HUMA 1315",
    },
}

academic_course_lookup = {}


COMMON_COURSES = {
    "EDUC 1300",
    "LMGT 1319",
    "LMGT 1321",
    "ENGL 1301",
    "LMGT 1345",
    "LMGT 2334",
    "LMGT 1325",
    "LMGT 1323",
    "BMGT 1309",
    "LMGT 2388",
    "OSHT 2401",
    "BUSI 2301",
    "PSYC 2301",
    "HUMA 1315",
    "MATH 1314",
}

PATH_A_COURSES = {
    "BUSI 1301",
    "CVOP 1145",
    "CVOP 1201",
    "BUSI 2305",
    "COSC 1301",
    "BMGT 2341",
}

PATH_B_NAUT_COURSES = {
    "NAUT 1343",
    "NAUT 1315",
    "NAUT 1305",
    "NAUT 1320",
}

PATH_B_SUPPLEMENTAL_SINGLE = {
    "BMGT 1301",
}

PATH_B_SUPPLEMENTAL_CVOP_PAIR = {
    "CVOP 1145",
    "CVOP 1201",
}


def make_course_lookup(
    terms: dict[str, int],
) -> dict[str, dict]:
    return {
        course_code: {
            "course_code": course_code,
            "term_taken": f"SYNTH_{term_sort}",
            "term_sort": int(
                term_sort
            ),
            "grade": "A",
        }
        for (
            course_code,
            term_sort,
        ) in terms.items()
    }


def terms_for(
    courses: set[str],
    term_sort: int,
) -> dict[str, int]:
    return {
        course_code: int(
            term_sort
        )
        for course_code in courses
    }


def merged_terms(
    *parts: dict[str, int],
) -> dict[str, int]:
    result = {}

    for part in parts:
        result.update(
            part
        )

    return result


def evaluate(
    name: str,
    terms: dict[str, int],
    *,
    expected_path: str,
    expected_status: str,
) -> list[dict]:
    rows = audit.audit_student_credential(
        student_id=f"SYNTH_{name}",
        catalog_year=CATALOG_YEAR,
        credential_id=CREDENTIAL_ID,
        credential_requirements=executable_requirements,
        course_lookup=make_course_lookup(
            terms
        ),
        core_lookup=core_lookup,
        elective_rules=elective_rules,
        academic_course_lookup=academic_course_lookup,
        compound_alternatives=compound_alternatives,
        alternative_path_lookup=alternative_path_lookup,
    )

    selected_path_ids = {
        str(
            row.get(
                "path_id",
                "",
            )
        )
        for row in rows
        if str(
            row.get(
                "path_selected",
                "",
            )
        ).upper()
        == "TRUE"
    }

    if selected_path_ids != {
        expected_path
    }:
        raise AssertionError(
            f"{name}: expected selected path "
            f"{expected_path}, got "
            f"{sorted(selected_path_ids)}"
        )

    counted = [
        row
        for row in rows
        if (
            not str(
                row.get(
                    "path_group_id",
                    "",
                )
            ).strip()
            or str(
                row.get(
                    "path_selected",
                    "",
                )
            ).strip().upper()
            == "TRUE"
        )
    ]

    total = len(
        counted
    )

    met = sum(
        str(
            row.get(
                "status",
                "",
            )
        ).upper()
        == "MET"
        for row in counted
    )

    unresolved = sum(
        str(
            row.get(
                "status",
                "",
            )
        ).upper().startswith(
            "UNRESOLVED"
        )
        for row in counted
    )

    missing = (
        total
        - met
        - unresolved
    )

    status = audit.get_audit_status(
        missing,
        unresolved,
    )

    if status != expected_status:
        raise AssertionError(
            f"{name}: expected status "
            f"{expected_status}, got {status}; "
            f"total={total}, met={met}, "
            f"missing={missing}, "
            f"unresolved={unresolved}"
        )

    print(
        f"PASS {name}: "
        f"path={expected_path} "
        f"status={status} "
        f"met={met}/{total}"
    )

    return rows


def main() -> None:
    # --------------------------------------------------------
    # CASE 1
    # Logistics/CDL path complete; Ordinary Seaman incomplete.
    # BUSI 2305 satisfies the catalog's BUSI-rubric elective.
    # --------------------------------------------------------

    evaluate(
        "PATH_A_ONLY",
        merged_terms(
            terms_for(
                COMMON_COURSES,
                100,
            ),
            terms_for(
                PATH_A_COURSES,
                200,
            ),
        ),
        expected_path=PATH_A,
        expected_status="COMPLETE",
    )


    # --------------------------------------------------------
    # CASE 2
    # Ordinary Seaman path complete; Logistics/CDL incomplete.
    # BMGT 1301 satisfies the 2-applied-SCH supplemental slot.
    # --------------------------------------------------------

    evaluate(
        "PATH_B_ONLY",
        merged_terms(
            terms_for(
                COMMON_COURSES,
                100,
            ),
            terms_for(
                PATH_B_NAUT_COURSES,
                200,
            ),
            terms_for(
                PATH_B_SUPPLEMENTAL_SINGLE,
                200,
            ),
        ),
        expected_path=PATH_B,
        expected_status="COMPLETE",
    )


    # --------------------------------------------------------
    # CASE 3
    # Both paths complete.
    #
    # Path B coursework is earlier than Path A, but one common
    # requirement is later than both paths. Therefore both paths
    # complete the credential in the same term and stable path
    # order must select Path A.
    # --------------------------------------------------------

    common_late = terms_for(
        COMMON_COURSES,
        100,
    )

    common_late[
        "EDUC 1300"
    ] = 300

    evaluate(
        "BOTH_COMPLETE_COMMON_LATE_TIE",
        merged_terms(
            common_late,
            terms_for(
                PATH_B_NAUT_COURSES,
                150,
            ),
            terms_for(
                PATH_B_SUPPLEMENTAL_SINGLE,
                150,
            ),
            terms_for(
                PATH_A_COURSES,
                200,
            ),
        ),
        expected_path=PATH_A,
        expected_status="COMPLETE",
    )


    # --------------------------------------------------------
    # CASE 4
    # Both paths complete and common work is earlier.
    # Path B completes at 150; Path A completes at 200.
    # Earliest credential completion must therefore select B.
    # --------------------------------------------------------

    evaluate(
        "BOTH_COMPLETE_PATH_B_EARLIER",
        merged_terms(
            terms_for(
                COMMON_COURSES,
                100,
            ),
            terms_for(
                PATH_B_NAUT_COURSES,
                150,
            ),
            terms_for(
                PATH_B_SUPPLEMENTAL_SINGLE,
                150,
            ),
            terms_for(
                PATH_A_COURSES,
                200,
            ),
        ),
        expected_path=PATH_B,
        expected_status="COMPLETE",
    )


    # --------------------------------------------------------
    # CASE 5
    # Neither path complete.
    #
    # Path A: one requirement missing, worth 2 applied SCH.
    # Path B: one requirement missing, worth 3 applied SCH.
    #
    # Missing requirement count ties at one, so missing applied
    # hours must select Path A.
    # --------------------------------------------------------

    path_a_without_elective = (
        PATH_A_COURSES
        - {
            "BUSI 2305",
        }
    )

    path_b_missing_one_naut = (
        PATH_B_NAUT_COURSES
        - {
            "NAUT 1320",
        }
    )

    evaluate(
        "NEITHER_COMPLETE_APPLIED_HOURS_TIEBREAK",
        merged_terms(
            terms_for(
                COMMON_COURSES,
                100,
            ),
            terms_for(
                path_a_without_elective,
                200,
            ),
            terms_for(
                path_b_missing_one_naut,
                200,
            ),
            terms_for(
                PATH_B_SUPPLEMENTAL_SINGLE,
                200,
            ),
        ),
        expected_path=PATH_A,
        expected_status="NEAR_COMPLETE",
    )


    # --------------------------------------------------------
    # CASE 6
    # Ordinary Seaman supplemental requirement is satisfied by
    # the compound CVOP 1145 + CVOP 1201 alternative.
    # --------------------------------------------------------

    rows = evaluate(
        "PATH_B_COMPOUND_CVOP_PAIR",
        merged_terms(
            terms_for(
                COMMON_COURSES,
                100,
            ),
            terms_for(
                PATH_B_NAUT_COURSES,
                200,
            ),
            terms_for(
                PATH_B_SUPPLEMENTAL_CVOP_PAIR,
                200,
            ),
        ),
        expected_path=PATH_B,
        expected_status="COMPLETE",
    )

    r26 = [
        row
        for row in rows
        if str(
            row.get(
                "requirement_id",
                "",
            )
        ).endswith(
            "_R26"
        )
        and str(
            row.get(
                "path_id",
                "",
            )
        )
        == PATH_B
    ]

    if len(r26) != 1:
        raise AssertionError(
            "Expected exactly one Path B R26 detail row"
        )

    if str(
        r26[0].get(
            "status",
            "",
        )
    ).upper() != "MET":
        raise AssertionError(
            "CVOP compound alternative did not satisfy R26"
        )

    matched = {
        value.strip()
        for value in str(
            r26[0].get(
                "matched_options",
                "",
            )
        ).split(";")
        if value.strip()
    }

    if matched != {
        "CVOP 1145",
        "CVOP 1201",
    }:
        raise AssertionError(
            "R26 matched unexpected compound courses: "
            f"{sorted(matched)}"
        )

    print(
        "PASS PATH_B_COMPOUND_CVOP_PAIR: "
        "R26 matched CVOP 1145 + CVOP 1201"
    )

    print()
    print(
        "ALL SYNTHETIC ALTERNATIVE-PATH TESTS PASSED"
    )
    print(
        "NO PRODUCTION FILES WERE MODIFIED"
    )


if __name__ == "__main__":
    main()
