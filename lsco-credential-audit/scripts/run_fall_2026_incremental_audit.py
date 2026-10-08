from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# IMPORT LOCAL, ALREADY-VALIDATED INTERFACES
# ======================================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SRC_DIR = ROOT / "src"

for value in (str(SCRIPT_DIR), str(SRC_DIR)):
    if value not in sys.path:
        sys.path.insert(0, value)

import profile_refresh_delta as refresh  # noqa: E402
import build_student_catalog_eligibility_v2 as eligibility_v2  # noqa: E402
from lsco_audit import audit_multiyear_sample_path_candidate as engine  # noqa: E402


# ======================================================================================
# PURPOSE
# ======================================================================================
# Selective empirical Fall 2026 audit runner.
#
# This runner:
#   * NEVER overwrites the July production full audit.
#   * Uses the validated staged six-year package (2021-2022 through 2026-2027).
#   * Reuses historical audit results only when both transcript state and rule state
#     are unchanged.
#   * Recomputes every applicable historical catalog for students whose Summer 2026
#     passing-course state changed.
#   * Computes 2026-2027 for every Fall 2026 student.
#   * Computes every applicable catalog for affected students absent from the prior
#     empirical audit.
#   * Invalidates the intentionally repaired 2025-2026 Logistics credential for every
#     currently eligible student, even when that student's transcript is unchanged.
#   * Preserves every alternative-path detail row produced by the path-aware engine.
#   * Keeps hypothetical Fall-success projection OUT of empirical results.
#   * Is resumable by student chunk.
#
# Raw sources remain untouched. All student-level outputs remain under data/processed.
#
# Run from repository root.
#
# Smoke:
#   python -u .\scripts\run_fall_2026_incremental_audit.py --limit-chunks 1
#
# Full/resume:
#   python -u .\scripts\run_fall_2026_incremental_audit.py
#
# The fixed default run directory intentionally allows restart/resume:
#   data/processed/incremental_audit/fall_2026_refresh_20261007


# ======================================================================================
# VALIDATED SIX-YEAR STAGING PACKAGE
# ======================================================================================

STAGING_ROOT = Path("data/processed/catalogs/staging_six_year")

REQUIREMENTS = STAGING_ROOT / "requirements_master_multiyear.csv"

CORE_LOOKUP = (
    STAGING_ROOT
    / "runtime_support"
    / "core_bucket_lookup_multicatalog.csv"
)

ACADEMIC_COURSE_CROSSWALK = (
    STAGING_ROOT
    / "runtime_support"
    / "catalog_academic_course_crosswalk_final.csv"
)

ELECTIVE_RULES = (
    STAGING_ROOT
    / "semantic_policies"
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

COMPOUND_REQUIREMENT_ALTERNATIVES = (
    STAGING_ROOT
    / "semantic_policies"
    / "compound_requirement_alternatives.csv"
)

ALTERNATIVE_REQUIREMENT_PATHS = (
    STAGING_ROOT
    / "semantic_policies"
    / "alternative_requirement_paths.csv"
)


# ======================================================================================
# PRIOR EMPIRICAL CACHE / ELIGIBILITY
# ======================================================================================

PRIOR_SUMMARY = Path(
    "data/processed/full_actual_audit/full_actual_credential_summary.csv"
)

PRIOR_ELIGIBILITY = Path(
    "data/processed/student_catalog_eligibility.csv"
)


# ======================================================================================
# KNOWN RULE-STATE INVALIDATION
# ======================================================================================

# Validated 2026-10-06:
# The six-year package intentionally repaired the path semantics for the 2025-2026
# Logistics credential. It was explicitly excluded from the 9,500 unchanged
# historical parity comparisons. Therefore cached July results for this exact
# credential are NOT reusable merely because a transcript is unchanged.
REPAIRED_LOGISTICS_CATALOG = "2025-2026"
REPAIRED_LOGISTICS_CREDENTIAL = "LOGISTICS_MANAGEMENT_2025"


# ======================================================================================
# OUTPUTS
# ======================================================================================

DEFAULT_OUTPUT_ROOT = Path(
    "data/processed/incremental_audit/fall_2026_refresh_20261007"
)

RUN_SCHEMA_VERSION = "fall_2026_incremental_empirical_v1"

CURRENT_SUMMARY_COLUMNS = [
    "student_id",
    "catalog_year",
    "credential_id",
    "requirements_met",
    "requirements_total",
    "requirements_missing",
    "requirements_unresolved",
    "audit_status",
    "award_term_sort",
    "award_term_taken",
    "invalidation_reason",
    "result_provenance",
]


# ======================================================================================
# PASSING-COURSE NORMALIZATION
# ======================================================================================

# Preserve the existing production normalizer's rank semantics.
GRADE_RANK = {
    "A": 4,
    "TA": 4,
    "B": 3,
    "TB": 3,
    "C": 2,
    "TC": 2,
    "D": 1,
    "TD": 1,
    "P": 1,
    "CR": 1,
    "S": 1,
}


def normalize_course_code(subject: object, number: object) -> str:
    subject_text = refresh.clean_text(subject)
    number_text = refresh.clean_text(number)

    if not subject_text or not number_text:
        return ""

    if number_text.endswith(".0"):
        number_text = number_text[:-2]

    number_text = number_text.split(".")[0].zfill(4)

    return f"{subject_text} {number_text}"


# ======================================================================================
# CLI / BASIC HELPERS
# ======================================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the resumable empirical Fall 2026 incremental audit "
            "against the validated six-year staged package."
        )
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=25,
        help="Students per resumable chunk.",
    )

    parser.add_argument(
        "--start-chunk",
        type=int,
        default=1,
        help="1-based chunk number to begin/resume from.",
    )

    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Optional number of chunks to execute; use 1 for smoke testing.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run chunk outputs that already have a completion marker.",
    )

    parser.add_argument(
        "--combine-only",
        action="store_true",
        help="Do not run audits; validate/combine already completed chunks.",
    )

    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Restricted local output directory.",
    )

    return parser.parse_args()


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)

    return digest.hexdigest()


def atomic_to_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(temp, index=False)
    temp.replace(path)


def atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp.replace(path)


def truthy(series: pd.Series) -> pd.Series:
    return refresh.truthy_series(series)


def pair_key(
    student_id: pd.Series,
    catalog_year: pd.Series,
) -> pd.Series:
    return (
        student_id.astype(str)
        + "|"
        + catalog_year.astype(str)
    )


def exact_key(
    student_id: pd.Series,
    catalog_year: pd.Series,
    credential_id: pd.Series,
) -> pd.Series:
    return (
        student_id.astype(str)
        + "|"
        + catalog_year.astype(str)
        + "|"
        + credential_id.astype(str)
    )


# ======================================================================================
# ENGINE CONFIGURATION
# ======================================================================================

def configure_engine_paths() -> None:
    engine.REQUIREMENTS = REQUIREMENTS
    engine.CORE_LOOKUP = CORE_LOOKUP
    engine.ELECTIVE_RULES = ELECTIVE_RULES
    engine.ACADEMIC_COURSE_CROSSWALK = ACADEMIC_COURSE_CROSSWALK
    engine.COMPOUND_REQUIREMENT_ALTERNATIVES = (
        COMPOUND_REQUIREMENT_ALTERNATIVES
    )
    engine.ALTERNATIVE_REQUIREMENT_PATHS = (
        ALTERNATIVE_REQUIREMENT_PATHS
    )


def load_engine_support(
    requirements: pd.DataFrame,
) -> dict:
    configure_engine_paths()

    core_lookup = engine.load_core_lookup()
    elective_rules = engine.load_elective_rules()
    academic_course_lookup = engine.load_academic_course_lookup()
    compound_alternatives = (
        engine.load_compound_requirement_alternatives()
    )
    alternative_paths = (
        engine.load_alternative_requirement_paths()
    )

    engine.validate_alternative_requirement_paths(
        alternative_paths,
        requirements,
    )

    alternative_path_lookup = (
        engine.build_alternative_path_lookup(
            alternative_paths
        )
    )

    return {
        "core_lookup": core_lookup,
        "elective_rules": elective_rules,
        "academic_course_lookup": academic_course_lookup,
        "compound_alternatives": compound_alternatives,
        "alternative_path_lookup": alternative_path_lookup,
    }


# ======================================================================================
# AUTHORITATIVE CURRENT ATTEMPT STATE
# ======================================================================================

def load_authoritative_attempt_state() -> dict:
    historical = refresh.read_historical_attempts(
        refresh.DEFAULT_HISTORICAL_ATTEMPTS
    )

    current_raw, current_sheet = refresh.read_new_attempts(
        refresh.DEFAULT_NEW_ATTEMPTS
    )

    current, conflicts = refresh.collapse_linked_sections(
        current_raw,
        label="CURRENT_2026",
    )

    if not conflicts.empty:
        raise RuntimeError(
            "Linked-section collapse found substantive disagreement. "
            "No audit will run until reviewed."
        )

    current_summer = current[
        current["term_sort"].eq(refresh.SUMMER_2026)
    ].copy()

    current_fall = current[
        current["term_sort"].eq(refresh.FALL_2026)
    ].copy()

    historical_summer = historical[
        historical["term_sort"].eq(refresh.SUMMER_2026)
    ].copy()

    # October 202660 supersedes the July 202660 snapshot for current state.
    refreshed = pd.concat(
        [
            historical[
                ~historical["term_sort"].eq(
                    refresh.SUMMER_2026
                )
            ],
            current[
                refresh.CANONICAL_ATTEMPT_COLUMNS
            ],
        ],
        ignore_index=True,
    )

    old_summer_ids = set(
        historical_summer["student_id"].unique()
    )
    summer_ids = set(
        current_summer["student_id"].unique()
    )
    fall_ids = set(
        current_fall["student_id"].unique()
    )

    affected_ids = (
        old_summer_ids
        | summer_ids
        | fall_ids
    )

    affected = refreshed[
        refreshed["student_id"].isin(affected_ids)
    ].copy()

    return {
        "historical": historical,
        "current_raw": current_raw,
        "current": current,
        "current_sheet": current_sheet,
        "current_summer": current_summer,
        "current_fall": current_fall,
        "historical_summer": historical_summer,
        "refreshed_all": refreshed,
        "affected": affected,
        "old_summer_ids": old_summer_ids,
        "summer_ids": summer_ids,
        "fall_ids": fall_ids,
        "affected_ids": affected_ids,
    }


# ======================================================================================
# AUDIT-COURSE VIEW
# ======================================================================================

def build_passing_course_view(
    affected_attempts: pd.DataFrame,
) -> pd.DataFrame:
    work = affected_attempts.copy()

    work["grade"] = (
        work["grade"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    work["course_code"] = [
        normalize_course_code(subject, number)
        for subject, number in zip(
            work["subject"],
            work["course_number"],
        )
    ]

    work["term_sort"] = pd.to_numeric(
        work["term_sort"],
        errors="coerce",
    )

    work = work[
        work["student_id"].ne("")
        & work["course_code"].ne("")
        & work["term_sort"].notna()
        & work["grade"].isin(
            eligibility_v2.PASSING_GRADES
        )
    ].copy()

    work["term_sort"] = work["term_sort"].astype(int)
    work["term_taken"] = (
        work["term_sort"].astype(str)
    )
    work["passed"] = True
    work["grade_rank"] = (
        work["grade"]
        .map(GRADE_RANK)
        .fillna(0)
        .astype(int)
    )

    # Match the established production normalizer:
    # highest passing grade rank, then latest term.
    work = work.sort_values(
        [
            "student_id",
            "course_code",
            "grade_rank",
            "term_sort",
        ],
        ascending=[
            True,
            True,
            False,
            False,
        ],
        kind="mergesort",
    )

    work = work.drop_duplicates(
        subset=[
            "student_id",
            "course_code",
        ],
        keep="first",
    ).copy()

    keep = [
        "student_id",
        "student_major",
        "course_code",
        "subject",
        "course_number",
        "grade",
        "passed",
        "grade_rank",
        "term_taken",
        "term_sort",
        "dual_credit_indicator",
        "high_school",
        "last_term_dual_credit",
        "source_dataset",
        "section",
    ]

    return work[keep].copy()


# ======================================================================================
# CURRENT STUDENT PROFILE -- PRESERVE, DO NOT OVER-INTERPRET
# ======================================================================================

def build_student_profile(
    affected_attempts: pd.DataFrame,
    *,
    fall_ids: set[str],
) -> pd.DataFrame:
    rows = []

    for student_id, group in affected_attempts.groupby(
        "student_id",
        sort=True,
    ):
        valid_terms = pd.to_numeric(
            group["term_sort"],
            errors="coerce",
        )

        if valid_terms.notna().any():
            latest_term = int(valid_terms.max())
            latest = group[
                pd.to_numeric(
                    group["term_sort"],
                    errors="coerce",
                ).eq(latest_term)
            ].copy()
        else:
            latest_term = ""
            latest = group.copy()

        def joined(column: str) -> str:
            values = sorted(
                {
                    refresh.clean_display(value)
                    for value in latest[column]
                    if refresh.clean_display(value)
                }
            )
            return "; ".join(values)

        rows.append(
            {
                "student_id": student_id,
                "first_name": joined("first_name"),
                "last_name": joined("last_name"),
                "latest_term_sort": latest_term,
                "current_major_values": joined(
                    "student_major"
                ),
                "dual_credit_indicator_values": joined(
                    "dual_credit_indicator"
                ),
                "high_school_values": joined(
                    "high_school"
                ),
                "last_term_dual_credit_values": joined(
                    "last_term_dual_credit"
                ),
                "current_fall_2026_enrollment": (
                    student_id in fall_ids
                ),
            }
        )

    return pd.DataFrame(rows)


# ======================================================================================
# ELIGIBILITY / BASELINE PRESENCE
# ======================================================================================

def build_refreshed_eligibility(
    affected_attempts: pd.DataFrame,
    catalog_years: list[str],
) -> pd.DataFrame:
    activity = refresh.activity_state(
        affected_attempts
    )

    return eligibility_v2.build_student_catalog_eligibility(
        activity_history=activity,
        catalog_years=catalog_years,
    )


def scan_prior_summary_student_ids(
    affected_ids: set[str],
) -> set[str]:
    require_file(PRIOR_SUMMARY)

    found: set[str] = set()

    for chunk in pd.read_csv(
        PRIOR_SUMMARY,
        dtype=str,
        usecols=["student_id"],
        chunksize=300_000,
        low_memory=False,
    ):
        ids = (
            chunk["student_id"]
            .fillna("")
            .map(refresh.clean_text)
        )

        found.update(
            ids[ids.isin(affected_ids)]
            .unique()
            .tolist()
        )

    return found


def build_current_eligible_pairs(
    refreshed_eligibility: pd.DataFrame,
    affected_ids: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    require_file(PRIOR_ELIGIBILITY)

    prior = pd.read_csv(
        PRIOR_ELIGIBILITY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    needed = {
        "student_id",
        "catalog_year",
        "catalog_eligible",
    }

    missing = needed - set(prior.columns)

    if missing:
        raise RuntimeError(
            "Prior eligibility missing columns: "
            + ", ".join(sorted(missing))
        )

    prior["student_id"] = (
        prior["student_id"].map(refresh.clean_text)
    )

    prior["catalog_year"] = (
        prior["catalog_year"]
        .astype(str)
        .str.strip()
    )

    unaffected_eligible = (
        prior[
            ~prior["student_id"].isin(affected_ids)
            & truthy(prior["catalog_eligible"])
        ][
            ["student_id", "catalog_year"]
        ]
        .drop_duplicates()
    )

    affected_eligible = (
        refreshed_eligibility[
            refreshed_eligibility[
                "catalog_eligible"
            ].eq(True)
        ][
            ["student_id", "catalog_year"]
        ]
        .drop_duplicates()
    )

    current = (
        pd.concat(
            [
                unaffected_eligible,
                affected_eligible,
            ],
            ignore_index=True,
        )
        .drop_duplicates()
        .sort_values(
            ["student_id", "catalog_year"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    return current, prior


# ======================================================================================
# EXACT CREDENTIAL-GRAIN INVALIDATION WORKLIST
# ======================================================================================

def build_worklist(
    *,
    refreshed_eligibility: pd.DataFrame,
    current_eligible_pairs: pd.DataFrame,
    passing_courses: pd.DataFrame,
    current_summer: pd.DataFrame,
    fall_ids: set[str],
    affected_ids: set[str],
    baseline_ids: set[str],
    requirements: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible_affected = (
        refreshed_eligibility[
            refreshed_eligibility[
                "catalog_eligible"
            ].eq(True)
        ][
            ["student_id", "catalog_year"]
        ]
        .drop_duplicates()
    )

    current_summer_ids = set(
        current_summer["student_id"].unique()
    )

    summer_grades = (
        current_summer["grade"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    summer_passing_ids = set(
        current_summer.loc[
            summer_grades.isin(
                eligibility_v2.PASSING_GRADES
            ),
            "student_id",
        ].unique()
    )

    no_baseline_ids = (
        affected_ids - baseline_ids
    )

    pair_reason_frames = []

    summer_pairs = eligible_affected[
        eligible_affected["student_id"].isin(
            summer_passing_ids
        )
    ].copy()
    summer_pairs["reason"] = (
        "SUMMER_2026_EARNED_TRANSCRIPT_CHANGE"
    )
    pair_reason_frames.append(summer_pairs)

    new_catalog_pairs = eligible_affected[
        eligible_affected["student_id"].isin(
            fall_ids
        )
        & eligible_affected["catalog_year"].eq(
            "2026-2027"
        )
    ].copy()
    new_catalog_pairs["reason"] = (
        "NEW_CATALOG_2026_2027"
    )
    pair_reason_frames.append(new_catalog_pairs)

    no_baseline_pairs = eligible_affected[
        eligible_affected["student_id"].isin(
            no_baseline_ids
        )
    ].copy()
    no_baseline_pairs["reason"] = (
        "NO_PRIOR_EMPIRICAL_BASELINE"
    )
    pair_reason_frames.append(no_baseline_pairs)

    pair_reasons = pd.concat(
        pair_reason_frames,
        ignore_index=True,
    )

    pair_reasons = (
        pair_reasons.groupby(
            ["student_id", "catalog_year"],
            as_index=False,
            sort=True,
        )["reason"]
        .agg(
            lambda values: ";".join(
                sorted(set(values))
            )
        )
    )

    credential_pairs = (
        requirements[
            ["catalog_year", "credential_id"]
        ]
        .drop_duplicates()
    )

    full_pair_worklist = pair_reasons.merge(
        credential_pairs,
        on="catalog_year",
        how="inner",
        validate="many_to_many",
    )

    # Exact rule-state invalidation:
    # audit repaired 2025 Logistics for EVERY currently eligible 2025-26 student,
    # even if the student's transcript itself did not change.
    logistics = current_eligible_pairs[
        current_eligible_pairs[
            "catalog_year"
        ].eq(REPAIRED_LOGISTICS_CATALOG)
    ].copy()

    logistics["credential_id"] = (
        REPAIRED_LOGISTICS_CREDENTIAL
    )
    logistics["reason"] = (
        "RULE_CHANGE_LOGISTICS_2025_PATH"
    )

    full_keys = (
        full_pair_worklist[
            [
                "student_id",
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .assign(_already=1)
    )

    logistics = logistics.merge(
        full_keys,
        on=[
            "student_id",
            "catalog_year",
            "credential_id",
        ],
        how="left",
    )

    logistics_only = logistics[
        logistics["_already"].isna()
    ][
        [
            "student_id",
            "catalog_year",
            "credential_id",
            "reason",
        ]
    ].copy()

    worklist = (
        pd.concat(
            [
                full_pair_worklist[
                    [
                        "student_id",
                        "catalog_year",
                        "credential_id",
                        "reason",
                    ]
                ],
                logistics_only,
            ],
            ignore_index=True,
        )
        .drop_duplicates(
            subset=[
                "student_id",
                "catalog_year",
                "credential_id",
            ],
            keep="first",
        )
        .sort_values(
            [
                "student_id",
                "catalog_year",
                "credential_id",
            ],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    return worklist, pair_reasons


# ======================================================================================
# SUMMARY LOGIC — MATCH PATH-AWARE ENGINE
# ======================================================================================

def summarize_one(
    rows: list[dict],
) -> dict:
    group = pd.DataFrame(rows)

    if group.empty:
        raise RuntimeError(
            "Audit engine returned no detail rows."
        )

    path_group = (
        group["path_group_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    path_selected = (
        group["path_selected"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    counted = group[
        path_group.eq("")
        | path_selected.eq("TRUE")
    ].copy()

    total = len(counted)
    met = int(
        counted["status"].eq("MET").sum()
    )
    unresolved = int(
        counted["status"]
        .astype(str)
        .str.startswith("UNRESOLVED")
        .sum()
    )
    missing = (
        total - met - unresolved
    )

    audit_status = engine.get_audit_status(
        missing,
        unresolved,
    )

    award_term_sort, award_term_taken = (
        engine.summarize_award_term(
            counted,
            audit_status,
        )
    )

    return {
        "requirements_met": met,
        "requirements_total": total,
        "requirements_missing": missing,
        "requirements_unresolved": unresolved,
        "audit_status": audit_status,
        "award_term_sort": award_term_sort,
        "award_term_taken": award_term_taken,
    }


# ======================================================================================
# MANIFEST / REPRODUCIBILITY
# ======================================================================================

def build_manifest() -> dict:
    files_to_hash = {
        "historical_attempts": (
            refresh.DEFAULT_HISTORICAL_ATTEMPTS
        ),
        "current_attempts": (
            refresh.DEFAULT_NEW_ATTEMPTS
        ),
        "requirements": REQUIREMENTS,
        "core_lookup": CORE_LOOKUP,
        "academic_course_crosswalk": (
            ACADEMIC_COURSE_CROSSWALK
        ),
        "elective_rules": ELECTIVE_RULES,
        "compound_alternatives": (
            COMPOUND_REQUIREMENT_ALTERNATIVES
        ),
        "alternative_paths": (
            ALTERNATIVE_REQUIREMENT_PATHS
        ),
        "eligibility_script": Path(
            eligibility_v2.__file__
        ),
        "engine_script": Path(
            engine.__file__
        ),
        "refresh_contract_script": Path(
            refresh.__file__
        ),
        "runner_script": Path(__file__),
    }

    for path in files_to_hash.values():
        require_file(path)

    require_file(PRIOR_SUMMARY)
    require_file(PRIOR_ELIGIBILITY)

    hashes = {
        name: {
            "path": str(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in files_to_hash.items()
    }

    prior_summary_stat = PRIOR_SUMMARY.stat()
    prior_eligibility_stat = (
        PRIOR_ELIGIBILITY.stat()
    )

    return {
        "run_schema_version": RUN_SCHEMA_VERSION,
        "files": hashes,
        "prior_summary": {
            "path": str(PRIOR_SUMMARY),
            "size_bytes": (
                prior_summary_stat.st_size
            ),
            "mtime_ns": (
                prior_summary_stat.st_mtime_ns
            ),
        },
        "prior_eligibility": {
            "path": str(PRIOR_ELIGIBILITY),
            "size_bytes": (
                prior_eligibility_stat.st_size
            ),
            "mtime_ns": (
                prior_eligibility_stat.st_mtime_ns
            ),
        },
        "known_rule_invalidations": [
            {
                "catalog_year": (
                    REPAIRED_LOGISTICS_CATALOG
                ),
                "credential_id": (
                    REPAIRED_LOGISTICS_CREDENTIAL
                ),
                "reason": (
                    "Validated 2025 Logistics "
                    "alternative-path repair"
                ),
            }
        ],
    }


def verify_or_write_manifest(
    output_root: Path,
) -> None:
    manifest_path = (
        output_root / "run_manifest.json"
    )

    current = build_manifest()

    if manifest_path.exists():
        prior = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        if prior != current:
            raise RuntimeError(
                "Run manifest changed. Existing chunk "
                "outputs cannot be safely reused. "
                "Use a new --output-root rather than "
                "mixing source/rule states."
            )

        return

    atomic_json(current, manifest_path)


# ======================================================================================
# RUN PLAN
# ======================================================================================

def build_run_state(
    output_root: Path,
) -> dict:
    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    needed = {
        "catalog_year",
        "credential_id",
        "requirement_id",
    }

    missing = needed - set(
        requirements.columns
    )

    if missing:
        raise RuntimeError(
            "Requirements master missing columns: "
            + ", ".join(sorted(missing))
        )

    requirements["catalog_year"] = (
        requirements["catalog_year"]
        .astype(str)
        .str.strip()
    )

    requirements["credential_id"] = (
        requirements["credential_id"]
        .astype(str)
        .str.strip()
    )

    catalog_years = sorted(
        requirements["catalog_year"]
        .dropna()
        .unique()
        .tolist()
    )

    if catalog_years != [
        "2021-2022",
        "2022-2023",
        "2023-2024",
        "2024-2025",
        "2025-2026",
        "2026-2027",
    ]:
        raise RuntimeError(
            "Unexpected staged catalog-year set: "
            + repr(catalog_years)
        )

    if not (
        (
            requirements[
                "catalog_year"
            ].eq(REPAIRED_LOGISTICS_CATALOG)
        )
        & (
            requirements[
                "credential_id"
            ].eq(REPAIRED_LOGISTICS_CREDENTIAL)
        )
    ).any():
        raise RuntimeError(
            "Known repaired Logistics credential "
            "not found in staged requirements."
        )

    attempt_state = (
        load_authoritative_attempt_state()
    )

    refreshed_eligibility = (
        build_refreshed_eligibility(
            attempt_state["affected"],
            catalog_years,
        )
    )

    current_eligible_pairs, prior_eligibility = (
        build_current_eligible_pairs(
            refreshed_eligibility,
            attempt_state["affected_ids"],
        )
    )

    passing_courses = build_passing_course_view(
        attempt_state["affected"]
    )

    baseline_ids = (
        scan_prior_summary_student_ids(
            attempt_state["affected_ids"]
        )
    )

    worklist, pair_reasons = build_worklist(
        refreshed_eligibility=refreshed_eligibility,
        current_eligible_pairs=current_eligible_pairs,
        passing_courses=passing_courses,
        current_summer=attempt_state[
            "current_summer"
        ],
        fall_ids=attempt_state["fall_ids"],
        affected_ids=attempt_state[
            "affected_ids"
        ],
        baseline_ids=baseline_ids,
        requirements=requirements,
    )

    student_profile = build_student_profile(
        attempt_state["affected"],
        fall_ids=attempt_state["fall_ids"],
    )

    # Hard eligibility sanity check established by the profiler:
    # every Fall 2026 student gains/holds 2026-2027 eligibility.
    fall_2026_eligible = set(
        refreshed_eligibility.loc[
            refreshed_eligibility[
                "catalog_year"
            ].eq("2026-2027")
            & refreshed_eligibility[
                "catalog_eligible"
            ].eq(True),
            "student_id",
        ].unique()
    )

    if fall_2026_eligible != (
        attempt_state["fall_ids"]
    ):
        missing_fall = (
            attempt_state["fall_ids"]
            - fall_2026_eligible
        )
        extra = (
            fall_2026_eligible
            - attempt_state["fall_ids"]
        )

        raise RuntimeError(
            "2026-2027 eligibility does not equal "
            "Fall enrollment population. "
            f"Missing Fall students={len(missing_fall):,}; "
            f"unexpected eligible students={len(extra):,}"
        )

    # Restricted state outputs. These are local data products, not Git artifacts.
    state_dir = output_root / "state"
    state_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    atomic_to_csv(
        refreshed_eligibility,
        state_dir
        / "RESTRICTED_refreshed_eligibility_affected.csv",
    )

    atomic_to_csv(
        current_eligible_pairs,
        state_dir
        / "RESTRICTED_current_eligible_pairs.csv",
    )

    atomic_to_csv(
        passing_courses,
        state_dir
        / "RESTRICTED_passing_course_view_affected.csv",
    )

    atomic_to_csv(
        worklist,
        state_dir
        / "RESTRICTED_exact_credential_worklist.csv",
    )

    atomic_to_csv(
        pair_reasons,
        state_dir
        / "RESTRICTED_full_pair_invalidation_reasons.csv",
    )

    atomic_to_csv(
        student_profile,
        state_dir
        / "RESTRICTED_current_student_profile.csv",
    )

    # FERPA-safe run plan.
    credentials_by_catalog = (
        requirements[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .groupby("catalog_year")
        .size()
        .to_dict()
    )

    worklist_by_catalog = (
        worklist.groupby("catalog_year")
        .agg(
            students=(
                "student_id",
                "nunique",
            ),
            credential_audits=(
                "credential_id",
                "size",
            ),
            distinct_credentials=(
                "credential_id",
                "nunique",
            ),
        )
        .reset_index()
    )

    worklist_by_catalog[
        "credentials_in_catalog"
    ] = (
        worklist_by_catalog[
            "catalog_year"
        ].map(credentials_by_catalog)
    )

    atomic_to_csv(
        worklist_by_catalog,
        output_root
        / "FERPA_SAFE_run_plan_by_catalog.csv",
    )

    reason_counts = (
        worklist["reason"]
        .value_counts()
        .rename_axis("reason")
        .reset_index(name="credential_audits")
    )

    atomic_to_csv(
        reason_counts,
        output_root
        / "FERPA_SAFE_run_plan_by_reason.csv",
    )

    return {
        "requirements": requirements,
        "catalog_years": catalog_years,
        "attempt_state": attempt_state,
        "refreshed_eligibility": (
            refreshed_eligibility
        ),
        "current_eligible_pairs": (
            current_eligible_pairs
        ),
        "prior_eligibility": prior_eligibility,
        "passing_courses": passing_courses,
        "baseline_ids": baseline_ids,
        "worklist": worklist,
        "pair_reasons": pair_reasons,
        "student_profile": student_profile,
        "worklist_by_catalog": (
            worklist_by_catalog
        ),
    }


# ======================================================================================
# CHUNKS
# ======================================================================================

def make_chunks(
    students: list[str],
    chunk_size: int,
) -> list[list[str]]:
    return [
        students[index:index + chunk_size]
        for index in range(
            0,
            len(students),
            chunk_size,
        )
    ]


def chunk_paths(
    chunk_dir: Path,
    number: int,
) -> dict[str, Path]:
    padded = f"{number:05d}"

    return {
        "detail": (
            chunk_dir
            / f"chunk_{padded}_detail.csv"
        ),
        "summary": (
            chunk_dir
            / f"chunk_{padded}_summary.csv"
        ),
        "marker": (
            chunk_dir
            / f"chunk_{padded}_COMPLETE.json"
        ),
    }


def run_one_chunk(
    *,
    chunk_number: int,
    student_ids: list[str],
    worklist: pd.DataFrame,
    passing_courses: pd.DataFrame,
    requirements: pd.DataFrame,
    engine_support: dict,
    paths: dict[str, Path],
) -> dict:
    started = time.time()

    chunk_worklist = worklist[
        worklist["student_id"].isin(
            student_ids
        )
    ].copy()

    chunk_courses = passing_courses[
        passing_courses["student_id"].isin(
            student_ids
        )
    ].copy()

    requirements_groups = {
        (str(catalog), str(credential)):
            group.copy()
        for (
            catalog,
            credential,
        ), group in requirements.groupby(
            [
                "catalog_year",
                "credential_id",
            ],
            sort=False,
        )
    }

    courses_by_student = {
        str(student):
            group.copy()
        for student, group in (
            chunk_courses.groupby(
                "student_id",
                sort=False,
            )
        )
    }

    work_by_student = {
        str(student):
            group.copy()
        for student, group in (
            chunk_worklist.groupby(
                "student_id",
                sort=False,
            )
        )
    }

    detail_rows: list[dict] = []
    summary_rows: list[dict] = []

    for student_id in student_ids:
        student_courses = (
            courses_by_student.get(
                student_id,
                pd.DataFrame(
                    columns=passing_courses.columns
                ),
            )
        )

        course_lookup = (
            engine.completed_course_lookup(
                student_courses
            )
        )

        student_work = (
            work_by_student.get(student_id)
        )

        if student_work is None:
            continue

        for _, target in student_work.iterrows():
            catalog_year = str(
                target["catalog_year"]
            )
            credential_id = str(
                target["credential_id"]
            )
            reason = str(
                target["reason"]
            )

            req_key = (
                catalog_year,
                credential_id,
            )

            credential_requirements = (
                requirements_groups.get(
                    req_key
                )
            )

            if credential_requirements is None:
                raise RuntimeError(
                    "Worklist target missing requirements: "
                    f"{catalog_year} / {credential_id}"
                )

            rows = engine.audit_student_credential(
                student_id=student_id,
                catalog_year=catalog_year,
                credential_id=credential_id,
                credential_requirements=(
                    credential_requirements
                ),
                course_lookup=course_lookup,
                core_lookup=engine_support[
                    "core_lookup"
                ],
                elective_rules=engine_support[
                    "elective_rules"
                ],
                academic_course_lookup=(
                    engine_support[
                        "academic_course_lookup"
                    ]
                ),
                compound_alternatives=(
                    engine_support[
                        "compound_alternatives"
                    ]
                ),
                alternative_path_lookup=(
                    engine_support[
                        "alternative_path_lookup"
                    ]
                ),
            )

            for row in rows:
                row["invalidation_reason"] = (
                    reason
                )
                row["result_provenance"] = (
                    "DELTA_RECOMPUTE_20261007"
                )

            detail_rows.extend(rows)

            summary = summarize_one(rows)

            summary_rows.append(
                {
                    "student_id": student_id,
                    "catalog_year": catalog_year,
                    "credential_id": (
                        credential_id
                    ),
                    **summary,
                    "invalidation_reason": (
                        reason
                    ),
                    "result_provenance": (
                        "DELTA_RECOMPUTE_20261007"
                    ),
                }
            )

    detail = pd.DataFrame(detail_rows)
    summary = pd.DataFrame(summary_rows)

    expected_summary = len(
        chunk_worklist
    )

    if len(summary) != expected_summary:
        raise RuntimeError(
            f"Chunk {chunk_number}: expected "
            f"{expected_summary:,} summary rows; "
            f"got {len(summary):,}"
        )

    if not summary.empty:
        dup = summary.duplicated(
            subset=[
                "student_id",
                "catalog_year",
                "credential_id",
            ],
            keep=False,
        )

        if dup.any():
            raise RuntimeError(
                f"Chunk {chunk_number}: duplicate "
                "summary keys detected."
            )

    atomic_to_csv(
        detail,
        paths["detail"],
    )

    atomic_to_csv(
        summary,
        paths["summary"],
    )

    elapsed = round(
        time.time() - started,
        2,
    )

    marker = {
        "chunk_number": chunk_number,
        "student_count": len(student_ids),
        "worklist_rows": len(
            chunk_worklist
        ),
        "summary_rows": len(summary),
        "detail_rows": len(detail),
        "elapsed_seconds": elapsed,
        "detail_path": str(
            paths["detail"]
        ),
        "summary_path": str(
            paths["summary"]
        ),
    }

    atomic_json(
        marker,
        paths["marker"],
    )

    return marker


# ======================================================================================
# COMBINATION / CURRENT EMPIRICAL SUMMARY
# ======================================================================================

def completed_chunk_numbers(
    chunk_dir: Path,
) -> set[int]:
    result = set()

    for marker in chunk_dir.glob(
        "chunk_*_COMPLETE.json"
    ):
        try:
            number = int(
                marker.name.split("_")[1]
            )
        except Exception:
            continue

        paths = chunk_paths(
            chunk_dir,
            number,
        )

        if (
            paths["detail"].exists()
            and paths["summary"].exists()
        ):
            result.add(number)

    return result


def combine_delta_summaries(
    *,
    chunk_dir: Path,
    total_chunks: int,
    worklist: pd.DataFrame,
    output_root: Path,
) -> pd.DataFrame:
    frames = []

    for number in range(
        1,
        total_chunks + 1,
    ):
        path = chunk_paths(
            chunk_dir,
            number,
        )["summary"]

        if not path.exists():
            raise RuntimeError(
                f"Missing completed summary chunk: {path}"
            )

        frames.append(
            pd.read_csv(
                path,
                dtype=str,
                low_memory=False,
            ).fillna("")
        )

    delta = pd.concat(
        frames,
        ignore_index=True,
    )

    if len(delta) != len(worklist):
        raise RuntimeError(
            "Combined delta summary row count "
            "does not equal exact worklist: "
            f"{len(delta):,} vs {len(worklist):,}"
        )

    key_cols = [
        "student_id",
        "catalog_year",
        "credential_id",
    ]

    if delta.duplicated(
        subset=key_cols,
        keep=False,
    ).any():
        raise RuntimeError(
            "Combined delta summary contains "
            "duplicate credential keys."
        )

    work_keys = set(
        map(
            tuple,
            worklist[
                key_cols
            ].values.tolist(),
        )
    )

    delta_keys = set(
        map(
            tuple,
            delta[
                key_cols
            ].values.tolist(),
        )
    )

    if work_keys != delta_keys:
        raise RuntimeError(
            "Combined delta summary key set "
            "does not equal exact worklist."
        )

    output = (
        output_root
        / "RESTRICTED_delta_credential_summary.csv"
    )

    atomic_to_csv(
        delta,
        output,
    )

    return delta


def build_current_empirical_summary(
    *,
    delta: pd.DataFrame,
    worklist: pd.DataFrame,
    current_eligible_pairs: pd.DataFrame,
    requirements: pd.DataFrame,
    output_root: Path,
) -> dict:
    output = (
        output_root
        / "RESTRICTED_current_eligible_empirical_credential_summary.csv"
    )

    temp = output.with_suffix(
        output.suffix + ".tmp"
    )

    current_pair_keys = set(
        pair_key(
            current_eligible_pairs[
                "student_id"
            ],
            current_eligible_pairs[
                "catalog_year"
            ],
        ).tolist()
    )

    recomputed_exact_keys = set(
        exact_key(
            worklist["student_id"],
            worklist["catalog_year"],
            worklist["credential_id"],
        ).tolist()
    )

    prior_header = pd.read_csv(
        PRIOR_SUMMARY,
        dtype=str,
        nrows=0,
    )

    required_prior = set(
        CURRENT_SUMMARY_COLUMNS[:-2]
    )

    missing_prior = (
        required_prior
        - set(prior_header.columns)
    )

    if missing_prior:
        raise RuntimeError(
            "Prior summary is missing core audit columns: "
            + ", ".join(sorted(missing_prior))
        )

    missing_delta = (
        set(CURRENT_SUMMARY_COLUMNS)
        - set(delta.columns)
    )

    if missing_delta:
        raise RuntimeError(
            "Delta summary is missing current-summary columns: "
            + ", ".join(sorted(missing_delta))
        )

    wrote_header = False
    cached_rows = 0

    if temp.exists():
        temp.unlink()

    for chunk in pd.read_csv(
        PRIOR_SUMMARY,
        dtype=str,
        chunksize=200_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")

        chunk["student_id"] = (
            chunk["student_id"].map(
                refresh.clean_text
            )
        )

        chunk["catalog_year"] = (
            chunk["catalog_year"]
            .astype(str)
            .str.strip()
        )

        chunk["credential_id"] = (
            chunk["credential_id"]
            .astype(str)
            .str.strip()
        )

        pkey = pair_key(
            chunk["student_id"],
            chunk["catalog_year"],
        )

        ekey = exact_key(
            chunk["student_id"],
            chunk["catalog_year"],
            chunk["credential_id"],
        )

        keep = (
            pkey.isin(current_pair_keys)
            & ~ekey.isin(
                recomputed_exact_keys
            )
        )

        selected = chunk.loc[
            keep,
            CURRENT_SUMMARY_COLUMNS[:-2],
        ].copy()

        if selected.empty:
            continue

        selected[
            "invalidation_reason"
        ] = ""

        selected[
            "result_provenance"
        ] = "CACHE_PRIOR_202607"

        selected = selected[
            CURRENT_SUMMARY_COLUMNS
        ]

        selected.to_csv(
            temp,
            mode="a",
            index=False,
            header=not wrote_header,
        )

        wrote_header = True
        cached_rows += len(selected)

    delta_current = delta[
        CURRENT_SUMMARY_COLUMNS
    ].copy()

    if delta_current.empty:
        raise RuntimeError(
            "Delta summary unexpectedly empty."
        )

    delta_current.to_csv(
        temp,
        mode="a",
        index=False,
        header=not wrote_header,
    )

    temp.replace(output)

    credential_count = (
        requirements[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .groupby("catalog_year")
        .size()
        .to_dict()
    )

    expected_current_rows = int(
        current_eligible_pairs[
            "catalog_year"
        ]
        .map(credential_count)
        .fillna(0)
        .sum()
    )

    actual_current_rows = (
        cached_rows + len(delta_current)
    )

    if actual_current_rows != (
        expected_current_rows
    ):
        raise RuntimeError(
            "Current empirical summary row count "
            "failed exact eligibility × credential "
            "reconciliation: "
            f"actual={actual_current_rows:,}; "
            f"expected={expected_current_rows:,}"
        )

    return {
        "current_summary_path": str(output),
        "cached_prior_rows": cached_rows,
        "delta_rows": len(delta_current),
        "current_rows": actual_current_rows,
        "expected_current_rows": (
            expected_current_rows
        ),
    }


def write_ferpa_safe_completion_report(
    *,
    delta: pd.DataFrame,
    worklist: pd.DataFrame,
    current_eligible_pairs: pd.DataFrame,
    requirements: pd.DataFrame,
    merge_metrics: dict,
    output_root: Path,
) -> None:
    status_counts = (
        delta.groupby(
            [
                "catalog_year",
                "audit_status",
            ],
            dropna=False,
        )
        .size()
        .rename("delta_credential_audits")
        .reset_index()
    )

    atomic_to_csv(
        status_counts,
        output_root
        / "FERPA_SAFE_delta_status_counts.csv",
    )

    review = delta[
        delta[
            "requirements_unresolved"
        ].astype(str).ne("0")
    ]

    review_counts = (
        review.groupby(
            [
                "catalog_year",
                "audit_status",
            ],
            dropna=False,
        )
        .size()
        .rename(
            "credential_audits_with_unresolved_requirements"
        )
        .reset_index()
    )

    atomic_to_csv(
        review_counts,
        output_root
        / "FERPA_SAFE_unresolved_status_counts.csv",
    )

    catalog_credentials = (
        requirements[
            [
                "catalog_year",
                "credential_id",
            ]
        ]
        .drop_duplicates()
        .groupby("catalog_year")
        .size()
        .rename("credential_count")
        .reset_index()
    )

    eligible_students = (
        current_eligible_pairs.groupby(
            "catalog_year"
        )["student_id"]
        .nunique()
        .rename("eligible_students")
        .reset_index()
    )

    expected = eligible_students.merge(
        catalog_credentials,
        on="catalog_year",
        how="left",
    )

    expected[
        "expected_current_summary_rows"
    ] = (
        expected["eligible_students"]
        * expected["credential_count"]
    )

    atomic_to_csv(
        expected,
        output_root
        / "FERPA_SAFE_current_universe_by_catalog.csv",
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": key,
                "value": value,
            }
            for key, value
            in merge_metrics.items()
        ]
    )

    atomic_to_csv(
        metrics,
        output_root
        / "FERPA_SAFE_merge_metrics.csv",
    )


# ======================================================================================
# MAIN
# ======================================================================================

def main() -> None:
    args = parse_args()

    if args.chunk_size <= 0:
        raise ValueError(
            "--chunk-size must be > 0"
        )

    output_root = Path(
        args.output_root
    )

    chunk_dir = (
        output_root / "chunks"
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    chunk_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in (
        REQUIREMENTS,
        CORE_LOOKUP,
        ACADEMIC_COURSE_CROSSWALK,
        ELECTIVE_RULES,
        COMPOUND_REQUIREMENT_ALTERNATIVES,
        ALTERNATIVE_REQUIREMENT_PATHS,
        PRIOR_SUMMARY,
        PRIOR_ELIGIBILITY,
        refresh.DEFAULT_HISTORICAL_ATTEMPTS,
        refresh.DEFAULT_NEW_ATTEMPTS,
    ):
        require_file(path)

    verify_or_write_manifest(
        output_root
    )

    print("=" * 100)
    print("LSCO FALL 2026 INCREMENTAL EMPIRICAL AUDIT")
    print("=" * 100)
    print(
        "Production July audit files will NOT be overwritten."
    )
    print(
        "Hypothetical Fall-success projection is NOT part of this run."
    )
    print()

    state_started = time.time()

    state = build_run_state(
        output_root
    )

    requirements = state[
        "requirements"
    ]
    worklist = state[
        "worklist"
    ]
    passing_courses = state[
        "passing_courses"
    ]
    current_eligible_pairs = state[
        "current_eligible_pairs"
    ]
    attempt_state = state[
        "attempt_state"
    ]

    print(
        f"Affected students:                    "
        f"{len(attempt_state['affected_ids']):,}"
    )
    print(
        f"Fall 2026 students:                   "
        f"{len(attempt_state['fall_ids']):,}"
    )
    print(
        f"Current eligible student/catalogs:    "
        f"{len(current_eligible_pairs):,}"
    )
    print(
        f"Exact credential audits in worklist:  "
        f"{len(worklist):,}"
    )
    print(
        f"Students in audit worklist:           "
        f"{worklist['student_id'].nunique():,}"
    )
    print(
        f"Run-state build seconds:              "
        f"{time.time() - state_started:.2f}"
    )
    print()

    print("WORKLIST BY CATALOG")
    print(
        state[
            "worklist_by_catalog"
        ].to_string(index=False)
    )
    print()

    logistics_count = int(
        (
            worklist["catalog_year"].eq(
                REPAIRED_LOGISTICS_CATALOG
            )
            & worklist["credential_id"].eq(
                REPAIRED_LOGISTICS_CREDENTIAL
            )
        ).sum()
    )

    print(
        "Targeted 2025 Logistics audits:       "
        f"{logistics_count:,}"
    )
    print()

    engine_support = (
        load_engine_support(
            requirements
        )
    )

    students = sorted(
        worklist["student_id"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    chunks = make_chunks(
        students,
        args.chunk_size,
    )

    total_chunks = len(chunks)

    chunk_index_rows = []

    for number, ids in enumerate(
        chunks,
        start=1,
    ):
        for student_id in ids:
            chunk_index_rows.append(
                {
                    "student_id": student_id,
                    "chunk_number": number,
                }
            )

    atomic_to_csv(
        pd.DataFrame(chunk_index_rows),
        output_root
        / "state"
        / "RESTRICTED_student_chunk_index.csv",
    )

    print(
        f"Chunk size:                           "
        f"{args.chunk_size:,}"
    )
    print(
        f"Total chunks:                         "
        f"{total_chunks:,}"
    )
    print()

    if args.combine_only:
        completed = completed_chunk_numbers(
            chunk_dir
        )

        if len(completed) != total_chunks:
            raise RuntimeError(
                "--combine-only requested but not all "
                "chunks are complete: "
                f"{len(completed):,}/{total_chunks:,}"
            )
    else:
        chunks_run = 0

        for number, student_ids in enumerate(
            chunks,
            start=1,
        ):
            if number < args.start_chunk:
                continue

            if (
                args.limit_chunks is not None
                and chunks_run >= args.limit_chunks
            ):
                break

            paths = chunk_paths(
                chunk_dir,
                number,
            )

            if (
                not args.force
                and paths["marker"].exists()
                and paths["detail"].exists()
                and paths["summary"].exists()
            ):
                print(
                    f"[{number}/{total_chunks}] "
                    "skip completed"
                )
                continue

            print(
                f"[{number}/{total_chunks}] "
                f"students={len(student_ids):,}"
            )

            marker = run_one_chunk(
                chunk_number=number,
                student_ids=student_ids,
                worklist=worklist,
                passing_courses=passing_courses,
                requirements=requirements,
                engine_support=engine_support,
                paths=paths,
            )

            chunks_run += 1

            print(
                "  credential audits="
                f"{marker['summary_rows']:,}; "
                "detail rows="
                f"{marker['detail_rows']:,}; "
                "seconds="
                f"{marker['elapsed_seconds']:,}"
            )

    completed = completed_chunk_numbers(
        chunk_dir
    )

    print()
    print(
        f"Completed chunks:                     "
        f"{len(completed):,}/{total_chunks:,}"
    )

    if len(completed) != total_chunks:
        print()
        print(
            "PARTIAL RUN COMPLETE. "
            "No merged current empirical summary was written."
        )
        print(
            "Re-run the same command without --force to resume."
        )
        print(
            f"Restricted output: {output_root}"
        )
        return

    print()
    print(
        "All chunks complete. Combining delta summaries..."
    )

    delta = combine_delta_summaries(
        chunk_dir=chunk_dir,
        total_chunks=total_chunks,
        worklist=worklist,
        output_root=output_root,
    )

    print(
        "Building current eligible empirical "
        "summary from cache + exact invalidations..."
    )

    merge_metrics = (
        build_current_empirical_summary(
            delta=delta,
            worklist=worklist,
            current_eligible_pairs=(
                current_eligible_pairs
            ),
            requirements=requirements,
            output_root=output_root,
        )
    )

    write_ferpa_safe_completion_report(
        delta=delta,
        worklist=worklist,
        current_eligible_pairs=(
            current_eligible_pairs
        ),
        requirements=requirements,
        merge_metrics=merge_metrics,
        output_root=output_root,
    )

    print()
    print("=" * 100)
    print("INCREMENTAL EMPIRICAL AUDIT COMPLETE")
    print("=" * 100)
    print(
        f"Delta credential audits:              "
        f"{len(delta):,}"
    )
    print(
        f"Cached prior current rows:            "
        f"{merge_metrics['cached_prior_rows']:,}"
    )
    print(
        f"Current eligible empirical rows:      "
        f"{merge_metrics['current_rows']:,}"
    )
    print(
        f"Exact expected current rows:          "
        f"{merge_metrics['expected_current_rows']:,}"
    )
    print()
    print(
        "Detail results remain safely chunked "
        "to avoid building a multi-gigabyte monolithic CSV."
    )
    print(
        f"Restricted output: {output_root}"
    )
    print()
    print(
        "NEXT: official-award suppression / latest-complete "
        "lineage selection, then separate Fall-success projection."
    )


if __name__ == "__main__":
    main()
