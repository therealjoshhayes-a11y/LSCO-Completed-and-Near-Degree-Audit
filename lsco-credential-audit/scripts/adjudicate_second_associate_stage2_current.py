from __future__ import annotations

import math
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd


# ======================================================================================
# GENERALIZED SECOND-ASSOCIATE — STAGE 2
# ======================================================================================
#
# Purpose:
#   Close the 2025+ second-associate cases wherever the FIRST prior associate
#   degree plan was successfully reconstructed as COMPLETE.
#
#   For each current candidate and for EVERY reconstructed COMPLETE prior plan:
#       target allocated courses
#       MINUS prior-plan allocated courses
#       => unique target courses
#
#   Then test:
#       >= 15 unique RESIDENT LSCO SCH
#       AND unique-resident GPA >= 2.0
#
#   This ports the recovered historical Stage-2 mechanics. If a current candidate
#   has ZERO reconstructed COMPLETE prior plans, it remains REVIEW rather than
#   being guessed from a near-complete/incomplete reconstruction.
#
# Important:
#   * Candidate grain is (student_id, catalog_year, credential_id), not student.
#     A student may legitimately have more than one current catalog-version case.
#   * PASS requires PASS under EVERY reconstructed COMPLETE prior plan.
#   * All FAIL decisions => FAIL.
#   * Mixed PASS/FAIL/REVIEW => REVIEW.
#   * Zero COMPLETE prior plans => REVIEW_NO_COMPLETE_PRIOR_PLAN_RECONSTRUCTION.
#
# Residence evidence:
#   The frozen current-attempt state has no explicit transfer/institution fields.
#   Therefore the recovered fallback semantics apply:
#       T/TA/TB/TC/TD/TS => NONRESIDENT
#       ordinary A/B/C/D/F/S/P/CR => RESIDENT
#       mixed/no signal => UNKNOWN
#
# This script does NOT:
#   * use NEAR_COMPLETE prior plans as if they were official plan allocations;
#   * invent substitutions for the 25 unreconstructed cases;
#   * adjudicate additional certificates;
#   * select latest catalog within lineage.
#
# Run:
#   python -u .\scripts\adjudicate_second_associate_stage2_current.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_STAGE2_PENDING = 39

TRANSFER_GRADE_CODES = {
    "T",
    "TA",
    "TB",
    "TC",
    "TD",
    "TS",
}

GPA_POINTS = {
    "A": 4.0,
    "B": 3.0,
    "C": 2.0,
    "D": 1.0,
    "F": 0.0,
}

PASSING_NON_GPA = {
    "S",
    "P",
    "CR",
}

COURSE_RE = re.compile(
    r"\b([A-Z]{2,5})\s*[- ]?\s*(\d{4}[A-Z]?)\b",
    re.I,
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"second_associate_stage2_current_{STAMP}"
)

RESTRICTED_CASES = (
    OUT_DIR
    / "RESTRICTED_second_associate_stage2_cases.csv"
)

RESTRICTED_COURSES = (
    OUT_DIR
    / "RESTRICTED_second_associate_stage2_unique_courses.csv"
)

RESTRICTED_FINAL = (
    OUT_DIR
    / "RESTRICTED_second_associate_stage2_final.csv"
)

SAFE_DECISIONS = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_stage2_decisions.csv"
)

SAFE_PRIOR_TESTS = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_stage2_prior_plan_tests.csv"
)

SAFE_REVIEWS = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_stage2_reviews.csv"
)

SAFE_METRICS = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_stage2_metrics.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def upper(value: object) -> str:
    return " ".join(
        txt(value).upper().split()
    )


def normalize_course(
    value: object,
) -> str:
    match = COURSE_RE.search(
        upper(value)
    )

    if not match:
        return ""

    return (
        f"{match.group(1).upper()} "
        f"{match.group(2).upper()}"
    )


def derive_hours(
    course: object,
) -> float:
    code = normalize_course(
        course
    )

    if not code:
        return np.nan

    number = code.split()[1]
    digits = "".join(
        ch
        for ch in number
        if ch.isdigit()
    )

    if len(
        digits
    ) < 2:
        return np.nan

    try:
        hours = int(
            digits[1]
        )
    except ValueError:
        return np.nan

    return (
        float(
            hours
        )
        if hours > 0
        else np.nan
    )


def split_semicolon(
    value: object,
) -> list[str]:
    raw = txt(
        value
    )

    if not raw:
        return []

    return [
        part.strip()
        for part in raw.split(
            ";"
        )
        if part.strip()
    ]


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
    matches = sorted(
        [
            path
            for path in REPORTING.glob(
                pattern
            )
            if (
                path.is_dir()
                and (
                    path
                    / required_name
                ).exists()
            )
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return matches[0]


def docx_text(
    path: Path,
) -> str:
    with zipfile.ZipFile(
        path
    ) as archive:
        raw = archive.read(
            "word/document.xml"
        )

    root = ET.fromstring(
        raw
    )

    return " ".join(
        node.text
        for node in root.iter()
        if (
            node.tag.endswith(
                "}t"
            )
            and node.text
        )
    )


def verify_2026_policy() -> tuple[bool, str]:
    """
    Verify that the local 2026-2027 catalog carries forward the modern
    15-additional-resident-hours rule before adjudicating 2026-2027 cases.
    """
    candidates = [
        ROOT
        / "data"
        / "raw"
        / "catalogs"
        / "2026-2027"
        / "2026-2027_Catalog.docx",
        ROOT
        / "data"
        / "raw"
        / "2026-2027 Catalog.docx",
    ]

    path = next(
        (
            value
            for value in candidates
            if value.exists()
        ),
        None,
    )

    if path is None:
        return (
            False,
            "2026-2027 catalog DOCX not found.",
        )

    body = " ".join(
        docx_text(
            path
        ).split()
    ).lower()

    required_fragments = [
        "fifteen (15) additional hours",
        "beyond the first degree plan",
        "in residence at lsco",
    ]

    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in body
    ]

    if missing:
        return (
            False,
            "2026-2027 catalog missing expected policy fragment(s): "
            + " | ".join(
                missing
            ),
        )

    return (
        True,
        str(
            path
        ),
    )


def extract_target_allocations(
    selected_detail: pd.DataFrame,
    pending_keys: set[
        tuple[
            str,
            str,
            str,
        ]
    ],
) -> pd.DataFrame:
    required = {
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "status",
        "matched_options",
        "matched_grades",
    }

    missing = (
        required
        - set(
            selected_detail.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Selected detail missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    tuples = selected_detail[
        [
            "student_id",
            "catalog_year",
            "credential_id",
        ]
    ].itertuples(
        index=False,
        name=None,
    )

    mask = [
        key
        in pending_keys
        for key in tuples
    ]

    detail = selected_detail.loc[
        mask
    ].copy()

    detail = detail[
        detail[
            "status"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq(
            "MET"
        )
    ].copy()

    rows = []

    for row in detail.itertuples(
        index=False
    ):
        courses = [
            normalize_course(
                value
            )
            for value in split_semicolon(
                row.matched_options
            )
        ]

        courses = [
            course
            for course in courses
            if course
        ]

        grades = [
            upper(
                value
            )
            for value in split_semicolon(
                row.matched_grades
            )
        ]

        terms = (
            split_semicolon(
                getattr(
                    row,
                    "matched_terms",
                    "",
                )
            )
            if "matched_terms"
            in detail.columns
            else []
        )

        for index, course in enumerate(
            courses
        ):
            rows.append(
                {
                    "student_id":
                        txt(
                            row.student_id
                        ),
                    "catalog_year":
                        txt(
                            row.catalog_year
                        ),
                    "credential_id":
                        txt(
                            row.credential_id
                        ),
                    "requirement_id":
                        txt(
                            row.requirement_id
                        ),
                    "course":
                        course,
                    "matched_grade":
                        (
                            grades[
                                index
                            ]
                            if index
                            < len(
                                grades
                            )
                            else ""
                        ),
                    "matched_term":
                        (
                            terms[
                                index
                            ]
                            if index
                            < len(
                                terms
                            )
                            else ""
                        ),
                    "hours":
                        derive_hours(
                            course
                        ),
                }
            )

    out = pd.DataFrame(
        rows
    )

    if out.empty:
        return out

    return (
        out.sort_values(
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "course",
                "requirement_id",
            ],
            kind="mergesort",
        )
        .drop_duplicates(
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "course",
            ],
            keep="first",
        )
    )


def residence_for_allocated_course(
    student_id: str,
    course: str,
    matched_grade: str,
    attempts: pd.DataFrame,
) -> tuple[
    str,
    str,
]:
    """
    Port of the recovered Stage-2 residence fallback under the current attempt
    schema, which has no explicit transfer/source/institution columns.
    """
    matched = upper(
        matched_grade
    )

    if matched in TRANSFER_GRADE_CODES:
        return (
            "NONRESIDENT",
            "MATCHED_TRANSFER_GRADE",
        )

    subset = attempts[
        attempts[
            "student_id"
        ].astype(str).eq(
            student_id
        )
        & attempts[
            "course_code"
        ].eq(
            course
        )
    ].copy()

    if subset.empty:
        if (
            matched
            in GPA_POINTS
            or matched
            in PASSING_NON_GPA
        ):
            return (
                "RESIDENT",
                "MATCHED_ORDINARY_GRADE_NO_ATTEMPT_METADATA",
            )

        return (
            "UNKNOWN",
            "ALLOCATED_COURSE_NOT_FOUND_IN_ATTEMPTS",
        )

    if matched:
        grade_match = (
            subset[
                "final_grade"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                matched
            )
        )

        if grade_match.any():
            subset = subset[
                grade_match
            ].copy()

    statuses = []

    for grade in (
        subset[
            "final_grade"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    ):
        if grade in TRANSFER_GRADE_CODES:
            statuses.append(
                (
                    "NONRESIDENT",
                    "TRANSFER_GRADE_CODE",
                )
            )

        elif (
            grade
            in GPA_POINTS
            or grade
            in PASSING_NON_GPA
        ):
            statuses.append(
                (
                    "RESIDENT",
                    "ORDINARY_GRADE_FALLBACK",
                )
            )

        else:
            statuses.append(
                (
                    "UNKNOWN",
                    "NO_RESIDENCE_SIGNAL",
                )
            )

    state_set = {
        state
        for state, _
        in statuses
    }

    if state_set == {
        "RESIDENT"
    }:
        return (
            "RESIDENT",
            "ORDINARY_GRADE_FALLBACK",
        )

    if state_set == {
        "NONRESIDENT"
    }:
        return (
            "NONRESIDENT",
            "TRANSFER_GRADE_CODE",
        )

    if (
        "RESIDENT"
        in state_set
        and "NONRESIDENT"
        not in state_set
    ):
        return (
            "RESIDENT",
            "ORDINARY_GRADE_FALLBACK",
        )

    if (
        "NONRESIDENT"
        in state_set
        and "RESIDENT"
        not in state_set
    ):
        return (
            "NONRESIDENT",
            "TRANSFER_GRADE_CODE",
        )

    if (
        "RESIDENT"
        in state_set
        and "NONRESIDENT"
        in state_set
    ):
        return (
            "UNKNOWN",
            "MIXED_RESIDENCE_EVIDENCE",
        )

    return (
        "UNKNOWN",
        "NO_RESIDENCE_SIGNAL",
    )


def weighted_gpa(
    rows: pd.DataFrame,
) -> tuple[
    float,
    float,
]:
    points = 0.0
    hours = 0.0

    for row in rows.itertuples(
        index=False
    ):
        grade = upper(
            row.matched_grade
        )

        sch = pd.to_numeric(
            pd.Series(
                [
                    row.hours
                ]
            ),
            errors="coerce",
        ).iloc[
            0
        ]

        if (
            grade
            not in GPA_POINTS
            or pd.isna(
                sch
            )
        ):
            continue

        points += (
            GPA_POINTS[
                grade
            ]
            * float(
                sch
            )
        )

        hours += float(
            sch
        )

    if hours == 0:
        return (
            np.nan,
            0.0,
        )

    return (
        points
        / hours,
        hours,
    )


def main() -> None:
    stage1_dir = latest_dir(
        "second_associate_stage1_current_*",
        "RESTRICTED_second_associate_stage2_pending.csv",
    )

    reconstruction_dir = latest_dir(
        "modern_second_associate_prior_plan_reconstruction_*",
        "RESTRICTED_reconstructed_prior_plan_candidates.csv",
    )

    applied_dir = latest_dir(
        "current_unsuppressed_applied_courses_*",
        "RESTRICTED_unsuppressed_complete_selected_detail.csv",
    )

    awardability_dir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_current_attempt_state_candidate_students.csv",
    )

    pending_path = (
        stage1_dir
        / "RESTRICTED_second_associate_stage2_pending.csv"
    )

    plan_path = (
        reconstruction_dir
        / "RESTRICTED_reconstructed_prior_plan_candidates.csv"
    )

    prior_alloc_path = (
        reconstruction_dir
        / "RESTRICTED_reconstructed_prior_plan_allocations.csv"
    )

    selected_detail_path = (
        applied_dir
        / "RESTRICTED_unsuppressed_complete_selected_detail.csv"
    )

    attempts_path = (
        awardability_dir
        / "RESTRICTED_current_attempt_state_candidate_students.csv"
    )

    for path in [
        pending_path,
        plan_path,
        prior_alloc_path,
        selected_detail_path,
        attempts_path,
    ]:
        if not path.exists():
            raise FileNotFoundError(
                path
            )

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    pending = pd.read_csv(
        pending_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    if len(
        pending
    ) != EXPECTED_STAGE2_PENDING:
        raise RuntimeError(
            "Stage-2 pending universe changed: "
            f"{len(pending):,} != "
            f"{EXPECTED_STAGE2_PENDING:,}"
        )

    if pending.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Pending universe is not unique at candidate key."
        )

    # 2026-2027 is adjudicated under the same modern rule only after direct
    # verification from the local 2026-2027 catalog.
    if pending[
        "catalog_year"
    ].eq(
        "2026-2027"
    ).any():
        verified, note = (
            verify_2026_policy()
        )

        if not verified:
            raise RuntimeError(
                "Cannot adjudicate 2026-2027 modern second-associate cases: "
                + note
            )

        policy_2026_evidence = (
            note
        )

    else:
        policy_2026_evidence = (
            "NO_2026_2027_PENDING_CASES"
        )

    plans = pd.read_csv(
        plan_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    prior_alloc = pd.read_csv(
        prior_alloc_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    selected_detail = pd.read_csv(
        selected_detail_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    attempts = pd.read_csv(
        attempts_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_attempts = {
        "student_id",
        "course_code",
        "final_grade",
    }

    missing = (
        required_attempts
        - set(
            attempts.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Current attempt source missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    attempts[
        "course_code"
    ] = attempts[
        "course_code"
    ].map(
        normalize_course
    )

    pending_keys = set(
        pending[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    target_alloc = extract_target_allocations(
        selected_detail,
        pending_keys,
    )

    if target_alloc.empty:
        raise RuntimeError(
            "No current target allocations found for Stage-2 pending cases."
        )

    target_coverage = set(
        target_alloc[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    missing_target_alloc = (
        pending_keys
        - target_coverage
    )

    if missing_target_alloc:
        raise RuntimeError(
            "Stage-2 pending candidate lacks current target allocation: "
            f"{len(missing_target_alloc):,}"
        )

    complete_plans = plans[
        plans[
            "audit_status"
        ].eq(
            "COMPLETE"
        )
    ].copy()

    # ------------------------------------------------------------------
    # Case-by-case / COMPLETE-prior-plan-by-prior-plan test.
    # ------------------------------------------------------------------
    case_rows = []
    course_rows = []

    for case in pending.itertuples(
        index=False
    ):
        student_id = txt(
            case.student_id
        )

        target_catalog = txt(
            case.catalog_year
        )

        target_credential = txt(
            case.credential_id
        )

        target = target_alloc[
            target_alloc[
                "student_id"
            ].eq(
                student_id
            )
            & target_alloc[
                "catalog_year"
            ].eq(
                target_catalog
            )
            & target_alloc[
                "credential_id"
            ].eq(
                target_credential
            )
        ].copy()

        target_courses = set(
            target[
                "course"
            ]
        )

        case_complete = complete_plans[
            complete_plans[
                "student_id"
            ].eq(
                student_id
            )
            & complete_plans[
                "target_catalog_year"
            ].eq(
                target_catalog
            )
            & complete_plans[
                "target_credential_id"
            ].eq(
                target_credential
            )
        ].copy()

        if case_complete.empty:
            case_rows.append(
                {
                    "student_id":
                        student_id,
                    "target_catalog_year":
                        target_catalog,
                    "target_credential_id":
                        target_credential,
                    "first_prior_family":
                        txt(
                            case.first_prior_family
                        ),
                    "first_prior_degree_code":
                        txt(
                            case.first_prior_degree_code
                        ),
                    "first_prior_grad_term":
                        txt(
                            case.first_prior_grad_term
                        ),
                    "prior_catalog_year":
                        "",
                    "prior_credential_id":
                        "",
                    "prior_plan_reconstruction_status":
                        "NO_COMPLETE_PRIOR_PLAN_RECONSTRUCTION",
                    "target_allocated_courses":
                        len(
                            target_courses
                        ),
                    "prior_allocated_courses":
                        0,
                    "shared_courses":
                        0,
                    "unique_target_courses":
                        len(
                            target_courses
                        ),
                    "unique_resident_sch":
                        np.nan,
                    "unique_nonresident_sch":
                        np.nan,
                    "unique_unknown_residence_sch":
                        np.nan,
                    "unique_resident_gpa":
                        np.nan,
                    "unique_resident_gpa_hours":
                        0.0,
                    "prior_plan_test_decision":
                        "REVIEW_NO_COMPLETE_PRIOR_PLAN_RECONSTRUCTION",
                }
            )

            continue

        for prior in case_complete.itertuples(
            index=False
        ):
            prior_catalog = txt(
                prior.prior_catalog_year
            )

            prior_credential = txt(
                prior.prior_credential_id
            )

            prior_rows = prior_alloc[
                prior_alloc[
                    "student_id"
                ].eq(
                    student_id
                )
                & prior_alloc[
                    "target_catalog_year"
                ].eq(
                    target_catalog
                )
                & prior_alloc[
                    "target_credential_id"
                ].eq(
                    target_credential
                )
                & prior_alloc[
                    "catalog_year"
                ].eq(
                    prior_catalog
                )
                & prior_alloc[
                    "credential_id"
                ].eq(
                    prior_credential
                )
            ].copy()

            if prior_rows.empty:
                raise RuntimeError(
                    "COMPLETE reconstructed prior plan has no allocated courses."
                )

            prior_rows[
                "course"
            ] = prior_rows[
                "course"
            ].map(
                normalize_course
            )

            prior_courses = set(
                prior_rows[
                    "course"
                ]
            )

            shared_courses = (
                target_courses
                & prior_courses
            )

            unique_courses = (
                target_courses
                - prior_courses
            )

            unique = target[
                target[
                    "course"
                ].isin(
                    unique_courses
                )
            ].copy()

            residence_statuses = []
            residence_methods = []

            for row in unique.itertuples(
                index=False
            ):
                status, method = (
                    residence_for_allocated_course(
                        student_id=student_id,
                        course=row.course,
                        matched_grade=row.matched_grade,
                        attempts=attempts,
                    )
                )

                residence_statuses.append(
                    status
                )

                residence_methods.append(
                    method
                )

            unique[
                "residence_status"
            ] = residence_statuses

            unique[
                "residence_method"
            ] = residence_methods

            unique[
                "hours_numeric"
            ] = pd.to_numeric(
                unique[
                    "hours"
                ],
                errors="coerce",
            )

            resident_sch = float(
                unique.loc[
                    unique[
                        "residence_status"
                    ].eq(
                        "RESIDENT"
                    ),
                    "hours_numeric",
                ].sum()
            )

            nonresident_sch = float(
                unique.loc[
                    unique[
                        "residence_status"
                    ].eq(
                        "NONRESIDENT"
                    ),
                    "hours_numeric",
                ].sum()
            )

            unknown_sch = float(
                unique.loc[
                    unique[
                        "residence_status"
                    ].eq(
                        "UNKNOWN"
                    ),
                    "hours_numeric",
                ].sum()
            )

            resident_rows = unique[
                unique[
                    "residence_status"
                ].eq(
                    "RESIDENT"
                )
            ].copy()

            gpa, gpa_hours = (
                weighted_gpa(
                    resident_rows
                )
            )

            if resident_sch >= 15:
                if pd.isna(
                    gpa
                ):
                    decision = (
                        "REVIEW_GPA_NOT_COMPUTABLE"
                    )

                elif gpa >= 2.0:
                    decision = (
                        "PASS_FOR_THIS_PRIOR_PLAN"
                    )

                else:
                    decision = (
                        "FAIL_GPA_FOR_THIS_PRIOR_PLAN"
                    )

            else:
                if (
                    resident_sch
                    + unknown_sch
                    >= 15
                ):
                    decision = (
                        "REVIEW_RESIDENCE_COULD_CHANGE_RESULT"
                    )

                else:
                    decision = (
                        "FAIL_UNIQUE_RESIDENT_HOURS_FOR_THIS_PRIOR_PLAN"
                    )

            case_rows.append(
                {
                    "student_id":
                        student_id,
                    "target_catalog_year":
                        target_catalog,
                    "target_credential_id":
                        target_credential,
                    "first_prior_family":
                        txt(
                            case.first_prior_family
                        ),
                    "first_prior_degree_code":
                        txt(
                            case.first_prior_degree_code
                        ),
                    "first_prior_grad_term":
                        txt(
                            case.first_prior_grad_term
                        ),
                    "prior_catalog_year":
                        prior_catalog,
                    "prior_credential_id":
                        prior_credential,
                    "prior_plan_reconstruction_status":
                        "COMPLETE_RECONSTRUCTED_PRIOR_PLAN",
                    "target_allocated_courses":
                        len(
                            target_courses
                        ),
                    "prior_allocated_courses":
                        len(
                            prior_courses
                        ),
                    "shared_courses":
                        len(
                            shared_courses
                        ),
                    "unique_target_courses":
                        len(
                            unique_courses
                        ),
                    "unique_resident_sch":
                        resident_sch,
                    "unique_nonresident_sch":
                        nonresident_sch,
                    "unique_unknown_residence_sch":
                        unknown_sch,
                    "unique_resident_gpa":
                        gpa,
                    "unique_resident_gpa_hours":
                        gpa_hours,
                    "prior_plan_test_decision":
                        decision,
                }
            )

            for row in unique.itertuples(
                index=False
            ):
                course_rows.append(
                    {
                        "student_id":
                            student_id,
                        "target_catalog_year":
                            target_catalog,
                        "target_credential_id":
                            target_credential,
                        "prior_catalog_year":
                            prior_catalog,
                        "prior_credential_id":
                            prior_credential,
                        "course":
                            row.course,
                        "hours":
                            row.hours,
                        "matched_grade":
                            row.matched_grade,
                        "matched_term":
                            row.matched_term,
                        "target_requirement_id":
                            row.requirement_id,
                        "residence_status":
                            row.residence_status,
                        "residence_method":
                            row.residence_method,
                    }
                )

    cases = pd.DataFrame(
        case_rows
    )

    unique_courses = pd.DataFrame(
        course_rows
    )

    if cases.empty:
        raise RuntimeError(
            "Stage-2 produced no case rows."
        )

    # ------------------------------------------------------------------
    # Collapse tests to one final decision per CURRENT CANDIDATE KEY.
    # ------------------------------------------------------------------
    final_rows = []

    for (
        student_id,
        catalog_year,
        credential_id,
    ), group in cases.groupby(
        [
            "student_id",
            "target_catalog_year",
            "target_credential_id",
        ],
        sort=True,
    ):
        decisions = set(
            group[
                "prior_plan_test_decision"
            ]
        )

        complete_group = group[
            group[
                "prior_plan_reconstruction_status"
            ].eq(
                "COMPLETE_RECONSTRUCTED_PRIOR_PLAN"
            )
        ].copy()

        if complete_group.empty:
            final_decision = (
                "REVIEW_SECOND_ASSOCIATE_2025_RULE"
            )

            final_reason = (
                "No reconstructed COMPLETE first-prior associate plan is "
                "available; near-complete/incomplete plans were not treated "
                "as substitutes."
            )

        else:
            complete_decisions = set(
                complete_group[
                    "prior_plan_test_decision"
                ]
            )

            if complete_decisions == {
                "PASS_FOR_THIS_PRIOR_PLAN"
            }:
                final_decision = (
                    "PASS_SECOND_ASSOCIATE_2025_RULE"
                )

                final_reason = (
                    "At least 15 unique resident SCH and GPA >= 2.0 "
                    "under every reconstructed COMPLETE prior plan."
                )

            elif all(
                decision.startswith(
                    "FAIL_"
                )
                for decision
                in complete_decisions
            ):
                final_decision = (
                    "FAIL_SECOND_ASSOCIATE_2025_RULE"
                )

                final_reason = (
                    "Fails the modern second-associate rule under every "
                    "reconstructed COMPLETE prior plan."
                )

            else:
                final_decision = (
                    "REVIEW_SECOND_ASSOCIATE_2025_RULE"
                )

                final_reason = (
                    "Result depends on reconstructed prior-plan choice, "
                    "residence evidence, or GPA computability."
                )

        final_rows.append(
            {
                "student_id":
                    student_id,
                "catalog_year":
                    catalog_year,
                "credential_id":
                    credential_id,
                "reconstructed_complete_prior_plan_count":
                    len(
                        complete_group
                    ),
                "min_unique_resident_sch":
                    pd.to_numeric(
                        complete_group[
                            "unique_resident_sch"
                        ],
                        errors="coerce",
                    ).min()
                    if not complete_group.empty
                    else np.nan,
                "max_unique_resident_sch":
                    pd.to_numeric(
                        complete_group[
                            "unique_resident_sch"
                        ],
                        errors="coerce",
                    ).max()
                    if not complete_group.empty
                    else np.nan,
                "min_unique_resident_gpa":
                    pd.to_numeric(
                        complete_group[
                            "unique_resident_gpa"
                        ],
                        errors="coerce",
                    ).min()
                    if not complete_group.empty
                    else np.nan,
                "max_unique_resident_gpa":
                    pd.to_numeric(
                        complete_group[
                            "unique_resident_gpa"
                        ],
                        errors="coerce",
                    ).max()
                    if not complete_group.empty
                    else np.nan,
                "final_stage2_decision":
                    final_decision,
                "final_stage2_reason":
                    final_reason,
            }
        )

    final = pd.DataFrame(
        final_rows
    )

    if len(
        final
    ) != EXPECTED_STAGE2_PENDING:
        raise RuntimeError(
            "Final Stage-2 candidate count changed: "
            f"{len(final):,} != "
            f"{EXPECTED_STAGE2_PENDING:,}"
        )

    cases = cases.merge(
        final[
            KEY
            + [
                "final_stage2_decision",
                "final_stage2_reason",
            ]
        ].rename(
            columns={
                "catalog_year":
                    "target_catalog_year",
                "credential_id":
                    "target_credential_id",
            }
        ),
        on=[
            "student_id",
            "target_catalog_year",
            "target_credential_id",
        ],
        how="left",
        validate="many_to_one",
    )

    cases.to_csv(
        RESTRICTED_CASES,
        index=False,
    )

    unique_courses.to_csv(
        RESTRICTED_COURSES,
        index=False,
    )

    final.to_csv(
        RESTRICTED_FINAL,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe outputs.
    # ------------------------------------------------------------------
    decisions_safe = (
        final.groupby(
            "final_stage2_decision",
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
            "candidate_combinations",
            ascending=False,
        )
    )

    decisions_safe.to_csv(
        SAFE_DECISIONS,
        index=False,
    )

    prior_safe = (
        cases.groupby(
            [
                "first_prior_family",
                "first_prior_degree_code",
                "prior_plan_reconstruction_status",
                "prior_plan_test_decision",
            ],
            dropna=False,
        )
        .agg(
            prior_plan_tests=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            min_unique_resident_sch=(
                "unique_resident_sch",
                "min",
            ),
            max_unique_resident_sch=(
                "unique_resident_sch",
                "max",
            ),
            min_unique_resident_gpa=(
                "unique_resident_gpa",
                "min",
            ),
            max_unique_resident_gpa=(
                "unique_resident_gpa",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            "prior_plan_tests",
            ascending=False,
        )
    )

    prior_safe.to_csv(
        SAFE_PRIOR_TESTS,
        index=False,
    )

    review_keys = set(
        final.loc[
            final[
                "final_stage2_decision"
            ].eq(
                "REVIEW_SECOND_ASSOCIATE_2025_RULE"
            ),
            KEY,
        ].itertuples(
            index=False,
            name=None,
        )
    )

    if review_keys:
        case_key_tuples = list(
            cases[
                [
                    "student_id",
                    "target_catalog_year",
                    "target_credential_id",
                ]
            ].itertuples(
                index=False,
                name=None,
            )
        )

        review_mask = [
            key
            in review_keys
            for key
            in case_key_tuples
        ]

        review_cases = cases.loc[
            review_mask
        ].copy()

        review_safe = (
            review_cases.groupby(
                [
                    "first_prior_family",
                    "first_prior_degree_code",
                    "prior_plan_reconstruction_status",
                    "prior_plan_test_decision",
                    "final_stage2_reason",
                ],
                dropna=False,
            )
            .agg(
                candidate_or_plan_rows=(
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
                "candidate_or_plan_rows",
                ascending=False,
            )
        )
    else:
        review_safe = pd.DataFrame()

    review_safe.to_csv(
        SAFE_REVIEWS,
        index=False,
    )

    pass_count = int(
        final[
            "final_stage2_decision"
        ].eq(
            "PASS_SECOND_ASSOCIATE_2025_RULE"
        ).sum()
    )

    fail_count = int(
        final[
            "final_stage2_decision"
        ].eq(
            "FAIL_SECOND_ASSOCIATE_2025_RULE"
        ).sum()
    )

    review_count = int(
        final[
            "final_stage2_decision"
        ].eq(
            "REVIEW_SECOND_ASSOCIATE_2025_RULE"
        ).sum()
    )

    zero_complete = int(
        final[
            "reconstructed_complete_prior_plan_count"
        ].eq(
            0
        ).sum()
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "stage2_pending_candidates",
                "value":
                    len(
                        final
                    ),
            },
            {
                "metric":
                    "stage2_pass",
                "value":
                    pass_count,
            },
            {
                "metric":
                    "stage2_fail",
                "value":
                    fail_count,
            },
            {
                "metric":
                    "stage2_review",
                "value":
                    review_count,
            },
            {
                "metric":
                    "stage2_review_zero_complete_prior_plan",
                "value":
                    zero_complete,
            },
            {
                "metric":
                    "reconstructed_complete_prior_plan_tests",
                "value":
                    int(
                        cases[
                            "prior_plan_reconstruction_status"
                        ].eq(
                            "COMPLETE_RECONSTRUCTED_PRIOR_PLAN"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "unique_course_evidence_rows",
                "value":
                    len(
                        unique_courses
                    ),
            },
            {
                "metric":
                    "policy_2026_verified",
                "value":
                    (
                        1
                        if policy_2026_evidence
                        != "NO_2026_2027_PENDING_CASES"
                        else 0
                    ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 112)
    print("GENERALIZED SECOND-ASSOCIATE — STAGE 2 COMPLETE")
    print("=" * 112)
    print(
        f"Stage-2 pending candidates:                {len(final):,}"
    )
    print(
        f"PASS_SECOND_ASSOCIATE_2025_RULE:           {pass_count:,}"
    )
    print(
        f"FAIL_SECOND_ASSOCIATE_2025_RULE:           {fail_count:,}"
    )
    print(
        f"REVIEW_SECOND_ASSOCIATE_2025_RULE:         {review_count:,}"
    )
    print(
        "  of which zero COMPLETE prior plan:       "
        f"{zero_complete:,}"
    )
    print()
    print("FINAL DECISIONS")
    print(
        decisions_safe.to_string(
            index=False
        )
    )
    print()
    print("PRIOR-PLAN TESTS")
    print(
        prior_safe.to_string(
            index=False
        )
    )
    print()
    if review_safe.empty:
        print("REVIEW BREAKDOWN: 0")
    else:
        print("REVIEW BREAKDOWN")
        print(
            review_safe.to_string(
                index=False
            )
        )
    print()
    print(
        "Control: only reconstructed COMPLETE prior plans were allowed "
        "to support Stage-2 PASS/FAIL."
    )
    print(
        "Control: NEAR_COMPLETE/INCOMPLETE reconstructions remain evidence "
        "only and were not substituted for an official prior plan."
    )
    print(
        "Control: PASS requires passing every reconstructed COMPLETE prior plan."
    )
    print(
        "Control: candidate grain is student/catalog/credential."
    )

    if pending[
        "catalog_year"
    ].eq(
        "2026-2027"
    ).any():
        print(
            "Control: 2026-2027 modern policy verified from local catalog: "
            + policy_2026_evidence
        )

    print()
    print(
        f"Stage-1 source:         {stage1_dir}"
    )
    print(
        f"Reconstruction source:  {reconstruction_dir}"
    )
    print(
        f"Target-detail source:   {applied_dir}"
    )
    print(
        f"Current-attempt source: {awardability_dir}"
    )
    print(
        f"Output directory:       {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
