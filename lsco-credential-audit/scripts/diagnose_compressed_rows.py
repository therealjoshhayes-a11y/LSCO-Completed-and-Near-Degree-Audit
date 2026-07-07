from pathlib import Path
import csv
import re

COURSE_RE = re.compile(r"\b[A-Z]{3,4}\s+\d{4}\b")

input_paths = sorted(Path("data/processed/catalogs").glob("*/requirements_docx_draft.csv"))
rows_out = []

for path in input_paths:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            flags = row.get("issue_flags", "")
            if "COMPRESSED_MULTI_COURSE_ROW" not in flags:
                continue

            text = row["raw_requirement_text"]
            course_codes = COURSE_RE.findall(text)

            # Split while preserving the course code at the front of each segment.
            parts = re.split(r"(?=\b[A-Z]{3,4}\s+\d{4}\b)", text)
            parts = [" ".join(p.split()) for p in parts if p.strip()]

            rows_out.append({
                "catalog_year": row["catalog_year"],
                "credential_title": row["credential_title"],
                "source_table_index": row["source_table_index"],
                "source_row_index": row["source_row_index"],
                "credit_hours": row["credit_hours"],
                "course_count": str(len(course_codes)),
                "course_codes": ";".join(course_codes),
                "split_part_count": str(len(parts)),
                "split_preview": " || ".join(parts),
                "raw_requirement_text": text,
            })

out_path = Path("data/interim/catalogs/compressed_row_diagnostic.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)

fieldnames = [
    "catalog_year",
    "credential_title",
    "source_table_index",
    "source_row_index",
    "credit_hours",
    "course_count",
    "course_codes",
    "split_part_count",
    "split_preview",
    "raw_requirement_text",
]

with out_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_out)

print(f"Wrote {len(rows_out)} compressed row diagnostics to {out_path}")
