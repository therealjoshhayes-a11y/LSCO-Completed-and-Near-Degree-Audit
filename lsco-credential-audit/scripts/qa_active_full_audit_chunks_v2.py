#!/usr/bin/env python
"""
Read-only QA for the contiguous prefix completed by the CURRENT forced audit run.

Run identification:
- Uses chunk_00001_audit_results.csv as the current run anchor.
- Includes only contiguous chunk pairs whose detail and summary timestamps are
  at or after the chunk-1 anchor.
- Excludes files modified within the last five minutes.
- Stops at the first missing, old, or still-active chunk.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(".").resolve()
CHUNK_DIR = ROOT / "data/processed/full_actual_audit/chunks"
SETTLE_MINUTES = 5
DETAIL_SAMPLE_SIZE = 10
EXPECTED_STUDENTS_PER_FULL_CHUNK = 25
TOTAL_CHUNKS = 514

DETAIL_RE = re.compile(r"chunk_(\d{5})_audit_results\.csv$")
SUMMARY_RE = re.compile(r"chunk_(\d{5})_credential_summary\.csv$")


def files_by_chunk(regex: re.Pattern[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for path in CHUNK_DIR.glob("chunk_*.csv"):
        match = regex.match(path.name)
        if match:
            result[int(match.group(1))] = path
    return result


def evenly_spaced(values: list[int], count: int) -> list[int]:
    if len(values) <= count:
        return values
    positions = sorted({
        round(i * (len(values) - 1) / (count - 1))
        for i in range(count)
    })
    return [values[i] for i in positions]


def main() -> int:
    details = files_by_chunk(DETAIL_RE)
    summaries = files_by_chunk(SUMMARY_RE)

    if 1 not in details or 1 not in summaries:
        print("FAIL: Current-run anchor chunk 00001 is missing.")
        return 2

    anchor = min(details[1].stat().st_mtime, summaries[1].stat().st_mtime)
    settle_cutoff = (datetime.now() - timedelta(minutes=SETTLE_MINUTES)).timestamp()

    completed: list[int] = []
    for chunk in range(1, TOTAL_CHUNKS + 1):
        detail = details.get(chunk)
        summary = summaries.get(chunk)
        if not detail or not summary:
            break

        detail_mtime = detail.stat().st_mtime
        summary_mtime = summary.stat().st_mtime

        # Stop at the first old file from the previous run.
        if detail_mtime < anchor or summary_mtime < anchor:
            break

        # Stop at the currently active/unsettled chunk.
        if detail_mtime > settle_cutoff or summary_mtime > settle_cutoff:
            break

        completed.append(chunk)

    if not completed:
        print("FAIL: No settled current-run chunks found.")
        return 2

    problems: list[str] = []
    summary_rows = 0
    summary_students: set[str] = set()
    summary_student_counts: dict[int, int] = {}

    for chunk in completed:
        path = summaries[chunk]
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except Exception as exc:
            problems.append(f"Chunk {chunk:05d} summary unreadable: {exc}")
            continue

        if df.empty:
            problems.append(f"Chunk {chunk:05d} summary is empty")
            continue

        summary_rows += len(df)

        for required in ("student_id", "credential_id", "catalog_year"):
            if required not in df.columns:
                problems.append(f"Chunk {chunk:05d} summary missing {required}")
            elif df[required].eq("").any():
                problems.append(f"Chunk {chunk:05d} summary has blank {required}")

        if "student_id" in df.columns:
            students = set(df["student_id"]) - {""}
            summary_students.update(students)
            summary_student_counts[chunk] = len(students)
            if chunk < TOTAL_CHUNKS and len(students) != EXPECTED_STUDENTS_PER_FULL_CHUNK:
                problems.append(
                    f"Chunk {chunk:05d} summary has {len(students)} students; expected 25"
                )

    sampled = evenly_spaced(completed, DETAIL_SAMPLE_SIZE)
    sampled_detail_rows = 0

    for chunk in sampled:
        path = details[chunk]
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except Exception as exc:
            problems.append(f"Chunk {chunk:05d} detail unreadable: {exc}")
            continue

        if df.empty:
            problems.append(f"Chunk {chunk:05d} detail is empty")
            continue

        sampled_detail_rows += len(df)

        for required in (
            "student_id",
            "credential_id",
            "catalog_year",
            "requirement_id",
            "rule_type",
        ):
            if required not in df.columns:
                problems.append(f"Chunk {chunk:05d} detail missing {required}")
            elif df[required].eq("").any():
                problems.append(f"Chunk {chunk:05d} detail has blank {required}")

        if "student_id" in df.columns:
            students = set(df["student_id"]) - {""}
            expected = summary_student_counts.get(chunk)
            if expected is not None and len(students) != expected:
                problems.append(
                    f"Chunk {chunk:05d} detail/summary student mismatch: "
                    f"{len(students)} vs {expected}"
                )

        if df.duplicated().any():
            problems.append(
                f"Chunk {chunk:05d} detail contains "
                f"{int(df.duplicated().sum())} exact duplicate rows"
            )

    latest = completed[-1]
    latest_time = datetime.fromtimestamp(details[latest].stat().st_mtime)

    print("=" * 104)
    print("CURRENT FORCED-RUN CHUNK QA")
    print("=" * 104)
    print(f"Run anchor:                       {datetime.fromtimestamp(anchor)}")
    print(f"Settled current-run chunks:       {len(completed)}")
    print(f"Contiguous settled range:         00001-{latest:05d}")
    print(f"Latest settled timestamp:         {latest_time}")
    print(f"All current-run summary rows:     {summary_rows:,}")
    print(f"Unique current-run students:      {len(summary_students):,}")
    print(f"Detail sample:                    {', '.join(f'{c:05d}' for c in sampled)}")
    print(f"Sampled current detail rows:      {sampled_detail_rows:,}")

    if problems:
        print("\nQA RESULT: REVIEW REQUIRED")
        for problem in problems[:50]:
            print(f"- {problem}")
        if len(problems) > 50:
            print(f"- ... plus {len(problems) - 50} additional findings")
        return 2

    print("\nQA RESULT: PASS")
    print("Only the settled contiguous prefix from the current forced run was checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
