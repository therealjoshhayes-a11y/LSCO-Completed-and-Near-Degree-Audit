#!/usr/bin/env python
"""
Final read-only QA for the completed LSCO full actual audit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(".").resolve()
CHUNK_DIR = ROOT / "data/processed/full_actual_audit/chunks"
DETAIL_COMBINED = ROOT / "data/processed/full_actual_audit/full_actual_audit_results.csv"
SUMMARY_COMBINED = ROOT / "data/processed/full_actual_audit/full_actual_credential_summary.csv"
RUN_LOG = ROOT / "data/processed/full_actual_audit/full_actual_audit_run_log.csv"

TOTAL_STUDENTS = 12_850
TOTAL_CHUNKS = 514
STUDENTS_PER_CHUNK = 25
SOURCE_REQUIREMENTS = 4_849
CREDENTIAL_YEARS = 381

EXPECTED_DETAIL_ROWS_PER_CHUNK = STUDENTS_PER_CHUNK * SOURCE_REQUIREMENTS
EXPECTED_SUMMARY_ROWS_PER_CHUNK = STUDENTS_PER_CHUNK * CREDENTIAL_YEARS
EXPECTED_DETAIL_ROWS = TOTAL_STUDENTS * SOURCE_REQUIREMENTS
EXPECTED_SUMMARY_ROWS = TOTAL_STUDENTS * CREDENTIAL_YEARS

HEALTH_IDS = {
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

DETAIL_RE = re.compile(r"chunk_(\d{5})_audit_results\.csv$")
SUMMARY_RE = re.compile(r"chunk_(\d{5})_credential_summary\.csv$")


def file_map(regex: re.Pattern[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for path in CHUNK_DIR.glob("chunk_*.csv"):
        match = regex.match(path.name)
        if match:
            result[int(match.group(1))] = path
    return result


def count_data_rows(path: Path, block_size: int = 16 * 1024 * 1024) -> int:
    newlines = 0
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            newlines += block.count(b"\n")
            last_byte = block[-1:]
    physical_lines = newlines + (1 if last_byte and last_byte != b"\n" else 0)
    return max(physical_lines - 1, 0)


def main() -> int:
    problems: list[str] = []

    for path in (CHUNK_DIR, DETAIL_COMBINED, SUMMARY_COMBINED, RUN_LOG):
        if not path.exists():
            problems.append(f"Missing required output: {path}")

    if problems:
        for problem in problems:
            print(f"- {problem}")
        return 2

    details = file_map(DETAIL_RE)
    summaries = file_map(SUMMARY_RE)
    expected_chunks = set(range(1, TOTAL_CHUNKS + 1))

    if set(details) != expected_chunks:
        problems.append("Detail chunk set is not exactly 1-514")
    if set(summaries) != expected_chunks:
        problems.append("Summary chunk set is not exactly 1-514")

    latest_chunk_mtime = 0.0
    detail_rows_from_chunks = 0
    summary_rows_from_chunks = 0
    all_students: set[str] = set()
    status_counts: dict[str, int] = {}

    for chunk in sorted(set(details) & set(summaries)):
        detail_path = details[chunk]
        summary_path = summaries[chunk]

        latest_chunk_mtime = max(
            latest_chunk_mtime,
            detail_path.stat().st_mtime,
            summary_path.stat().st_mtime,
        )

        detail_rows = count_data_rows(detail_path)
        summary_rows = count_data_rows(summary_path)
        detail_rows_from_chunks += detail_rows
        summary_rows_from_chunks += summary_rows

        if detail_rows != EXPECTED_DETAIL_ROWS_PER_CHUNK:
            problems.append(
                f"Chunk {chunk:05d} detail rows {detail_rows:,}; "
                f"expected {EXPECTED_DETAIL_ROWS_PER_CHUNK:,}"
            )
        if summary_rows != EXPECTED_SUMMARY_ROWS_PER_CHUNK:
            problems.append(
                f"Chunk {chunk:05d} summary rows {summary_rows:,}; "
                f"expected {EXPECTED_SUMMARY_ROWS_PER_CHUNK:,}"
            )

        try:
            summary = pd.read_csv(summary_path, dtype=str, keep_default_na=False)
        except Exception as exc:
            problems.append(f"Chunk {chunk:05d} summary unreadable: {exc}")
            continue

        required = {"student_id", "catalog_year", "credential_id", "audit_status"}
        missing = required - set(summary.columns)
        if missing:
            problems.append(
                f"Chunk {chunk:05d} summary missing columns: {sorted(missing)}"
            )
            continue

        for column in required:
            if summary[column].eq("").any():
                problems.append(f"Chunk {chunk:05d} summary has blank {column}")

        duplicate_keys = summary.duplicated(
            subset=["student_id", "catalog_year", "credential_id"]
        ).sum()
        if duplicate_keys:
            problems.append(
                f"Chunk {chunk:05d} summary has {int(duplicate_keys)} duplicate keys"
            )

        students = set(summary["student_id"]) - {""}
        if len(students) != STUDENTS_PER_CHUNK:
            problems.append(
                f"Chunk {chunk:05d} summary has {len(students)} students; expected 25"
            )
        all_students.update(students)

        for status, count in summary["audit_status"].value_counts().items():
            status_counts[status] = status_counts.get(status, 0) + int(count)

    if detail_rows_from_chunks != EXPECTED_DETAIL_ROWS:
        problems.append(
            f"Detail chunk total {detail_rows_from_chunks:,}; "
            f"expected {EXPECTED_DETAIL_ROWS:,}"
        )
    if summary_rows_from_chunks != EXPECTED_SUMMARY_ROWS:
        problems.append(
            f"Summary chunk total {summary_rows_from_chunks:,}; "
            f"expected {EXPECTED_SUMMARY_ROWS:,}"
        )
    if len(all_students) != TOTAL_STUDENTS:
        problems.append(
            f"Unique students across chunk summaries {len(all_students):,}; "
            f"expected {TOTAL_STUDENTS:,}"
        )

    if DETAIL_COMBINED.stat().st_mtime < latest_chunk_mtime:
        problems.append("Combined detail file predates latest chunk")
    if SUMMARY_COMBINED.stat().st_mtime < latest_chunk_mtime:
        problems.append("Combined summary file predates latest chunk")

    print("Counting combined detail rows; this may take several minutes...")
    combined_detail_rows = count_data_rows(DETAIL_COMBINED)
    if combined_detail_rows != EXPECTED_DETAIL_ROWS:
        problems.append(
            f"Combined detail rows {combined_detail_rows:,}; "
            f"expected {EXPECTED_DETAIL_ROWS:,}"
        )

    combined_summary_rows = 0
    combined_students: set[str] = set()
    combined_credential_years: set[tuple[str, str]] = set()
    health_rows = 0
    health_ids_seen: set[str] = set()

    for frame in pd.read_csv(
        SUMMARY_COMBINED,
        dtype=str,
        keep_default_na=False,
        chunksize=250_000,
    ):
        combined_summary_rows += len(frame)

        required = {"student_id", "catalog_year", "credential_id", "audit_status"}
        missing = required - set(frame.columns)
        if missing:
            problems.append(f"Combined summary missing columns: {sorted(missing)}")
            break

        combined_students.update(set(frame["student_id"]) - {""})
        combined_credential_years.update(
            zip(frame["catalog_year"], frame["credential_id"])
        )

        health = frame["credential_id"].isin(HEALTH_IDS)
        health_rows += int(health.sum())
        health_ids_seen.update(set(frame.loc[health, "credential_id"]))

    if combined_summary_rows != EXPECTED_SUMMARY_ROWS:
        problems.append(
            f"Combined summary rows {combined_summary_rows:,}; "
            f"expected {EXPECTED_SUMMARY_ROWS:,}"
        )
    if len(combined_students) != TOTAL_STUDENTS:
        problems.append(
            f"Combined summary students {len(combined_students):,}; "
            f"expected {TOTAL_STUDENTS:,}"
        )
    if len(combined_credential_years) != CREDENTIAL_YEARS:
        problems.append(
            f"Combined credential-years {len(combined_credential_years):,}; "
            f"expected {CREDENTIAL_YEARS:,}"
        )

    expected_health_rows = TOTAL_STUDENTS * len(HEALTH_IDS)
    if health_rows != expected_health_rows:
        problems.append(
            f"Combined health rows {health_rows:,}; expected {expected_health_rows:,}"
        )
    if health_ids_seen != HEALTH_IDS:
        problems.append("Recovered health credential coverage mismatch")

    print("\n" + "=" * 108)
    print("FINAL FULL-AUDIT QA")
    print("=" * 108)
    print(f"Detail chunk files:                 {len(details):,}")
    print(f"Summary chunk files:                {len(summaries):,}")
    print(f"Detail rows from chunks:            {detail_rows_from_chunks:,}")
    print(f"Combined detail rows:               {combined_detail_rows:,}")
    print(f"Summary rows from chunks:           {summary_rows_from_chunks:,}")
    print(f"Combined summary rows:              {combined_summary_rows:,}")
    print(f"Unique students:                    {len(combined_students):,}")
    print(f"Credential-years:                   {len(combined_credential_years):,}")
    print(f"Recovered health rows:              {health_rows:,}")
    print(f"Recovered health credential-years:  {len(health_ids_seen):,}")

    print("\nAudit status counts:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status or '<blank>':30s} {count:,}")

    if problems:
        print("\nQA RESULT: REVIEW REQUIRED")
        for problem in problems[:100]:
            print(f"- {problem}")
        if len(problems) > 100:
            print(f"- ... plus {len(problems)-100} additional findings")
        return 2

    print("\nQA RESULT: PASS")
    print("The chunks, combined files, student universe, credential-year universe,")
    print("and recovered health-program coverage reconcile exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
