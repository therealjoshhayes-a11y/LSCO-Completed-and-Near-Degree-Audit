from pathlib import Path
from datetime import datetime
import pandas as pd

# -------------------------------------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------------------------------------

SEARCH_ROOTS = [
    Path(r"data\processed\full_actual_audit"),
    Path(r"data\processed\reporting"),
]

OUTPUT_PATH = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\current_maximum_award_output_inventory.csv"
)

NAME_TERMS = (
    "award",
    "maximum",
    "max_award",
    "modeled",
    "countable",
    "selected",
    "completion",
)

SELECTED_FLAG_CANDIDATES = (
    "countable_award",
    "is_countable_award",
    "selected_award",
    "is_selected_award",
    "award_selected",
    "selected",
    "include_in_award_count",
    "is_maximum_award",
)

STUDENT_CANDIDATES = (
    "student_id",
    "banner_id",
    "pidm",
)

LINEAGE_CANDIDATES = (
    "credential_family",
    "credential_lineage",
    "lineage_id",
    "credential_family_id",
    "family_id",
)

CREDENTIAL_CANDIDATES = (
    "credential_id",
    "selected_credential_id",
    "best_credential_id",
)

CATALOG_CANDIDATES = (
    "catalog_year",
    "selected_catalog_year",
    "best_catalog_year",
)

STATUS_CANDIDATES = (
    "audit_status",
    "status",
    "selected_status",
)

TRUTHY = {
    "1",
    "TRUE",
    "T",
    "YES",
    "Y",
    "SELECTED",
    "COUNTABLE",
    "INCLUDE",
    "INCLUDED",
}


# -------------------------------------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------------------------------------

def find_column(columns, candidates):
    normalized = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]

    return None


def catalog_sort(value):
    text = str(value).strip()

    try:
        return int(text.split("-")[0])
    except (ValueError, IndexError):
        return -1


def looks_like_award_file(path):
    name = path.name.lower()
    return any(term in name for term in NAME_TERMS)


def display_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# -------------------------------------------------------------------------------------------------
# LOCATE CANDIDATE OUTPUTS
# -------------------------------------------------------------------------------------------------

print("=" * 110)
print("CURRENT MAXIMUM-AWARD OUTPUT INVENTORY")
print("=" * 110)

candidate_paths = []

for root in SEARCH_ROOTS:
    if not root.exists():
        continue

    for path in root.rglob("*.csv"):
        if looks_like_award_file(path):
            candidate_paths.append(path)

candidate_paths = sorted(
    set(candidate_paths),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)

print("Candidate files found:", f"{len(candidate_paths):,}")

inventory_rows = []
usable_results = []

for path in candidate_paths:
    try:
        header = pd.read_csv(
            path,
            nrows=0,
        )
    except Exception as exc:
        inventory_rows.append(
            {
                "path": str(path),
                "modified": display_time(path.stat().st_mtime),
                "usable": False,
                "reason": f"HEADER_READ_ERROR: {exc}",
            }
        )
        continue

    columns = list(header.columns)

    student_col = find_column(
        columns,
        STUDENT_CANDIDATES,
    )

    lineage_col = find_column(
        columns,
        LINEAGE_CANDIDATES,
    )

    credential_col = find_column(
        columns,
        CREDENTIAL_CANDIDATES,
    )

    catalog_col = find_column(
        columns,
        CATALOG_CANDIDATES,
    )

    status_col = find_column(
        columns,
        STATUS_CANDIDATES,
    )

    selected_flag_col = find_column(
        columns,
        SELECTED_FLAG_CANDIDATES,
    )

    # A useful award output must identify students and either a
    # credential or credential lineage.
    usable = (
        student_col is not None
        and (
            lineage_col is not None
            or credential_col is not None
        )
    )

    inventory_rows.append(
        {
            "path": str(path),
            "modified": display_time(path.stat().st_mtime),
            "usable": usable,
            "student_col": student_col or "",
            "lineage_col": lineage_col or "",
            "credential_col": credential_col or "",
            "catalog_col": catalog_col or "",
            "status_col": status_col or "",
            "selected_flag_col": selected_flag_col or "",
            "reason": "" if usable else "MISSING AWARD KEY COLUMNS",
        }
    )

    if not usable:
        continue

    try:
        df = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
        )
    except Exception as exc:
        inventory_rows[-1]["usable"] = False
        inventory_rows[-1]["reason"] = (
            f"FULL_READ_ERROR: {exc}"
        )
        continue

    original_rows = len(df)

    for column in [
        student_col,
        lineage_col,
        credential_col,
        catalog_col,
        status_col,
        selected_flag_col,
    ]:
        if column is not None:
            df[column] = df[column].astype(str).str.strip()

    selection_method = "ALL_ROWS_IN_OUTPUT"

    # Use an explicit selected/countable flag when present.
    if selected_flag_col is not None:
        selected_values = (
            df[selected_flag_col]
            .str.upper()
        )

        df = df[
            selected_values.isin(TRUTHY)
        ].copy()

        selection_method = (
            f"FLAG:{selected_flag_col}"
        )

    # Award counts should contain completed records only when a
    # status column exists.
    if status_col is not None:
        statuses = (
            df[status_col]
            .str.upper()
        )

        complete_mask = statuses.eq("COMPLETE")

        if complete_mask.any():
            df = df[complete_mask].copy()
            selection_method += "+STATUS_COMPLETE"

    df = df[
        df[student_col].ne("")
    ].copy()

    award_key_col = (
        lineage_col
        if lineage_col is not None
        else credential_col
    )

    selected_rows = len(df)
    distinct_students = df[student_col].nunique()
    distinct_award_keys = df[award_key_col].nunique()

    duplicate_student_award_rows = int(
        df.duplicated(
            subset=[
                student_col,
                award_key_col,
            ],
            keep=False,
        ).sum()
    )

    result = {
        "path": str(path),
        "modified": display_time(path.stat().st_mtime),
        "original_rows": original_rows,
        "selected_rows": selected_rows,
        "distinct_students": distinct_students,
        "distinct_award_keys": distinct_award_keys,
        "duplicate_student_award_rows": (
            duplicate_student_award_rows
        ),
        "selection_method": selection_method,
        "student_col": student_col,
        "award_key_col": award_key_col,
        "catalog_col": catalog_col or "",
        "status_col": status_col or "",
        "selected_flag_col": selected_flag_col or "",
        "data": df,
    }

    usable_results.append(result)


# -------------------------------------------------------------------------------------------------
# PRINT CURRENT COUNTS
# -------------------------------------------------------------------------------------------------

print()
print("=" * 110)
print("USABLE AWARD OUTPUTS — NEWEST FIRST")
print("=" * 110)

if not usable_results:
    print("No usable award-selection outputs were found.")
else:
    for number, result in enumerate(
        usable_results,
        start=1,
    ):
        print()
        print(f"[{number}] {result['path']}")
        print("    Modified:              ", result["modified"])
        print(
            "    Original rows:         ",
            f"{result['original_rows']:,}",
        )
        print(
            "    Selected/countable:    ",
            f"{result['selected_rows']:,}",
        )
        print(
            "    Distinct students:     ",
            f"{result['distinct_students']:,}",
        )
        print(
            "    Distinct award keys:   ",
            f"{result['distinct_award_keys']:,}",
        )
        print(
            "    Duplicate student/key: ",
            f"{result['duplicate_student_award_rows']:,}",
        )
        print(
            "    Selection method:      ",
            result["selection_method"],
        )

        catalog_col = result["catalog_col"]
        df = result["data"]

        if catalog_col and catalog_col in df.columns:
            by_catalog = (
                df.groupby(catalog_col)
                .agg(
                    maximum_awards=(
                        result["award_key_col"],
                        "size",
                    ),
                    distinct_students=(
                        result["student_col"],
                        "nunique",
                    ),
                )
                .reset_index()
            )

            by_catalog["_sort"] = (
                by_catalog[catalog_col]
                .map(catalog_sort)
            )

            by_catalog = (
                by_catalog.sort_values("_sort")
                .drop(columns="_sort")
            )

            print()
            print("    By catalog year:")
            print(
                by_catalog.to_string(
                    index=False,
                )
            )


# -------------------------------------------------------------------------------------------------
# IDENTIFY EXACT 3,081 OUTPUTS
# -------------------------------------------------------------------------------------------------

matches_3081 = [
    result
    for result in usable_results
    if result["selected_rows"] == 3_081
]

print()
print("=" * 110)
print("3,081 MAXIMUM-AWARD MATCH")
print("=" * 110)

if not matches_3081:
    print(
        "No currently located output contains exactly "
        "3,081 selected/countable award rows."
    )
    print(
        "That means the 3,081 result is either stored under a "
        "filename not captured by the search terms or must be "
        "regenerated by its reporting script."
    )
else:
    for result in matches_3081:
        print()
        print(result["path"])
        print("Modified:", result["modified"])
        print(
            "Maximum awards:",
            f"{result['selected_rows']:,}",
        )
        print(
            "Distinct students:",
            f"{result['distinct_students']:,}",
        )
        print(
            "Distinct award keys:",
            f"{result['distinct_award_keys']:,}",
        )


# -------------------------------------------------------------------------------------------------
# WRITE COMPACT INVENTORY
# -------------------------------------------------------------------------------------------------

OUTPUT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)

inventory = pd.DataFrame(
    [
        {
            key: value
            for key, value in result.items()
            if key != "data"
        }
        for result in usable_results
    ]
)

inventory.to_csv(
    OUTPUT_PATH,
    index=False,
)

print()
print("=" * 110)
print("WROTE")
print("=" * 110)
print(OUTPUT_PATH)
