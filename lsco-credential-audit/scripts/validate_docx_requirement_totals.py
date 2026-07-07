from pathlib import Path
import csv
from collections import defaultdict


def to_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


rows_out = []

for req_path in sorted(Path("data/processed/catalogs").glob("*/requirements_docx_draft.csv")):
    year = req_path.parent.name
    totals_path = req_path.parent / "requirement_totals_docx_draft.csv"

    requirements = read_csv(req_path)
    totals = read_csv(totals_path)

    req_by_credential_semester = defaultdict(list)
    req_by_credential = defaultdict(list)

    for row in requirements:
        key = (row["catalog_year"], row["credential_id"], row["credential_title"])
        sem_key = key + (row["semester_label"],)
        req_by_credential[key].append(row)
        req_by_credential_semester[sem_key].append(row)

    semester_totals = {}
    program_totals = {}

    for row in totals:
        key = (row["catalog_year"], row["credential_id"], row["credential_title"])
        sem_key = key + (row["semester_label"],)

        semester_hours = to_int(row.get("semester_hours", ""))
        total_program_hours = to_int(row.get("total_program_hours", ""))

        if semester_hours is not None:
            semester_totals[sem_key] = semester_hours

        if total_program_hours is not None:
            program_totals[key] = total_program_hours

    for sem_key, req_rows in sorted(req_by_credential_semester.items()):
        catalog_year, credential_id, credential_title, semester_label = sem_key

        parsed_hours = sum(
            to_int(row.get("credit_hours", "")) or 0
            for row in req_rows
            if row.get("rule_type") != "NON_COURSE"
        )

        expected_hours = semester_totals.get(sem_key)

        if expected_hours is None:
            status = "NO_SEMESTER_TOTAL"
            delta = ""
        else:
            delta_value = parsed_hours - expected_hours
            delta = str(delta_value)
            status = "OK" if delta_value == 0 else "SEMESTER_TOTAL_MISMATCH"

        rows_out.append({
            "validation_level": "SEMESTER",
            "catalog_year": catalog_year,
            "credential_id": credential_id,
            "credential_title": credential_title,
            "semester_label": semester_label,
            "parsed_hours": str(parsed_hours),
            "expected_hours": "" if expected_hours is None else str(expected_hours),
            "delta": delta,
            "status": status,
            "requirement_count": str(len(req_rows)),
        })

    for key, req_rows in sorted(req_by_credential.items()):
        catalog_year, credential_id, credential_title = key

        parsed_hours = sum(
            to_int(row.get("credit_hours", "")) or 0
            for row in req_rows
            if row.get("rule_type") != "NON_COURSE"
        )

        expected_hours = program_totals.get(key)

        if expected_hours is None:
            status = "NO_PROGRAM_TOTAL"
            delta = ""
        else:
            delta_value = parsed_hours - expected_hours
            delta = str(delta_value)
            status = "OK" if delta_value == 0 else "PROGRAM_TOTAL_MISMATCH"

        rows_out.append({
            "validation_level": "PROGRAM",
            "catalog_year": catalog_year,
            "credential_id": credential_id,
            "credential_title": credential_title,
            "semester_label": "",
            "parsed_hours": str(parsed_hours),
            "expected_hours": "" if expected_hours is None else str(expected_hours),
            "delta": delta,
            "status": status,
            "requirement_count": str(len(req_rows)),
        })


out_path = Path("data/interim/catalogs/requirement_total_validation.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)

fieldnames = [
    "validation_level",
    "catalog_year",
    "credential_id",
    "credential_title",
    "semester_label",
    "parsed_hours",
    "expected_hours",
    "delta",
    "status",
    "requirement_count",
]

with out_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_out)

print(f"Wrote {len(rows_out)} validation rows to {out_path}")

status_counts = defaultdict(int)
for row in rows_out:
    status_counts[(row["validation_level"], row["status"])] += 1

for key, count in sorted(status_counts.items()):
    print(f"{key[0]} {key[1]}: {count}")
