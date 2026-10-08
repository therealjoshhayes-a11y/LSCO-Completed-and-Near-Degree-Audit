from pathlib import Path
import re
import pandas as pd

CASES = [
    {
        "student_id": "R80016075",
        "catalog_year": "2021-2022",
        "search_terms": ["PROCESS", "TECHNOLOGY"],
        "label": "Process Technology 2021-2022",
    },
    {
        "student_id": "R80078992",
        "catalog_year": "2022-2023",
        "search_terms": ["LIBERAL", "ARTS"],
        "label": "Liberal Arts 2022-2023",
    },
]

ROOT = Path(".")
CHUNK_DIR = ROOT / "data/processed/full_actual_audit/chunks"

COURSE_PATH = (
    ROOT
    / "data/processed/"
      "normalized_actual_student_course_history.csv"
)

OUT_DIR = (
    ROOT
    / "data/processed/reporting/"
      "degreeworks_discrepancy_qa_20260803"
)

OUT_DIR.mkdir(parents=True, exist_ok=True)


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize(value):
    value = clean(value).upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def matches_terms(value, terms):
    text = normalize(value)
    return all(term.upper() in text for term in terms)


# =============================================================================
# FIND THE EXACT SUMMARY CHUNK AND CREDENTIAL
# =============================================================================

resolved = []

summary_files = sorted(
    CHUNK_DIR.glob("chunk_*_credential_summary.csv")
)

print("=" * 100)
print("LOCATING TARGET STUDENTS")
print("=" * 100)
print(f"Summary chunks available: {len(summary_files):,}")

for case in CASES:
    found_rows = []

    for summary_path in summary_files:
        summary = pd.read_csv(
            summary_path,
            dtype="string",
            low_memory=False,
        ).fillna("")

        if "student_id" not in summary.columns:
            raise KeyError(
                f"{summary_path.name} lacks student_id"
            )

        student_rows = summary.loc[
            summary["student_id"]
            .astype(str)
            .str.strip()
            .eq(case["student_id"])
        ].copy()

        if student_rows.empty:
            continue

        student_rows["_summary_file"] = str(summary_path)
        found_rows.append(student_rows)

    if not found_rows:
        raise RuntimeError(
            f"{case['student_id']} was not found in any "
            "credential-summary chunk."
        )

    all_student_summary = pd.concat(
        found_rows,
        ignore_index=True,
    )

    catalog_rows = all_student_summary.loc[
        all_student_summary["catalog_year"]
        .astype(str)
        .str.strip()
        .eq(case["catalog_year"])
    ].copy()

    if catalog_rows.empty:
        raise RuntimeError(
            f"{case['student_id']} has no summary rows for "
            f"catalog {case['catalog_year']}."
        )

    text_columns = [
        column
        for column in [
            "credential_id",
            "credential_title",
            "credential_name",
            "canonical_lineage",
            "detected_lineage",
        ]
        if column in catalog_rows.columns
    ]

    if not text_columns:
        raise RuntimeError(
            "No credential-identification columns found in "
            "the summary files."
        )

    catalog_rows["_credential_search"] = (
        catalog_rows[text_columns]
        .astype(str)
        .agg(" | ".join, axis=1)
    )

    target_rows = catalog_rows.loc[
        catalog_rows["_credential_search"].map(
            lambda value: matches_terms(
                value,
                case["search_terms"],
            )
        )
    ].copy()

    if target_rows.empty:
        print()
        print(
            f"No automatic credential match for "
            f"{case['student_id']}."
        )
        print("Available catalog credentials:")
        print(
            catalog_rows[
                [
                    column
                    for column in [
                        "credential_id",
                        "credential_title",
                        "audit_status",
                    ]
                    if column in catalog_rows.columns
                ]
            ].to_string(index=False)
        )
        raise RuntimeError(
            f"Credential could not be resolved for "
            f"{case['label']}."
        )

    # Prefer the COMPLETE row.
    if "audit_status" in target_rows.columns:
        complete = target_rows.loc[
            target_rows["audit_status"]
            .astype(str)
            .str.upper()
            .eq("COMPLETE")
        ]

        if not complete.empty:
            target_rows = complete

    target = target_rows.iloc[0]

    summary_path = Path(target["_summary_file"])

    match = re.search(
        r"chunk_(\d{5})_credential_summary\.csv$",
        summary_path.name,
    )

    if not match:
        raise RuntimeError(
            f"Could not parse chunk from {summary_path.name}"
        )

    chunk_number = match.group(1)

    detail_path = (
        CHUNK_DIR
        / f"chunk_{chunk_number}_audit_results.csv"
    )

    if not detail_path.exists():
        raise FileNotFoundError(
            f"Expected detail chunk not found:\n{detail_path}"
        )

    credential_id = clean(target["credential_id"])

    print()
    print(
        f"{case['student_id']} | "
        f"chunk {chunk_number} | "
        f"{credential_id} | "
        f"{clean(target.get('audit_status', ''))}"
    )

    resolved.append(
        {
            **case,
            "chunk_number": chunk_number,
            "summary_path": summary_path,
            "detail_path": detail_path,
            "credential_id": credential_id,
            "summary_row": target.to_dict(),
        }
    )


# =============================================================================
# EXTRACT EXACT REQUIREMENT-LEVEL DETAIL
# =============================================================================

print()
print("=" * 100)
print("EXTRACTING REQUIREMENT DETAIL")
print("=" * 100)

for case in resolved:
    detail = pd.read_csv(
        case["detail_path"],
        dtype="string",
        low_memory=False,
    ).fillna("")

    required_columns = {
        "student_id",
        "catalog_year",
        "credential_id",
    }

    missing = required_columns - set(detail.columns)

    if missing:
        raise KeyError(
            f"{case['detail_path'].name} missing columns: "
            f"{sorted(missing)}"
        )

    target_detail = detail.loc[
        detail["student_id"]
        .astype(str)
        .str.strip()
        .eq(case["student_id"])
        & detail["catalog_year"]
        .astype(str)
        .str.strip()
        .eq(case["catalog_year"])
        & detail["credential_id"]
        .astype(str)
        .str.strip()
        .eq(case["credential_id"])
    ].copy()

    if target_detail.empty:
        raise RuntimeError(
            f"No exact detail rows found for "
            f"{case['student_id']} / "
            f"{case['credential_id']} / "
            f"{case['catalog_year']}."
        )

    preferred_columns = [
        "student_id",
        "catalog_year",
        "credential_id",
        "requirement_id",
        "rule_type",
        "status",
        "requirement_met",
        "required_options",
        "option_types",
        "matched_options",
        "matched_terms",
        "matched_grades",
        "used_course_count",
        "required_hours",
        "matched_hours",
        "missing_hours",
    ]

    ordered_columns = [
        column
        for column in preferred_columns
        if column in target_detail.columns
    ]

    remaining_columns = [
        column
        for column in target_detail.columns
        if column not in ordered_columns
    ]

    target_detail = target_detail[
        ordered_columns + remaining_columns
    ]

    detail_out = (
        OUT_DIR
        / (
            f"{case['student_id']}_"
            f"{case['credential_id']}_"
            f"{case['catalog_year']}_audit_detail.csv"
        )
    )

    target_detail.to_csv(
        detail_out,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"{case['student_id']}: "
        f"{len(target_detail):,} requirement rows"
    )
    print(f"  {detail_out}")


# =============================================================================
# EXTRACT FULL COURSE HISTORIES
# =============================================================================

print()
print("=" * 100)
print("EXTRACTING COURSE HISTORIES")
print("=" * 100)

target_ids = {
    case["student_id"]
    for case in resolved
}

course_parts = []

for chunk in pd.read_csv(
    COURSE_PATH,
    dtype="string",
    low_memory=False,
    chunksize=50_000,
):
    if "student_id" not in chunk.columns:
        raise KeyError(
            "Course history lacks student_id"
        )

    ids = (
        chunk["student_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    selected = chunk.loc[
        ids.isin(target_ids)
    ].copy()

    if not selected.empty:
        selected["student_id"] = ids.loc[
            selected.index
        ]
        course_parts.append(selected)

if not course_parts:
    raise RuntimeError(
        "No course-history rows found."
    )

courses = pd.concat(
    course_parts,
    ignore_index=True,
).fillna("")

for case in resolved:
    student_courses = courses.loc[
        courses["student_id"].eq(
            case["student_id"]
        )
    ].copy()

    term_column = next(
        (
            column
            for column in [
                "term_code",
                "term",
                "course_term",
                "academic_term",
            ]
            if column in student_courses.columns
        ),
        None,
    )

    if term_column:
        student_courses["_sort_term"] = pd.to_numeric(
            student_courses[term_column],
            errors="coerce",
        )

        student_courses = student_courses.sort_values(
            "_sort_term",
            na_position="last",
        ).drop(
            columns="_sort_term"
        )

    course_out = (
        OUT_DIR
        / f"{case['student_id']}_course_history.csv"
    )

    student_courses.to_csv(
        course_out,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"{case['student_id']}: "
        f"{len(student_courses):,} course rows"
    )
    print(f"  {course_out}")


# =============================================================================
# SAVE RESOLUTION CONTROL FILE
# =============================================================================

control_rows = []

for case in resolved:
    control_rows.append(
        {
            "student_id": case["student_id"],
            "requested_program": case["label"],
            "catalog_year": case["catalog_year"],
            "chunk_number": case["chunk_number"],
            "credential_id": case["credential_id"],
            "summary_file": str(case["summary_path"]),
            "detail_file": str(case["detail_path"]),
            "audit_status": clean(
                case["summary_row"].get(
                    "audit_status",
                    "",
                )
            ),
        }
    )

control = pd.DataFrame(control_rows)

control_out = OUT_DIR / "two_student_audit_resolution.csv"

control.to_csv(
    control_out,
    index=False,
    encoding="utf-8-sig",
)

print()
print("=" * 100)
print("SURGICAL EXTRACTION COMPLETE")
print("=" * 100)
print(f"Control file:\n{control_out}")
print(f"\nOutput directory:\n{OUT_DIR}")
