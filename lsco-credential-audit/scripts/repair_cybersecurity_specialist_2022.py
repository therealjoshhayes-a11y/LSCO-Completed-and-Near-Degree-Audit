from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd


TARGET_CATALOG = "2022-2023"
TARGET_CREDENTIAL = "CYBERSECURITY_SPECIALIST_2022"
MISSING_COURSE = "ITNW 1313"
MISSING_HOURS = "3"
TARGET_REQUIREMENT_ID = "CYBERSECURITY_SPECIALIST_2022_R5"

MASTER_PATHS = [
    Path("data/processed/catalogs/requirements_master_multiyear.csv"),
]

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def backup(path: Path) -> Path:
    destination = path.with_suffix(
        path.suffix + f".before_cybersecurity_2022_repair_{STAMP}.bak"
    )
    shutil.copy2(path, destination)
    return destination


def credential_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        frame["catalog_year"].astype(str).eq(TARGET_CATALOG)
        & frame["credential_id"].astype(str).eq(TARGET_CREDENTIAL)
    ].copy()


def executable_total(frame: pd.DataFrame) -> float:
    rows = credential_rows(frame)

    one_per_requirement = rows.drop_duplicates(
        subset=["requirement_id"],
        keep="first",
    )

    return float(
        pd.to_numeric(
            one_per_requirement["credit_hours"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )


def requirement_count(frame: pd.DataFrame) -> int:
    return int(
        credential_rows(frame)["requirement_id"].nunique()
    )


def find_template(rows: pd.DataFrame) -> pd.Series:
    semester_col = next(
        (
            column
            for column in ("semester_label", "semester_name")
            if column in rows.columns
        ),
        None,
    )

    candidates = rows.copy()

    if semester_col is not None:
        first_semester = candidates[
            candidates[semester_col]
            .astype(str)
            .str.upper()
            .str.contains("FIRST", regex=False)
        ]
        if not first_semester.empty:
            candidates = first_semester

    exact = candidates[
        candidates["rule_type"]
        .astype(str)
        .str.upper()
        .eq("EXACT")
    ]

    if not exact.empty:
        candidates = exact

    course = candidates[
        candidates["option_type"]
        .astype(str)
        .str.upper()
        .eq("COURSE")
    ]

    if not course.empty:
        candidates = course

    if candidates.empty:
        raise RuntimeError(
            "Could not locate a template requirement row."
        )

    return candidates.iloc[0].copy()


def build_new_row(
    frame: pd.DataFrame,
    template: pd.Series,
) -> pd.Series:
    row = template.copy()

    replacements = {
        "catalog_year": TARGET_CATALOG,
        "credential_id": TARGET_CREDENTIAL,
        "credential_title": "Cybersecurity Specialist",
        "requirement_id": TARGET_REQUIREMENT_ID,
        "requirement_name": MISSING_COURSE,
        "requirement_text": MISSING_COURSE,
        "display_text": MISSING_COURSE,
        "raw_text": MISSING_COURSE,
        "course_code": MISSING_COURSE,
        "rule_type": "EXACT",
        "min_required": "1",
        "minimum_required": "1",
        "required_count": "1",
        "credit_hours": MISSING_HOURS,
        "option_type": "COURSE",
        "option_value": MISSING_COURSE,
        "option_group": "1",
        "option_index": "1",
        "source_note": (
            "AUTHORIZED_PARSING_REPAIR: restored ITNW 1313 "
            "Computer Virtualization to Cybersecurity Specialist "
            "2022-2023 First Semester."
        ),
        "repair_note": (
            "AUTHORIZED_PARSING_REPAIR: source validation confirms "
            "5 first-semester requirements and 30 program SCH."
        ),
    }

    for column, value in replacements.items():
        if column in row.index:
            row[column] = value

    for semester_column in (
        "semester_label",
        "semester_name",
        "term_label",
    ):
        if semester_column in row.index:
            row[semester_column] = "First Semester"

    return row


def patch_master(path: Path) -> dict[str, object]:
    frame = pd.read_csv(
        path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "rule_type",
        "credit_hours",
        "option_type",
        "option_value",
    }

    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(
            f"{path} is missing columns: "
            + ", ".join(sorted(missing))
        )

    rows = credential_rows(frame)

    if rows.empty:
        raise RuntimeError(
            f"{TARGET_CATALOG} / {TARGET_CREDENTIAL} "
            f"not found in {path}."
        )

    existing_course = rows[
        rows["option_value"].map(normalize).eq(MISSING_COURSE)
    ]

    existing_requirement_id = rows[
        rows["requirement_id"]
        .astype(str)
        .eq(TARGET_REQUIREMENT_ID)
    ]

    before_total = executable_total(frame)
    before_count = requirement_count(frame)

    if not existing_course.empty:
        if before_total != 30 or before_count != 10:
            raise RuntimeError(
                f"{path}: {MISSING_COURSE} already exists, "
                f"but total/count are {before_total:g}/{before_count}."
            )

        return {
            "path": str(path),
            "action": "ALREADY_REPAIRED",
            "before_total": before_total,
            "after_total": before_total,
            "before_count": before_count,
            "after_count": before_count,
            "backup": "",
        }

    if not existing_requirement_id.empty:
        raise RuntimeError(
            f"{path}: requirement ID {TARGET_REQUIREMENT_ID} "
            "already exists for another row."
        )

    if before_total != 27 or before_count != 9:
        raise RuntimeError(
            f"{path}: expected pre-repair total/count 27/9; "
            f"found {before_total:g}/{before_count}."
        )

    template = find_template(rows)
    new_row = build_new_row(frame, template)

    path_backup = backup(path)

    frame = pd.concat(
        [
            frame,
            pd.DataFrame(
                [new_row],
                columns=frame.columns,
            ),
        ],
        ignore_index=True,
    )

    after_total = executable_total(frame)
    after_count = requirement_count(frame)

    if after_total != 30 or after_count != 10:
        raise RuntimeError(
            f"{path}: repair validation failed. "
            f"Expected 30 SCH / 10 requirements; "
            f"found {after_total:g} / {after_count}."
        )

    course_matches = credential_rows(frame)[
        credential_rows(frame)["option_value"]
        .map(normalize)
        .eq(MISSING_COURSE)
    ]

    if len(course_matches) != 1:
        raise RuntimeError(
            f"{path}: expected exactly one {MISSING_COURSE} row "
            f"after repair; found {len(course_matches)}."
        )

    frame = frame.sort_values(
        [
            "catalog_year",
            "credential_id",
            "requirement_id",
            "option_value",
        ],
        kind="mergesort",
    )

    frame.to_csv(path, index=False)

    return {
        "path": str(path),
        "action": "ADDED_ITNW_1313",
        "before_total": before_total,
        "after_total": after_total,
        "before_count": before_count,
        "after_count": after_count,
        "backup": str(path_backup),
    }


def main() -> None:
    existing_paths = [
        path
        for path in MASTER_PATHS
        if path.exists()
    ]

    if not existing_paths:
        raise FileNotFoundError(
            "Neither requirements master file was found."
        )

    print("=" * 100)
    print("CYBERSECURITY SPECIALIST 2022 PARSING REPAIR")
    print("=" * 100)

    results = []

    for path in existing_paths:
        result = patch_master(path)
        results.append(result)

        print(
            f"{path}: {result['action']} | "
            f"{result['before_total']:g} SCH / "
            f"{result['before_count']} requirements -> "
            f"{result['after_total']:g} SCH / "
            f"{result['after_count']} requirements"
        )

    log_path = (
        Path("data/processed/catalogs")
        / f"cybersecurity_specialist_2022_repair_{STAMP}.csv"
    )

    pd.DataFrame(results).to_csv(
        log_path,
        index=False,
    )

    print()
    for result in results:
        if result["backup"]:
            print(
                f"Backup: {result['backup']}"
            )

    print(f"Repair log: {log_path}")
    print()
    print(
        "Controlled repair: added ITNW 1313 "
        "Computer Virtualization, 3 SCH, First Semester."
    )
    print("CYBERSECURITY REPAIR GATE: PASSED")
    print()
    print("Next command:")
    print(
        "python -u .\\scripts\\"
        "check_validated_credential_attainable_hours.py"
    )


if __name__ == "__main__":
    main()
