from __future__ import annotations

import ast
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# STEP 2 — RECONSTRUCT APPLIED-COURSE EVIDENCE FOR THE CURRENT UNSUPPRESSED COMPLETE SET
# ======================================================================================
#
# This script DOES NOT rerun the degree audit.
#
# Starting universe:
#   1,410 curriculum-COMPLETE combinations that survived official-award screening.
#
# Evidence sources:
#   1. Current Fall-2026 incremental/recovery detail chunks, for recomputed combinations.
#   2. July full-audit detail, ONLY for combinations whose final summary provenance is
#      CACHE_PRIOR_202607 and which therefore legitimately retained the prior audit detail.
#
# Path-aware rule:
#   * common requirement rows: path_group_id == ""  -> count
#   * alternative-path rows:   path_selected == TRUE -> count
#   * unselected alternative paths -> exclude
#
# The script proves that every candidate's selected detail requirement count reconciles
# exactly to requirements_total before extracting applied courses.
#
# Outputs are written to a new timestamped reporting directory.
#
# Run from repository root:
#   python -u .\scripts\build_current_unsuppressed_applied_courses.py
#
# No Git files are modified.


ROOT = Path.cwd()

CANDIDATES = Path(
    "data/processed/reporting/"
    "official_award_screening_final_20261008_092747/"
    "RESTRICTED_unsuppressed_complete_combinations_FINAL.csv"
)

CURRENT_AUDIT_ROOT = Path(
    "data/processed/incremental_audit/fall_2026_refresh_20261007"
)

PRIOR_DETAIL = Path(
    "data/processed/full_actual_audit/full_actual_audit_results.csv"
)

REQUIREMENTS = Path(
    "data/processed/catalogs/staging_six_year/"
    "requirements_master_multiyear.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / f"current_unsuppressed_applied_courses_{RUN_STAMP}"

APPLIED_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_unsuppressed_complete_applied_courses.csv"
)

SELECTED_DETAIL_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_unsuppressed_complete_selected_detail.csv"
)

CANDIDATE_QA_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_unsuppressed_complete_detail_reconciliation.csv"
)

SAFE_METRICS_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_applied_course_reconstruction_metrics.csv"
)

SAFE_BY_PROVENANCE_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_applied_course_reconstruction_by_provenance.csv"
)

SAFE_BY_CATALOG_OUT = (
    OUTPUT_DIR
    / "FERPA_SAFE_applied_course_reconstruction_by_catalog.csv"
)

EXPECTED_CANDIDATES = 1_410

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]

DETAIL_CORE_COLUMNS = [
    "student_id",
    "catalog_year",
    "credential_id",
    "requirement_id",
    "rule_type",
    "status",
    "matched_options",
    "matched_terms",
    "matched_term_sorts",
    "matched_grades",
    "latest_matched_term_sort",
    "latest_matched_term_taken",
    "required_options",
    "option_types",
    "used_course_count",
]

PATH_COLUMNS = [
    "path_group_id",
    "path_id",
    "path_label",
    "path_order",
    "path_expected_applied_hours",
    "path_selected",
]

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


def truthy(value: object) -> bool:
    return text(value).upper() in {
        "TRUE",
        "T",
        "YES",
        "Y",
        "1",
    }


def normalize_course(value: object) -> str:
    match = COURSE_RE.search(text(value).upper())
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2)}"


def derived_hours(course_code: object) -> float | None:
    course = normalize_course(course_code)
    if not course:
        return None

    number = course.split()[1]

    if len(number) != 4 or not number.isdigit():
        return None

    value = int(number[1])

    # Preserve the old awardability-screen behavior: zero in the SCH digit
    # is treated as unresolved rather than silently counted as zero.
    if value == 0:
        return None

    return float(value)


def course_level(course_code: object) -> float | None:
    course = normalize_course(course_code)
    if not course:
        return None

    number = course.split()[1]

    if len(number) != 4 or not number.isdigit():
        return None

    return float(number[0])


def split_semantic_list(value: object) -> list[str]:
    """
    Support both historical Python-list serialization and the current engine's
    semicolon serialization.
    """
    raw = text(value)

    if not raw:
        return []

    if raw[:1] in {"[", "(", "{"}:
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (list, tuple, set)):
                return [
                    text(item)
                    for item in parsed
                    if text(item)
                ]
        except Exception:
            pass

    return [
        item.strip()
        for item in raw.split(";")
        if item.strip()
    ]


def split_courses(value: object) -> list[str]:
    raw_items = split_semantic_list(value)
    result: list[str] = []

    for item in raw_items:
        normalized = normalize_course(item)
        if normalized:
            result.append(normalized)

    # Historical rows can occasionally contain a textual blob rather than
    # semicolon serialization. Fall back to regex extraction only if needed.
    if not result:
        result = [
            f"{match.group(1).upper()} {match.group(2)}"
            for match in COURSE_RE.finditer(text(value).upper())
        ]

    return result


def split_grades(value: object) -> list[str]:
    return [
        text(item).upper()
        for item in split_semantic_list(value)
    ]


def tuple_keys(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    return list(
        frame[KEY].itertuples(
            index=False,
            name=None,
        )
    )


def header_columns(path: Path) -> list[str]:
    try:
        return list(
            pd.read_csv(
                path,
                nrows=0,
                low_memory=False,
            ).columns
        )
    except Exception:
        return []


def discover_current_detail_files(root: Path) -> list[Path]:
    """
    Discover detail CSVs by schema, not filename. This intentionally survives
    the original incremental runner and recovery-backfill filename differences.
    """
    files: list[Path] = []

    required = {
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "status",
        "matched_options",
    }

    for path in sorted(root.rglob("*.csv")):
        columns = set(
            header_columns(path)
        )

        if required.issubset(columns):
            files.append(path)

    return files


def selected_path_mask(frame: pd.DataFrame) -> pd.Series:
    """
    Mirrors the validated path-aware engine summary logic:
        path_group_id == "" OR path_selected == TRUE
    Ordinary legacy detail has no path columns and is entirely countable.
    """
    if "path_group_id" not in frame.columns:
        return pd.Series(
            True,
            index=frame.index,
        )

    group_id = (
        frame["path_group_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if "path_selected" in frame.columns:
        selected = (
            frame["path_selected"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("TRUE")
        )
    else:
        selected = pd.Series(
            False,
            index=frame.index,
        )

    return group_id.eq("") | selected


def read_detail_subset(
    path: Path,
    candidate_keys: set[tuple[str, str, str]],
    *,
    chunksize: int | None = None,
    source_label: str,
) -> list[pd.DataFrame]:
    columns = header_columns(path)

    required = {
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "status",
        "matched_options",
        "matched_grades",
    }

    missing = required - set(columns)

    if missing:
        raise RuntimeError(
            f"Detail source missing required columns: {path}\n"
            + ", ".join(sorted(missing))
        )

    usecols = [
        column
        for column in DETAIL_CORE_COLUMNS + PATH_COLUMNS
        if column in columns
    ]

    def filter_frame(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.fillna("")

        for column in KEY:
            frame[column] = (
                frame[column]
                .astype(str)
                .str.strip()
            )

        mask = [
            key in candidate_keys
            for key in frame[KEY].itertuples(
                index=False,
                name=None,
            )
        ]

        subset = frame.loc[mask].copy()

        if subset.empty:
            return subset

        subset["detail_source"] = source_label
        subset["detail_source_file"] = str(path)

        return subset

    parts: list[pd.DataFrame] = []

    if chunksize is None:
        frame = pd.read_csv(
            path,
            usecols=usecols,
            dtype=str,
            low_memory=False,
        )

        subset = filter_frame(frame)

        if not subset.empty:
            parts.append(subset)

        return parts

    for chunk_number, frame in enumerate(
        pd.read_csv(
            path,
            usecols=usecols,
            dtype=str,
            chunksize=chunksize,
            low_memory=False,
        ),
        start=1,
    ):
        subset = filter_frame(frame)

        if not subset.empty:
            parts.append(subset)

        if chunk_number % 20 == 0:
            print(
                f"  prior detail chunks read: {chunk_number:,}"
            )

    return parts


def requirement_metadata(
    requirements: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "rule_type",
        "option_type",
        "credit_hours",
    }

    missing = required - set(requirements.columns)

    if missing:
        raise RuntimeError(
            "Requirements master missing columns: "
            + ", ".join(sorted(missing))
        )

    group_name_col = (
        "group_name"
        if "group_name" in requirements.columns
        else None
    )

    source_text_col = (
        "source_requirement_text"
        if "source_requirement_text" in requirements.columns
        else None
    )

    rows: list[dict] = []

    for key, group in requirements.groupby(
        [
            "catalog_year",
            "credential_id",
            "requirement_id",
        ],
        sort=False,
        dropna=False,
    ):
        rule_types = {
            text(value).upper()
            for value in group["rule_type"]
            if text(value)
        }

        option_types = {
            text(value).upper()
            for value in group["option_type"]
            if text(value)
        }

        group_names = (
            " | ".join(
                sorted(
                    {
                        text(value)
                        for value in group[group_name_col]
                        if text(value)
                    }
                )
            )
            if group_name_col
            else ""
        )

        source_texts = (
            " | ".join(
                sorted(
                    {
                        text(value)
                        for value in group[source_text_col]
                        if text(value)
                    }
                )
            )
            if source_text_col
            else ""
        )

        text_blob = (
            f"{group_names} {source_texts}"
        ).upper()

        is_core = (
            "CORE_BUCKET" in rule_types
            or "CORE_BUCKET" in option_types
            or "CORE CURRICULUM" in text_blob
        )

        is_elective = (
            "ELECTIVE" in rule_types
            or "ELECTIVE" in option_types
            or "ELECTIVE" in text_blob
        )

        credit_values = pd.to_numeric(
            group["credit_hours"],
            errors="coerce",
        ).dropna().unique()

        if len(credit_values) > 1:
            raise RuntimeError(
                "Requirement has inconsistent credit_hours: "
                f"{key}: {credit_values.tolist()}"
            )

        rows.append(
            {
                "catalog_year": str(key[0]).strip(),
                "credential_id": str(key[1]).strip(),
                "requirement_id": str(key[2]).strip(),
                "requirement_credit_hours": (
                    float(credit_values[0])
                    if len(credit_values) == 1
                    else None
                ),
                "requirement_group_name": group_names,
                "requirement_source_text": source_texts,
                "requirement_rule_types": " | ".join(
                    sorted(rule_types)
                ),
                "requirement_option_types": " | ".join(
                    sorted(option_types)
                ),
                "is_core": bool(is_core),
                "is_elective": bool(is_elective),
                "estimated_major": bool(
                    not is_core
                    and not is_elective
                ),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    for path in (
        CANDIDATES,
        CURRENT_AUDIT_ROOT,
        PRIOR_DETAIL,
        REQUIREMENTS,
    ):
        require(path)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    candidates = pd.read_csv(
        CANDIDATES,
        dtype=str,
        low_memory=False,
    ).fillna("")

    missing_candidate_columns = (
        set(KEY + [
            "audit_status",
            "requirements_total",
            "result_provenance",
        ])
        - set(candidates.columns)
    )

    if missing_candidate_columns:
        raise RuntimeError(
            "Candidate file missing columns: "
            + ", ".join(
                sorted(missing_candidate_columns)
            )
        )

    if len(candidates) != EXPECTED_CANDIDATES:
        raise RuntimeError(
            "Unsuppressed COMPLETE candidate count changed: "
            f"{len(candidates):,} != {EXPECTED_CANDIDATES:,}"
        )

    if not (
        candidates["audit_status"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("COMPLETE")
        .all()
    ):
        raise RuntimeError(
            "Candidate file contains a non-COMPLETE row."
        )

    if candidates.duplicated(KEY).any():
        raise RuntimeError(
            "Candidate grain is not unique at student/catalog/credential."
        )

    for column in KEY:
        candidates[column] = (
            candidates[column]
            .astype(str)
            .str.strip()
        )

    candidate_keys = set(
        tuple_keys(candidates)
    )

    # ------------------------------------------------------------------
    # 1. Scan current incremental/recovery detail by schema.
    # ------------------------------------------------------------------
    current_detail_files = (
        discover_current_detail_files(
            CURRENT_AUDIT_ROOT
        )
    )

    if not current_detail_files:
        raise RuntimeError(
            "No current incremental detail CSVs discovered under "
            f"{CURRENT_AUDIT_ROOT}"
        )

    print("=" * 100)
    print("CURRENT UNSUPPRESSED APPLIED-COURSE RECONSTRUCTION")
    print("=" * 100)
    print(
        f"Candidate COMPLETE combinations:         {len(candidates):,}"
    )
    print(
        f"Current detail files discovered:         {len(current_detail_files):,}"
    )
    print()

    current_parts: list[pd.DataFrame] = []

    for index, path in enumerate(
        current_detail_files,
        start=1,
    ):
        parts = read_detail_subset(
            path,
            candidate_keys,
            source_label="CURRENT_INCREMENTAL_OR_RECOVERY",
        )

        current_parts.extend(parts)

        if (
            index % 50 == 0
            or index == len(current_detail_files)
        ):
            print(
                "Current detail files scanned: "
                f"{index:,}/{len(current_detail_files):,}"
            )

    if current_parts:
        current_raw = pd.concat(
            current_parts,
            ignore_index=True,
        )
    else:
        current_raw = pd.DataFrame()

    current_found = (
        set(tuple_keys(current_raw))
        if not current_raw.empty
        else set()
    )

    # Any non-cache candidate MUST have current detail.
    provenance = (
        candidates[
            KEY + ["result_provenance"]
        ]
        .copy()
    )

    provenance[
        "is_cache_prior"
    ] = (
        provenance[
            "result_provenance"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("CACHE_PRIOR_202607")
    )

    noncache_keys = set(
        tuple_keys(
            provenance[
                ~provenance["is_cache_prior"]
            ]
        )
    )

    missing_noncache = (
        noncache_keys
        - current_found
    )

    if missing_noncache:
        sample = sorted(
            missing_noncache
        )[:20]

        raise RuntimeError(
            "Current recomputed candidate detail is missing for "
            f"{len(missing_noncache):,} non-cache candidate keys. "
            "Do not fall back to stale July detail for these rows.\n"
            f"Sample: {sample}"
        )

    # ------------------------------------------------------------------
    # 2. For remaining legitimate cache keys, scan July full detail.
    # ------------------------------------------------------------------
    all_missing_after_current = (
        candidate_keys
        - current_found
    )

    cache_keys = set(
        tuple_keys(
            provenance[
                provenance["is_cache_prior"]
            ]
        )
    )

    illegal_prior_fallback = (
        all_missing_after_current
        - cache_keys
    )

    if illegal_prior_fallback:
        raise RuntimeError(
            "A non-cache key would require July detail fallback; stopped."
        )

    prior_parts: list[pd.DataFrame] = []

    if all_missing_after_current:
        print()
        print(
            "Cache candidates requiring July detail: "
            f"{len(all_missing_after_current):,}"
        )

        prior_parts = read_detail_subset(
            PRIOR_DETAIL,
            all_missing_after_current,
            chunksize=500_000,
            source_label="PRIOR_CACHE_202607",
        )

    if prior_parts:
        prior_raw = pd.concat(
            prior_parts,
            ignore_index=True,
        )
    else:
        prior_raw = pd.DataFrame()

    prior_found = (
        set(tuple_keys(prior_raw))
        if not prior_raw.empty
        else set()
    )

    still_missing = (
        candidate_keys
        - current_found
        - prior_found
    )

    if still_missing:
        sample = sorted(
            still_missing
        )[:20]

        raise RuntimeError(
            "No detail evidence found for "
            f"{len(still_missing):,} candidate combinations.\n"
            f"Sample: {sample}"
        )

    raw_parts = [
        frame
        for frame in (
            current_raw,
            prior_raw,
        )
        if not frame.empty
    ]

    detail = pd.concat(
        raw_parts,
        ignore_index=True,
    )

    # Candidate key must come from exactly one evidence vintage.
    source_counts = (
        detail.groupby(
            KEY,
            dropna=False,
        )["detail_source"]
        .nunique()
    )

    multi_source_keys = (
        source_counts[
            source_counts > 1
        ]
    )

    if not multi_source_keys.empty:
        raise RuntimeError(
            "Some candidate combinations were sourced from both current "
            "and prior detail. Refusing ambiguous evidence selection. "
            f"Keys: {len(multi_source_keys):,}"
        )

    # ------------------------------------------------------------------
    # 3. Select only common rows + winning alternative path.
    # ------------------------------------------------------------------
    selected = detail[
        selected_path_mask(detail)
    ].copy()

    selected["status_normalized"] = (
        selected["status"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # These are COMPLETE combinations. Every selected requirement must be MET.
    nonmet = selected[
        ~selected["status_normalized"]
        .eq("MET")
    ]

    if not nonmet.empty:
        nonmet.to_csv(
            OUTPUT_DIR
            / "RESTRICTED_ERROR_nonmet_selected_rows.csv",
            index=False,
        )

        raise RuntimeError(
            "COMPLETE candidates contain selected-path non-MET requirements: "
            f"{len(nonmet):,}. Diagnostic written."
        )

    # ------------------------------------------------------------------
    # 4. Exact selected-detail count reconciliation against requirements_total.
    # ------------------------------------------------------------------
    detail_counts = (
        selected.groupby(
            KEY,
            dropna=False,
        )
        .agg(
            selected_requirement_rows=(
                "requirement_id",
                "size",
            ),
            selected_requirement_ids=(
                "requirement_id",
                "nunique",
            ),
            detail_source=(
                "detail_source",
                "first",
            ),
        )
        .reset_index()
    )

    qa = candidates[
        KEY
        + [
            "requirements_total",
            "result_provenance",
        ]
    ].merge(
        detail_counts,
        on=KEY,
        how="left",
        validate="one_to_one",
    )

    qa["requirements_total_numeric"] = pd.to_numeric(
        qa["requirements_total"],
        errors="coerce",
    )

    qa["selected_requirement_rows"] = pd.to_numeric(
        qa["selected_requirement_rows"],
        errors="coerce",
    )

    qa["selected_requirement_ids"] = pd.to_numeric(
        qa["selected_requirement_ids"],
        errors="coerce",
    )

    qa["detail_count_matches_summary"] = (
        qa["requirements_total_numeric"]
        .eq(qa["selected_requirement_rows"])
        & qa["selected_requirement_rows"]
        .eq(qa["selected_requirement_ids"])
    )

    qa.to_csv(
        CANDIDATE_QA_OUT,
        index=False,
    )

    bad_count = qa[
        ~qa[
            "detail_count_matches_summary"
        ]
    ]

    if not bad_count.empty:
        raise RuntimeError(
            "Selected detail does not reconcile to requirements_total for "
            f"{len(bad_count):,} candidates. "
            f"See {CANDIDATE_QA_OUT}"
        )

    selected.to_csv(
        SELECTED_DETAIL_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # 5. Join requirement semantics and explode matched courses/grades.
    # ------------------------------------------------------------------
    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    req_meta = requirement_metadata(
        requirements
    )

    selected = selected.merge(
        req_meta,
        on=[
            "catalog_year",
            "credential_id",
            "requirement_id",
        ],
        how="left",
        validate="many_to_one",
    )

    missing_meta = selected[
        "requirement_rule_types"
    ].isna()

    if missing_meta.any():
        raise RuntimeError(
            "Selected detail rows failed requirement-metadata join: "
            f"{int(missing_meta.sum()):,}"
        )

    applied_rows: list[dict] = []
    parse_issues: list[dict] = []

    for row in selected.itertuples(
        index=False,
    ):
        courses = split_courses(
            getattr(
                row,
                "matched_options",
                "",
            )
        )

        grades = split_grades(
            getattr(
                row,
                "matched_grades",
                "",
            )
        )

        terms = split_semantic_list(
            getattr(
                row,
                "matched_terms",
                "",
            )
        )

        term_sorts = split_semantic_list(
            getattr(
                row,
                "matched_term_sorts",
                "",
            )
        )

        if len(courses) != len(grades):
            parse_issues.append(
                {
                    "student_id": row.student_id,
                    "catalog_year": row.catalog_year,
                    "credential_id": row.credential_id,
                    "requirement_id": row.requirement_id,
                    "issue_type": (
                        "MATCHED_COURSE_GRADE_COUNT_MISMATCH"
                    ),
                    "course_count": len(courses),
                    "grade_count": len(grades),
                    "matched_options": getattr(
                        row,
                        "matched_options",
                        "",
                    ),
                    "matched_grades": getattr(
                        row,
                        "matched_grades",
                        "",
                    ),
                }
            )
            continue

        # Terms/term_sorts are provenance metadata. Older detail may not carry
        # them; do not block course/grade reconstruction when absent.
        if terms and len(terms) != len(courses):
            terms = [""] * len(courses)

        if term_sorts and len(term_sorts) != len(courses):
            term_sorts = [""] * len(courses)

        if not terms:
            terms = [""] * len(courses)

        if not term_sorts:
            term_sorts = [""] * len(courses)

        for sequence, (
            course,
            grade,
            term,
            term_sort,
        ) in enumerate(
            zip(
                courses,
                grades,
                terms,
                term_sorts,
            ),
            start=1,
        ):
            applied_rows.append(
                {
                    "student_id": row.student_id,
                    "catalog_year": row.catalog_year,
                    "credential_id": row.credential_id,
                    "requirement_id": row.requirement_id,
                    "course": course,
                    "grade": grade,
                    "term_taken": term,
                    "term_sort": term_sort,
                    "derived_hours": derived_hours(
                        course
                    ),
                    "course_level": course_level(
                        course
                    ),
                    "is_core": bool(
                        row.is_core
                    ),
                    "is_elective": bool(
                        row.is_elective
                    ),
                    "estimated_major": bool(
                        row.estimated_major
                    ),
                    "requirement_credit_hours": (
                        row.requirement_credit_hours
                    ),
                    "requirement_group_name": (
                        row.requirement_group_name
                    ),
                    "requirement_source_text": (
                        row.requirement_source_text
                    ),
                    "requirement_rule_types": (
                        row.requirement_rule_types
                    ),
                    "requirement_option_types": (
                        row.requirement_option_types
                    ),
                    "path_group_id": getattr(
                        row,
                        "path_group_id",
                        "",
                    ),
                    "path_id": getattr(
                        row,
                        "path_id",
                        "",
                    ),
                    "path_selected": getattr(
                        row,
                        "path_selected",
                        "",
                    ),
                    "matched_course_sequence": sequence,
                    "detail_source": (
                        row.detail_source
                    ),
                    "detail_source_file": (
                        row.detail_source_file
                    ),
                }
            )

    if parse_issues:
        issue_frame = pd.DataFrame(
            parse_issues
        )

        issue_frame.to_csv(
            OUTPUT_DIR
            / "RESTRICTED_ERROR_applied_course_parse_issues.csv",
            index=False,
        )

        raise RuntimeError(
            "Applied-course parsing found "
            f"{len(issue_frame):,} course/grade mismatches. "
            "Stopped before awardability screening."
        )

    applied = pd.DataFrame(
        applied_rows
    )

    if applied.empty:
        raise RuntimeError(
            "No applied courses were reconstructed."
        )

    duplicate_course_use = (
        applied.duplicated(
            KEY + ["course"],
            keep=False,
        )
    )

    if duplicate_course_use.any():
        duplicate_rows = applied[
            duplicate_course_use
        ].sort_values(
            KEY + ["course"]
        )

        duplicate_rows.to_csv(
            OUTPUT_DIR
            / "RESTRICTED_ERROR_duplicate_applied_course_use.csv",
            index=False,
        )

        raise RuntimeError(
            "One-course-one-slot invariant failed for "
            f"{duplicate_rows[KEY + ['course']].drop_duplicates().shape[0]:,} "
            "candidate/course keys. Diagnostic written."
        )

    applied.to_csv(
        APPLIED_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # 6. FERPA-safe QA summaries.
    # ------------------------------------------------------------------
    candidate_evidence = (
        qa.groupby(
            [
                "result_provenance",
                "detail_source",
            ],
            dropna=False,
        )
        .agg(
            candidate_combinations=(
                "student_id",
                "size",
            ),
        )
        .reset_index()
    )

    candidate_evidence.to_csv(
        SAFE_BY_PROVENANCE_OUT,
        index=False,
    )

    by_catalog = (
        candidates.groupby(
            "catalog_year",
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
        .merge(
            applied.groupby(
                "catalog_year",
                dropna=False,
            )
            .agg(
                applied_course_rows=(
                    "course",
                    "size",
                ),
                distinct_applied_courses=(
                    "course",
                    "nunique",
                ),
            )
            .reset_index(),
            on="catalog_year",
            how="left",
            validate="one_to_one",
        )
    )

    by_catalog.to_csv(
        SAFE_BY_CATALOG_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "unsuppressed_complete_candidate_combinations",
                "value": len(candidates),
            },
            {
                "metric": "current_detail_files_discovered",
                "value": len(current_detail_files),
            },
            {
                "metric": "candidate_keys_found_in_current_detail",
                "value": len(current_found),
            },
            {
                "metric": "candidate_keys_filled_from_prior_cache_detail",
                "value": len(prior_found),
            },
            {
                "metric": "candidate_keys_missing_after_reconstruction",
                "value": len(still_missing),
            },
            {
                "metric": "selected_requirement_rows",
                "value": len(selected),
            },
            {
                "metric": "selected_detail_count_mismatches",
                "value": int(
                    (~qa[
                        "detail_count_matches_summary"
                    ]).sum()
                ),
            },
            {
                "metric": "applied_course_rows",
                "value": len(applied),
            },
            {
                "metric": "candidate_course_duplicate_uses",
                "value": int(
                    duplicate_course_use.sum()
                ),
            },
            {
                "metric": "course_grade_parse_issues",
                "value": len(parse_issues),
            },
            {
                "metric": "applied_rows_estimated_major",
                "value": int(
                    applied[
                        "estimated_major"
                    ].sum()
                ),
            },
            {
                "metric": "applied_rows_core",
                "value": int(
                    applied[
                        "is_core"
                    ].sum()
                ),
            },
            {
                "metric": "applied_rows_elective",
                "value": int(
                    applied[
                        "is_elective"
                    ].sum()
                ),
            },
            {
                "metric": "applied_rows_unresolved_derived_hours",
                "value": int(
                    applied[
                        "derived_hours"
                    ].isna()
                    .sum()
                ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print()
    print("=" * 100)
    print("APPLIED-COURSE EVIDENCE RECONSTRUCTION — PASSED")
    print("=" * 100)
    print(
        f"Candidate combinations:                   {len(candidates):,}"
    )
    print(
        f"Found in current detail:                  {len(current_found):,}"
    )
    print(
        f"Filled from July cache detail:            {len(prior_found):,}"
    )
    print(
        f"Selected requirement rows:                {len(selected):,}"
    )
    print(
        f"Applied course rows:                      {len(applied):,}"
    )
    print(
        "Requirement-count mismatches:             "
        f"{int((~qa['detail_count_matches_summary']).sum()):,}"
    )
    print(
        "Duplicate candidate/course uses:          "
        f"{int(duplicate_course_use.sum()):,}"
    )
    print(
        f"Course/grade parse issues:                {len(parse_issues):,}"
    )
    print(
        "Applied rows with unresolved code-hours:  "
        f"{int(applied['derived_hours'].isna().sum()):,}"
    )
    print()
    print(
        f"Output directory: {OUTPUT_DIR}"
    )
    print()
    print(
        "NEXT GATE: port the established GPA / minimum-C / residency "
        "awardability screen to this exact applied-course evidence."
    )


if __name__ == "__main__":
    main()
