from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


ACTUAL_COURSES = Path("data/processed/normalized_actual_student_course_history.csv")
ENGINE_INPUT = Path("data/processed/student_course_history_normalized.csv")

ENGINE_DETAIL_OUTPUT = Path("data/processed/multiyear_sample_audit_results.csv")
ENGINE_SUMMARY_OUTPUT = Path("data/processed/multiyear_sample_credential_summary.csv")

FULL_OUTPUT_DIR = Path("data/processed/full_actual_audit")
CHUNK_DIR = FULL_OUTPUT_DIR / "chunks"

FULL_DETAIL_OUTPUT = FULL_OUTPUT_DIR / "full_actual_audit_results.csv"
FULL_SUMMARY_OUTPUT = FULL_OUTPUT_DIR / "full_actual_credential_summary.csv"
RUN_LOG_OUTPUT = FULL_OUTPUT_DIR / "full_actual_audit_run_log.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full actual student audit in resumable chunks."
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=25,
        help="Number of students per audit chunk.",
    )

    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Optional maximum number of chunks to run for smoke testing.",
    )

    parser.add_argument(
        "--start-chunk",
        type=int,
        default=1,
        help="1-based chunk number to start from.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run chunks even if chunk outputs already exist.",
    )

    parser.add_argument(
        "--combine-only",
        action="store_true",
        help="Do not run audits; only combine existing chunk outputs.",
    )

    return parser.parse_args()


def load_actual_courses() -> pd.DataFrame:
    if not ACTUAL_COURSES.exists():
        raise FileNotFoundError(ACTUAL_COURSES)

    courses = pd.read_csv(ACTUAL_COURSES, dtype=str, low_memory=False).fillna("")

    if "student_id" not in courses.columns:
        raise ValueError("Expected student_id column in actual normalized course file.")

    if "course_code" not in courses.columns:
        raise ValueError("Expected course_code column in actual normalized course file.")

    return courses


def make_student_chunks(students: list[str], chunk_size: int) -> list[list[str]]:
    return [
        students[i : i + chunk_size]
        for i in range(0, len(students), chunk_size)
    ]


def chunk_paths(chunk_number: int) -> tuple[Path, Path, Path]:
    padded = f"{chunk_number:05d}"
    chunk_input = CHUNK_DIR / f"chunk_{padded}_student_course_history.csv"
    chunk_detail = CHUNK_DIR / f"chunk_{padded}_audit_results.csv"
    chunk_summary = CHUNK_DIR / f"chunk_{padded}_credential_summary.csv"
    return chunk_input, chunk_detail, chunk_summary


def run_engine() -> None:
    subprocess.run(
        [sys.executable, "-m", "lsco_audit.audit_multiyear_sample"],
        check=True,
    )


def append_csv_files(chunk_files: list[Path], output_path: Path) -> None:
    if not chunk_files:
        raise ValueError(f"No chunk files to combine for {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    wrote_header = False
    with output_path.open("w", encoding="utf-8", newline="") as out:
        for file in chunk_files:
            with file.open("r", encoding="utf-8", newline="") as inp:
                header = inp.readline()

                if not wrote_header:
                    out.write(header)
                    wrote_header = True

                shutil.copyfileobj(inp, out)


def combine_chunks() -> None:
    detail_files = sorted(CHUNK_DIR.glob("chunk_*_audit_results.csv"))
    summary_files = sorted(CHUNK_DIR.glob("chunk_*_credential_summary.csv"))

    print()
    print("Combining chunk outputs...")
    print(f"Detail chunks:  {len(detail_files)}")
    print(f"Summary chunks: {len(summary_files)}")

    append_csv_files(detail_files, FULL_DETAIL_OUTPUT)
    append_csv_files(summary_files, FULL_SUMMARY_OUTPUT)

    print(f"Wrote {FULL_DETAIL_OUTPUT}")
    print(f"Wrote {FULL_SUMMARY_OUTPUT}")


def write_run_log(rows: list[dict]) -> None:
    if not rows:
        return

    RUN_LOG_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(RUN_LOG_OUTPUT, index=False)


def main() -> None:
    args = parse_args()

    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be greater than zero")

    FULL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    courses = load_actual_courses()
    students = sorted(courses["student_id"].dropna().astype(str).unique())
    chunks = make_student_chunks(students, args.chunk_size)

    total_chunks = len(chunks)

    print("FULL ACTUAL AUDIT CHUNK RUNNER")
    print(f"Actual course rows: {len(courses)}")
    print(f"Unique students:    {len(students)}")
    print(f"Chunk size:         {args.chunk_size}")
    print(f"Total chunks:       {total_chunks}")
    print(f"Start chunk:        {args.start_chunk}")
    print(f"Limit chunks:       {args.limit_chunks}")
    print(f"Force rerun:        {args.force}")
    print(f"Combine only:       {args.combine_only}")

    if args.combine_only:
        combine_chunks()
        return

    run_log_rows = []
    chunks_run = 0
    overall_start = time.time()

    for chunk_index, student_chunk in enumerate(chunks, start=1):
        if chunk_index < args.start_chunk:
            continue

        if args.limit_chunks is not None and chunks_run >= args.limit_chunks:
            break

        chunk_input, chunk_detail, chunk_summary = chunk_paths(chunk_index)

        if (
            not args.force
            and chunk_detail.exists()
            and chunk_summary.exists()
        ):
            print()
            print(f"[{chunk_index}/{total_chunks}] Skipping existing chunk outputs")
            chunks_run += 1
            continue

        chunk_start = time.time()

        chunk_courses = courses[courses["student_id"].isin(student_chunk)].copy()
        chunk_courses.to_csv(chunk_input, index=False)

        shutil.copyfile(chunk_input, ENGINE_INPUT)

        print()
        print("=" * 100)
        print(f"Running chunk {chunk_index}/{total_chunks}")
        print(f"Students: {len(student_chunk)}")
        print(f"Course rows: {len(chunk_courses)}")
        print(f"Input: {chunk_input}")
        print("=" * 100)

        run_engine()

        if not ENGINE_DETAIL_OUTPUT.exists():
            raise FileNotFoundError(ENGINE_DETAIL_OUTPUT)
        if not ENGINE_SUMMARY_OUTPUT.exists():
            raise FileNotFoundError(ENGINE_SUMMARY_OUTPUT)

        shutil.copyfile(ENGINE_DETAIL_OUTPUT, chunk_detail)
        shutil.copyfile(ENGINE_SUMMARY_OUTPUT, chunk_summary)

        elapsed = round(time.time() - chunk_start, 2)
        chunks_run += 1

        run_log_rows.append(
            {
                "chunk_number": chunk_index,
                "student_count": len(student_chunk),
                "course_row_count": len(chunk_courses),
                "chunk_input": str(chunk_input),
                "chunk_detail": str(chunk_detail),
                "chunk_summary": str(chunk_summary),
                "elapsed_seconds": elapsed,
            }
        )

        write_run_log(run_log_rows)

        avg_elapsed = (time.time() - overall_start) / chunks_run
        remaining_chunks = total_chunks - chunk_index
        eta_seconds = remaining_chunks * avg_elapsed

        print(f"Chunk elapsed seconds: {elapsed}")
        print(f"Average seconds/chunk: {round(avg_elapsed, 2)}")
        print(f"Estimated remaining minutes: {round(eta_seconds / 60, 2)}")

    combine_chunks()
    write_run_log(run_log_rows)

    print()
    print("DONE")
    print(f"Full detail:  {FULL_DETAIL_OUTPUT}")
    print(f"Full summary: {FULL_SUMMARY_OUTPUT}")
    print(f"Run log:      {RUN_LOG_OUTPUT}")


if __name__ == "__main__":
    main()