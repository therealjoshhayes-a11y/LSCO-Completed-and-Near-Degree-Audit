#!/usr/bin/env python
"""
Safely merge the approved missing-health-credentials overlay into the production
multicatalog requirements master, rebuild the executable multiyear requirements
layer, and run rollback-protected integrity tests.

Expected workflow:
    python ./scripts/merge_missing_health_credentials_into_production.py

Safety:
- Regenerates and verifies the v9 overlay first.
- Creates timestamped backups of both production CSVs.
- Writes through temporary files and uses atomic replacement.
- Verifies all non-target production rows are byte-equivalent by normalized hash.
- Rolls back both production files if merge, rebuild, or post-build validation fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError


TARGET_CREDENTIAL_IDS = {
    "REGISTERED_NURSING_AAS_2021",
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2021",
    "REGISTERED_NURSING_TRANSITION_2022",
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2022",
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2023",
    "REGISTERED_NURSING_TRANSITION_2023",
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2023",
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2024",
    "REGISTERED_NURSING_TRANSITION_2024",
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2024",
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2025",
    "REGISTERED_NURSING_TRANSITION_2025",
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2025",
    "PHYSICAL_THERAPY_ASSISTANT_2025",
}

EXPECTED_AUDITABLE_HOURS = {
    "REGISTERED_NURSING_AAS_2021": 36,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2021": 39,
    "REGISTERED_NURSING_TRANSITION_2022": 36,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2022": 39,
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2023": 46,
    "REGISTERED_NURSING_TRANSITION_2023": 36,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2023": 43,
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2024": 46,
    "REGISTERED_NURSING_TRANSITION_2024": 39,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2024": 43,
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2025": 46,
    "REGISTERED_NURSING_TRANSITION_2025": 39,
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2025": 43,
    "PHYSICAL_THERAPY_ASSISTANT_2025": 52,
}

ALLOWED_SOURCE_RULE_TYPES = {"EXACT", "ANY_N", "CORE_BUCKET", "ELECTIVE"}
PASS_STATUS = "PASS_AUDITABLE_TOTAL_MATCH"


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        fail(f"Required file not found: {path}")
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except EmptyDataError:
        return pd.DataFrame()


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def normalized_frame_hash(df: pd.DataFrame) -> str:
    """Stable content hash independent of DataFrame index."""
    if df.empty:
        return hashlib.sha256(b"").hexdigest()

    normalized = df.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    for column in normalized.columns:
        normalized[column] = normalized[column].fillna("").astype(str)

    sort_columns = [
        column
        for column in ("catalog_year", "credential_id", "requirement_id")
        if column in normalized.columns
    ]
    if sort_columns:
        normalized = normalized.sort_values(sort_columns, kind="stable")
    else:
        normalized = normalized.sort_values(list(normalized.columns), kind="stable")

    payload = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_checked(command: list[str], cwd: Path, label: str) -> None:
    print(f"\nRUNNING: {label}")
    print(" ".join(command))
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode != 0:
        fail(f"{label} failed with exit code {completed.returncode}")


def validate_overlay(
    overlay: pd.DataFrame,
    validation: pd.DataFrame,
    duplicates: pd.DataFrame,
) -> None:
    required_columns = {
        "requirement_id",
        "catalog_year",
        "credential_id",
        "credential_title",
        "rule_type",
        "credit_hours",
    }
    missing = sorted(required_columns - set(overlay.columns))
    if missing:
        fail(f"Overlay is missing required columns: {missing}")

    credential_ids = set(overlay["credential_id"])
    if credential_ids != TARGET_CREDENTIAL_IDS:
        fail(
            "Overlay credential IDs do not match approved target set.\n"
            f"Missing: {sorted(TARGET_CREDENTIAL_IDS - credential_ids)}\n"
            f"Unexpected: {sorted(credential_ids - TARGET_CREDENTIAL_IDS)}"
        )

    if len(overlay) != 200:
        fail(f"Overlay must contain exactly 200 rows; found {len(overlay)}")

    if overlay["requirement_id"].duplicated().any():
        fail("Overlay contains duplicate requirement IDs")

    if not duplicates.empty:
        fail(f"Duplicate-ID report is not empty ({len(duplicates)} rows)")

    bad_rule_types = sorted(set(overlay["rule_type"]) - ALLOWED_SOURCE_RULE_TYPES)
    if bad_rule_types:
        fail(f"Overlay contains unsupported source rule types: {bad_rule_types}")

    if (numeric(overlay["credit_hours"]) <= 0).any():
        fail("Overlay contains zero, negative, or nonnumeric credit hours")

    validation_ids = set(validation["credential_id"])
    if validation_ids != TARGET_CREDENTIAL_IDS:
        fail("Validation report credential IDs do not match approved target set")

    bad_status = validation.loc[
        validation["validation_status"] != PASS_STATUS,
        ["catalog_year", "credential_id", "validation_status"],
    ]
    if not bad_status.empty:
        fail(
            "Overlay validation contains non-pass rows:\n"
            + bad_status.to_string(index=False)
        )

    if len(validation) != 14:
        fail(f"Validation report must contain 14 credential-years; found {len(validation)}")

    totals = (
        overlay.assign(_hours=numeric(overlay["credit_hours"]))
        .groupby("credential_id", as_index=True)["_hours"]
        .sum()
        .to_dict()
    )
    mismatches = {
        credential_id: {
            "expected": expected,
            "actual": totals.get(credential_id),
        }
        for credential_id, expected in EXPECTED_AUDITABLE_HOURS.items()
        if float(totals.get(credential_id, -1)) != float(expected)
    }
    if mismatches:
        fail("Overlay auditable-hour mismatch:\n" + json.dumps(mismatches, indent=2))


def align_overlay_to_master(
    overlay: pd.DataFrame,
    master: pd.DataFrame,
) -> pd.DataFrame:
    aligned = overlay.copy()

    # Production master columns are authoritative. Missing overlay fields are blank;
    # extra diagnostic fields are not injected into production.
    for column in master.columns:
        if column not in aligned.columns:
            aligned[column] = ""

    return aligned.loc[:, master.columns]


def validate_merged_source(
    before: pd.DataFrame,
    merged: pd.DataFrame,
    overlay: pd.DataFrame,
) -> dict:
    required = {"requirement_id", "credential_id", "catalog_year", "rule_type", "credit_hours"}
    missing = sorted(required - set(merged.columns))
    if missing:
        fail(f"Merged source master is missing required columns: {missing}")

    before_non_target = before.loc[
        ~before["credential_id"].isin(TARGET_CREDENTIAL_IDS)
    ].copy()
    after_non_target = merged.loc[
        ~merged["credential_id"].isin(TARGET_CREDENTIAL_IDS)
    ].copy()

    before_hash = normalized_frame_hash(before_non_target)
    after_hash = normalized_frame_hash(after_non_target)
    if before_hash != after_hash:
        fail("Non-target source-master rows changed during merge")

    target_rows = merged.loc[
        merged["credential_id"].isin(TARGET_CREDENTIAL_IDS)
    ].copy()
    if len(target_rows) != len(overlay):
        fail(
            f"Merged target row count must be {len(overlay)}; found {len(target_rows)}"
        )

    if merged["requirement_id"].duplicated().any():
        dupes = merged.loc[
            merged["requirement_id"].duplicated(keep=False),
            ["requirement_id", "credential_id", "catalog_year"],
        ]
        fail("Merged source master has duplicate requirement IDs:\n" + dupes.to_string(index=False))

    if target_rows["requirement_id"].duplicated().any():
        fail("Merged target rows contain duplicate requirement IDs")

    if set(target_rows["credential_id"]) != TARGET_CREDENTIAL_IDS:
        fail("Merged source master does not contain the complete target credential set")

    if target_rows["rule_type"].eq("").any():
        fail("Merged target rows contain missing rule_type")

    if (numeric(target_rows["credit_hours"]) <= 0).any():
        fail("Merged target rows contain invalid credit_hours")

    removed_existing = len(
        before.loc[before["credential_id"].isin(TARGET_CREDENTIAL_IDS)]
    )
    expected_rows = len(before) - removed_existing + len(overlay)
    if len(merged) != expected_rows:
        fail(
            f"Unexpected merged row count: expected {expected_rows}, found {len(merged)}"
        )

    return {
        "before_rows": len(before),
        "removed_existing_target_rows": removed_existing,
        "overlay_rows_added": len(overlay),
        "after_rows": len(merged),
        "non_target_hash": after_hash,
    }


def validate_rebuilt_audit(
    rebuilt: pd.DataFrame,
    baseline: pd.DataFrame | None,
) -> dict:
    required = {
        "credential_id",
        "catalog_year",
        "requirement_id",
        "rule_type",
        "credit_hours",
    }
    missing = sorted(required - set(rebuilt.columns))
    if missing:
        fail(f"Rebuilt audit master is missing required columns: {missing}")

    target = rebuilt.loc[
        rebuilt["credential_id"].isin(TARGET_CREDENTIAL_IDS)
    ].copy()
    if target.empty:
        fail("Rebuilt audit master contains none of the merged credentials")

    if set(target["credential_id"]) != TARGET_CREDENTIAL_IDS:
        missing_ids = TARGET_CREDENTIAL_IDS - set(target["credential_id"])
        fail(f"Rebuilt audit master is missing target IDs: {sorted(missing_ids)}")

    if rebuilt["requirement_id"].eq("").any():
        fail("Rebuilt audit master contains blank requirement_id")

    if rebuilt["rule_type"].eq("").any():
        fail("Rebuilt audit master contains blank rule_type")

    if (numeric(rebuilt["credit_hours"]) <= 0).any():
        fail("Rebuilt audit master contains invalid credit_hours")

    # requirement_id may legitimately repeat after option explosion, so test exact
    # duplicate executable rows rather than requirement_id alone.
    duplicate_key = [
        column
        for column in (
            "requirement_id",
            "credential_id",
            "catalog_year",
            "rule_type",
            "course_code",
            "course_codes",
            "option_type",
        )
        if column in rebuilt.columns
    ]
    exact_dupes = rebuilt.duplicated(subset=duplicate_key, keep=False)
    if exact_dupes.any():
        sample = rebuilt.loc[exact_dupes, duplicate_key].head(20)
        fail(
            "Rebuilt audit master contains exact duplicate executable rows:\n"
            + sample.to_string(index=False)
        )

    non_target_preserved = None
    if baseline is not None and "credential_id" in baseline.columns:
        before_non_target = baseline.loc[
            ~baseline["credential_id"].isin(TARGET_CREDENTIAL_IDS)
        ].copy()
        after_non_target = rebuilt.loc[
            ~rebuilt["credential_id"].isin(TARGET_CREDENTIAL_IDS)
        ].copy()

        # Rebuild scripts should be deterministic. This is the strongest regression test.
        before_hash = normalized_frame_hash(before_non_target)
        after_hash = normalized_frame_hash(after_non_target)
        non_target_preserved = before_hash == after_hash
        if not non_target_preserved:
            fail("Rebuild changed non-target executable audit rows")

    credential_years = (
        target[["catalog_year", "credential_id"]].drop_duplicates().shape[0]
    )
    if credential_years != 14:
        fail(f"Rebuilt audit master should contain 14 target credential-years; found {credential_years}")

    return {
        "rebuilt_rows": len(rebuilt),
        "target_executable_rows": len(target),
        "target_credential_years": credential_years,
        "non_target_rows_preserved": non_target_preserved,
    }


def atomic_write_csv(df: pd.DataFrame, destination: Path) -> None:
    temp = destination.with_suffix(destination.suffix + ".tmp")
    df.to_csv(temp, index=False)
    temp.replace(destination)


def restore_file(backup: Path | None, destination: Path) -> None:
    if backup and backup.exists():
        shutil.copy2(backup, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-overlay-rebuild",
        action="store_true",
        help="Use the existing approved overlay instead of rerunning the v9 builder.",
    )
    args = parser.parse_args()

    root = Path(".").resolve()
    scripts_dir = root / "scripts"
    overlay_builder = scripts_dir / "build_missing_health_credentials_overlay_v9.py"
    audit_builder = scripts_dir / "build_audit_requirements_multiyear.py"

    source_master_path = (
        root / "data/processed/catalogs/requirements_master_multicatalog.csv"
    )
    audit_master_path = (
        root / "data/processed/catalogs/requirements_master_multiyear.csv"
    )
    overlay_dir = (
        root / "data/processed/catalogs/missing_health_credentials_overlay"
    )
    overlay_path = overlay_dir / "missing_health_requirements_overlay.csv"
    validation_path = overlay_dir / "overlay_validation.csv"
    duplicates_path = overlay_dir / "duplicate_requirement_ids.csv"

    if not args.skip_overlay_rebuild:
        if not overlay_builder.exists():
            fail(f"Overlay builder not found: {overlay_builder}")
        run_checked(
            [sys.executable, str(overlay_builder)],
            root,
            "approved v9 overlay rebuild",
        )

    overlay = read_csv(overlay_path)
    validation = read_csv(validation_path)
    duplicates = read_csv(duplicates_path)
    validate_overlay(overlay, validation, duplicates)

    source_before = read_csv(source_master_path)
    audit_before = read_csv(audit_master_path) if audit_master_path.exists() else None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "data/processed/catalogs/backups" / f"health_overlay_merge_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    source_backup = backup_dir / source_master_path.name
    shutil.copy2(source_master_path, source_backup)

    audit_backup = None
    if audit_master_path.exists():
        audit_backup = backup_dir / audit_master_path.name
        shutil.copy2(audit_master_path, audit_backup)

    report_path = backup_dir / "merge_validation_report.json"

    try:
        aligned_overlay = align_overlay_to_master(overlay, source_before)

        source_without_targets = source_before.loc[
            ~source_before["credential_id"].isin(TARGET_CREDENTIAL_IDS)
        ].copy()
        merged = pd.concat(
            [source_without_targets, aligned_overlay],
            ignore_index=True,
            sort=False,
        )

        source_metrics = validate_merged_source(
            source_before,
            merged,
            aligned_overlay,
        )

        atomic_write_csv(merged, source_master_path)

        # Read back from disk before rebuilding to catch CSV serialization issues.
        source_readback = read_csv(source_master_path)
        validate_merged_source(source_before, source_readback, aligned_overlay)

        if not audit_builder.exists():
            fail(f"Audit requirements builder not found: {audit_builder}")

        run_checked(
            [sys.executable, str(audit_builder)],
            root,
            "multiyear executable-requirements rebuild",
        )

        audit_after = read_csv(audit_master_path)
        audit_metrics = validate_rebuilt_audit(audit_after, audit_before)

        report = {
            "status": "PASS",
            "timestamp": timestamp,
            "source_master": str(source_master_path),
            "audit_master": str(audit_master_path),
            "backup_directory": str(backup_dir),
            "source_validation": source_metrics,
            "audit_validation": audit_metrics,
            "approved_target_credential_years": 14,
            "approved_overlay_rows": 200,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("\n" + "=" * 118)
        print("PRODUCTION MERGE AND REGRESSION TESTS: PASS")
        print("=" * 118)
        print(f"Source rows before:                 {source_metrics['before_rows']:,}")
        print(f"Existing target rows replaced:      {source_metrics['removed_existing_target_rows']:,}")
        print(f"Approved overlay rows merged:       {source_metrics['overlay_rows_added']:,}")
        print(f"Source rows after:                  {source_metrics['after_rows']:,}")
        print(f"Executable rows after rebuild:      {audit_metrics['rebuilt_rows']:,}")
        print(f"Target executable rows:             {audit_metrics['target_executable_rows']:,}")
        print(f"Target credential-years:            {audit_metrics['target_credential_years']}")
        print(f"Non-target source rows unchanged:   YES")
        print(
            "Non-target executable rows unchanged: "
            + (
                "YES"
                if audit_metrics["non_target_rows_preserved"] is True
                else "NOT TESTED (no prior executable master)"
            )
        )
        print(f"Backup directory:                   {backup_dir}")
        print(f"Validation report:                  {report_path}")
        return 0

    except Exception as exc:
        print("\nMERGE OR TEST FAILURE — ROLLING BACK PRODUCTION FILES", file=sys.stderr)
        restore_file(source_backup, source_master_path)

        if audit_backup is not None:
            restore_file(audit_backup, audit_master_path)
        elif audit_master_path.exists():
            audit_master_path.unlink()

        failure_report = {
            "status": "ROLLED_BACK",
            "timestamp": timestamp,
            "error": str(exc),
            "source_master_restored": str(source_master_path),
            "audit_master_restored": str(audit_master_path),
            "backup_directory": str(backup_dir),
        }
        report_path.write_text(
            json.dumps(failure_report, indent=2),
            encoding="utf-8",
        )
        print(f"Rollback complete. Details: {report_path}", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
