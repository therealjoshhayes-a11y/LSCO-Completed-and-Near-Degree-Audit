from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


# ======================================================================================
# STEP 3 — PORT THE ESTABLISHED AWARDABILITY SCREEN TO THE CURRENT 1,410 COMBINATIONS
# ======================================================================================
#
# This is a port of the previously validated awardability layer:
#   - associate institutional GPA >= 2.0
#   - certificate plan GPA >= 2.0 (General Studies exception retained)
#   - major-field minimum C treatment
#   - catalog-year residency rules
#   - applied-program-hours gate
#   - applied failing-grade gate
#
# It DOES NOT:
#   - rerun the curriculum audit
#   - suppress official awards (already done)
#   - select latest catalog within a lineage
#   - apply second-associate / additional-certificate rules
#
# Current attempt-state rule:
#   - historical all-attempts is used through Spring 2026
#   - old Summer 2026 rows are replaced by the authoritative 10/5/26 refresh
#   - Fall 2026 rows are added from the authoritative 10/5/26 refresh
#   - blank Fall 2026 FinalGrade remains IN PROGRESS and contributes no earned/GPA credit
#
# Run from repository root:
#   python -u .\scripts\screen_current_unsuppressed_awardability.py
#
# No Git files are modified.


ROOT = Path.cwd()

CANDIDATES = Path(
    "data/processed/reporting/"
    "official_award_screening_final_20261008_092747/"
    "RESTRICTED_unsuppressed_complete_combinations_FINAL.csv"
)

APPLIED_DIR = Path(
    "data/processed/reporting/"
    "current_unsuppressed_applied_courses_20261008_095506"
)

APPLIED = (
    APPLIED_DIR
    / "RESTRICTED_unsuppressed_complete_applied_courses.csv"
)

SELECTED_DETAIL = (
    APPLIED_DIR
    / "RESTRICTED_unsuppressed_complete_selected_detail.csv"
)

RECONCILIATION = (
    APPLIED_DIR
    / "RESTRICTED_unsuppressed_complete_detail_reconciliation.csv"
)

HISTORICAL_ATTEMPTS = Path(
    "data/processed/all_student_course_attempts_normalized.csv"
)

REQUIREMENTS = Path(
    "data/processed/catalogs/staging_six_year/"
    "requirements_master_multiyear.csv"
)

REFRESH_EXACT_NAME = (
    "Summer 2026 and Fall 2026 Course Attempts_(10.5.26).xlsx"
)

REFRESH_SHEET = "202660 Course Attempts"

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / f"current_awardability_screen_{RUN_STAMP}"

DETAIL_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_unsuppressed_awardability.csv"
)

PASS_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_awardability_pass_combinations.csv"
)

FAIL_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_awardability_fail_combinations.csv"
)

REVIEW_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_awardability_review_combinations.csv"
)

INST_GPA_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_student_institutional_gpa_estimates.csv"
)

CURRENT_ATTEMPTS_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_attempt_state_candidate_students.csv"
)

SAFE_METRICS_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_metrics.csv"
)

SAFE_GATE_SUMMARY_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_gate_summary.csv"
)

SAFE_BY_CATALOG_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_by_catalog.csv"
)

SAFE_BY_CREDENTIAL_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_awardability_by_credential.csv"
)

EXPECTED_CANDIDATES = 1_410
EXPECTED_REFRESH_SUMMER_ATTEMPTS = 2_302
EXPECTED_REFRESH_FALL_ATTEMPTS = 18_641

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]

GRADE_POINTS = {
    "A": 4.0,
    "B": 3.0,
    "C": 2.0,
    "D": 1.0,
    "F": 0.0,
}

# Preserve the prior awardability calculation exactly:
# best resident grade for a repeated course, latest term as tie-break.
GRADE_RANK = {
    "A": 5,
    "B": 4,
    "C": 3,
    "D": 2,
    "F": 1,
}

CLEAR_TRANSFER_C_OR_BETTER = {
    "TA",
    "TB",
    "TC",
}

CLEAR_TRANSFER_BELOW_C = {
    "TD",
}

TRANSFER_GRADE_UNVERIFIED = {
    "T",
    "TS",
}

OTHER_UNVERIFIED_MAJOR_GRADES = {
    "S",
    "P",
    "CR",
    "E",
}

COURSE_RE = re.compile(
    r"\b([A-Z]{2,6})\s*[- ]?\s*(\d{4})\b",
    re.I,
)


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_grade(value: object) -> str:
    grade = text(value).upper()

    return {
        "A+": "A",
        "A-": "A",
        "B+": "B",
        "B-": "B",
        "C+": "C",
        "C-": "C",
        "D+": "D",
        "D-": "D",
    }.get(
        grade,
        grade,
    )


def normalize_course_code(
    subject_or_course: object,
    number: object | None = None,
) -> str:
    if number is not None:
        subject = text(
            subject_or_course
        ).upper()

        course_number = text(
            number
        )

        if (
            not subject
            or not course_number
        ):
            return ""

        course_number = (
            course_number
            .split(".")[0]
            .zfill(4)
        )

        if not course_number.isdigit():
            return ""

        return (
            f"{subject} {course_number}"
        )

    match = COURSE_RE.search(
        text(
            subject_or_course
        ).upper()
    )

    if not match:
        return ""

    return (
        f"{match.group(1).upper()} "
        f"{match.group(2)}"
    )


def derived_hours(
    course_code: object,
) -> float | None:
    course = normalize_course_code(
        course_code
    )

    if not course:
        return None

    number = course.split()[1]

    if (
        len(number) != 4
        or not number.isdigit()
    ):
        return None

    value = int(
        number[1]
    )

    if value == 0:
        return None

    return float(
        value
    )


def course_level(
    course_code: object,
) -> float | None:
    course = normalize_course_code(
        course_code
    )

    if not course:
        return None

    number = course.split()[1]

    if (
        len(number) != 4
        or not number.isdigit()
    ):
        return None

    return float(
        number[0]
    )


def as_bool(
    value: object,
) -> bool:
    return text(
        value
    ).upper() in {
        "TRUE",
        "T",
        "YES",
        "Y",
        "1",
    }


def catalog_start_year(
    catalog_year: object,
) -> int | None:
    match = re.match(
        r"^\s*(20\d{2})-20\d{2}\s*$",
        text(
            catalog_year
        ),
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def find_refresh_workbook() -> Path:
    established = (
        ROOT
        / "data"
        / "raw"
        / "student_exports"
        / REFRESH_EXACT_NAME
    )

    if established.exists():
        return established

    exact = list(
        ROOT.rglob(
            REFRESH_EXACT_NAME
        )
    )

    if len(exact) == 1:
        return exact[0]

    if len(exact) > 1:
        raise RuntimeError(
            "Multiple exact refresh workbooks found:\n"
            + "\n".join(
                str(path)
                for path in exact
            )
        )

    fallback = list(
        ROOT.rglob(
            "Summer 2026 and Fall 2026 Course Attempts*.xlsx"
        )
    )

    if len(fallback) != 1:
        raise RuntimeError(
            "Could not uniquely locate the authoritative "
            "Summer/Fall 2026 refresh workbook. Found:\n"
            + "\n".join(
                str(path)
                for path in fallback
            )
        )

    return fallback[0]


def normalize_refresh(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize the 10/5/26 Summer/Fall extract using the SAME source schema and
    linked-section rule already validated in profile_refresh_delta.py.

    New extract schema:
        Student_Id, First_Name, Last_Name, StudentMajor,
        Subject_Code, Course_Numb, Section_Numb, Final_Grade, Term_Code,
        DualCreditIndicator, High School, LastTermDualCredit

    Linked sections collapse at:
        student + term + subject + course number

    Section may vary. Every other substantive source field must agree.
    """
    required = {
        "Student_Id",
        "First_Name",
        "Last_Name",
        "StudentMajor",
        "Subject_Code",
        "Course_Numb",
        "Section_Numb",
        "Final_Grade",
        "Term_Code",
        "DualCreditIndicator",
        "High School",
        "LastTermDualCredit",
    }

    missing = (
        required
        - set(
            raw.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Refresh workbook missing required NEW-extract columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
            + "\nColumns found: "
            + " | ".join(
                map(
                    str,
                    raw.columns,
                )
            )
        )

    frame = pd.DataFrame()

    frame[
        "student_id"
    ] = (
        raw[
            "Student_Id"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame[
        "first_name"
    ] = (
        raw[
            "First_Name"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    frame[
        "last_name"
    ] = (
        raw[
            "Last_Name"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    frame[
        "student_major"
    ] = (
        raw[
            "StudentMajor"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame[
        "subject"
    ] = (
        raw[
            "Subject_Code"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame[
        "course_number"
    ] = (
        raw[
            "Course_Numb"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.split(".")
        .str[0]
        .str.zfill(4)
    )

    frame[
        "section"
    ] = (
        raw[
            "Section_Numb"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame[
        "final_grade"
    ] = (
        raw[
            "Final_Grade"
        ]
        .fillna("")
        .map(
            norm_grade
        )
    )

    frame[
        "term_sort"
    ] = pd.to_numeric(
        raw[
            "Term_Code"
        ],
        errors="coerce",
    )

    frame[
        "dual_credit_indicator"
    ] = (
        raw[
            "DualCreditIndicator"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame[
        "high_school"
    ] = (
        raw[
            "High School"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    frame[
        "last_term_dual_credit"
    ] = (
        raw[
            "LastTermDualCredit"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame[
        "source_row_number"
    ] = range(
        2,
        len(
            raw
        )
        + 2,
    )

    frame = frame[
        frame[
            "student_id"
        ].ne("")
        & frame[
            "term_sort"
        ].notna()
        & frame[
            "subject"
        ].ne("")
        & frame[
            "course_number"
        ].ne("")
    ].copy()

    frame[
        "term_sort"
    ] = (
        frame[
            "term_sort"
        ]
        .astype(int)
    )

    frame = frame[
        frame[
            "term_sort"
        ].isin(
            [
                202660,
                202690,
            ]
        )
    ].copy()

    frame[
        "course_code"
    ] = (
        frame[
            "subject"
        ]
        + " "
        + frame[
            "course_number"
        ]
    )

    # ------------------------------------------------------------------
    # Exact previously validated linked-section collapse.
    # ------------------------------------------------------------------
    key = [
        "student_id",
        "term_sort",
        "subject",
        "course_number",
    ]

    substantive = [
        "first_name",
        "last_name",
        "student_major",
        "final_grade",
        "dual_credit_indicator",
        "high_school",
        "last_term_dual_credit",
    ]

    grouped = frame.groupby(
        key,
        dropna=False,
        sort=False,
    )

    conflict_keys: set[tuple] = set()

    for column in substantive:
        varying = grouped[
            column
        ].nunique(
            dropna=False
        )

        conflict_keys.update(
            varying[
                varying > 1
            ].index.tolist()
        )

    if conflict_keys:
        conflict_index = pd.MultiIndex.from_tuples(
            conflict_keys,
            names=key,
        )

        indexed = frame.set_index(
            key
        )

        conflicts = (
            indexed.loc[
                indexed.index.isin(
                    conflict_index
                )
            ]
            .reset_index()
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        conflicts.to_csv(
            OUTPUT_DIR
            / "RESTRICTED_ERROR_refresh_linked_section_conflicts.csv",
            index=False,
        )

        raise RuntimeError(
            "Refresh linked-section collapse found substantive conflicts "
            f"in {len(conflict_keys):,} academic attempt keys. "
            "Diagnostic written; stopped before awardability."
        )

    collapsed_rows: list[dict] = []

    for group_key, group in frame.groupby(
        key,
        dropna=False,
        sort=False,
    ):
        first = group.iloc[
            0
        ]

        sections = sorted(
            {
                text(
                    value
                ).upper()
                for value in group[
                    "section"
                ]
                if text(
                    value
                )
            }
        )

        collapsed_rows.append(
            {
                "student_id": first[
                    "student_id"
                ],
                "student_major": first[
                    "student_major"
                ],
                "course_code": first[
                    "course_code"
                ],
                "final_grade": first[
                    "final_grade"
                ],
                "term_taken": str(
                    int(
                        first[
                            "term_sort"
                        ]
                    )
                ),
                "term_sort": int(
                    first[
                        "term_sort"
                    ]
                ),
                "section": ";".join(
                    sections
                ),
                "dual_credit_indicator": first[
                    "dual_credit_indicator"
                ],
                "high_school": first[
                    "high_school"
                ],
                "last_term_dual_credit": first[
                    "last_term_dual_credit"
                ],
                "raw_row_count": len(
                    group
                ),
                "linked_section_count": len(
                    sections
                ),
            }
        )

    collapsed = pd.DataFrame(
        collapsed_rows
    )

    summer = collapsed[
        collapsed[
            "term_sort"
        ].eq(
            202660
        )
    ]

    fall = collapsed[
        collapsed[
            "term_sort"
        ].eq(
            202690
        )
    ]

    if len(
        summer
    ) != EXPECTED_REFRESH_SUMMER_ATTEMPTS:
        raise RuntimeError(
            "Authoritative Summer normalized-attempt count changed: "
            f"{len(summer):,} != "
            f"{EXPECTED_REFRESH_SUMMER_ATTEMPTS:,}"
        )

    if len(
        fall
    ) != EXPECTED_REFRESH_FALL_ATTEMPTS:
        raise RuntimeError(
            "Authoritative Fall normalized-attempt count changed: "
            f"{len(fall):,} != "
            f"{EXPECTED_REFRESH_FALL_ATTEMPTS:,}"
        )

    if (
        fall[
            "final_grade"
        ]
        .ne("")
        .any()
    ):
        raise RuntimeError(
            "Fall 2026 contains a nonblank Final_Grade. "
            "The governed refresh state expects all Fall grades blank/in progress."
        )

    return collapsed


def build_current_attempt_state(
    candidate_students: set[str],
) -> tuple[pd.DataFrame, Path]:
    require(
        HISTORICAL_ATTEMPTS
    )

    historical = pd.read_csv(
        HISTORICAL_ATTEMPTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required = {
        "student_id",
        "student_major",
        "course_code",
        "final_grade",
        "term_taken",
        "term_sort",
    }

    missing = (
        required
        - set(
            historical.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Historical all-attempts file missing columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    historical[
        "student_id"
    ] = (
        historical[
            "student_id"
        ]
        .astype(str)
        .str.strip()
    )

    historical[
        "course_code"
    ] = historical[
        "course_code"
    ].map(
        normalize_course_code
    )

    historical[
        "final_grade"
    ] = historical[
        "final_grade"
    ].map(
        norm_grade
    )

    historical[
        "term_sort"
    ] = pd.to_numeric(
        historical[
            "term_sort"
        ],
        errors="coerce",
    )

    historical = historical[
        historical[
            "term_sort"
        ].notna()
    ].copy()

    historical[
        "term_sort"
    ] = (
        historical[
            "term_sort"
        ]
        .astype(int)
    )

    # October Summer snapshot supersedes July Summer state.
    historical = historical[
        ~historical[
            "term_sort"
        ].isin(
            [
                202660,
                202690,
            ]
        )
    ].copy()

    refresh_path = (
        find_refresh_workbook()
    )

    refresh_raw = pd.read_excel(
        refresh_path,
        sheet_name=REFRESH_SHEET,
        dtype=str,
    )

    refresh = normalize_refresh(
        refresh_raw
    )

    combined = pd.concat(
        [
            historical[
                [
                    "student_id",
                    "student_major",
                    "course_code",
                    "final_grade",
                    "term_taken",
                    "term_sort",
                ]
            ],
            refresh[
                [
                    "student_id",
                    "student_major",
                    "course_code",
                    "final_grade",
                    "term_taken",
                    "term_sort",
                ]
            ],
        ],
        ignore_index=True,
    )

    combined = combined[
        combined[
            "student_id"
        ].isin(
            candidate_students
        )
    ].copy()

    # Exact duplicate protection only. Distinct repeated attempts remain.
    combined = combined.drop_duplicates(
        subset=[
            "student_id",
            "student_major",
            "course_code",
            "final_grade",
            "term_taken",
            "term_sort",
        ]
    ).copy()

    return (
        combined,
        refresh_path,
    )


def weighted_gpa(
    frame: pd.DataFrame,
) -> tuple[
    float,
    float,
    float,
]:
    valid = frame[
        frame[
            "grade"
        ].isin(
            GRADE_POINTS
        )
        & frame[
            "derived_hours"
        ].notna()
    ].copy()

    if valid.empty:
        return (
            np.nan,
            0.0,
            0.0,
        )

    quality_points = sum(
        GRADE_POINTS[
            grade
        ]
        * float(
            hours
        )
        for grade, hours
        in zip(
            valid[
                "grade"
            ],
            valid[
                "derived_hours"
            ],
        )
    )

    gpa_hours = float(
        valid[
            "derived_hours"
        ].sum()
    )

    return (
        (
            quality_points
            / gpa_hours
        )
        if gpa_hours
        else np.nan,
        float(
            quality_points
        ),
        gpa_hours,
    )


def institutional_gpa_table(
    attempts: pd.DataFrame,
) -> pd.DataFrame:
    frame = attempts.copy()

    frame[
        "grade"
    ] = frame[
        "final_grade"
    ].map(
        norm_grade
    )

    frame[
        "derived_hours"
    ] = frame[
        "course_code"
    ].map(
        derived_hours
    )

    frame[
        "rank"
    ] = frame[
        "grade"
    ].map(
        GRADE_RANK
    )

    resident = frame[
        frame[
            "grade"
        ].isin(
            GRADE_POINTS
        )
    ].copy()

    resident[
        "term_sort_numeric"
    ] = pd.to_numeric(
        resident[
            "term_sort"
        ],
        errors="coerce",
    )

    resolved = (
        resident.sort_values(
            [
                "student_id",
                "course_code",
                "rank",
                "term_sort_numeric",
            ],
            ascending=[
                True,
                True,
                False,
                False,
            ],
            kind="mergesort",
        )
        .drop_duplicates(
            [
                "student_id",
                "course_code",
            ],
            keep="first",
        )
        .copy()
    )

    rows = []

    for student_id, group in resolved.groupby(
        "student_id",
        sort=False,
    ):
        gpa, quality_points, gpa_hours = weighted_gpa(
            group.rename(
                columns={
                    "course_code": "course",
                }
            )
        )

        original = resident[
            resident[
                "student_id"
            ].eq(
                student_id
            )
        ]

        rows.append(
            {
                "student_id": student_id,
                "estimated_institutional_gpa": gpa,
                "institutional_quality_points": quality_points,
                "institutional_gpa_hours": gpa_hours,
                "repeated_course_count": int(
                    original[
                        "course_code"
                    ]
                    .value_counts()
                    .gt(
                        1
                    )
                    .sum()
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def credential_inventory(
    candidates: pd.DataFrame,
    applied: pd.DataFrame,
    requirements: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resolve awardability metadata without overwriting/colliding with columns
    already carried forward from the official-award screening product.

    Program hours are calculated from the exact selected requirement stream:
        common requirements + selected alternative path only.
    """
    requirement_hours = (
        applied[
            KEY
            + [
                "requirement_id",
                "requirement_credit_hours",
            ]
        ]
        .drop_duplicates(
            KEY
            + [
                "requirement_id",
            ]
        )
        .copy()
    )

    requirement_hours[
        "requirement_credit_hours"
    ] = pd.to_numeric(
        requirement_hours[
            "requirement_credit_hours"
        ],
        errors="coerce",
    )

    bad = requirement_hours[
        "requirement_credit_hours"
    ].isna()

    if bad.any():
        raise RuntimeError(
            "Selected applied-course evidence contains "
            f"{int(bad.sum()):,} requirements with unresolved credit hours."
        )

    program = (
        requirement_hours.groupby(
            KEY,
            dropna=False,
        )[
            "requirement_credit_hours"
        ]
        .sum()
        .rename(
            "awardability_program_hours"
        )
        .reset_index()
    )

    title_col = (
        "credential_title"
        if "credential_title"
        in requirements.columns
        else None
    )

    if title_col is None:
        titles = (
            candidates[
                KEY
            ]
            .copy()
            .assign(
                awardability_credential_title=""
            )
        )
    else:
        titles = (
            requirements[
                [
                    "catalog_year",
                    "credential_id",
                    title_col,
                ]
            ]
            .drop_duplicates(
                [
                    "catalog_year",
                    "credential_id",
                ]
            )
            .rename(
                columns={
                    title_col:
                        "awardability_credential_title"
                }
            )
        )

    result = (
        candidates[
            KEY
        ]
        .merge(
            program,
            on=KEY,
            how="left",
            validate="one_to_one",
        )
        .merge(
            titles,
            on=[
                "catalog_year",
                "credential_id",
            ],
            how="left",
            validate="many_to_one",
        )
    )

    if result[
        "awardability_program_hours"
    ].isna().any():
        raise RuntimeError(
            "Program hours could not be resolved for "
            f"{int(result['awardability_program_hours'].isna().sum()):,} candidates."
        )

    result[
        "awardability_credential_title"
    ] = result[
        "awardability_credential_title"
    ].fillna("")

    # If the screening universe already carries a title, prove that it does not
    # conflict with the requirements-master title. Do not silently choose.
    if "credential_title" in candidates.columns:
        source_titles = (
            candidates[
                KEY
                + [
                    "credential_title",
                ]
            ]
            .copy()
            .rename(
                columns={
                    "credential_title":
                        "source_credential_title"
                }
            )
        )

        result = result.merge(
            source_titles,
            on=KEY,
            how="left",
            validate="one_to_one",
        )

        left = (
            result[
                "source_credential_title"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        right = (
            result[
                "awardability_credential_title"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        conflicts = (
            left.ne("")
            & right.ne("")
            & left.ne(right)
        )

        if conflicts.any():
            result.loc[
                conflicts
            ].to_csv(
                OUTPUT_DIR
                / "RESTRICTED_ERROR_credential_title_conflicts.csv",
                index=False,
            )

            raise RuntimeError(
                "Credential-title conflict between the official-award "
                "screening product and requirements master. Diagnostic written."
            )

        result[
            "awardability_credential_title"
        ] = result[
            "awardability_credential_title"
        ].where(
            right.ne(""),
            result[
                "source_credential_title"
            ],
        )

    return result


def validate_selected_dependency_paths(
    selected_detail: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate the intra-credential alternative/dependency paths at the
    REQUIREMENT level.

    Important:
      path_expected_applied_hours is requirement/path metadata and is carried
      in RESTRICTED_unsuppressed_complete_selected_detail.csv, not in the
      exploded applied-course output.

    The applied-course reconstruction already selected:
        common requirements + path_selected == TRUE
    This function independently proves that the selected requirement stream is
    internally consistent before awardability is calculated.
    """
    required = {
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "path_group_id",
        "path_id",
        "path_selected",
        "path_expected_applied_hours",
    }

    missing = (
        required
        - set(
            selected_detail.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Selected-detail evidence is missing path columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    work = selected_detail.copy()

    for column in KEY + [
        "requirement_id",
        "path_group_id",
        "path_id",
        "path_selected",
        "path_expected_applied_hours",
    ]:
        work[column] = (
            work[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # The selected-detail file itself should contain only common rows and
    # selected alternative-path rows. Re-prove that here.
    alt = work[
        work[
            "path_group_id"
        ].ne("")
    ].copy()

    bad_selected = alt[
        ~alt[
            "path_selected"
        ]
        .str.upper()
        .eq(
            "TRUE"
        )
    ]

    if not bad_selected.empty:
        bad_selected.to_csv(
            OUTPUT_DIR
            / "RESTRICTED_ERROR_unselected_dependency_path_rows.csv",
            index=False,
        )

        raise RuntimeError(
            "Selected-detail evidence contains an unselected alternative-path row. "
            "Diagnostic written."
        )

    if alt.empty:
        candidate_paths = (
            work[
                KEY
            ]
            .drop_duplicates()
            .copy()
        )

        candidate_paths[
            "uses_alternative_dependency_path"
        ] = False

        candidate_paths[
            "selected_dependency_path_ids"
        ] = ""

        candidate_paths[
            "dependency_path_validation_status"
        ] = "NO_ALTERNATIVE_PATH"

        return candidate_paths

    # A selected path group must point to exactly one selected path_id, and the
    # selected requirements must reconcile to the path's declared expected hours.
    #
    # requirement_credit_hours is present in the selected-detail output only if
    # the engine emitted it; otherwise recover requirement hours from the already
    # reconstructed requirement evidence is inappropriate here. We therefore use
    # path_expected_applied_hours as a declared path-level invariant and validate
    # one consistent declaration per selected path group.
    path_groups = (
        alt.groupby(
            KEY
            + [
                "path_group_id",
            ],
            dropna=False,
        )
        .agg(
            selected_path_id_count=(
                "path_id",
                "nunique",
            ),
            selected_dependency_path_ids=(
                "path_id",
                lambda s:
                    " | ".join(
                        sorted(
                            {
                                str(v).strip()
                                for v in s
                                if str(v).strip()
                            }
                        )
                    ),
            ),
            expected_applied_hour_variants=(
                "path_expected_applied_hours",
                lambda s:
                    len(
                        {
                            str(v).strip()
                            for v in s
                            if str(v).strip()
                        }
                    ),
            ),
            declared_path_expected_applied_hours=(
                "path_expected_applied_hours",
                lambda s:
                    " | ".join(
                        sorted(
                            {
                                str(v).strip()
                                for v in s
                                if str(v).strip()
                            }
                        )
                    ),
            ),
            selected_path_requirement_rows=(
                "requirement_id",
                "nunique",
            ),
        )
        .reset_index()
    )

    path_groups[
        "dependency_path_metadata_valid"
    ] = (
        path_groups[
            "selected_path_id_count"
        ].eq(1)
        & path_groups[
            "expected_applied_hour_variants"
        ].eq(1)
        & path_groups[
            "declared_path_expected_applied_hours"
        ].ne("")
    )

    bad = path_groups[
        ~path_groups[
            "dependency_path_metadata_valid"
        ]
    ]

    if not bad.empty:
        bad.to_csv(
            OUTPUT_DIR
            / "RESTRICTED_ERROR_dependency_path_metadata_mismatches.csv",
            index=False,
        )

        raise RuntimeError(
            "Selected alternative/dependency-path metadata failed validation "
            f"for {len(bad):,} path groups. Diagnostic written."
        )

    candidate_paths = (
        work[
            KEY
        ]
        .drop_duplicates()
        .copy()
    )

    path_summary = (
        path_groups.groupby(
            KEY,
            dropna=False,
        )
        .agg(
            selected_dependency_path_ids=(
                "selected_dependency_path_ids",
                lambda s:
                    " | ".join(
                        sorted(
                            {
                                str(v).strip()
                                for v in s
                                if str(v).strip()
                            }
                        )
                    ),
            ),
        )
        .reset_index()
    )

    candidate_paths = candidate_paths.merge(
        path_summary,
        on=KEY,
        how="left",
        validate="one_to_one",
    )

    candidate_paths[
        "selected_dependency_path_ids"
    ] = (
        candidate_paths[
            "selected_dependency_path_ids"
        ]
        .fillna("")
    )

    candidate_paths[
        "uses_alternative_dependency_path"
    ] = candidate_paths[
        "selected_dependency_path_ids"
    ].ne("")

    candidate_paths[
        "dependency_path_validation_status"
    ] = np.where(
        candidate_paths[
            "uses_alternative_dependency_path"
        ],
        "SELECTED_PATH_METADATA_VALIDATED",
        "NO_ALTERNATIVE_PATH",
    )

    return candidate_paths


def classify_by_hours(
    program_hours: float,
    credential_title: str,
) -> str:
    """
    Preserve the controlled rule from the prior corrected awardability screen:
      - every 60-hour credential is an associate;
      - the 57-hour Court Reporting credential is an associate;
      - everything else is a certificate;
      - there are no IA credentials in the modeled audit universe.
    """
    title = text(
        credential_title
    ).upper()

    if (
        pd.notna(
            program_hours
        )
        and abs(
            float(
                program_hours
            )
            - 60.0
        )
        < 0.001
    ):
        return "ASSOCIATE"

    if (
        pd.notna(
            program_hours
        )
        and abs(
            float(
                program_hours
            )
            - 57.0
        )
        < 0.001
        and "COURT"
        in title
        and "REPORT"
        in title
    ):
        return "ASSOCIATE"

    return "CERT"


def residency_policy(
    catalog_year: str,
    credential_type: str,
    program_hours: float,
) -> tuple[
    str,
    float,
    float,
]:
    if (
        pd.isna(
            program_hours
        )
        or float(
            program_hours
        )
        <= 0
    ):
        return (
            "PROGRAM_HOURS_UNRESOLVED",
            np.nan,
            np.nan,
        )

    start_year = catalog_start_year(
        catalog_year
    )

    if start_year is None:
        return (
            "CATALOG_YEAR_UNRESOLVED",
            np.nan,
            np.nan,
        )

    quarter = int(
        math.ceil(
            float(
                program_hours
            )
            * 0.25
        )
    )

    if (
        credential_type
        == "ASSOCIATE"
    ):
        if start_year >= 2025:
            return (
                "ASSOCIATE_25_PERCENT_MINIMUM_15",
                max(
                    quarter,
                    15,
                ),
                0,
            )

        return (
            "ASSOCIATE_25_PERCENT_PLUS_12_UPPER_OR_CORE",
            quarter,
            12,
        )

    if start_year >= 2025:
        return (
            "CERTIFICATE_25_PERCENT",
            quarter,
            0,
        )

    return (
        "CERTIFICATE_FIXED_13_HOURS",
        13,
        0,
    )


def minimum_c_evaluation(
    award_courses: pd.DataFrame,
    credential_id: str,
    credential_title: str,
) -> tuple[
    str,
    str,
    float,
    float,
    float,
    int,
    int,
    str,
]:
    """
    Port the previously validated/finalized minimum-C treatment EXACTLY.

    Prior validated sequence:
      1. estimated major = applied non-core / non-elective courses
      2. D or F in that set => FAIL
      3. nonempty set with no D/F => PASS
      4. empty estimated-major set => REVIEW
      5. ONLY when a General Studies / Liberal Arts case was REVIEW,
         finalize it to NOT_APPLICABLE

    Do not promote transfer/special grades to new REVIEW/FAIL semantics here.
    The prior pipeline handled unresolved transfer-major questions in its
    separate transfer-credit diagnostic stage.
    """
    title = text(
        credential_title
    ).upper()

    credential = text(
        credential_id
    ).upper()

    general_academic = (
        "GENERAL STUDIES"
        in title
        or "LIBERAL ARTS"
        in title
        or "GENERAL_STUDIES"
        in credential
        or "LIBERAL_ARTS"
        in credential
    )

    major = award_courses[
        award_courses[
            "estimated_major_bool"
        ]
    ].copy()

    major_gpa, major_qp, major_gpa_hours = weighted_gpa(
        major
    )

    below_c = major[
        major[
            "grade"
        ].isin(
            {
                "D",
                "F",
            }
        )
    ]

    if major.empty:
        status = "REVIEW"
        reason = (
            "ESTIMATED_MAJOR_COURSES_UNRESOLVED"
        )

    elif not below_c.empty:
        status = "FAIL"
        reason = (
            "ESTIMATED_MAJOR_COURSE_BELOW_C"
        )

    else:
        status = "PASS"
        reason = ""

    # Exact behavior of finalize_minimum_c_treatment.py:
    # only general-academic rows that were REVIEW become NOT_APPLICABLE.
    if (
        general_academic
        and status == "REVIEW"
    ):
        status = (
            "NOT_APPLICABLE"
        )
        reason = ""

    codes = " | ".join(
        sorted(
            set(
                below_c[
                    "course"
                ]
                .dropna()
                .astype(str)
            )
        )
    )

    return (
        status,
        reason,
        major_gpa,
        major_qp,
        major_gpa_hours,
        len(
            major
        ),
        len(
            below_c
        ),
        codes,
    )


def main() -> None:
    for path in (
        CANDIDATES,
        APPLIED,
        SELECTED_DETAIL,
        RECONCILIATION,
        HISTORICAL_ATTEMPTS,
        REQUIREMENTS,
    ):
        require(
            path
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    candidates = pd.read_csv(
        CANDIDATES,
        dtype=str,
        low_memory=False,
    ).fillna("")

    applied = pd.read_csv(
        APPLIED,
        dtype=str,
        low_memory=False,
    ).fillna("")

    selected_detail = pd.read_csv(
        SELECTED_DETAIL,
        dtype=str,
        low_memory=False,
    ).fillna("")

    reconciliation = pd.read_csv(
        RECONCILIATION,
        dtype=str,
        low_memory=False,
    ).fillna("")

    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    if len(
        candidates
    ) != EXPECTED_CANDIDATES:
        raise RuntimeError(
            "Candidate universe changed: "
            f"{len(candidates):,} != "
            f"{EXPECTED_CANDIDATES:,}"
        )

    if (
        reconciliation[
            "detail_count_matches_summary"
        ]
        .map(
            as_bool
        )
        .sum()
        != EXPECTED_CANDIDATES
    ):
        raise RuntimeError(
            "Applied-course evidence reconciliation is no longer fully clean."
        )

    if candidates.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Candidate file is not unique at student/catalog/credential grain."
        )

    candidate_keys = set(
        candidates[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    applied_keys = set(
        applied[
            KEY
        ].drop_duplicates()
        .itertuples(
            index=False,
            name=None,
        )
    )

    if (
        candidate_keys
        != applied_keys
    ):
        raise RuntimeError(
            "Applied-course candidate key coverage differs from the "
            "1,410-row screening universe."
        )

    candidate_students = set(
        candidates[
            "student_id"
        ].astype(str)
    )

    # ------------------------------------------------------------------
    # Current authoritative all-attempt state for candidate students.
    # ------------------------------------------------------------------
    current_attempts, refresh_path = (
        build_current_attempt_state(
            candidate_students
        )
    )

    current_attempts.to_csv(
        CURRENT_ATTEMPTS_OUT,
        index=False,
    )

    institutional = institutional_gpa_table(
        current_attempts
    )

    institutional.to_csv(
        INST_GPA_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # Prepare applied-course evidence.
    # ------------------------------------------------------------------
    applied[
        "course"
    ] = applied[
        "course"
    ].map(
        normalize_course_code
    )

    applied[
        "grade"
    ] = applied[
        "grade"
    ].map(
        norm_grade
    )

    applied[
        "derived_hours"
    ] = pd.to_numeric(
        applied[
            "derived_hours"
        ],
        errors="coerce",
    )

    applied[
        "course_level"
    ] = pd.to_numeric(
        applied[
            "course_level"
        ],
        errors="coerce",
    )

    applied[
        "is_core_bool"
    ] = applied[
        "is_core"
    ].map(
        as_bool
    )

    applied[
        "is_elective_bool"
    ] = applied[
        "is_elective"
    ].map(
        as_bool
    )

    applied[
        "estimated_major_bool"
    ] = applied[
        "estimated_major"
    ].map(
        as_bool
    )

    if applied[
        "derived_hours"
    ].isna().any():
        raise RuntimeError(
            "Applied-course evidence now contains unresolved course hours."
        )

    selected_detail_keys = set(
        selected_detail[
            KEY
        ]
        .drop_duplicates()
        .itertuples(
            index=False,
            name=None,
        )
    )

    if selected_detail_keys != candidate_keys:
        raise RuntimeError(
            "Selected-detail candidate key coverage differs from the "
            "1,410-row screening universe."
        )

    dependency_paths = validate_selected_dependency_paths(
        selected_detail
    )

    inventory = credential_inventory(
        candidates,
        applied,
        requirements,
    )

    inventory[
        "awardability_credential_type"
    ] = [
        classify_by_hours(
            hours,
            title,
        )
        for hours, title
        in zip(
            inventory[
                "awardability_program_hours"
            ],
            inventory[
                "awardability_credential_title"
            ],
        )
    ]

    screened = (
        candidates.merge(
            inventory[
                KEY
                + [
                    "awardability_credential_title",
                    "awardability_program_hours",
                    "awardability_credential_type",
                ]
            ],
            on=KEY,
            how="left",
            validate="one_to_one",
        )
        .merge(
            dependency_paths,
            on=KEY,
            how="left",
            validate="one_to_one",
        )
    )

    rows: list[dict] = []

    for award in screened.itertuples(
        index=False,
    ):
        award_courses = applied[
            applied[
                "student_id"
            ].eq(
                award.student_id
            )
            & applied[
                "catalog_year"
            ].eq(
                award.catalog_year
            )
            & applied[
                "credential_id"
            ].eq(
                award.credential_id
            )
        ].copy()

        reasons: list[str] = []

        program_hours = float(
            award.awardability_program_hours
        )

        # --------------------------------------------------------------
        # Applied-hours and failing-grade gates from the corrected old screen.
        # --------------------------------------------------------------
        applied_program_hours = float(
            award_courses[
                "derived_hours"
            ].sum()
        )

        if (
            applied_program_hours
            + 1e-9
            >= program_hours
        ):
            applied_hours_status = (
                "PASS"
            )
        else:
            applied_hours_status = (
                "FAIL"
            )

            reasons.append(
                "APPLIED_PROGRAM_HOURS_BELOW_REQUIREMENT"
            )

        failing_applied = award_courses[
            award_courses[
                "grade"
            ].isin(
                {
                    "F",
                    "TF",
                }
            )
        ]

        if failing_applied.empty:
            applied_failing_grade_status = (
                "PASS"
            )
        else:
            applied_failing_grade_status = (
                "FAIL"
            )

            reasons.append(
                "APPLIED_FAILING_GRADE_PRESENT"
            )

        # --------------------------------------------------------------
        # Residency — existing catalog-year rules.
        # --------------------------------------------------------------
        (
            policy_name,
            required_resident,
            required_special,
        ) = residency_policy(
            award.catalog_year,
            award.awardability_credential_type,
            program_hours,
        )

        resident_earned = award_courses[
            award_courses[
                "grade"
            ].isin(
                {
                    "A",
                    "B",
                    "C",
                    "D",
                }
            )
        ].copy()

        resident_hours = float(
            resident_earned[
                "derived_hours"
            ].sum()
        )

        special_resident = resident_earned[
            resident_earned[
                "course_level"
            ].eq(
                2
            )
            | resident_earned[
                "is_core_bool"
            ]
        ]

        special_hours = float(
            special_resident[
                "derived_hours"
            ].sum()
        )

        if (
            pd.isna(
                required_resident
            )
            or pd.isna(
                required_special
            )
        ):
            residency_status = (
                "REVIEW"
            )

            reasons.append(
                "RESIDENCY_POLICY_UNRESOLVED"
            )

        elif (
            resident_hours
            >= float(
                required_resident
            )
            and special_hours
            >= float(
                required_special
            )
        ):
            residency_status = (
                "PASS"
            )

        else:
            residency_status = (
                "FAIL"
            )

            if (
                resident_hours
                < float(
                    required_resident
                )
            ):
                reasons.append(
                    "RESIDENCY_HOURS_BELOW_MINIMUM"
                )

            if (
                special_hours
                < float(
                    required_special
                )
            ):
                reasons.append(
                    "SPECIAL_RESIDENCY_HOURS_BELOW_MINIMUM"
                )

        # --------------------------------------------------------------
        # Certificate plan GPA.
        # --------------------------------------------------------------
        certificate_gpa = np.nan
        certificate_quality_points = np.nan
        certificate_gpa_hours = np.nan
        certificate_gpa_status = (
            "NOT_APPLICABLE"
        )

        if (
            award.awardability_credential_type
            == "CERT"
        ):
            (
                certificate_gpa,
                certificate_quality_points,
                certificate_gpa_hours,
            ) = weighted_gpa(
                award_courses
            )

            if pd.isna(
                certificate_gpa
            ):
                certificate_gpa_status = (
                    "REVIEW"
                )

                reasons.append(
                    "CERTIFICATE_PLAN_GPA_UNRESOLVED"
                )

            elif (
                certificate_gpa
                >= 2.0
            ):
                certificate_gpa_status = (
                    "PASS"
                )

            else:
                certificate_gpa_status = (
                    "FAIL"
                )

                reasons.append(
                    "CERTIFICATE_PLAN_GPA_BELOW_2_00"
                )

        # --------------------------------------------------------------
        # Major minimum-C treatment — exact port of the prior finalized
        # screen. Transfer-major uncertainty remains a separate diagnostic.
        # --------------------------------------------------------------
        (
            minimum_c_status,
            minimum_c_reason,
            major_gpa,
            major_quality_points,
            major_gpa_hours,
            major_course_count,
            major_below_c_count,
            major_below_c_codes,
        ) = minimum_c_evaluation(
            award_courses,
            award.credential_id,
            award.awardability_credential_title,
        )

        if minimum_c_reason and (
            minimum_c_status
            in {
                "FAIL",
                "REVIEW",
            }
        ):
            reasons.append(
                minimum_c_reason
            )

        # --------------------------------------------------------------
        # Associate institutional GPA using current authoritative attempts.
        # --------------------------------------------------------------
        institutional_gpa = np.nan
        institutional_gpa_hours = np.nan
        institutional_gpa_status = (
            "NOT_APPLICABLE"
        )
        repeated_course_count = np.nan

        if (
            award.awardability_credential_type
            == "ASSOCIATE"
        ):
            match = institutional[
                institutional[
                    "student_id"
                ].eq(
                    award.student_id
                )
            ]

            if match.empty:
                institutional_gpa_status = (
                    "REVIEW"
                )

                reasons.append(
                    "INSTITUTIONAL_GPA_UNRESOLVED"
                )

            else:
                record = match.iloc[
                    0
                ]

                institutional_gpa = pd.to_numeric(
                    pd.Series(
                        [
                            record[
                                "estimated_institutional_gpa"
                            ]
                        ]
                    ),
                    errors="coerce",
                ).iloc[
                    0
                ]

                institutional_gpa_hours = pd.to_numeric(
                    pd.Series(
                        [
                            record[
                                "institutional_gpa_hours"
                            ]
                        ]
                    ),
                    errors="coerce",
                ).iloc[
                    0
                ]

                repeated_course_count = pd.to_numeric(
                    pd.Series(
                        [
                            record[
                                "repeated_course_count"
                            ]
                        ]
                    ),
                    errors="coerce",
                ).iloc[
                    0
                ]

                if pd.isna(
                    institutional_gpa
                ):
                    institutional_gpa_status = (
                        "REVIEW"
                    )

                    reasons.append(
                        "INSTITUTIONAL_GPA_UNRESOLVED"
                    )

                elif (
                    institutional_gpa
                    >= 2.0
                ):
                    institutional_gpa_status = (
                        "PASS"
                    )

                else:
                    institutional_gpa_status = (
                        "FAIL"
                    )

                    reasons.append(
                        "INSTITUTIONAL_GPA_BELOW_2_00"
                    )

        # --------------------------------------------------------------
        # Overall ordinary awardability.
        # A REVIEW does not override an independent FAIL.
        # --------------------------------------------------------------
        formal_statuses = [
            residency_status,
            minimum_c_status,
            applied_hours_status,
            applied_failing_grade_status,
        ]

        if (
            award.awardability_credential_type
            == "ASSOCIATE"
        ):
            formal_statuses.append(
                institutional_gpa_status
            )
        else:
            formal_statuses.append(
                certificate_gpa_status
            )

        if "FAIL" in formal_statuses:
            overall = (
                "ACADEMIC_COMPLETE_SCREEN_FAIL"
            )

        elif "REVIEW" in formal_statuses:
            overall = (
                "ACADEMIC_COMPLETE_POLICY_REVIEW"
            )

        else:
            overall = (
                "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"
            )

        rows.append(
            {
                **award._asdict(),
                "residency_policy": policy_name,
                "estimated_resident_applied_hours": resident_hours,
                "required_resident_hours": required_resident,
                "estimated_special_resident_hours": special_hours,
                "required_special_resident_hours": required_special,
                "residency_status": residency_status,
                "estimated_institutional_gpa": institutional_gpa,
                "institutional_gpa_hours": institutional_gpa_hours,
                "institutional_gpa_status": institutional_gpa_status,
                "repeated_course_count": repeated_course_count,
                "estimated_certificate_plan_gpa": certificate_gpa,
                "certificate_plan_quality_points": certificate_quality_points,
                "certificate_plan_gpa_hours": certificate_gpa_hours,
                "certificate_plan_gpa_status": certificate_gpa_status,
                "estimated_major_gpa": major_gpa,
                "estimated_major_quality_points": major_quality_points,
                "estimated_major_gpa_hours": major_gpa_hours,
                "estimated_major_course_count": major_course_count,
                "estimated_major_courses_below_c": major_below_c_count,
                "estimated_major_courses_below_c_codes": major_below_c_codes,
                "minimum_c_status": minimum_c_status,
                "applied_course_count": len(
                    award_courses
                ),
                "applied_program_hours": applied_program_hours,
                "applied_program_hours_status": applied_hours_status,
                "applied_failing_grade_count": len(
                    failing_applied
                ),
                "applied_failing_grade_status": applied_failing_grade_status,
                "awardability_status": overall,
                "awardability_reasons": " | ".join(
                    sorted(
                        set(
                            reasons
                        )
                    )
                ),
            }
        )

    awardability = pd.DataFrame(
        rows
    )

    if len(
        awardability
    ) != EXPECTED_CANDIDATES:
        raise RuntimeError(
            "Awardability screen changed candidate row count."
        )

    if awardability.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Awardability output is not unique at student/catalog/credential."
        )

    passes = awardability[
        awardability[
            "awardability_status"
        ].eq(
            "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"
        )
    ].copy()

    failures = awardability[
        awardability[
            "awardability_status"
        ].eq(
            "ACADEMIC_COMPLETE_SCREEN_FAIL"
        )
    ].copy()

    reviews = awardability[
        awardability[
            "awardability_status"
        ].eq(
            "ACADEMIC_COMPLETE_POLICY_REVIEW"
        )
    ].copy()

    if (
        len(
            passes
        )
        + len(
            failures
        )
        + len(
            reviews
        )
        != len(
            awardability
        )
    ):
        raise RuntimeError(
            "Awardability partition does not reconcile."
        )

    awardability.to_csv(
        DETAIL_OUT,
        index=False,
    )

    passes.to_csv(
        PASS_OUT,
        index=False,
    )

    failures.to_csv(
        FAIL_OUT,
        index=False,
    )

    reviews.to_csv(
        REVIEW_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe summaries.
    # ------------------------------------------------------------------
    gate_columns = [
        "awardability_credential_type",
        "residency_status",
        "institutional_gpa_status",
        "certificate_plan_gpa_status",
        "minimum_c_status",
        "applied_program_hours_status",
        "applied_failing_grade_status",
        "awardability_status",
    ]

    gate_rows = []

    for column in gate_columns:
        for value, count in (
            awardability[
                column
            ]
            .fillna(
                "BLANK"
            )
            .value_counts(
                dropna=False
            )
            .items()
        ):
            gate_rows.append(
                {
                    "metric": column,
                    "value": value,
                    "count": int(
                        count
                    ),
                }
            )

    gate_summary = pd.DataFrame(
        gate_rows
    )

    gate_summary.to_csv(
        SAFE_GATE_SUMMARY_OUT,
        index=False,
    )

    by_catalog = (
        awardability.groupby(
            [
                "catalog_year",
                "awardability_status",
            ],
            dropna=False,
        )
        .agg(
            candidate_combinations=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
        .reset_index()
    )

    by_catalog.to_csv(
        SAFE_BY_CATALOG_OUT,
        index=False,
    )

    by_credential = (
        awardability.groupby(
            [
                "catalog_year",
                "credential_id",
                "awardability_credential_title",
                "awardability_credential_type",
                "awardability_program_hours",
                "awardability_status",
            ],
            dropna=False,
        )
        .agg(
            candidate_combinations=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "candidate_combinations",
                "catalog_year",
                "credential_id",
            ],
            ascending=[
                False,
                True,
                True,
            ],
        )
    )

    by_credential.to_csv(
        SAFE_BY_CREDENTIAL_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "input_unsuppressed_complete_combinations",
                "value": len(
                    awardability
                ),
            },
            {
                "metric": "awardability_pass_combinations",
                "value": len(
                    passes
                ),
            },
            {
                "metric": "awardability_fail_combinations",
                "value": len(
                    failures
                ),
            },
            {
                "metric": "awardability_review_combinations",
                "value": len(
                    reviews
                ),
            },
            {
                "metric": "candidate_students",
                "value": awardability[
                    "student_id"
                ].nunique(),
            },
            {
                "metric": "current_attempt_rows_candidate_students",
                "value": len(
                    current_attempts
                ),
            },
            {
                "metric": "current_institutional_gpa_students",
                "value": len(
                    institutional
                ),
            },
            {
                "metric": "authoritative_refresh_summer_attempts",
                "value": int(
                    current_attempts[
                        "term_sort"
                    ].eq(
                        202660
                    ).sum()
                ),
            },
            {
                "metric": "authoritative_refresh_fall_attempts",
                "value": int(
                    current_attempts[
                        "term_sort"
                    ].eq(
                        202690
                    ).sum()
                ),
            },
            {
                "metric": "candidates_using_validated_alternative_dependency_path",
                "value": int(
                    awardability[
                        "uses_alternative_dependency_path"
                    ].fillna(False).astype(bool).sum()
                ),
            },
            {
                "metric": "refresh_workbook",
                "value": str(
                    refresh_path
                ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 100)
    print("CURRENT ORDINARY AWARDABILITY SCREEN — COMPLETE")
    print("=" * 100)
    print("No curriculum audit was rerun.")
    print("No latest-catalog lineage selection was performed.")
    print("No second-associate/additional-certificate rule was applied.")
    print(
        "Intra-credential alternative/dependency paths: VALIDATED "
        "(common requirements + selected path metadata only)."
    )
    print(
        "Inter-credential parent/child stack dependencies: NOT APPLIED HERE; "
        "reserved for the multiple-award gate."
    )
    print(
        "Minimum-C / certificate-GPA semantics: exact prior finalized behavior; "
        "no new transfer-grade policy was introduced."
    )
    print()
    print(
        f"Input COMPLETE/unawarded combinations:     {len(awardability):,}"
    )
    print(
        f"Ordinary awardability PASS:                {len(passes):,}"
    )
    print(
        f"Ordinary awardability FAIL:                {len(failures):,}"
    )
    print(
        f"Ordinary awardability REVIEW:              {len(reviews):,}"
    )
    print()
    print("GATE COUNTS")
    for column in [
        "residency_status",
        "institutional_gpa_status",
        "certificate_plan_gpa_status",
        "minimum_c_status",
        "applied_program_hours_status",
        "applied_failing_grade_status",
    ]:
        print()
        print(
            column
        )
        print(
            awardability[
                column
            ]
            .value_counts(
                dropna=False
            )
            .to_string()
        )

    print()
    print("CREDENTIAL TYPE / PROGRAM-HOUR CHECK")
    print(
        awardability.groupby(
            [
                "awardability_credential_type",
                "awardability_program_hours",
            ],
            dropna=False,
        )
        .size()
        .sort_index()
        .to_string()
    )

    print()
    print(
        f"Refresh workbook: {refresh_path}"
    )
    print(
        f"Output directory: {OUTPUT_DIR}"
    )
    print()
    print(
        "NEXT GATE: parity review against the prior awardability results, "
        "then multiple-award rules (second associates / additional certificates)."
    )


if __name__ == "__main__":
    main()
