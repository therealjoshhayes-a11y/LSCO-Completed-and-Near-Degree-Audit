from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from lsco_audit.catalog.registry import load_catalog_registry


COURSE_RE = re.compile(r"\b[A-Z]{3,4}\s+\d{4}\b")
POSSIBLE_BAD_COURSE_RE = re.compile(r"\b[A-Z]{3,4}\s+\d{1,3}\b")
CORE_CATEGORY_RE = re.compile(r"\bCORE\s+0[1-9]0\b", re.I)
SEMESTER_RE = re.compile(r"^(First|Second|Third|Fourth|Fifth|Sixth)\s+Semester$", re.I)
SESSION_LABEL_RE = re.compile(
    r"^(First|Second|Third|Fourth|Fifth|Sixth)?\s*"
    r"(Semester|Summer Session|First Summer Semester|FourthSemester)"
    r"(\s*\(.*\))?$",
    re.I,
)


def clean_text(value: str) -> str:
    text = " ".join((value or "").split())

    # DOCX exports sometimes collapse the space between a course code
    # and its title: MRKG 1301Customer -> MRKG 1301 Customer.
    text = re.sub(r"\b([A-Z]{3,4}\s+\d{4})(?=[A-Za-z])", r"\1 ", text)

    return text


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.upper()).strip("_")
    return cleaned or "UNKNOWN"


def iter_block_items(document):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def parse_hours(value: str) -> list[int]:
    return [int(x) for x in re.findall(r"\b\d+\b", value or "")]


def is_plan_table(table: Table) -> bool:
    if not table.rows:
        return False

    first_row = [clean_text(cell.text) for cell in table.rows[0].cells]

    return (
        len(first_row) >= 2
        and first_row[0].lower().endswith("semester")
        and first_row[1].lower() == "credit hours"
    )


def parse_rule_type(text: str) -> str:
    upper = text.upper()

    if CORE_CATEGORY_RE.search(text):
        return "CORE_BUCKET"

    if COURSE_RE.search(text) and " OR " in upper:
        return "ANY_N"

    if COURSE_RE.search(text):
        return "EXACT"

    if "ELECTIVE" in upper:
        return "ELECTIVE"

    if "LANGUAGE, PHILOSOPHY, AND CULTURE" in upper:
        return "CORE_BUCKET"

    if "LANG, PHIL, CULTURE" in upper:
        return "CORE_BUCKET"

    if "SOCIAL AND BEHAVIORAL SCIENCE" in upper:
        return "CORE_BUCKET"

    if "SOCIAL BEHAVIORAL SCIENCE" in upper:
        return "CORE_BUCKET"

    if "CREATIVE ARTS" in upper:
        return "CORE_BUCKET"

    if "CORE MATH" in upper:
        return "CORE_BUCKET"

    return "NON_COURSE"


def parse_requirement_row(
    *,
    catalog_year: str,
    credential_title: str,
    table_index: int,
    row_index: int,
    semester_label: str,
    requirement_sequence: int,
    cells: list[str],
) -> dict[str, str]:
    requirement_text = clean_text(cells[0]) if cells else ""
    hours_text = clean_text(cells[1]) if len(cells) > 1 else ""
    hours = parse_hours(hours_text)
    course_codes = COURSE_RE.findall(requirement_text)
    rule_type = parse_rule_type(requirement_text)

    issues: list[str] = []

    if rule_type in {"EXACT", "ANY_N"} and not course_codes:
        issues.append("NO_VALID_COURSE_CODE_FOUND")

    if rule_type == "ANY_N" and len(course_codes) < 2:
        issues.append("ANY_N_WITH_FEWER_THAN_TWO_COURSES")

    requirement_hour_values = strip_trailing_total_hours(hours)

    if not requirement_hour_values:
        issues.append("NO_CREDIT_HOURS_FOUND")
        credit_hours = ""
    elif len(requirement_hour_values) > 1:
        issues.append("MULTIPLE_CREDIT_HOUR_VALUES")
        credit_hours = str(requirement_hour_values[0])
    else:
        credit_hours = str(requirement_hour_values[0])

    if SESSION_LABEL_RE.match(requirement_text):
        rule_type = "NON_COURSE"
        issues = []

    elif (
        POSSIBLE_BAD_COURSE_RE.search(requirement_text)
        and not course_codes
        and not CORE_CATEGORY_RE.search(requirement_text)
    ):
        issues.append("POSSIBLE_MALFORMED_COURSE_CODE")

    if len(course_codes) > 1 and len(hours) > 1 and rule_type in {"EXACT", "ANY_N"}:
        issues.append("COMPRESSED_MULTI_COURSE_ROW")

    credential_id = f"{slugify(credential_title)}_{catalog_year[:4]}"

    return {
        "catalog_year": catalog_year,
        "credential_id": credential_id,
        "credential_title": credential_title,
        "source_table_index": str(table_index),
        "source_row_index": str(row_index),
        "requirement_sequence": str(requirement_sequence),
        "semester_label": semester_label,
        "raw_requirement_text": requirement_text,
        "credit_hours": credit_hours,
        "raw_credit_hours_text": hours_text,
        "rule_type": rule_type,
        "course_codes": ";".join(course_codes),
        "issue_flags": ";".join(issues),
    }


def parse_total_row(
    *,
    catalog_year: str,
    credential_title: str,
    table_index: int,
    row_index: int,
    semester_label: str,
    cells: list[str],
) -> dict[str, str]:
    label = clean_text(cells[0]) if cells else ""
    value = clean_text(cells[1]) if len(cells) > 1 else ""
    hours = parse_hours(value)

    semester_hours = ""
    total_program_hours = ""

    if "Semester Hours" in label and "Total Program Hours" in label:
        if len(hours) >= 2:
            semester_hours = str(hours[-2])
            total_program_hours = str(hours[-1])
    elif "Semester Hours" in label:
        if hours:
            semester_hours = str(hours[-1])
    elif "Total Program Hours" in label:
        if hours:
            total_program_hours = str(hours[-1])

    credential_id = f"{slugify(credential_title)}_{catalog_year[:4]}"

    return {
        "catalog_year": catalog_year,
        "credential_id": credential_id,
        "credential_title": credential_title,
        "source_table_index": str(table_index),
        "source_row_index": str(row_index),
        "semester_label": semester_label,
        "raw_total_text": label,
        "semester_hours": semester_hours,
        "total_program_hours": total_program_hours,
        "raw_hours_text": value,
    }



def strip_trailing_total_hours(hours: list[int]) -> list[int]:
    """Remove semester/program total values from a parsed hour list.

    DOCX tables sometimes combine requirement cells with trailing
    Semester Hours and Total Program Hours values. Example:
        3 3 3 3 3 15 60

    Requirement emission should use only:
        3 3 3 3 3
    """
    values = list(hours)

    # Program totals are normally 30/45/60+ and appear last.
    if len(values) >= 2 and values[-1] >= 30:
        values = values[:-1]

    # Semester subtotal usually equals the sum of the preceding row hours.
    if len(values) >= 2 and values[-1] == sum(values[:-1]):
        values = values[:-1]

    return values


MIXED_NON_COURSE_MARKER_RE = re.compile(
    r"\b(?:"
    r"Lang(?:uage)?[, ]+Phil(?:osophy)?[, ]+Culture\s+OR\s+Creative Arts"
    r"|Language,\s*Philosophy,\s*and Culture"
    r"|Life\s+and\s+Physical\s+Sciences?"
    r"|Social\s+Behavioral\s+Science"
    r"|Component\s+Area\s+Option"
    r"|BUSI\s+Elective"
    r"|Business\s+Elective"
    r"|Elective"
    r")\b",
    re.I,
)


def _non_overlapping_marker_matches(text: str) -> list[re.Match]:
    matches = sorted(MIXED_NON_COURSE_MARKER_RE.finditer(text), key=lambda m: (m.start(), -(m.end() - m.start())))
    kept = []
    last_end = -1

    for match in matches:
        if match.start() < last_end:
            continue
        kept.append(match)
        last_end = match.end()

    return kept


def split_mixed_course_core_elective_row(row: dict[str, str]) -> list[dict[str, str]]:
    """Split rows mixing course codes with core/elective placeholders.

    Example:
        MRKG 1301... BUSG 2309... Lang, Phil, Culture OR Creative Arts
        Social Behavioral Science BUSI Elective
        hours: 3 3 3 3 3 15 60
    """
    text = row["raw_requirement_text"]
    course_matches = list(COURSE_RE.finditer(text))
    marker_matches = _non_overlapping_marker_matches(text)

    if not course_matches or not marker_matches:
        return [row]

    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))
    hour_values = strip_trailing_total_hours(parse_hours(raw_hours_text))

    boundaries = []
    for match in course_matches:
        boundaries.append((match.start(), "course", match))
    for match in marker_matches:
        boundaries.append((match.start(), "non_course", match))

    boundaries.sort(key=lambda item: item[0])

    # Only use this splitter when it discovers more fragments than course-only parsing.
    if len(boundaries) <= len(course_matches):
        return [row]

    if len(hour_values) < len(boundaries):
        return [row]

    split_rows = []

    for index, (start, kind, match) in enumerate(boundaries, start=1):
        end = boundaries[index][0] if index < len(boundaries) else len(text)
        fragment = clean_text(text[start:end])

        if not fragment:
            return [row]

        new_row = dict(row)
        new_row["requirement_sequence"] = f'{row["requirement_sequence"]}.{index}'
        new_row["raw_requirement_text"] = fragment
        new_row["credit_hours"] = str(hour_values[index - 1])

        fragment_courses = COURSE_RE.findall(fragment)
        new_row["course_codes"] = ";".join(fragment_courses)
        new_row["rule_type"] = parse_rule_type(fragment)
        new_row["issue_flags"] = ""

        split_rows.append(new_row)

    return split_rows


def split_internal_or_compressed_course_row(row: dict[str, str]) -> list[dict[str, str]]:
    """Split compressed course rows where one requirement is an internal OR pair.

    Example:
        ACCT 2301 ... ACNT 1329 ... BUSG 1304 ...
        COSC 1301 ... OR BCIS 1305 ... BMGT 1327 ...
        hours: 3 3 3 3 3 15

    Expected emitted requirements:
        ACCT 2301
        ACNT 1329
        BUSG 1304
        COSC 1301 OR BCIS 1305
        BMGT 1327
    """
    text = row["raw_requirement_text"]

    if " OR " not in text.upper():
        return [row]

    course_codes = COURSE_RE.findall(text)
    if len(course_codes) < 3:
        return [row]

    parts = re.split(r"(?=\b[A-Z]{3,4}\s+\d{4}\b)", text)
    parts = [clean_text(part) for part in parts if clean_text(part)]

    if len(parts) != len(course_codes):
        return [row]

    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))
    hour_values = strip_trailing_total_hours(parse_hours(raw_hours_text))

    grouped_parts: list[str] = []
    index = 0

    while index < len(parts):
        part = parts[index]

        if index + 1 < len(parts) and re.search(r"\bOR\s*$", part, re.I):
            grouped_parts.append(clean_text(f"{part} {parts[index + 1]}"))
            index += 2
        else:
            grouped_parts.append(part)
            index += 1

    if len(grouped_parts) != len(hour_values):
        return [row]

    split_rows = []

    for idx, part in enumerate(grouped_parts, start=1):
        new_row = dict(row)
        new_row["requirement_sequence"] = f'{row["requirement_sequence"]}.{idx}'
        new_row["raw_requirement_text"] = clean_text(part)
        new_row["credit_hours"] = str(hour_values[idx - 1])

        fragment_courses = COURSE_RE.findall(part)
        new_row["course_codes"] = ";".join(fragment_courses)
        new_row["rule_type"] = parse_rule_type(part)
        new_row["issue_flags"] = ""

        split_rows.append(new_row)

    return split_rows

def split_leading_or_compressed_row(row: dict[str, str]) -> list[dict[str, str]]:
    text = row["raw_requirement_text"]
    upper = text.upper()

    if " OR " not in upper:
        return [row]

    course_codes = COURSE_RE.findall(text)
    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))
    hour_values = strip_trailing_total_hours(parse_hours(raw_hours_text))

    if len(course_codes) < 3:
        return [row]

    if len(hour_values) != len(course_codes) - 1:
        return [row]

    parts = re.split(r"(?=\b[A-Z]{3,4}\s+\d{4}\b)", text)
    parts = [clean_text(part) for part in parts if clean_text(part)]

    if len(parts) != len(course_codes):
        return [row]

    # Only handle the safe shape:
    # course 1 OR course 2, then remaining courses are required.
    if not re.search(r"\bOR\s*$", parts[0], re.I):
        return [row]

    if any(" OR " in part.upper() for part in parts[1:]):
        return [row]

    split_rows = []

    first = dict(row)
    first["requirement_sequence"] = f'{row["requirement_sequence"]}.1'
    first["raw_requirement_text"] = f"{parts[0]} {parts[1]}"
    first["credit_hours"] = str(hour_values[0])
    first["rule_type"] = "ANY_N"
    first["course_codes"] = ";".join(course_codes[:2])
    first["issue_flags"] = ""
    split_rows.append(first)

    for index, part in enumerate(parts[2:], start=2):
        new_row = dict(row)
        new_row["requirement_sequence"] = f'{row["requirement_sequence"]}.{index}'
        new_row["raw_requirement_text"] = clean_text(part)
        new_row["credit_hours"] = str(hour_values[index - 1])
        new_row["rule_type"] = "EXACT"
        new_row["course_codes"] = course_codes[index]
        new_row["issue_flags"] = ""
        split_rows.append(new_row)

    return split_rows

def split_compressed_course_row(row: dict[str, str]) -> list[dict[str, str]]:
    text = row["raw_requirement_text"]
    upper = text.upper()

    if " OR " in upper:
        leading_split = split_leading_or_compressed_row(row)
        if len(leading_split) > 1:
            return leading_split

        internal_or_split = split_internal_or_compressed_course_row(row)
        if len(internal_or_split) > 1:
            return internal_or_split

        mixed_split = split_mixed_course_core_elective_row(row)
        if len(mixed_split) > 1:
            return mixed_split

        return [row]

    course_codes = COURSE_RE.findall(text)

    if len(course_codes) <= 1:
        return [row]

    parts = re.split(r"(?=\b[A-Z]{3,4}\s+\d{4}\b)", text)
    parts = [clean_text(part) for part in parts if clean_text(part)]

    if len(parts) != len(course_codes):
        return [row]

    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))
    hour_values = strip_trailing_total_hours(parse_hours(raw_hours_text))

    if len(hour_values) < len(course_codes):
        return [row]

    split_rows = []

    for index, part in enumerate(parts, start=1):
        clean_part = re.sub(
            r"\s+Semester Hours\s+Total Program Hours\s*$",
            "",
            part,
            flags=re.I,
        )
        clean_part = re.sub(
            r"\s+Semester Hours\s*$",
            "",
            clean_part,
            flags=re.I,
        )
        clean_part = clean_text(clean_part)

        new_row = dict(row)
        new_row["requirement_sequence"] = f'{row["requirement_sequence"]}.{index}'
        new_row["raw_requirement_text"] = clean_part
        new_row["credit_hours"] = str(hour_values[index - 1])
        new_row["rule_type"] = "EXACT"
        new_row["course_codes"] = course_codes[index - 1]
        new_row["issue_flags"] = ""
        split_rows.append(new_row)

    return split_rows

def parse_plan_table(
    *,
    catalog_year: str,
    credential_title: str,
    table: Table,
    table_index: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    requirement_rows = []
    total_rows = []

    semester_label = ""
    requirement_sequence = 0

    for row_index, row in enumerate(table.rows):
        cells = [clean_text(cell.text) for cell in row.cells]
        first_cell = cells[0] if cells else ""

        if not first_cell:
            continue

        if row_index == 0 and first_cell.lower().endswith("semester"):
            semester_label = first_cell
            continue

        if SEMESTER_RE.match(first_cell):
            semester_label = first_cell
            continue

        if "Semester Hours" in first_cell or "Total Program Hours" in first_cell:
            if COURSE_RE.search(first_cell):
                requirement_text = re.sub(
                    r"\s+Semester Hours\s+Total Program Hours\s*$",
                    "",
                    first_cell,
                    flags=re.I,
                )
                requirement_text = re.sub(
                    r"\s+Semester Hours\s*$",
                    "",
                    requirement_text,
                    flags=re.I,
                )
                requirement_text = clean_text(requirement_text)

                requirement_sequence += 1
                parsed_row = parse_requirement_row(
                    catalog_year=catalog_year,
                    credential_title=credential_title,
                    table_index=table_index,
                    row_index=row_index,
                    semester_label=semester_label,
                    requirement_sequence=requirement_sequence,
                    cells=[requirement_text, cells[1] if len(cells) > 1 else ""],
                )

                requirement_rows.extend(split_compressed_course_row(parsed_row))

            total_rows.append(
                parse_total_row(
                    catalog_year=catalog_year,
                    credential_title=credential_title,
                    table_index=table_index,
                    row_index=row_index,
                    semester_label=semester_label,
                    cells=cells,
                )
            )
            continue

        requirement_sequence += 1
        parsed_row = parse_requirement_row(
            catalog_year=catalog_year,
            credential_title=credential_title,
            table_index=table_index,
            row_index=row_index,
            semester_label=semester_label,
            requirement_sequence=requirement_sequence,
            cells=cells,
        )

        requirement_rows.extend(split_compressed_course_row(parsed_row))

    return requirement_rows, total_rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def extract_catalog(record) -> None:
    doc = Document(record.source_docx_path)

    current_heading_2 = ""
    table_index = 0

    all_requirements = []
    all_totals = []
    table_map_rows = []

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = clean_text(block.text)
            style = block.style.name if block.style else ""

            if text and style == "Heading 2":
                current_heading_2 = text

        elif isinstance(block, Table):
            if is_plan_table(block) and current_heading_2:
                requirements, totals = parse_plan_table(
                    catalog_year=record.catalog_year,
                    credential_title=current_heading_2,
                    table=block,
                    table_index=table_index,
                )

                credential_id = f"{slugify(current_heading_2)}_{record.catalog_year[:4]}"

                table_map_rows.append(
                    {
                        "catalog_year": record.catalog_year,
                        "credential_title": current_heading_2,
                        "credential_id": credential_id,
                        "source_table_index": str(table_index),
                        "requirement_row_count": str(len(requirements)),
                        "total_row_count": str(len(totals)),
                    }
                )

                all_requirements.extend(requirements)
                all_totals.extend(totals)

            table_index += 1

    out_dir = Path("data") / "processed" / "catalogs" / record.catalog_year

    write_csv(
        out_dir / "requirements_docx_draft.csv",
        all_requirements,
        [
            "catalog_year",
            "credential_id",
            "credential_title",
            "source_table_index",
            "source_row_index",
            "requirement_sequence",
            "semester_label",
            "raw_requirement_text",
            "credit_hours",
            "raw_credit_hours_text",
            "rule_type",
            "course_codes",
            "issue_flags",
        ],
    )

    write_csv(
        out_dir / "requirement_totals_docx_draft.csv",
        all_totals,
        [
            "catalog_year",
            "credential_id",
            "credential_title",
            "source_table_index",
            "source_row_index",
            "semester_label",
            "raw_total_text",
            "semester_hours",
            "total_program_hours",
            "raw_hours_text",
        ],
    )

    write_csv(
        out_dir / "credential_table_map_docx_draft.csv",
        table_map_rows,
        [
            "catalog_year",
            "credential_title",
            "credential_id",
            "source_table_index",
            "requirement_row_count",
            "total_row_count",
        ],
    )

    print(
        f"{record.catalog_year}: "
        f"{len(table_map_rows)} credential tables, "
        f"{len(all_requirements)} requirement rows, "
        f"{len(all_totals)} total rows"
    )


def main() -> None:
    for record in load_catalog_registry(active_only=True):
        extract_catalog(record)


if __name__ == "__main__":
    main()













