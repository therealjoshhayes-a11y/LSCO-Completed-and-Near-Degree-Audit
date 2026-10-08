from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd


# ======================================================================================
# IMPORT THE ALREADY-COMPLETED FALL 2026 RUNNER / VALIDATED ENGINE CONTRACT
# ======================================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SRC_DIR = ROOT / "src"

for value in (str(SCRIPT_DIR), str(SRC_DIR)):
    if value not in sys.path:
        sys.path.insert(0, value)

import run_fall_2026_incremental_audit as base  # noqa: E402


# ======================================================================================
# PURPOSE
# ======================================================================================
# Recovery/backfill for the ONLY failure that occurred after all 476 expensive
# Fall 2026 delta chunks had completed.
#
# The original merge invariant assumed every catalog-eligible student already had
# a July empirical audit baseline. That is not true: the eligibility registry may
# contain students with enrollment activity but no rows in the July passing-course
# audit population.
#
# This script does NOT rerun the 476 completed chunks.
#
# It:
#   1. proves the July baseline summary is structurally complete for its own student set;
#   2. identifies exact current eligible credential keys with neither a July baseline
#      result nor an already-computed Fall-2026 delta result;
#   3. runs ONLY those missing credential keys through the SAME validated path-aware
#      six-year engine;
#   4. combines prior cache + original delta + supplemental backfill;
#   5. requires exact reconciliation to current eligibility × catalog credentials;
#   6. writes FERPA-safe recovery diagnostics and the final restricted empirical summary.
#
# Run from repository root:
#   python -u .\scripts\recover_fall_2026_empirical_merge.py
#
# It is resumable. Do not use --force unless a backfill chunk itself is known bad.


DEFAULT_OUTPUT_ROOT = base.DEFAULT_OUTPUT_ROOT

PRIOR_PASSING_COURSES = Path(
    "data/processed/normalized_actual_student_course_history.csv"
)

CURRENT_SUMMARY_COLUMNS = base.CURRENT_SUMMARY_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill exact empirical keys missing from the July cache and "
            "finish the Fall 2026 current empirical merge."
        )
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Optional smoke limit. Omit to finish the recovery.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
    )
    return parser.parse_args()


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def atomic_to_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(temp, index=False)
    temp.replace(path)


def exact_key_frame(df: pd.DataFrame) -> pd.Series:
    return base.exact_key(
        df["student_id"],
        df["catalog_year"],
        df["credential_id"],
    )


def pair_key_frame(df: pd.DataFrame) -> pd.Series:
    return base.pair_key(
        df["student_id"],
        df["catalog_year"],
    )


# ======================================================================================
# PROVE WHAT THE JULY EMPIRICAL CACHE ACTUALLY CONTAINS
# ======================================================================================

def scan_prior_baseline(
    staged_requirements: pd.DataFrame,
) -> dict:
    require(base.PRIOR_SUMMARY)

    staged_historical_pairs = set(
        map(
            tuple,
            staged_requirements.loc[
                ~staged_requirements["catalog_year"].eq("2026-2027"),
                ["catalog_year", "credential_id"],
            ]
            .drop_duplicates()
            .values.tolist(),
        )
    )

    student_counts: Counter[str] = Counter()
    prior_pairs: set[tuple[str, str]] = set()
    total_rows = 0

    for chunk in pd.read_csv(
        base.PRIOR_SUMMARY,
        dtype=str,
        usecols=["student_id", "catalog_year", "credential_id"],
        chunksize=250_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        chunk["student_id"] = chunk["student_id"].map(base.refresh.clean_text)
        chunk["catalog_year"] = chunk["catalog_year"].astype(str).str.strip()
        chunk["credential_id"] = chunk["credential_id"].astype(str).str.strip()

        total_rows += len(chunk)

        student_counts.update(
            chunk["student_id"].value_counts().to_dict()
        )

        prior_pairs.update(
            map(
                tuple,
                chunk[
                    ["catalog_year", "credential_id"]
                ]
                .drop_duplicates()
                .values.tolist(),
            )
        )

    if prior_pairs != staged_historical_pairs:
        missing = staged_historical_pairs - prior_pairs
        extra = prior_pairs - staged_historical_pairs
        raise RuntimeError(
            "July baseline credential-pair universe does not match the staged "
            "five historical catalogs. "
            f"missing_pairs={len(missing):,}; extra_pairs={len(extra):,}"
        )

    expected_per_baseline_student = len(prior_pairs)

    bad_student_counts = {
        student_id: count
        for student_id, count in student_counts.items()
        if count != expected_per_baseline_student
    }

    if bad_student_counts:
        raise RuntimeError(
            "July baseline is not a complete student × historical-credential "
            "Cartesian corpus. Students with unexpected row counts: "
            f"{len(bad_student_counts):,}"
        )

    baseline_ids = set(student_counts)

    return {
        "baseline_ids": baseline_ids,
        "baseline_rows": total_rows,
        "baseline_students": len(baseline_ids),
        "historical_credential_pairs": len(prior_pairs),
        "rows_per_baseline_student": expected_per_baseline_student,
    }


# ======================================================================================
# IDENTIFY THE EXACT MISSING KEYS
# ======================================================================================

def build_missing_worklist(
    *,
    current_eligible_pairs: pd.DataFrame,
    requirements: pd.DataFrame,
    original_delta: pd.DataFrame,
    baseline_ids: set[str],
) -> pd.DataFrame:
    credential_pairs = (
        requirements[
            ["catalog_year", "credential_id"]
        ]
        .drop_duplicates()
    )

    eligible_without_baseline = (
        current_eligible_pairs[
            ~current_eligible_pairs["student_id"].isin(baseline_ids)
        ]
        .copy()
    )

    candidates = eligible_without_baseline.merge(
        credential_pairs,
        on="catalog_year",
        how="inner",
        validate="many_to_many",
    )

    original_delta_keys = set(
        exact_key_frame(original_delta).tolist()
    )

    candidate_keys = exact_key_frame(candidates)

    missing = candidates.loc[
        ~candidate_keys.isin(original_delta_keys)
    ].copy()

    missing["reason"] = (
        "NO_JULY_EMPIRICAL_BASELINE_BACKFILL"
    )

    missing = (
        missing[
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "reason",
            ]
        ]
        .drop_duplicates(
            subset=[
                "student_id",
                "catalog_year",
                "credential_id",
            ]
        )
        .sort_values(
            ["student_id", "catalog_year", "credential_id"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    return missing


# ======================================================================================
# COURSE VIEW FOR ONLY THE MISSING STUDENTS
# ======================================================================================

def load_missing_student_courses(
    *,
    missing_ids: set[str],
    output_root: Path,
) -> pd.DataFrame:
    require(PRIOR_PASSING_COURSES)

    prior = pd.read_csv(
        PRIOR_PASSING_COURSES,
        dtype=str,
        low_memory=False,
    ).fillna("")

    prior["student_id"] = (
        prior["student_id"].map(
            base.refresh.clean_text
        )
    )

    prior = prior[
        prior["student_id"].isin(missing_ids)
    ].copy()

    # If any missing student is part of the refreshed affected population,
    # authoritative refreshed passing rows must supersede the July passing view.
    refreshed_path = (
        output_root
        / "state"
        / "RESTRICTED_passing_course_view_affected.csv"
    )
    require(refreshed_path)

    refreshed = pd.read_csv(
        refreshed_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    refreshed["student_id"] = (
        refreshed["student_id"].map(
            base.refresh.clean_text
        )
    )

    refreshed = refreshed[
        refreshed["student_id"].isin(missing_ids)
    ].copy()

    refreshed_ids = set(
        refreshed["student_id"].unique()
    )

    if refreshed_ids:
        prior = prior[
            ~prior["student_id"].isin(
                refreshed_ids
            )
        ].copy()

    all_columns = sorted(
        set(prior.columns)
        | set(refreshed.columns)
    )

    for frame in (prior, refreshed):
        for column in all_columns:
            if column not in frame.columns:
                frame[column] = ""

    courses = pd.concat(
        [
            prior[all_columns],
            refreshed[all_columns],
        ],
        ignore_index=True,
    )

    return courses


# ======================================================================================
# RESUMABLE SUPPLEMENTAL BACKFILL
# ======================================================================================

def make_chunks(students: list[str], chunk_size: int) -> list[list[str]]:
    return [
        students[i:i + chunk_size]
        for i in range(0, len(students), chunk_size)
    ]


def combine_backfill_summaries(
    *,
    backfill_chunk_dir: Path,
    total_chunks: int,
    missing_worklist: pd.DataFrame,
    output_root: Path,
) -> pd.DataFrame:
    frames = []

    for number in range(1, total_chunks + 1):
        path = base.chunk_paths(
            backfill_chunk_dir,
            number,
        )["summary"]

        if not path.exists():
            raise RuntimeError(
                f"Missing backfill summary chunk: {path}"
            )

        frames.append(
            pd.read_csv(
                path,
                dtype=str,
                low_memory=False,
            ).fillna("")
        )

    backfill = pd.concat(
        frames,
        ignore_index=True,
    )

    if len(backfill) != len(missing_worklist):
        raise RuntimeError(
            "Backfill summary count does not equal missing-key worklist: "
            f"{len(backfill):,} vs {len(missing_worklist):,}"
        )

    if backfill.duplicated(
        subset=["student_id", "catalog_year", "credential_id"],
        keep=False,
    ).any():
        raise RuntimeError(
            "Backfill summary has duplicate exact credential keys."
        )

    expected_keys = set(
        exact_key_frame(missing_worklist).tolist()
    )
    actual_keys = set(
        exact_key_frame(backfill).tolist()
    )

    if expected_keys != actual_keys:
        raise RuntimeError(
            "Backfill key set does not equal missing-key worklist."
        )

    output = (
        output_root
        / "RESTRICTED_backfill_credential_summary.csv"
    )

    atomic_to_csv(
        backfill,
        output,
    )

    return backfill


# ======================================================================================
# FINAL CACHE + ORIGINAL DELTA + BACKFILL MERGE
# ======================================================================================

def write_final_current_summary(
    *,
    current_eligible_pairs: pd.DataFrame,
    requirements: pd.DataFrame,
    original_delta: pd.DataFrame,
    backfill: pd.DataFrame,
    output_root: Path,
) -> dict:
    combined_delta = pd.concat(
        [original_delta, backfill],
        ignore_index=True,
    )

    key_cols = [
        "student_id",
        "catalog_year",
        "credential_id",
    ]

    if combined_delta.duplicated(
        subset=key_cols,
        keep=False,
    ).any():
        raise RuntimeError(
            "Original delta + backfill contains duplicate exact keys."
        )

    current_pair_keys = set(
        pair_key_frame(current_eligible_pairs).tolist()
    )

    recomputed_keys = set(
        exact_key_frame(combined_delta).tolist()
    )

    output = (
        output_root
        / "RESTRICTED_current_eligible_empirical_credential_summary.csv"
    )

    temp = output.with_suffix(
        output.suffix + ".tmp"
    )

    if temp.exists():
        temp.unlink()

    wrote_header = False
    cached_rows = 0

    prior_header = pd.read_csv(
        base.PRIOR_SUMMARY,
        dtype=str,
        nrows=0,
    )

    missing_core = (
        set(CURRENT_SUMMARY_COLUMNS[:-2])
        - set(prior_header.columns)
    )

    if missing_core:
        raise RuntimeError(
            "Prior summary missing core audit columns: "
            + ", ".join(sorted(missing_core))
        )

    for chunk in pd.read_csv(
        base.PRIOR_SUMMARY,
        dtype=str,
        chunksize=200_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        chunk["student_id"] = chunk["student_id"].map(
            base.refresh.clean_text
        )
        chunk["catalog_year"] = chunk["catalog_year"].astype(str).str.strip()
        chunk["credential_id"] = chunk["credential_id"].astype(str).str.strip()

        pkeys = pair_key_frame(chunk)
        ekeys = exact_key_frame(chunk)

        keep = (
            pkeys.isin(current_pair_keys)
            & ~ekeys.isin(recomputed_keys)
        )

        selected = chunk.loc[
            keep,
            CURRENT_SUMMARY_COLUMNS[:-2],
        ].copy()

        if selected.empty:
            continue

        selected["invalidation_reason"] = ""
        selected["result_provenance"] = (
            "CACHE_PRIOR_202607"
        )

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

    combined_current = combined_delta[
        CURRENT_SUMMARY_COLUMNS
    ].copy()

    combined_current.to_csv(
        temp,
        mode="a",
        index=False,
        header=not wrote_header,
    )

    credential_count = (
        requirements[
            ["catalog_year", "credential_id"]
        ]
        .drop_duplicates()
        .groupby("catalog_year")
        .size()
        .to_dict()
    )

    expected_rows = int(
        current_eligible_pairs[
            "catalog_year"
        ]
        .map(credential_count)
        .fillna(0)
        .sum()
    )

    actual_rows = (
        cached_rows
        + len(combined_current)
    )

    if actual_rows != expected_rows:
        raise RuntimeError(
            "Recovery merge still does not reconcile exactly: "
            f"actual={actual_rows:,}; expected={expected_rows:,}"
        )

    temp.replace(output)

    return {
        "cached_prior_rows": cached_rows,
        "original_delta_rows": len(original_delta),
        "backfill_rows": len(backfill),
        "combined_recomputed_rows": len(combined_current),
        "actual_current_rows": actual_rows,
        "expected_current_rows": expected_rows,
        "final_summary_path": str(output),
    }


# ======================================================================================
# MAIN
# ======================================================================================

def main() -> None:
    args = parse_args()

    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be > 0")

    output_root = Path(args.output_root)

    state_dir = output_root / "state"
    original_delta_path = (
        output_root
        / "RESTRICTED_delta_credential_summary.csv"
    )
    current_pairs_path = (
        state_dir
        / "RESTRICTED_current_eligible_pairs.csv"
    )

    for path in (
        base.REQUIREMENTS,
        base.PRIOR_SUMMARY,
        base.PRIOR_ELIGIBILITY,
        original_delta_path,
        current_pairs_path,
    ):
        require(path)

    print("=" * 100)
    print("FALL 2026 EMPIRICAL MERGE RECOVERY")
    print("=" * 100)
    print("The 476 completed original audit chunks will NOT be rerun.")
    print()

    requirements = pd.read_csv(
        base.REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

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

    current_eligible_pairs = pd.read_csv(
        current_pairs_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    current_eligible_pairs["student_id"] = (
        current_eligible_pairs["student_id"]
        .map(base.refresh.clean_text)
    )
    current_eligible_pairs["catalog_year"] = (
        current_eligible_pairs["catalog_year"]
        .astype(str)
        .str.strip()
    )

    original_delta = pd.read_csv(
        original_delta_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    print("Proving July baseline structure...")
    baseline = scan_prior_baseline(
        requirements
    )

    print(
        f"July baseline students:                "
        f"{baseline['baseline_students']:,}"
    )
    print(
        f"Rows per July baseline student:        "
        f"{baseline['rows_per_baseline_student']:,}"
    )
    print(
        f"July baseline rows:                    "
        f"{baseline['baseline_rows']:,}"
    )
    print()

    missing_worklist = build_missing_worklist(
        current_eligible_pairs=current_eligible_pairs,
        requirements=requirements,
        original_delta=original_delta,
        baseline_ids=baseline["baseline_ids"],
    )

    missing_ids = set(
        missing_worklist["student_id"].unique()
    )

    print("EXACT MERGE GAP")
    print(
        f"Students with missing empirical keys:  "
        f"{len(missing_ids):,}"
    )
    print(
        f"Missing credential keys:               "
        f"{len(missing_worklist):,}"
    )

    by_catalog = (
        missing_worklist.groupby("catalog_year")
        .agg(
            students=("student_id", "nunique"),
            missing_credential_keys=("credential_id", "size"),
        )
        .reset_index()
    )

    print()
    print("MISSING KEYS BY CATALOG")
    if by_catalog.empty:
        print("<none>")
    else:
        print(by_catalog.to_string(index=False))
    print()

    atomic_to_csv(
        by_catalog,
        output_root
        / "FERPA_SAFE_merge_gap_by_catalog.csv",
    )

    metrics_before = pd.DataFrame(
        [
            {
                "metric": "baseline_students",
                "value": baseline["baseline_students"],
            },
            {
                "metric": "baseline_rows",
                "value": baseline["baseline_rows"],
            },
            {
                "metric": "original_delta_rows",
                "value": len(original_delta),
            },
            {
                "metric": "missing_students",
                "value": len(missing_ids),
            },
            {
                "metric": "missing_credential_keys",
                "value": len(missing_worklist),
            },
        ]
    )

    atomic_to_csv(
        metrics_before,
        output_root
        / "FERPA_SAFE_merge_gap_metrics.csv",
    )

    if missing_worklist.empty:
        print(
            "No missing keys remain. Proceeding directly to final merge."
        )
        backfill = pd.DataFrame(
            columns=original_delta.columns
        )
    else:
        backfill_root = (
            output_root / "recovery_backfill"
        )
        chunk_dir = (
            backfill_root / "chunks"
        )
        chunk_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        atomic_to_csv(
            missing_worklist,
            backfill_root
            / "RESTRICTED_missing_exact_worklist.csv",
        )

        courses = load_missing_student_courses(
            missing_ids=missing_ids,
            output_root=output_root,
        )

        print(
            f"Passing-course rows for missing students: "
            f"{len(courses):,}"
        )
        print()

        engine_support = base.load_engine_support(
            requirements
        )

        students = sorted(missing_ids)
        chunks = make_chunks(
            students,
            args.chunk_size,
        )
        total_chunks = len(chunks)

        print(
            f"Backfill chunks:                       "
            f"{total_chunks:,}"
        )
        print()

        chunks_run = 0

        for number, student_ids in enumerate(
            chunks,
            start=1,
        ):
            if (
                args.limit_chunks is not None
                and chunks_run >= args.limit_chunks
            ):
                break

            paths = base.chunk_paths(
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
                    f"[backfill {number}/{total_chunks}] skip completed"
                )
                continue

            print(
                f"[backfill {number}/{total_chunks}] "
                f"students={len(student_ids):,}"
            )

            marker = base.run_one_chunk(
                chunk_number=number,
                student_ids=student_ids,
                worklist=missing_worklist,
                passing_courses=courses,
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

        completed = base.completed_chunk_numbers(
            chunk_dir
        )

        print()
        print(
            f"Completed backfill chunks:             "
            f"{len(completed):,}/{total_chunks:,}"
        )

        if len(completed) != total_chunks:
            print()
            print(
                "PARTIAL RECOVERY COMPLETE. Re-run the same command "
                "to resume; original 476 chunks remain untouched."
            )
            return

        backfill = combine_backfill_summaries(
            backfill_chunk_dir=chunk_dir,
            total_chunks=total_chunks,
            missing_worklist=missing_worklist,
            output_root=output_root,
        )

    print()
    print("Writing exact current empirical summary...")

    merge_metrics = write_final_current_summary(
        current_eligible_pairs=current_eligible_pairs,
        requirements=requirements,
        original_delta=original_delta,
        backfill=backfill,
        output_root=output_root,
    )

    final_metrics = pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in merge_metrics.items()
        ]
    )

    atomic_to_csv(
        final_metrics,
        output_root
        / "FERPA_SAFE_recovery_merge_metrics.csv",
    )

    print()
    print("=" * 100)
    print("RECOVERY MERGE COMPLETE")
    print("=" * 100)

    for key, value in merge_metrics.items():
        print(
            f"{key}: {value}"
        )

    print()
    print(
        "The empirical universe now reconciles exactly. "
        "Original 476 chunk detail outputs remain unchanged."
    )


if __name__ == "__main__":
    main()
