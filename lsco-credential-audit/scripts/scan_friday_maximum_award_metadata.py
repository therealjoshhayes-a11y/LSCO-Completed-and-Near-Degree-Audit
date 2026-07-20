from pathlib import Path
from datetime import datetime
import os
import pandas as pd

ROOTS = [
    Path(r"data\processed\full_actual_audit"),
    Path(r"data\processed"),
    Path(r"outputs"),
]

TARGET_COUNTS = {3081, 6801, 11273}
FRIDAY_START = datetime(2026, 7, 17, 0, 0, 0)
FRIDAY_END = datetime(2026, 7, 18, 0, 0, 0)

NAME_TERMS = (
    "award",
    "complete",
    "completion",
    "eligible",
    "family",
    "lineage",
    "selected",
    "modeled",
    "summary",
)

TEXT_EXTENSIONS = {
    ".csv",
    ".txt",
    ".log",
    ".md",
    ".json",
}


def fmt_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def friday(timestamp):
    dt = datetime.fromtimestamp(timestamp)
    return FRIDAY_START <= dt < FRIDAY_END


files = []

for root in ROOTS:
    if not root.exists():
        continue

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        stat = path.stat()
        lower_name = path.name.lower()

        files.append(
            {
                "path": str(path),
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified": fmt_time(stat.st_mtime),
                "modified_timestamp": stat.st_mtime,
                "created": fmt_time(stat.st_ctime),
                "created_timestamp": stat.st_ctime,
                "modified_friday": friday(stat.st_mtime),
                "created_friday": friday(stat.st_ctime),
                "name_relevant": any(
                    term in lower_name
                    for term in NAME_TERMS
                ),
            }
        )

inventory = pd.DataFrame(files)

print("=" * 120)
print("FILES MODIFIED OR CREATED FRIDAY, JULY 17, 2026")
print("=" * 120)

friday_files = inventory[
    inventory["modified_friday"]
    | inventory["created_friday"]
].copy()

friday_files = friday_files.sort_values(
    ["modified_timestamp", "path"]
)

if friday_files.empty:
    print("None found.")
else:
    print(
        friday_files[
            [
                "modified",
                "created",
                "size_bytes",
                "path",
            ]
        ].to_string(index=False)
    )

print()
print("=" * 120)
print("RELEVANT AWARD / COMPLETION FILES — NEWEST FIRST")
print("=" * 120)

relevant = inventory[
    inventory["name_relevant"]
].sort_values(
    "modified_timestamp",
    ascending=False,
)

if relevant.empty:
    print("None found.")
else:
    print(
        relevant[
            [
                "modified",
                "created",
                "size_bytes",
                "path",
            ]
        ].head(100).to_string(index=False)
    )

print()
print("=" * 120)
print("FILES WHOSE CONTENT CONTAINS 3,081 / 3081 / 6,801 / 11,273")
print("=" * 120)

content_matches = []

for row in inventory.itertuples(index=False):
    path = Path(row.path)

    if row.extension not in TEXT_EXTENSIONS:
        continue

    # Skip huge production CSVs. We are looking for reports,
    # logs, summaries, and saved selector outputs.
    if row.size_bytes > 250_000_000:
        continue

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        continue

    normalized = text.replace(",", "")

    found = [
        count
        for count in TARGET_COUNTS
        if str(count) in normalized
    ]

    if found:
        content_matches.append(
            {
                "modified": row.modified,
                "created": row.created,
                "size_bytes": row.size_bytes,
                "counts_found": ",".join(
                    str(value)
                    for value in sorted(found)
                ),
                "path": row.path,
            }
        )

if not content_matches:
    print("No textual matches found.")
else:
    matches = pd.DataFrame(content_matches).sort_values(
        "modified",
        ascending=False,
    )
    print(matches.to_string(index=False))

print()
print("=" * 120)
print("CSV ROW-COUNT CHECK FOR RELEVANT SMALL/MEDIUM FILES")
print("=" * 120)

row_counts = []

for row in relevant.itertuples(index=False):
    path = Path(row.path)

    if path.suffix.lower() != ".csv":
        continue

    if row.size_bytes > 500_000_000:
        continue

    try:
        with path.open(
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as handle:
            count = sum(1 for _ in handle) - 1

        row_counts.append(
            {
                "rows": max(count, 0),
                "modified": row.modified,
                "created": row.created,
                "path": row.path,
            }
        )
    except Exception:
        continue

row_counts_df = pd.DataFrame(row_counts)

if row_counts_df.empty:
    print("No readable candidate CSVs.")
else:
    exact = row_counts_df[
        row_counts_df["rows"].isin(TARGET_COUNTS)
    ].sort_values(
        "modified",
        ascending=False,
    )

    print("Exact target row counts:")
    if exact.empty:
        print("None.")
    else:
        print(exact.to_string(index=False))

    print()
    print("All relevant candidate CSV row counts:")
    print(
        row_counts_df.sort_values(
            "modified",
            ascending=False,
        ).head(100).to_string(index=False)
    )

OUTPUT = Path(
    r"data\processed\full_actual_audit\evidence"
    r"\friday_3081_metadata_scan.csv"
)

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

friday_files[
    [
        "modified",
        "created",
        "size_bytes",
        "path",
    ]
].to_csv(
    OUTPUT,
    index=False,
)

print()
print("=" * 120)
print("WROTE")
print("=" * 120)
print(OUTPUT)
