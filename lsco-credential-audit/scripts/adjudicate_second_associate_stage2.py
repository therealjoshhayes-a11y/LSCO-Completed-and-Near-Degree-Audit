from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


# ======================================================================================
# CONFIGURATION
# ======================================================================================

ROOT = Path.cwd()

REPORT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "reporting"
    / "additional_awards_clean_query_20260803"
)

STAGE1 = (
    REPORT_DIR
    / "second_associate_review_20260811"
    / "RESTRICTED_SECOND_ASSOCIATE_STAGE1.csv"
)

SUMMARY = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "full_actual_credential_summary.csv"
)

DETAIL = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "full_actual_audit_results.csv"
)

CHUNK_DIR = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "chunks"
)

ATTEMPTS = (
    ROOT
    / "data"
    / "processed"
    / "all_student_course_attempts_normalized.csv"
)

FALLBACK_HISTORY = (
    ROOT
    / "data"
    / "processed"
    / "normalized_actual_student_course_history.csv"
)

OUTDIR = (
    REPORT_DIR
    / "second_associate_review_20260811"
    / "stage2_2025_unique_resident_hours"
)
OUTDIR.mkdir(parents=True, exist_ok=True)

RESTRICTED_CASES = OUTDIR / "RESTRICTED_SECOND_ASSOCIATE_STAGE2_CASES.csv"
RESTRICTED_COURSES = OUTDIR / "RESTRICTED_SECOND_ASSOCIATE_STAGE2_UNIQUE_COURSES.csv"
STUDENT_BLIND = OUTDIR / "STUDENT_BLIND_SECOND_ASSOCIATE_STAGE2_SUMMARY.csv"

PENDING_DECISION = "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"
TARGET_CATALOG = "2025-2026"

COURSE_RE = re.compile(r"\b([A-Z]{2,5})\s*[- ]?\s*(\d{4}[A-Z]?)\b", re.I)

TRANSFER_GRADE_CODES = {
    "T", "TA", "TB", "TC", "TD", "TS",
}

GPA_POINTS = {
    "A": 4.0,
    "B": 3.0,
    "C": 2.0,
    "D": 1.0,
    "F": 0.0,
}

PASSING_NON_GPA = {
    "S", "P", "CR",
}

METHOD_COLUMN_CANDIDATES = [
    "credit_type",
    "credit_source",
    "source_type",
    "institution_type",
    "course_source",
    "nontraditional_credit_type",
    "prior_learning_type",
    "registration_status",
]

TRANSFER_COLUMN_CANDIDATES = [
    "transfer_indicator",
    "transfer_flag",
    "is_transfer",
    "transfer_course",
]

INSTITUTION_COLUMN_CANDIDATES = [
    "institution",
    "institution_name",
    "source_institution",
    "transfer_institution",
    "school_name",
]

LOCAL_INSTITUTION_TOKENS = [
    "LAMAR STATE COLLEGE ORANGE",
    "LAMAR STATE COLLEGE-ORANGE",
    "LAMAR STATE COLLEGE - ORANGE",
    "LSCO",
    "LSC-O",
]

NONRESIDENT_METHOD_TOKENS = [
    "TRANSFER",
    "CLEP",
    "ADVANCED PLACEMENT",
    "AP CREDIT",
    "AP EXAM",
    "INTERNATIONAL BACCALAUREATE",
    "IB CREDIT",
    "DSST",
    "EXAM",
    "TEST CREDIT",
    "MILITARY",
    "JST",
    "ACE CREDIT",
    "PRIOR LEARNING",
    "PLA",
    "PORTFOLIO",
    "ARTICULATED",
    "ARTICULATION",
]


# ======================================================================================
# HELPERS
# ======================================================================================

def text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def upper(value: object) -> str:
    return " ".join(text(value).upper().split())


def truthy(value: object) -> bool:
    return upper(value) in {
        "TRUE", "T", "YES", "Y", "1", "TRANSFER",
    }


def normalize_course(value: object) -> str:
    match = COURSE_RE.search(upper(value))
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def derive_hours(course: object) -> float:
    code = normalize_course(course)
    if not code:
        return np.nan

    number = code.split()[1]
    digits = "".join(ch for ch in number if ch.isdigit())

    if len(digits) < 2:
        return np.nan

    try:
        hours = int(digits[1])
    except ValueError:
        return np.nan

    return float(hours) if hours > 0 else np.nan


def split_semicolon(value: object) -> list[str]:
    raw = text(value)
    if not raw:
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


def numeric_term(value: object) -> float:
    return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]


def is_aat1_credential(credential_id: object) -> bool:
    key = upper(credential_id).replace("-", "_")

    return (
        "TEACHING_AAT1" in key
        or "TEACHING_T038" in key
        or "TEACHING_T074" in key
    )


def source_files(kind: str) -> list[Path]:
    if kind == "summary":
        if SUMMARY.exists():
            return [SUMMARY]

        paths = sorted(CHUNK_DIR.glob("chunk_*_credential_summary.csv"))
        if paths:
            return paths

        raise FileNotFoundError(
            "Could not find combined summary or summary chunks."
        )

    if kind == "detail":
        if DETAIL.exists():
            return [DETAIL]

        paths = sorted(CHUNK_DIR.glob("chunk_*_audit_results.csv"))
        if paths:
            return paths

        raise FileNotFoundError(
            "Could not find combined detail or detail chunks."
        )

    raise ValueError(kind)


def scan_summary(student_ids: set[str]) -> pd.DataFrame:
    keep_columns = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "catalog_eligible",
    ]

    parts = []
    files = source_files("summary")

    for file_index, path in enumerate(files, start=1):
        header = pd.read_csv(path, nrows=0).columns.tolist()
        present = [column for column in keep_columns if column in header]

        required = {
            "student_id",
            "catalog_year",
            "credential_id",
            "audit_status",
        }

        missing = required - set(present)
        if missing:
            raise RuntimeError(
                f"{path.name} missing summary columns: "
                + ", ".join(sorted(missing))
            )

        for chunk in pd.read_csv(
            path,
            dtype=str,
            usecols=present,
            chunksize=250_000,
            low_memory=False,
        ):
            chunk = chunk.fillna("")
            subset = chunk[
                chunk["student_id"].astype(str).isin(student_ids)
            ].copy()

            if not subset.empty:
                parts.append(subset)

        if len(files) > 1 and (
            file_index % 100 == 0 or file_index == len(files)
        ):
            print(
                f"Read summary files: {file_index:,}/{len(files):,}"
            )

    if not parts:
        return pd.DataFrame(columns=keep_columns)

    out = pd.concat(parts, ignore_index=True)

    for column in keep_columns:
        if column not in out.columns:
            out[column] = ""

    return out[keep_columns].copy()


def choose_plausible_prior_audits(
    pending: pd.DataFrame,
    summary: pd.DataFrame,
    student_col: str,
) -> pd.DataFrame:

    rows = []

    for case in pending.itertuples(index=False):
        student_id = text(getattr(case, student_col))
        prior_grad_term = numeric_term(
            getattr(case, "first_prior_grad_term", "")
        )

        candidates = summary[
            summary["student_id"].eq(student_id)
            & summary["credential_id"].map(is_aat1_credential)
            & summary["audit_status"].str.upper().eq("COMPLETE")
        ].copy()

        if "catalog_eligible" in candidates.columns:
            eligible_text = (
                candidates["catalog_eligible"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            if eligible_text.ne("").any():
                candidates = candidates[
                    eligible_text.isin(
                        {"TRUE", "T", "YES", "Y", "1", "ELIGIBLE"}
                    )
                ].copy()

        if candidates.empty:
            rows.append(
                {
                    "student_id": student_id,
                    "prior_catalog_year": "",
                    "prior_credential_id": "",
                    "prior_modeled_completion_term": "",
                    "prior_candidate_basis":
                        "NO_COMPLETE_AAT1_AUDIT_FOUND",
                }
            )
            continue

        candidates["_award_term_num"] = pd.to_numeric(
            candidates["award_term_sort"],
            errors="coerce",
        )

        if pd.notna(prior_grad_term):
            on_time = candidates[
                candidates["_award_term_num"].notna()
                & candidates["_award_term_num"].le(prior_grad_term)
            ].copy()

            if not on_time.empty:
                candidates = on_time
                basis = (
                    "COMPLETE_AAT1_MODELED_NO_LATER_THAN_OFFICIAL_AWARD_TERM"
                )
            else:
                basis = (
                    "COMPLETE_AAT1_FOUND_BUT_MODELED_TERM_DID_NOT_FILTER_"
                    "TO_OFFICIAL_AWARD_TERM"
                )
        else:
            basis = "COMPLETE_AAT1_OFFICIAL_AWARD_TERM_UNAVAILABLE"

        candidates = candidates.drop_duplicates(
            ["student_id", "catalog_year", "credential_id"]
        ).copy()

        for row in candidates.itertuples(index=False):
            rows.append(
                {
                    "student_id": student_id,
                    "prior_catalog_year": text(row.catalog_year),
                    "prior_credential_id": text(row.credential_id),
                    "prior_modeled_completion_term":
                        text(row.award_term_sort),
                    "prior_candidate_basis": basis,
                }
            )

    return pd.DataFrame(rows)


def scan_detail(keys: set[tuple[str, str, str]]) -> pd.DataFrame:
    keep_columns = [
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "status",
        "matched_options",
        "matched_grades",
        "matched_terms",
    ]

    parts = []
    files = source_files("detail")

    for file_index, path in enumerate(files, start=1):
        header = pd.read_csv(path, nrows=0).columns.tolist()
        present = [column for column in keep_columns if column in header]

        required = {
            "student_id",
            "catalog_year",
            "credential_id",
            "status",
            "matched_options",
        }

        missing = required - set(present)
        if missing:
            raise RuntimeError(
                f"{path.name} missing detail columns: "
                + ", ".join(sorted(missing))
            )

        row_count = 0

        for chunk_number, chunk in enumerate(
            pd.read_csv(
                path,
                dtype=str,
                usecols=present,
                chunksize=500_000,
                low_memory=False,
            ),
            start=1,
        ):
            row_count += len(chunk)
            chunk = chunk.fillna("")

            tuples = chunk[
                ["student_id", "catalog_year", "credential_id"]
            ].itertuples(index=False, name=None)

            mask = [key in keys for key in tuples]
            subset = chunk.loc[mask].copy()

            if not subset.empty:
                parts.append(subset)

            if len(files) == 1 and chunk_number % 20 == 0:
                print(
                    f"Read detail chunks: {chunk_number:,} "
                    f"| rows: {row_count:,}"
                )

        if len(files) > 1 and (
            file_index % 100 == 0 or file_index == len(files)
        ):
            print(
                f"Read detail files: {file_index:,}/{len(files):,}"
            )

    if not parts:
        return pd.DataFrame(columns=keep_columns)

    out = pd.concat(parts, ignore_index=True)

    for column in keep_columns:
        if column not in out.columns:
            out[column] = ""

    return out[keep_columns].copy()


def allocation_rows(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []

    met = detail[
        detail["status"].astype(str).str.strip().str.upper().eq("MET")
    ].copy()

    for row in met.itertuples(index=False):
        courses = [
            normalize_course(value)
            for value in split_semicolon(row.matched_options)
        ]
        courses = [course for course in courses if course]

        grades = [
            upper(value)
            for value in split_semicolon(row.matched_grades)
        ]
        terms = split_semicolon(row.matched_terms)

        for index, course in enumerate(courses):
            grade = grades[index] if index < len(grades) else ""
            term = terms[index] if index < len(terms) else ""

            rows.append(
                {
                    "student_id": text(row.student_id),
                    "catalog_year": text(row.catalog_year),
                    "credential_id": text(row.credential_id),
                    "requirement_id": text(row.requirement_id),
                    "course": course,
                    "matched_grade": grade,
                    "matched_term": term,
                    "hours": derive_hours(course),
                    "grade_alignment_ok":
                        len(grades) in {0, len(courses)},
                    "term_alignment_ok":
                        len(terms) in {0, len(courses)},
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "student_id",
                "catalog_year",
                "credential_id",
                "requirement_id",
                "course",
                "matched_grade",
                "matched_term",
                "hours",
                "grade_alignment_ok",
                "term_alignment_ok",
            ]
        )

    return pd.DataFrame(rows)


def attempts_source() -> Path:
    if ATTEMPTS.exists():
        return ATTEMPTS

    if FALLBACK_HISTORY.exists():
        return FALLBACK_HISTORY

    raise FileNotFoundError(
        "Neither all_student_course_attempts_normalized.csv nor "
        "normalized_actual_student_course_history.csv exists."
    )


def load_attempts(student_ids: set[str]) -> tuple[pd.DataFrame, str]:
    path = attempts_source()
    header = pd.read_csv(path, nrows=0).columns.tolist()

    student_col = "student_id"
    course_col = "course_code"

    if student_col not in header or course_col not in header:
        raise RuntimeError(
            f"{path.name} lacks student_id/course_code."
        )

    grade_columns = [
        column
        for column in ["final_grade", "grade"]
        if column in header
    ]

    term_columns = [
        column
        for column in ["term_sort", "term_taken"]
        if column in header
    ]

    method_columns = [
        column
        for column in METHOD_COLUMN_CANDIDATES
        if column in header
    ]

    transfer_columns = [
        column
        for column in TRANSFER_COLUMN_CANDIDATES
        if column in header
    ]

    institution_columns = [
        column
        for column in INSTITUTION_COLUMN_CANDIDATES
        if column in header
    ]

    usecols = list(
        dict.fromkeys(
            [
                student_col,
                course_col,
                *grade_columns,
                *term_columns,
                *method_columns,
                *transfer_columns,
                *institution_columns,
            ]
        )
    )

    parts = []

    for chunk in pd.read_csv(
        path,
        dtype=str,
        usecols=usecols,
        chunksize=250_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        subset = chunk[
            chunk[student_col].astype(str).isin(student_ids)
        ].copy()

        if not subset.empty:
            parts.append(subset)

    if parts:
        out = pd.concat(parts, ignore_index=True)
    else:
        out = pd.DataFrame(columns=usecols)

    out["course_code"] = out["course_code"].map(normalize_course)

    method_description = (
        f"source={path.name}; "
        f"transfer_columns={','.join(transfer_columns) or 'NONE'}; "
        f"method_columns={','.join(method_columns) or 'NONE'}; "
        f"institution_columns={','.join(institution_columns) or 'NONE'}; "
        "fallback=matched transfer-grade codes"
    )

    return out, method_description


def row_residence_signal(
    row: pd.Series,
    method_columns: list[str],
    transfer_columns: list[str],
    institution_columns: list[str],
    grade_columns: list[str],
) -> tuple[str, str]:

    for column in transfer_columns:
        value = upper(row.get(column, ""))
        if truthy(value):
            return "NONRESIDENT", f"EXPLICIT_TRANSFER:{column}"

    method_text = " | ".join(
        upper(row.get(column, ""))
        for column in method_columns
        if upper(row.get(column, ""))
    )

    if any(token in method_text for token in NONRESIDENT_METHOD_TOKENS):
        return "NONRESIDENT", "NONRESIDENT_METHOD"

    institution_text = " | ".join(
        upper(row.get(column, ""))
        for column in institution_columns
        if upper(row.get(column, ""))
    )

    if institution_text:
        if any(
            token in institution_text
            for token in LOCAL_INSTITUTION_TOKENS
        ):
            return "RESIDENT", "EXPLICIT_LSCO_INSTITUTION"

        return "NONRESIDENT", "EXTERNAL_INSTITUTION"

    grades = [
        upper(row.get(column, ""))
        for column in grade_columns
        if upper(row.get(column, ""))
    ]

    if any(grade in TRANSFER_GRADE_CODES for grade in grades):
        return "NONRESIDENT", "TRANSFER_GRADE_CODE"

    if any(
        grade in GPA_POINTS or grade in PASSING_NON_GPA
        for grade in grades
    ):
        return "RESIDENT", "ORDINARY_GRADE_FALLBACK"

    return "UNKNOWN", "NO_RESIDENCE_SIGNAL"


def residence_for_allocated_course(
    student_id: str,
    course: str,
    matched_grade: str,
    attempts: pd.DataFrame,
) -> tuple[str, str]:

    if upper(matched_grade) in TRANSFER_GRADE_CODES:
        return "NONRESIDENT", "MATCHED_TRANSFER_GRADE"

    subset = attempts[
        attempts["student_id"].astype(str).eq(student_id)
        & attempts["course_code"].eq(course)
    ].copy()

    if subset.empty:
        if upper(matched_grade) in GPA_POINTS or upper(matched_grade) in PASSING_NON_GPA:
            return "RESIDENT", "MATCHED_ORDINARY_GRADE_NO_ATTEMPT_METADATA"
        return "UNKNOWN", "ALLOCATED_COURSE_NOT_FOUND_IN_ATTEMPTS"

    method_columns = [
        column
        for column in METHOD_COLUMN_CANDIDATES
        if column in subset.columns
    ]

    transfer_columns = [
        column
        for column in TRANSFER_COLUMN_CANDIDATES
        if column in subset.columns
    ]

    institution_columns = [
        column
        for column in INSTITUTION_COLUMN_CANDIDATES
        if column in subset.columns
    ]

    grade_columns = [
        column
        for column in ["final_grade", "grade"]
        if column in subset.columns
    ]

    matched = upper(matched_grade)

    if matched and grade_columns:
        grade_match = pd.Series(False, index=subset.index)

        for column in grade_columns:
            grade_match |= (
                subset[column]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(matched)
            )

        if grade_match.any():
            subset = subset[grade_match].copy()

    signals = [
        row_residence_signal(
            row,
            method_columns,
            transfer_columns,
            institution_columns,
            grade_columns,
        )
        for _, row in subset.iterrows()
    ]

    statuses = {status for status, _ in signals}

    if statuses == {"RESIDENT"}:
        methods = sorted({method for _, method in signals})
        return "RESIDENT", "|".join(methods)

    if statuses == {"NONRESIDENT"}:
        methods = sorted({method for _, method in signals})
        return "NONRESIDENT", "|".join(methods)

    if "RESIDENT" in statuses and "NONRESIDENT" not in statuses:
        methods = sorted(
            {
                method
                for status, method in signals
                if status == "RESIDENT"
            }
        )
        return "RESIDENT", "|".join(methods)

    if "NONRESIDENT" in statuses and "RESIDENT" not in statuses:
        methods = sorted(
            {
                method
                for status, method in signals
                if status == "NONRESIDENT"
            }
        )
        return "NONRESIDENT", "|".join(methods)

    if "RESIDENT" in statuses and "NONRESIDENT" in statuses:
        return "UNKNOWN", "MIXED_RESIDENCE_EVIDENCE"

    return "UNKNOWN", "NO_RESIDENCE_SIGNAL"


def weighted_gpa(rows: pd.DataFrame) -> tuple[float, float]:
    points = 0.0
    hours = 0.0

    for row in rows.itertuples(index=False):
        grade = upper(row.matched_grade)
        sch = pd.to_numeric(
            pd.Series([row.hours]),
            errors="coerce",
        ).iloc[0]

        if grade not in GPA_POINTS or pd.isna(sch):
            continue

        points += GPA_POINTS[grade] * float(sch)
        hours += float(sch)

    if hours == 0:
        return np.nan, 0.0

    return points / hours, hours


# ======================================================================================
# LOAD STAGE 1 PENDING CASES
# ======================================================================================

if not STAGE1.exists():
    raise FileNotFoundError(STAGE1)

stage1 = pd.read_csv(
    STAGE1,
    dtype=str,
    low_memory=False,
).fillna("")

student_col = next(
    (
        column
        for column in [
            "student_id",
            "RNUM",
            "rnum",
            "student_key",
        ]
        if column in stage1.columns
    ),
    None,
)

if student_col is None:
    raise RuntimeError(
        "Could not find student identifier column in stage-1 file."
    )

required_stage1 = {
    student_col,
    "catalog_year",
    "credential_id",
    "stage1_decision",
    "first_prior_degree_code",
    "first_prior_lineage",
    "first_prior_grad_term",
}

missing = required_stage1 - set(stage1.columns)

if missing:
    raise RuntimeError(
        "Stage-1 file missing columns: "
        + ", ".join(sorted(missing))
    )

pending = stage1[
    stage1["stage1_decision"].eq(PENDING_DECISION)
].copy()

if pending.empty:
    print("No stage-2 pending cases. Nothing to do.")
    raise SystemExit(0)

if not pending["catalog_year"].eq(TARGET_CATALOG).all():
    raise RuntimeError(
        "Stage-2 pending set contains a catalog other than 2025-2026."
    )

if not pending["first_prior_degree_code"].str.upper().eq("AAT").all():
    raise RuntimeError(
        "Unexpected first-prior degree type in stage-2 pending set."
    )

student_ids = set(
    pending[student_col].astype(str)
)


# ======================================================================================
# FIND PLAUSIBLE FIRST AAT1 AUDITS
# ======================================================================================

summary = scan_summary(student_ids)

prior = choose_plausible_prior_audits(
    pending=pending,
    summary=summary,
    student_col=student_col,
)

valid_prior = prior[
    prior["prior_credential_id"].ne("")
].copy()

target_keys = set(
    pending[
        [student_col, "catalog_year", "credential_id"]
    ]
    .rename(columns={student_col: "student_id"})
    .itertuples(index=False, name=None)
)

prior_keys = set(
    valid_prior[
        ["student_id", "prior_catalog_year", "prior_credential_id"]
    ]
    .rename(
        columns={
            "prior_catalog_year": "catalog_year",
            "prior_credential_id": "credential_id",
        }
    )
    .itertuples(index=False, name=None)
)

all_keys = target_keys | prior_keys


# ======================================================================================
# EXTRACT ALLOCATED COURSES FOR TARGET + PRIOR PLANS
# ======================================================================================

detail = scan_detail(all_keys)
alloc = allocation_rows(detail)

if alloc.empty:
    raise RuntimeError(
        "No MET allocation rows found for target/prior audit keys."
    )


# ======================================================================================
# LOAD ATTEMPT-LEVEL RESIDENCE EVIDENCE
# ======================================================================================

attempts, residence_method = load_attempts(student_ids)


# ======================================================================================
# CASE-BY-CASE / PRIOR-PLAN-BY-PRIOR-PLAN TEST
# ======================================================================================

case_rows = []
course_rows = []

for case in pending.itertuples(index=False):
    student_id = text(getattr(case, student_col))
    target_catalog = text(case.catalog_year)
    target_credential = text(case.credential_id)

    target_alloc = alloc[
        alloc["student_id"].eq(student_id)
        & alloc["catalog_year"].eq(target_catalog)
        & alloc["credential_id"].eq(target_credential)
    ].copy()

    target_alloc = target_alloc.sort_values(
        ["course", "requirement_id"],
        kind="mergesort",
    ).drop_duplicates(
        ["course"],
        keep="first",
    )

    target_courses = set(target_alloc["course"])

    student_prior = valid_prior[
        valid_prior["student_id"].eq(student_id)
    ].copy()

    if student_prior.empty:
        case_rows.append(
            {
                "student_id": student_id,
                "target_catalog_year": target_catalog,
                "target_credential_id": target_credential,
                "prior_catalog_year": "",
                "prior_credential_id": "",
                "prior_candidate_basis":
                    "NO_COMPLETE_AAT1_AUDIT_FOUND",
                "target_allocated_courses": len(target_courses),
                "prior_allocated_courses": 0,
                "shared_courses": 0,
                "unique_target_courses": len(target_courses),
                "unique_resident_sch": np.nan,
                "unique_nonresident_sch": np.nan,
                "unique_unknown_residence_sch": np.nan,
                "unique_resident_gpa": np.nan,
                "unique_resident_gpa_hours": 0.0,
                "prior_plan_test_decision":
                    "REVIEW_NO_PRIOR_AAT1_AUDIT",
            }
        )
        continue

    for prior_row in student_prior.itertuples(index=False):
        prior_alloc = alloc[
            alloc["student_id"].eq(student_id)
            & alloc["catalog_year"].eq(
                prior_row.prior_catalog_year
            )
            & alloc["credential_id"].eq(
                prior_row.prior_credential_id
            )
        ].copy()

        prior_alloc = prior_alloc.sort_values(
            ["course", "requirement_id"],
            kind="mergesort",
        ).drop_duplicates(
            ["course"],
            keep="first",
        )

        prior_courses = set(prior_alloc["course"])
        shared_courses = target_courses & prior_courses
        unique_courses = target_courses - prior_courses

        unique = target_alloc[
            target_alloc["course"].isin(unique_courses)
        ].copy()

        residence_statuses = []
        residence_methods = []

        for row in unique.itertuples(index=False):
            status, method = residence_for_allocated_course(
                student_id=student_id,
                course=row.course,
                matched_grade=row.matched_grade,
                attempts=attempts,
            )

            residence_statuses.append(status)
            residence_methods.append(method)

        unique["residence_status"] = residence_statuses
        unique["residence_method"] = residence_methods

        unique["hours_numeric"] = pd.to_numeric(
            unique["hours"],
            errors="coerce",
        )

        resident_sch = float(
            unique.loc[
                unique["residence_status"].eq("RESIDENT"),
                "hours_numeric",
            ].sum()
        )

        nonresident_sch = float(
            unique.loc[
                unique["residence_status"].eq("NONRESIDENT"),
                "hours_numeric",
            ].sum()
        )

        unknown_sch = float(
            unique.loc[
                unique["residence_status"].eq("UNKNOWN"),
                "hours_numeric",
            ].sum()
        )

        resident_rows = unique[
            unique["residence_status"].eq("RESIDENT")
        ].copy()

        gpa, gpa_hours = weighted_gpa(resident_rows)

        if resident_sch >= 15:
            if pd.isna(gpa):
                decision = "REVIEW_GPA_NOT_COMPUTABLE"
            elif gpa >= 2.0:
                decision = "PASS_FOR_THIS_PRIOR_PLAN"
            else:
                decision = "FAIL_GPA_FOR_THIS_PRIOR_PLAN"

        else:
            if resident_sch + unknown_sch >= 15:
                decision = "REVIEW_RESIDENCE_COULD_CHANGE_RESULT"
            else:
                decision = "FAIL_UNIQUE_RESIDENT_HOURS_FOR_THIS_PRIOR_PLAN"

        case_rows.append(
            {
                "student_id": student_id,
                "target_catalog_year": target_catalog,
                "target_credential_id": target_credential,
                "prior_catalog_year":
                    prior_row.prior_catalog_year,
                "prior_credential_id":
                    prior_row.prior_credential_id,
                "prior_modeled_completion_term":
                    prior_row.prior_modeled_completion_term,
                "prior_candidate_basis":
                    prior_row.prior_candidate_basis,
                "target_allocated_courses": len(target_courses),
                "prior_allocated_courses": len(prior_courses),
                "shared_courses": len(shared_courses),
                "unique_target_courses": len(unique_courses),
                "unique_resident_sch": resident_sch,
                "unique_nonresident_sch": nonresident_sch,
                "unique_unknown_residence_sch": unknown_sch,
                "unique_resident_gpa": gpa,
                "unique_resident_gpa_hours": gpa_hours,
                "prior_plan_test_decision": decision,
            }
        )

        for row in unique.itertuples(index=False):
            course_rows.append(
                {
                    "student_id": student_id,
                    "target_catalog_year": target_catalog,
                    "target_credential_id": target_credential,
                    "prior_catalog_year":
                        prior_row.prior_catalog_year,
                    "prior_credential_id":
                        prior_row.prior_credential_id,
                    "course": row.course,
                    "hours": row.hours,
                    "matched_grade": row.matched_grade,
                    "matched_term": row.matched_term,
                    "target_requirement_id": row.requirement_id,
                    "residence_status":
                        row.residence_status,
                    "residence_method":
                        row.residence_method,
                }
            )


cases = pd.DataFrame(case_rows)
unique_course_detail = pd.DataFrame(course_rows)

if cases.empty:
    raise RuntimeError(
        "Stage-2 produced no case rows."
    )


# ======================================================================================
# COLLAPSE PRIOR-PLAN TESTS TO ONE FINAL DECISION PER STUDENT
# ======================================================================================

final_rows = []

for student_id, group in cases.groupby("student_id", sort=True):
    decisions = set(group["prior_plan_test_decision"])

    if decisions == {"PASS_FOR_THIS_PRIOR_PLAN"}:
        final_decision = "PASS_SECOND_ASSOCIATE_2025_RULE"
        final_reason = (
            "At least 15 unique resident SCH and GPA >= 2.0 "
            "under every plausible prior AAT1 audit."
        )

    elif all(
        decision.startswith("FAIL_")
        for decision in decisions
    ):
        final_decision = "FAIL_SECOND_ASSOCIATE_2025_RULE"
        final_reason = (
            "Fails the 2025 second-associate rule under every "
            "plausible prior AAT1 audit."
        )

    else:
        final_decision = "REVIEW_SECOND_ASSOCIATE_2025_RULE"
        final_reason = (
            "Result depends on prior-plan choice, residence evidence, "
            "or GPA computability."
        )

    final_rows.append(
        {
            "student_id": student_id,
            "plausible_prior_plan_count": len(group),
            "min_unique_resident_sch": pd.to_numeric(
                group["unique_resident_sch"],
                errors="coerce",
            ).min(),
            "max_unique_resident_sch": pd.to_numeric(
                group["unique_resident_sch"],
                errors="coerce",
            ).max(),
            "min_unique_resident_gpa": pd.to_numeric(
                group["unique_resident_gpa"],
                errors="coerce",
            ).min(),
            "max_unique_resident_gpa": pd.to_numeric(
                group["unique_resident_gpa"],
                errors="coerce",
            ).max(),
            "final_stage2_decision": final_decision,
            "final_stage2_reason": final_reason,
        }
    )

final = pd.DataFrame(final_rows)

cases = cases.merge(
    final[
        [
            "student_id",
            "final_stage2_decision",
            "final_stage2_reason",
        ]
    ],
    on="student_id",
    how="left",
    validate="many_to_one",
)


# ======================================================================================
# WRITE LOCAL RESTRICTED DETAIL
# ======================================================================================

cases["residence_evidence_method"] = residence_method

cases.to_csv(
    RESTRICTED_CASES,
    index=False,
)

unique_course_detail.to_csv(
    RESTRICTED_COURSES,
    index=False,
)


# ======================================================================================
# STUDENT-BLIND SUMMARY
# ======================================================================================

student_blind = (
    final.groupby(
        "final_stage2_decision",
        dropna=False,
    )
    .agg(
        candidates=("student_id", "size"),
        min_unique_resident_sch=(
            "min_unique_resident_sch",
            "min",
        ),
        max_unique_resident_sch=(
            "max_unique_resident_sch",
            "max",
        ),
        min_unique_resident_gpa=(
            "min_unique_resident_gpa",
            "min",
        ),
        max_unique_resident_gpa=(
            "max_unique_resident_gpa",
            "max",
        ),
    )
    .reset_index()
)

student_blind.to_csv(
    STUDENT_BLIND,
    index=False,
)


# ======================================================================================
# CONSOLE — NO STUDENT IDENTIFIERS
# ======================================================================================

print("=" * 110)
print("SECOND ASSOCIATE — STAGE 2: 2025-2026 UNIQUE RESIDENT HOURS")
print("=" * 110)

print()
print("Pending candidates:", len(final))

print()
print("PRIOR AAT1 PLAN CANDIDATES")
print("-" * 110)
print(
    final["plausible_prior_plan_count"]
    .value_counts()
    .sort_index()
    .rename_axis("plausible_prior_plan_count")
    .rename("students")
    .to_string()
)

print()
print("FINAL STAGE 2 DECISIONS")
print("-" * 110)
print(
    final["final_stage2_decision"]
    .value_counts(dropna=False)
    .to_string()
)

print()
print("UNIQUE RESIDENT SCH RANGE BY DECISION")
print("-" * 110)
print(
    student_blind[
        [
            "final_stage2_decision",
            "candidates",
            "min_unique_resident_sch",
            "max_unique_resident_sch",
        ]
    ].to_string(index=False)
)

print()
print("RESIDENCE EVIDENCE")
print("-" * 110)
print(residence_method)

print()
print("CONTROL")
print("-" * 110)
print("Pending candidates partitioned:", len(final), "=", len(final))
print("PASS")

print()
print("Restricted local case detail:")
print(RESTRICTED_CASES)

print()
print("Restricted local unique-course detail:")
print(RESTRICTED_COURSES)

print()
print("Student-blind summary:")
print(STUDENT_BLIND)

print()
print(
    "NOTICE: do not upload the RESTRICTED files. "
    "Paste only the student-blind console output."
)
