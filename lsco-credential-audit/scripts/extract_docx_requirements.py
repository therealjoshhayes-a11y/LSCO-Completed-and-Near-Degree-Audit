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

    # Catalog typo observed in Ordinary Seaman tables: NAUT1 #### -> NAUT ####.
    text = re.sub(r"\bNAUT1\s+(\d{4})\b", r"NAUT \1", text)
    text = re.sub(r"[.?]{2,}", " ", text)
    text = " ".join(text.split())

    # DOCX exports sometimes collapse course spacing:
    #   ENGL1301 -> ENGL 1301
    #   MRKG 1301Customer -> MRKG 1301 Customer.
    text = re.sub(r"\b([A-Z]{3,4})(\d{4})\b", r"\1 \2", text)
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

    if "AMERICAN HISTORY CORE" in upper:
        return "CORE_BUCKET"

    if upper.strip() == "AMERICAN HISTORY":
        return "CORE_BUCKET"

    if "COMMUNICATION CORE" in upper:
        return "CORE_BUCKET"

    if upper.strip() == "COMMUNICATION":
        return "CORE_BUCKET"

    if "COMPONENT AREA OPTION" in upper:
        return "CORE_BUCKET"

    if "GOVERNMENT/POLITICAL SCIENCE CORE" in upper:
        return "CORE_BUCKET"

    if "LIFE AND PHYSICAL SCIENCE" in upper:
        return "CORE_BUCKET"

    if "LIFE AND PHYSICAL SCIENCES" in upper:
        return "CORE_BUCKET"

    if "MATHEMATICS CORE" in upper:
        return "CORE_BUCKET"

    if upper.strip() == "MATHEMATICS":
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


def normalize_requirement_hours(raw_hours_text: str, expected_count: int) -> list[int]:
    """Return requirement-level hours aligned to emitted fragments.

    Handles rows like:
        3 3 3 3 15

    where 15 is the semester total and the final requirement hour is omitted.
    In that case:
        15 - (3 + 3 + 3 + 3) = 3
    """
    values = strip_trailing_total_hours(parse_hours(raw_hours_text))

    if expected_count > 1 and len(values) == expected_count:
        possible_total = values[-1]
        previous_sum = sum(values[:-1])
        inferred_last = possible_total - previous_sum

        if possible_total >= 10 and 1 <= inferred_last <= 6:
            return values[:-1] + [inferred_last]

    return values




CORE_ATOM_SYNONYMS = {
    "COMMUNICATION": [
        r"Communication(?:\s+CORE(?:\s+0?10)?)?",
    ],
    "MATHEMATICS": [
        r"Mathematics(?:\s+CORE(?:\s+0?20)?)?",
    ],
    "LIFE_PHYSICAL_SCIENCE": [
        r"Life\s+and\s+Physical\s+Sciences?(?:\s+CORE(?:\s+0?30)?)?",
    ],
    "LANGUAGE_PHILOSOPHY_CULTURE": [
        r"Language,\s*Philosophy,\s*and\s+Culture(?:\s+CORE(?:\s+0?40)?)?",
        r"Lang(?:uage)?[, ]+Phil(?:osophy)?(?:,?\s+and)?[, ]+Culture(?:\s+CORE(?:\s+0?40)?)?",
        r"Language\s+and\s+Philosophy",
    ],
    "CREATIVE_ARTS": [
        r"Creative\s+Arts(?:\s+CORE(?:\s+0?50)?)?(?:\s+Elective)?",
    ],
    "AMERICAN_HISTORY": [
        r"American\s+History(?:\s+CORE\s+0?60)?",
    ],
    "GOVERNMENT_POLITICAL_SCIENCE": [
        r"Government/Political\s+Science\s+CORE\s+0?70",
    ],
    "SOCIAL_BEHAVIORAL_SCIENCE": [
        r"Social(?:/|\s+(?:and\s+)?)Behavioral\s+Sciences?(?:\s+(?:CORE|Elective))?",
    ],
    "COMPONENT_AREA_OPTION": [
        r"Component\s+Area\s+Option(?:\s+CORE\s+0?90)?",
    ],
}

CASCADE_CORE_ATOM_RE = re.compile(
    r"\b(?:"
    + "|".join(pattern for patterns in CORE_ATOM_SYNONYMS.values() for pattern in patterns)
    + r")\b",
    re.I,
)

CASCADE_RUBRIC_ELECTIVE_RE = re.compile(r"\b[A-Z]{2,6}\s+Elective\b", re.I)
CASCADE_PROGRAM_AREA_ELECTIVE_RE = re.compile(
    r"\b(?:Business|Animal\s+Science|Agribusiness)\s+Elective\b",
    re.I,
)
CASCADE_GENERIC_ELECTIVE_RE = re.compile(r"\bElective\b", re.I)


def canonical_core_atom(value: str) -> str:
    value = clean_text(value)
    for canonical, patterns in CORE_ATOM_SYNONYMS.items():
        for pattern in patterns:
            if re.fullmatch(pattern, value, re.I):
                return canonical
    return slugify(value)


def cascade_atom_matches(text: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []

    for match in COURSE_RE.finditer(text):
        matches.append((match.start(), match.end(), "COURSE", match.group()))

    for match in CASCADE_CORE_ATOM_RE.finditer(text):
        matches.append((match.start(), match.end(), "CORE_BUCKET", match.group()))

    for match in CASCADE_RUBRIC_ELECTIVE_RE.finditer(text):
        matches.append((match.start(), match.end(), "RUBRIC_ELECTIVE", match.group()))

    for match in CASCADE_PROGRAM_AREA_ELECTIVE_RE.finditer(text):
        matches.append((match.start(), match.end(), "PROGRAM_AREA_ELECTIVE", match.group()))

    kept: list[tuple[int, int, str, str]] = []
    for item in sorted(matches, key=lambda x: (x[0], -(x[1] - x[0]))):
        start, end, kind, value = item
        if any(start >= kept_start and end <= kept_end for kept_start, kept_end, _, _ in kept):
            continue
        kept.append(item)

    return sorted(kept, key=lambda x: x[0])


def cascade_classify_expression(fragment: str) -> tuple[str, str]:
    fragment = clean_text(fragment)
    course_codes = ";".join(dict.fromkeys(COURSE_RE.findall(fragment)))

    if re.search(r"\bOR\b", fragment, re.I):
        return "ANY_N", course_codes

    if course_codes:
        return "EXACT", course_codes

    if CASCADE_CORE_ATOM_RE.search(fragment):
        return "CORE_BUCKET", ""

    if CASCADE_RUBRIC_ELECTIVE_RE.search(fragment):
        return "RUBRIC_ELECTIVE", ""

    if CASCADE_PROGRAM_AREA_ELECTIVE_RE.search(fragment):
        return "PROGRAM_AREA_ELECTIVE", ""

    if CASCADE_GENERIC_ELECTIVE_RE.search(fragment):
        return "ELECTIVE", ""

    return "UNRESOLVED", course_codes


def try_cascade_mixed_option_split(row: dict) -> list[dict] | None:
    raw_text = row.get("raw_requirement_text", "")
    text = clean_text(raw_text)

    issue_flags = str(row.get("issue_flags", ""))
    raw_hours_text = (
        row.get("raw_credit_hours_text")
        or row.get("raw_hours_text")
        or row.get("credit_hours")
        or ""
    )
    hour_count = len(parse_hours(str(raw_hours_text)))

    has_structural_evidence = (
        "COMPRESSED_MULTI_COURSE_ROW" in issue_flags
        or "MULTIPLE_CREDIT_HOUR_VALUES" in issue_flags
        or hour_count > 1
    )

    has_mixed_option_language = re.search(
        r"\bOR\b|\bElective\b|CORE|Social|Creative|Language|Communication|Mathematics",
        text,
        re.I,
    )

    if not (has_structural_evidence and has_mixed_option_language):
        return None

    atoms = cascade_atom_matches(text)
    if len(atoms) < 2:
        return None

    fragments: list[str] = []
    for index, (start, end, kind, value) in enumerate(atoms):
        next_start = atoms[index + 1][0] if index + 1 < len(atoms) else len(text)
        fragments.append(clean_text(text[start:next_start]))

    grouped: list[str] = []
    index = 0

    while index < len(fragments):
        current = fragments[index]

        while (
            index + 1 < len(fragments)
            and (
                re.search(r"\bOR\s*$", current, re.I)
                or re.search(r"\bor\s+[A-Z]{2,6}\s*$", current, re.I)
                or re.search(r"\bor\s*$", current, re.I)
            )
        ):
            current = clean_text(f"{current} {fragments[index + 1]}")
            index += 1

        grouped.append(current)
        index += 1

    # Second pass: join non-course phrase + trailing bare/generic elective fragment.
    repaired: list[str] = []
    index = 0
    while index < len(grouped):
        current = grouped[index]
        if (
            index + 1 < len(grouped)
            and re.fullmatch(r"Elective(?:\s+OR)?", grouped[index + 1], re.I)
            and (
                CASCADE_CORE_ATOM_RE.search(current)
                or re.search(r"\bor\s+[A-Z]{2,6}\s*$", current, re.I)
            )
        ):
            combined = clean_text(f"{current} {grouped[index + 1]}")
            index += 2

            while index < len(grouped) and re.search(r"\bOR\s*$", combined, re.I):
                combined = clean_text(f"{combined} {grouped[index]}")
                index += 1

            repaired.append(combined)
        else:
            repaired.append(current)
            index += 1

    raw_hours_text = (
        row.get("raw_credit_hours_text")
        or row.get("raw_hours_text")
        or row.get("credit_hours")
        or ""
    )
    hour_values = normalize_requirement_hours(raw_hours_text, len(repaired))

    if len(repaired) < 2 or len(hour_values) != len(repaired):
        return None

    base_sequence_raw = row.get("requirement_sequence", 0)
    try:
        base_sequence = int(float(base_sequence_raw))
    except (TypeError, ValueError):
        base_sequence = 0

    out: list[dict] = []
    for offset, fragment in enumerate(repaired):
        new_row = dict(row)
        rule_type, course_codes = cascade_classify_expression(fragment)

        new_row["requirement_sequence"] = base_sequence + offset
        new_row["raw_requirement_text"] = fragment
        new_row["credit_hours"] = hour_values[offset]
        new_row["rule_type"] = rule_type
        new_row["course_codes"] = course_codes

        if "issue_flags" in new_row:
            flags = [
                flag for flag in str(new_row.get("issue_flags", "")).split(";")
                if flag and flag not in {"COMPRESSED_MULTI_COURSE_ROW", "MULTIPLE_CREDIT_HOUR_VALUES"}
            ]
            flags.append("CASCADE_MIXED_OPTION_SPLIT")
            new_row["issue_flags"] = ";".join(dict.fromkeys(flags))

        out.append(new_row)

    return out

MIXED_NON_COURSE_MARKER_RE = re.compile(
    r"\b(?:"
    r"Lang(?:uage)?[, ]+Phil(?:osophy)?(?:,?\s+and)?[, ]+Culture(?:\s+CORE(?:\s+0?40)?)?\s+OR\s+Creative\s+Arts(?:\s+CORE(?:\s+0?50)?)?"
    r"|Language,\s*Philosophy,\s*and\s+Culture(?:\s+CORE(?:\s+0?40)?)?"
    r"|Language\s+and\s+Philosophy\s+or\s+Creative\s+Arts"
    r"|American\s+History(?:\s+CORE\s+0?60)?"
    r"|Communication(?:\s+CORE\s+0?10)?"
    r"|Government/Political\s+Science\s+CORE\s+0?70"
    r"|Life\s+and\s+Physical\s+Sciences?(?:\s+CORE\s+0?30)?"
    r"|Mathematics(?:\s+CORE(?:\s+0?20)?)?"
    r"|Creative\s+Arts(?:\s+CORE(?:\s+0?50)?)?"
    r"|Social(?:/|\s+(?:and\s+)?)Behavioral\s+Sciences?(?:\s+CORE|\s+Elective)?"
    r"|Component\s+Area\s+Option(?:\s+CORE\s+0?90)?"
    r"|BUSI\s+Elective"
    r"|Business\s+Elective"
    r"|Elective"
    r")\b",
    re.I,
)


def _is_parenthetical_annotation(text: str, match: re.Match) -> bool:
    """Skip core markers that are parenthetical annotations on a course.

    Example:
        ENGL 1301 (COMMUNICATION CORE 010)

    That should stay attached to ENGL 1301, while a later standalone
    AMERICAN HISTORY CORE 060 should become its own requirement.
    """
    last_open = text.rfind("(", 0, match.start())
    last_close = text.rfind(")", 0, match.start())

    if last_open <= last_close:
        return False

    next_close = text.find(")", match.end())
    return next_close != -1


def _is_plain_mathematics_course_title_match(text: str, match: re.Match) -> bool:
    """Skip plain core words when they are part of a course title.

    Examples:
        MATH 1332 Contemporary Mathematics ... OR CORE MATHEMATICS
        COMM 1307 Introduction to Mass Communication

    The title-word occurrence should be ignored. The standalone/core-bucket
    occurrence should be kept.
    """
    if match.group().upper() not in {"MATHEMATICS", "COMMUNICATION"}:
        return False

    preceding_text = text[:match.start()]
    following_text = text[match.end():]

    nearest_course = list(COURSE_RE.finditer(preceding_text))
    if not nearest_course:
        return False

    last_course = nearest_course[-1]

    # If another explicit OR appears before the marker, it is likely a core bucket.
    text_after_course = preceding_text[last_course.end():]
    if re.search(r"\bOR\s+(?:CORE\s+)?$", text_after_course, re.I):
        return False

    # High-confidence standalone bucket sequence:
    #   ENGL 1301 Composition I AMERICAN HISTORY MATHEMATICS CREATIVE ARTS
    text_after_course = preceding_text[last_course.end():]
    if (
        match.group().upper() == "MATHEMATICS"
        and "AMERICAN HISTORY" in text_after_course.upper()
        and re.search(r"^\s+CREATIVE\s+ARTS\b", following_text, re.I)
    ):
        return False

    # High-confidence non-course OR pair:
    #   COMMUNICATION or COMPONENT AREA OPTION
    if (
        match.group().upper() == "COMMUNICATION"
        and re.search(r"^\s+or\s+COMPONENT\s+AREA\s+OPTION\b", following_text, re.I)
    ):
        return False

    # High-confidence standalone bucket after a language/creative-arts pair:
    #   LANGUAGE, PHILOSOPHY, AND CULTURE or CREATIVE ARTS MATHEMATICS
    if (
        match.group().upper() == "MATHEMATICS"
        and re.search(r"LANGUAGE,\s*PHILOSOPHY,\s*(?:AND\s+)?CULTURE\s+or\s+CREATIVE\s+ARTS\s*$", preceding_text, re.I)
    ):
        return False

    # If it is followed by another course before an OR, treat it as a standalone marker.
    next_or = re.search(r"\bOR\b", following_text, re.I)
    next_course = COURSE_RE.search(following_text)
    if next_course and (not next_or or next_course.start() < next_or.start()):
        return False

    return True


def _non_overlapping_marker_matches(text: str) -> list[re.Match]:
    matches = sorted(MIXED_NON_COURSE_MARKER_RE.finditer(text), key=lambda m: (m.start(), -(m.end() - m.start())))
    kept = []
    last_end = -1

    for match in matches:
        if _is_parenthetical_annotation(text, match):
            continue

        # In elective lists, only keep the first elective marker.
        # Example:
        #   Business Elective, Animal Science Elective, or Agribusiness Elective
        # The whole phrase is one requirement option group, not three requirements.
        if (
            match.group().upper() == "ELECTIVE"
            and kept
            and "ELECTIVE" in kept[-1].group().upper()
            and re.fullmatch(r"[\s,orA-Za-z]*", text[kept[-1].end():match.start()], re.I)
        ):
            continue

        # Skip COMMUNICATION when it is course-title text, not a core bucket.
        # Example:
        #   SPCH 1321 Business & Professional Communication GOVT 2305 ...
        if (
            match.group().upper() == "COMMUNICATION"
            and re.search(r"Business\s*&\s*Professional\s*$", text[:match.start()], re.I)
        ):
            continue

        if _is_plain_mathematics_course_title_match(text, match):
            continue

        if match.start() < last_end:
            continue

        kept.append(match)
        last_end = match.end()

    return kept


def split_mixed_course_core_elective_row(row: dict[str, str]) -> list[dict[str, str]]:
    """Split rows mixing course codes with core/elective placeholders.

    Handles:
        course + standalone core placeholder
        course OR standalone core/elective placeholder
        course + core + course OR elective + course
    """
    text = row["raw_requirement_text"]
    course_matches = list(COURSE_RE.finditer(text))
    marker_matches = _non_overlapping_marker_matches(text)

    if not course_matches or not marker_matches:
        return [row]

    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))

    boundaries = []
    for match in course_matches:
        boundaries.append((match.start(), "course", match))
    for match in marker_matches:
        boundaries.append((match.start(), "non_course", match))

    boundaries.sort(key=lambda item: item[0])

    if len(boundaries) <= len(course_matches):
        return [row]

    hour_values = normalize_requirement_hours(raw_hours_text, len(boundaries))

    fragments = []
    for index, (start, kind, match) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        fragment = clean_text(text[start:end])

        if not fragment:
            return [row]

        fragments.append(fragment)

    grouped_fragments: list[str] = []
    index = 0

    while index < len(fragments):
        fragment = fragments[index]

        if (
            index + 1 < len(fragments)
            and (
                re.search(r"\(?\s*OR(?:\s+CORE)?\s*$", fragment, re.I)
                or re.search(r"\bOR\s*$", fragment, re.I)
            )
        ):
            # Group chained OR options into one requirement:
            #   MATH 1314 ... or MATH 1332 ... or MATH 1342 ...
            combined_fragment = fragment
            index += 1

            while index < len(fragments):
                combined_fragment = clean_text(f"{combined_fragment} {fragments[index]}")
                index += 1

                if not (
                    re.search(r"\(?\s*OR(?:\s+CORE)?\s*$", combined_fragment, re.I)
                    or re.search(r"\bOR\s*$", combined_fragment, re.I)
                ):
                    break

            grouped_fragments.append(combined_fragment)
        elif (
            index + 1 < len(fragments)
            and re.fullmatch(r"Elective(?:\\s+OR)?", fragments[index + 1], re.I)
            and (
                "CREATIVE ARTS" in fragment.upper()
                or "LANGUAGE, PHILOSOPHY" in fragment.upper()
                or "LANG, PHIL" in fragment.upper()
                or re.search(r"\bor\s+[A-Z]{2,6}\s*$", fragment, re.I)
            )
        ):
            # Group non-course OR elective options:
            #   LANGUAGE ... or CREATIVE ARTS
            #   EDUC 1300 Learning Framework or EMSP Elective
            #   COSC 1301 ... OR SPCH Elective OR EDUC 1301 ...
            combined_fragment = clean_text(f"{fragment} {fragments[index + 1]}")
            index += 2

            while (
                index < len(fragments)
                and (
                    re.search(r"\bOR\s*$", combined_fragment, re.I)
                    or re.search(r"\(?\s*OR(?:\s+CORE)?\s*$", combined_fragment, re.I)
                )
            ):
                combined_fragment = clean_text(f"{combined_fragment} {fragments[index]}")
                index += 1

            grouped_fragments.append(combined_fragment)
        else:
            grouped_fragments.append(fragment)
            index += 1

    if len(grouped_fragments) != len(hour_values):
        # Second-pass residue case:
        #   ENGL 1301 Composition I AMERICAN HISTORY MATHEMATICS CREATIVE ARTS
        #   GOVT 2306 Texas Government LIFE AND PHYSICAL SCIENCES
        if len(course_matches) == 1 and len(grouped_fragments) > 1:
            base_hour = int(float(row.get("credit_hours", "3") or 3))
            inferred_hours = [base_hour]

            for fragment in grouped_fragments[1:]:
                upper_fragment = fragment.upper()
                if "LIFE AND PHYSICAL SCIENCES" in upper_fragment:
                    inferred_hours.append(4)
                else:
                    inferred_hours.append(3)

            hour_values = inferred_hours
        else:
            cascade_rows = try_cascade_mixed_option_split(row)
            if cascade_rows:
                return cascade_rows
            return [row]

    split_rows = []

    for index, fragment in enumerate(grouped_fragments, start=1):
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

    if " OR " not in text.upper() and not re.search(r"\(\s*or\s+[A-Z]{3,4}\s+\d{4}", text, re.I):
        return [row]

    course_codes = COURSE_RE.findall(text)
    if len(course_codes) < 3:
        return [row]

    parts = re.split(r"(?=\b[A-Z]{3,4}\s+\d{4}\b)", text)
    parts = [clean_text(part) for part in parts if clean_text(part)]

    if len(parts) != len(course_codes):
        return [row]

    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))

    grouped_parts: list[str] = []
    index = 0

    while index < len(parts):
        part = parts[index]

        if (
            index + 1 < len(parts)
            and (
                re.search(r"\(?\s*OR(?:\s+CORE)?\s*$", part, re.I)
                or re.search(r"\bOR\s*$", part, re.I)
            )
        ):
            combined_part = part
            index += 1

            while index < len(parts):
                combined_part = clean_text(f"{combined_part} {parts[index]}")
                index += 1

                if not (
                    re.search(r"\(?\s*OR(?:\s+CORE)?\s*$", combined_part, re.I)
                    or re.search(r"\bOR\s*$", combined_part, re.I)
                ):
                    break

            grouped_parts.append(combined_part)
        else:
            grouped_parts.append(part)
            index += 1

    hour_values = normalize_requirement_hours(raw_hours_text, len(grouped_parts))

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
    hour_values = normalize_requirement_hours(raw_hours_text, len(course_codes) - 1)

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

    mixed_split = split_mixed_course_core_elective_row(row)
    if len(mixed_split) > 1:
        return mixed_split

    if re.search(r"\(\s*or\s+[A-Z]{3,4}\s+\d{4}", text, re.I):
        internal_or_split = split_internal_or_compressed_course_row(row)
        if len(internal_or_split) > 1:
            return internal_or_split

    if " OR " in upper:
        leading_split = split_leading_or_compressed_row(row)
        if len(leading_split) > 1:
            return leading_split

        internal_or_split = split_internal_or_compressed_course_row(row)
        if len(internal_or_split) > 1:
            return internal_or_split

        return [row]

    course_codes = COURSE_RE.findall(text)

    if len(course_codes) <= 1:
        return [row]

    parts = re.split(r"(?=\b[A-Z]{3,4}\s+\d{4}\b)", text)
    parts = [clean_text(part) for part in parts if clean_text(part)]

    if len(parts) != len(course_codes):
        return [row]

    raw_hours_text = row.get("raw_credit_hours_text", row.get("credit_hours", ""))
    hour_values = normalize_requirement_hours(raw_hours_text, len(course_codes))

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

    # Some DOCX rows first split cleanly by course code but leave a
    # standalone core bucket attached to one emitted course row:
    #   GOVT 2306 Texas Government LIFE AND PHYSICAL SCIENCES
    # Give the mixed course/core splitter one final cleanup pass.
    final_rows = []
    for split_row in split_rows:
        final_rows.extend(split_mixed_course_core_elective_row(split_row))

    # If that cleanup created more rows, realign credits from the original
    # raw hour stream instead of keeping stale pre-cleanup course hours.
    if len(final_rows) != len(split_rows):
        final_hour_values = normalize_requirement_hours(raw_hours_text, len(final_rows))
        if len(final_hour_values) == len(final_rows):
            for idx, final_row in enumerate(final_rows):
                final_row["credit_hours"] = str(final_hour_values[idx])

    return final_rows

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

        if SEMESTER_RE.match(first_cell) or SESSION_LABEL_RE.match(first_cell):
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







def split_compact_core_total_text(text: str, hour_values: list[int]) -> list[str] | None:
    """Split compact core/elective total-row text into requirement fragments."""

    working = clean_text(text)
    working = re.sub(r"\bSemester Hours\b.*$", "", working, flags=re.I).strip()
    working = re.sub(r"\bTotal Program Hours\b.*$", "", working, flags=re.I).strip()

    if not working:
        return None

    patterns = [
        r"EDUC\s+1300\s+\([^)]*CORE\s+\d{3}\)",
        r"ENGL\s+1301\s+\([^)]*CORE\s+\d{3}\)",
        r"AMERICAN\s+HISTORY\s+CORE\s+\d{3}",
        r"MATHEMATICS\s+CORE\s+\d{3}",
        r"CREATIVE\s+ARTS\s+CORE\s+\d{3}",
        r"COMMUNICATION\s+CORE\s+\d{3}",
        r"LANGUAGE,\s*PHILOSOPHY,\s+AND\s+CULTURE\s+CORE\s+\d{3}",
        r"GOVERNMENT/POLITICAL\s+SCIENCE\s+CORE\s+\d{3}",
        r"LIFE\s+AND\s+PHYSICAL\s+SCIENCES\s+CORE\s+\d{3}",
        r"SOCIAL\s+AND\s+BEHAVIORAL\s+SCIENCE\s+CORE\s+\d{3}",
        r"COMPONENT\s+AREA\s+OPTION\s+CORE\s+\d{3}",
        r"APPROVED\s+ACADEMIC\s+ELECTIVE",
    ]

    token_re = re.compile("|".join(f"({pattern})" for pattern in patterns), re.I)
    matches = list(token_re.finditer(working))

    if not matches:
        return None

    fragments = [clean_text(match.group(0)) for match in matches]

    return fragments




def repair_combined_semester_program_total_rows(totals: list[dict[str, str]]) -> list[dict[str, str]]:
    """Repair rows that combine semester and program totals.

    Shapes:
        Semester Hours Program Hours | 5 15
        ITCC ... Semester Hours Program Total Hours | 3 3 3 9 15

    In the second shape, the final two numbers are semester total and program
    total when the preceding requirement hours sum to the penultimate number.
    """

    repaired = [dict(row) for row in totals]

    for row in repaired:
        raw_total_text = clean_text(str(row.get("raw_total_text", "")))
        raw_hours_text = str(row.get("raw_hours_text", ""))

        hours = parse_hours(raw_hours_text)

        if re.fullmatch(r"Semester Hours Program Hours", raw_total_text, re.I):
            if len(hours) != 2:
                continue

            semester_total, program_total = hours
            row["semester_hours"] = str(semester_total)
            row["total_program_hours"] = str(program_total)
            continue

        if not re.search(r"\bSemester Hours\s+Program Total Hours\b", raw_total_text, re.I):
            continue

        if len(hours) < 3:
            continue

        requirement_hours = hours[:-2]
        semester_total = hours[-2]
        program_total = hours[-1]

        if not requirement_hours:
            continue

        if sum(requirement_hours) != semester_total:
            continue

        row["semester_hours"] = str(semester_total)
        row["total_program_hours"] = str(program_total)

    return repaired




def repair_compact_total_row_semester_hours(totals: list[dict[str, str]]) -> list[dict[str, str]]:
    """Fix only compact rows where semester total was misfiled as program total.

    Narrow target:
        raw_hours_text = 3 3 4 3 3 13
        semester_hours = 3
        total_program_hours = 13

    If the first N hour values, where N is the number of parsed requirement
    fragments, sum to the value stored as total_program_hours, then that value
    is the semester total, not the program total.
    """

    repaired = [dict(row) for row in totals]

    for row in repaired:
        raw_total_text = str(row.get("raw_total_text", ""))
        raw_hours_text = str(row.get("raw_hours_text", ""))

        if "Semester Hours" not in raw_total_text or "Total Program Hours" not in raw_total_text:
            continue

        parsed_hours = parse_hours(raw_hours_text)
        if len(parsed_hours) < 3:
            continue

        fragments = split_compact_core_total_text(raw_total_text, parsed_hours)
        if not fragments:
            continue

        fragment_count = len(fragments)
        if fragment_count >= len(parsed_hours):
            continue

        try:
            declared_semester_total = int(float(row.get("semester_hours", "")))
        except (TypeError, ValueError):
            continue

        try:
            declared_program_total = int(float(row.get("total_program_hours", "")))
        except (TypeError, ValueError):
            continue

        leading_requirement_hours = parsed_hours[:fragment_count]
        leading_total = sum(leading_requirement_hours)

        # Do not touch normal rows like:
        #   3 3 3 3 4 16 60
        # where semester_hours is already 16 and program total is actually 60.
        if declared_semester_total == leading_total:
            continue

        # Target only rows where the alleged program total is actually the
        # semester total for the leading requirement-hour sequence.
        if declared_program_total != leading_total:
            continue

        row["semester_hours"] = str(leading_total)
        row["total_program_hours"] = ""

    return repaired




def synthesize_requirements_from_compact_total_rows(
    requirements: list[dict[str, str]],
    totals: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Create requirement rows from compact total rows when parser emitted no rows.

    Some DOCX tables put an entire semester in one table row:
        AMERICAN HISTORY CORE 060 ... Semester Hours | 3 3 3 3 4 16

    The totals parser sees the semester total, but the requirement parser may not
    emit individual requirement rows. This repair fills only empty semester blocks.
    """

    repaired = [dict(row) for row in requirements]

    existing_keys = {
        (
            str(row.get("credential_id", "")),
            str(row.get("source_table_index", "")),
            str(row.get("semester_label", "")),
            str(row.get("catalog_year", "")),
        )
        for row in repaired
    }

    for total in totals:
        semester_label = str(total.get("semester_label", ""))
        if semester_label not in ORDINAL_SEMESTER_LABELS:
            continue

        key = (
            str(total.get("credential_id", "")),
            str(total.get("source_table_index", "")),
            semester_label,
            str(total.get("catalog_year", "")),
        )

        if key in existing_keys:
            continue

        semester_hours = total.get("semester_hours")
        if not semester_hours or str(semester_hours).lower() == "nan":
            continue

        raw_hours_text = str(total.get("raw_hours_text", ""))
        parsed_hours = parse_hours(raw_hours_text)
        if not parsed_hours:
            continue

        total_program_raw = total.get("total_program_hours", "")
        try:
            declared_semester_total = int(float(semester_hours))
        except (TypeError, ValueError):
            continue

        try:
            declared_program_total = int(float(total_program_raw)) if total_program_raw and str(total_program_raw).lower() != "nan" else None
        except (TypeError, ValueError):
            declared_program_total = None

        # Prefer the actual hour stream shape over misread total columns.
        # Compact rows sometimes show:
        #   3 3 4 3 13
        # where 13 is the semester total, even if the parser misfiled it as
        # total_program_hours because the text says "Semester Hours Total Program Hours".
        if len(parsed_hours) >= 2 and sum(parsed_hours[:-1]) == parsed_hours[-1]:
            hour_values = parsed_hours[:-1]
            semester_total = parsed_hours[-1]
        elif (
            len(parsed_hours) >= 3
            and declared_program_total is not None
            and parsed_hours[-1] == declared_program_total
            and sum(parsed_hours[:-2]) == parsed_hours[-2]
        ):
            hour_values = parsed_hours[:-2]
            semester_total = parsed_hours[-2]
        else:
            semester_total = declared_semester_total
            hour_values = list(parsed_hours)
            trailing_totals = {semester_total}
            if declared_program_total is not None:
                trailing_totals.add(declared_program_total)

            while hour_values and hour_values[-1] in trailing_totals:
                hour_values = hour_values[:-1]

        if not hour_values:
            continue

        fragments = split_compact_core_total_text(str(total.get("raw_total_text", "")), hour_values)
        if not fragments:
            continue

        if len(hour_values) != len(fragments) or sum(hour_values) != semester_total:
            # Some compact rows have one extra stray hour value before the
            # semester total, or the total columns are misread because the row
            # says both "Semester Hours" and "Total Program Hours". Choose a
            # same-order hour subset that matches the fragment count and a
            # plausible total.
            from itertools import combinations

            plausible_totals = {semester_total}
            if parsed_hours:
                plausible_totals.add(parsed_hours[-1])
            if declared_program_total is not None:
                plausible_totals.add(declared_program_total)

            fixed_hour_values = None
            fixed_semester_total = None

            for target_total in sorted(plausible_totals, reverse=True):
                for indexes in combinations(range(len(parsed_hours)), len(fragments)):
                    candidate = [parsed_hours[i] for i in indexes]
                    if sum(candidate) == target_total:
                        fixed_hour_values = candidate
                        fixed_semester_total = target_total
                        break
                if fixed_hour_values is not None:
                    break

            if fixed_hour_values is None:
                continue

            hour_values = fixed_hour_values
            semester_total = fixed_semester_total

        try:
            base_sequence = int(float(total.get("source_row_index", 0)))
        except (TypeError, ValueError):
            base_sequence = 0

        for offset, fragment in enumerate(fragments):
            new_row = {
                "catalog_year": total.get("catalog_year", ""),
                "credential_id": total.get("credential_id", ""),
                "credential_title": total.get("credential_title", ""),
                "source_table_index": total.get("source_table_index", ""),
                "source_row_index": total.get("source_row_index", ""),
                "requirement_sequence": f"{base_sequence}.{offset + 1}",
                "semester_label": semester_label,
                "raw_requirement_text": fragment,
                "credit_hours": str(hour_values[offset]),
                "raw_credit_hours_text": raw_hours_text,
                "rule_type": "ELECTIVE" if re.search(r"\bELECTIVE\b", fragment, re.I) else "CORE_BUCKET",
                "course_codes": ";".join(dict.fromkeys(COURSE_RE.findall(fragment))),
                "issue_flags": "SYNTHESIZED_FROM_COMPACT_TOTAL_ROW",
            }
            repaired.append(new_row)

        existing_keys.add(key)

    return repaired



ORDINAL_SEMESTER_LABELS = [
    "First Semester",
    "Second Semester",
    "Third Semester",
    "Fourth Semester",
    "Fifth Semester",
    "Sixth Semester",
    "Seventh Semester",
    "Eighth Semester",
]



def repair_ordinary_seaman_iii_merged_fourth_semester(
    requirements: list[dict[str, str]],
    totals: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Recover merged Ordinary Seaman III Fourth Semester requirement rows.

    In some DOCX exports, this source block:
        NAUT 2265 Practicum Marine Science/Marine Merchant Officer
        Semester Hours
        Total Program Hours
        2
        2
        42

    is exposed as:
        Fourth Semester
        Total Program Hours | 2 2 42

    The requirement text is visually present in the catalog but lost in the
    DOCX table cell extraction. This repair is intentionally narrow.
    """

    repaired = [dict(row) for row in requirements]

    existing_keys = {
        (
            str(row.get("catalog_year", "")),
            str(row.get("credential_id", "")),
            str(row.get("semester_label", "")),
            str(row.get("course_codes", "")),
        )
        for row in repaired
    }

    for total in totals:
        credential_id = str(total.get("credential_id", ""))
        semester_label = str(total.get("semester_label", ""))
        raw_total_text = clean_text(str(total.get("raw_total_text", "")))
        raw_hours_text = str(total.get("raw_hours_text", ""))

        if not credential_id.startswith("ORDINARY_SEAMAN_III_"):
            continue

        if semester_label != "Fourth Semester":
            continue

        if raw_total_text != "Total Program Hours":
            continue

        hours = parse_hours(raw_hours_text)
        if hours != [2, 2, 42]:
            continue

        key = (
            str(total.get("catalog_year", "")),
            credential_id,
            semester_label,
            "NAUT 2265",
        )
        if key in existing_keys:
            continue

        repaired.append(
            {
                "catalog_year": total.get("catalog_year", ""),
                "credential_id": credential_id,
                "credential_title": total.get("credential_title", ""),
                "source_table_index": total.get("source_table_index", ""),
                "source_row_index": total.get("source_row_index", ""),
                "requirement_sequence": str(total.get("source_row_index", "")),
                "semester_label": semester_label,
                "raw_requirement_text": "NAUT 2265 Practicum Marine Science/Marine Merchant Officer",
                "credit_hours": "2",
                "raw_credit_hours_text": raw_hours_text,
                "rule_type": "EXACT",
                "course_codes": "NAUT 2265",
                "issue_flags": "REPAIRED_MERGED_TOTAL_REQUIREMENT_ROW",
            }
        )

        existing_keys.add(key)

    return repaired




def repair_ordinary_seaman_iii_term_sequence(
    requirements: list[dict[str, str]],
    totals: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Enforce canonical Ordinary Seaman III five-term sequence.

    Canonical terms:
        First Semester
        Second Semester
        Summer Session
        Third Semester
        Fourth Semester

    Some DOCX exports collapse the Fourth Semester NAUT 2265 row into the
    final totals row:
        NAUT 2265 ...
        Semester Hours
        Total Program Hours
        2
        2
        42
    """

    repaired_requirements = [dict(row) for row in requirements]
    repaired_totals = [dict(row) for row in totals]

    # Correct term labels for known Ordinary Seaman III practicum courses.
    for row in repaired_requirements:
        credential_id = str(row.get("credential_id", ""))
        if not credential_id.startswith("ORDINARY_SEAMAN_III_"):
            continue

        text = clean_text(str(row.get("raw_requirement_text", "")))
        codes = str(row.get("course_codes", ""))

        if "NAUT 1264" in codes or "NAUT 1264" in text:
            row["semester_label"] = "Summer Session"

        if "NAUT 2265" in codes or "NAUT 2265" in text:
            row["semester_label"] = "Fourth Semester"

    existing = {
        (
            str(row.get("catalog_year", "")),
            str(row.get("credential_id", "")),
            str(row.get("semester_label", "")),
            str(row.get("course_codes", "")),
        )
        for row in repaired_requirements
    }

    for total in repaired_totals:
        credential_id = str(total.get("credential_id", ""))
        if not credential_id.startswith("ORDINARY_SEAMAN_III_"):
            continue

        if str(total.get("semester_label", "")) != "Fourth Semester":
            continue

        raw_total_text = clean_text(str(total.get("raw_total_text", "")))
        hours = parse_hours(str(total.get("raw_hours_text", "")))

        if raw_total_text != "Total Program Hours":
            continue

        if hours != [2, 2, 42]:
            continue

        # The visual source is a merged requirement + semester total + program total.
        total["raw_total_text"] = "Semester Hours Total Program Hours"
        total["semester_hours"] = "2"
        total["total_program_hours"] = "42"

        key = (
            str(total.get("catalog_year", "")),
            credential_id,
            "Fourth Semester",
            "NAUT 2265",
        )

        if key not in existing:
            repaired_requirements.append(
                {
                    "catalog_year": total.get("catalog_year", ""),
                    "credential_id": credential_id,
                    "credential_title": total.get("credential_title", ""),
                    "source_table_index": total.get("source_table_index", ""),
                    "source_row_index": total.get("source_row_index", ""),
                    "requirement_sequence": str(total.get("source_row_index", "")),
                    "semester_label": "Fourth Semester",
                    "raw_requirement_text": "NAUT 2265 Practicum Marine Science/Marine Merchant Officer",
                    "credit_hours": "2",
                    "raw_credit_hours_text": total.get("raw_hours_text", ""),
                    "rule_type": "EXACT",
                    "course_codes": "NAUT 2265",
                    "issue_flags": "REPAIRED_MERGED_TOTAL_REQUIREMENT_ROW",
                }
            )
            existing.add(key)

    return repaired_requirements, repaired_totals



def repair_repeated_semester_total_labels(
    requirements: list[dict[str, str]],
    totals: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Repair semester labels when DOCX omits a heading between semester totals.

    Example observed:
        First Semester total
        Second Semester total
        Second Semester total
        Third Semester total

    If the total rows are ordered semester blocks, relabel them by position:
        First, Second, Third, Fourth
    and relabel requirement rows according to the total row that closes each block.
    """

    repaired_requirements = [dict(row) for row in requirements]
    repaired_totals = [dict(row) for row in totals]

    totals_by_table: dict[tuple[str, str, str], list[tuple[int, dict[str, str]]]] = {}

    for total_index, row in enumerate(repaired_totals):
        semester_label = str(row.get("semester_label", ""))
        if semester_label not in ORDINAL_SEMESTER_LABELS:
            continue

        key = (
            str(row.get("credential_id", "")),
            str(row.get("source_table_index", "")),
            str(row.get("catalog_year", "")),
        )
        totals_by_table.setdefault(key, []).append((total_index, row))

    for key, indexed_totals in totals_by_table.items():
        indexed_totals.sort(key=lambda item: int(float(item[1].get("source_row_index", 0))))

        if len(indexed_totals) < 3 or len(indexed_totals) > len(ORDINAL_SEMESTER_LABELS):
            continue

        current_labels = [row.get("semester_label", "") for _, row in indexed_totals]

        # Only repair obvious repeated-label sequences.
        if len(set(current_labels)) == len(current_labels):
            continue

        if any(label not in ORDINAL_SEMESTER_LABELS for label in current_labels):
            continue

        inferred_labels = ORDINAL_SEMESTER_LABELS[:len(indexed_totals)]

        if current_labels == inferred_labels:
            continue

        boundary_rows: list[tuple[int, str]] = []

        for offset, (total_index, total_row) in enumerate(indexed_totals):
            inferred_label = inferred_labels[offset]
            total_row_index = int(float(total_row.get("source_row_index", 0)))

            repaired_totals[total_index]["semester_label"] = inferred_label

            boundary_rows.append((total_row_index, inferred_label))

        previous_boundary = -1
        credential_id, source_table_index, catalog_year = key

        for total_row_index, inferred_label in boundary_rows:
            for req in repaired_requirements:
                if str(req.get("credential_id", "")) != credential_id:
                    continue
                if str(req.get("source_table_index", "")) != source_table_index:
                    continue
                if str(req.get("catalog_year", "")) != catalog_year:
                    continue

                req_row_index = int(float(req.get("source_row_index", 0)))
                if previous_boundary < req_row_index < total_row_index:
                    req["semester_label"] = inferred_label

                    flags = [
                        flag for flag in str(req.get("issue_flags", "")).split(";")
                        if flag and flag.lower() != "nan"
                    ]
                    flags.append("REPAIRED_REPEATED_SEMESTER_TOTAL_LABEL")
                    req["issue_flags"] = ";".join(dict.fromkeys(flags))

            previous_boundary = total_row_index

    return repaired_requirements, repaired_totals




def split_simple_compressed_course_stack_row(row: dict[str, str]) -> list[dict[str, str]] | None:
    """Split compressed one-semester course stacks.

    Example:
        COSC 1301 ... OR BCIS 1305 ... ITSY 1342 ... ITSC 1325 ...

    becomes separate requirement rows, preserving OR options in one row.
    """

    text = clean_text(row.get("raw_requirement_text", ""))
    issue_flags = str(row.get("issue_flags", ""))

    if "COMPRESSED_MULTI_COURSE_ROW" not in issue_flags:
        return None

    # Let specialized criminal justice stack repair handle those rows.
    if re.search(r"\b(?:CRIJ|CJSA|CJCR)\s+\d{4}\b", text):
        return None

    raw_hours_text = (
        row.get("raw_credit_hours_text")
        or row.get("raw_hours_text")
        or row.get("credit_hours")
        or ""
    )
    parsed_hours = parse_hours(str(raw_hours_text))

    course_matches = list(COURSE_RE.finditer(text))
    if len(course_matches) < 3:
        return None

    fragments: list[str] = []
    for index, match in enumerate(course_matches):
        start = match.start()
        end = course_matches[index + 1].start() if index + 1 < len(course_matches) else len(text)
        fragment = clean_text(text[start:end])

        # DOCX can compress a rubric elective option onto the end of the
        # previous course option:
        #   CRIJ 2328 ... (Capstone Course) CRIJ/CJSA elective OR
        #   EDUC 1300 Learning Framework
        rubric_elective_match = re.search(
            r"\b((?:CRIJ|CJSA|CJCR)(?:/(?:CRIJ|CJSA|CJCR))+\s+elective\s+OR\s*)$",
            fragment,
            re.I,
        )
        if rubric_elective_match:
            prefix = clean_text(fragment[:rubric_elective_match.start()])
            suffix = clean_text(rubric_elective_match.group(1))
            if prefix:
                fragments.append(prefix)
            if suffix:
                fragments.append(suffix)
        else:
            fragments.append(fragment)

    grouped: list[str] = []
    current = ""

    for fragment in fragments:
        if not current:
            current = fragment
            continue

        should_continue = bool(re.search(r"\bOR\s*$", current, re.I))

        if should_continue:
            current = clean_text(f"{current} {fragment}")
        else:
            grouped.append(current)
            current = fragment

    if current:
        grouped.append(current)

    # A grouped criminal justice course option may still carry a trailing
    # rubric-elective option that should be its own requirement:
    #   CRIJ 2314 ... OR CRIJ 2328 ... (Capstone Course) CRIJ/CJSA elective OR EDUC 1300
    # should become:
    #   CRIJ 2314 ... OR CRIJ 2328 ...
    #   CRIJ/CJSA elective OR EDUC 1300
    regrouped: list[str] = []
    for fragment in grouped:
        tail_match = re.search(
            r"\s+((?:CRIJ|CJSA|CJCR)(?:/(?:CRIJ|CJSA|CJCR))+\s+elective\s+OR\s+.+)$",
            fragment,
            re.I,
        )
        if tail_match:
            prefix = clean_text(fragment[:tail_match.start()])
            suffix = clean_text(tail_match.group(1))
            if prefix:
                regrouped.append(prefix)
            if suffix:
                regrouped.append(suffix)
        else:
            regrouped.append(fragment)

    grouped = regrouped

    if len(grouped) < 2:
        return None

    if len(parsed_hours) < len(grouped):
        return None

    hour_values = parsed_hours[:len(grouped)]
    if len(hour_values) != len(grouped):
        return None

    base_sequence_raw = row.get("requirement_sequence", 0)
    try:
        base_sequence = int(float(base_sequence_raw))
    except (TypeError, ValueError):
        base_sequence = 0

    out: list[dict[str, str]] = []

    for offset, fragment in enumerate(grouped):
        new_row = dict(row)
        new_row["requirement_sequence"] = f"{base_sequence}.{offset + 1}"
        new_row["raw_requirement_text"] = fragment
        new_row["credit_hours"] = str(hour_values[offset])
        new_row["course_codes"] = ";".join(dict.fromkeys(COURSE_RE.findall(fragment)))
        new_row["rule_type"] = "ANY_N" if re.search(r"\bOR\b", fragment, re.I) else parse_rule_type(fragment)

        flags = [
            flag for flag in str(new_row.get("issue_flags", "")).split(";")
            if flag and flag.lower() != "nan"
        ]
        flags.append("SPLIT_SIMPLE_COMPRESSED_COURSE_STACK")
        new_row["issue_flags"] = ";".join(dict.fromkeys(flags))

        out.append(new_row)

    return out


def repair_simple_compressed_course_stack_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    repaired: list[dict[str, str]] = []

    for row in rows:
        split_rows = split_simple_compressed_course_stack_row(row)
        if split_rows:
            repaired.extend(split_rows)
        else:
            repaired.append(row)

    return repaired



def repair_adjacent_elective_option_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge option rows split from their trailing Elective token.

    Examples:
        EDUC 1300 (...) or Approved
        Elective

        ITDF 1300 ... OR *CRIJ/CJSA/CJCR
        elective
    """

    repaired: list[dict[str, str]] = []
    index = 0

    while index < len(rows):
        current = dict(rows[index])
        next_row = dict(rows[index + 1]) if index + 1 < len(rows) else None

        current_text = clean_text(current.get("raw_requirement_text", ""))
        next_text = clean_text(next_row.get("raw_requirement_text", "")) if next_row else ""

        same_requirement_group = (
            next_row is not None
            and current.get("credential_id") == next_row.get("credential_id")
            and current.get("source_table_index") == next_row.get("source_table_index")
            and current.get("semester_label") == next_row.get("semester_label")
        )

        should_merge = (
            same_requirement_group
            and re.fullmatch(r"elective", next_text, re.I)
            and (
                re.search(r"\bor\s+approved\s*$", current_text, re.I)
                or re.search(r"\bor\s+academic\s*$", current_text, re.I)
                or re.search(r"\bOR\s+\*[A-Z]{3,4}(?:/[A-Z]{3,4})+\s*$", current_text, re.I)
            )
        )

        if should_merge:
            merged_text = clean_text(f"{current_text} {next_text}")

            current["raw_requirement_text"] = merged_text
            current["course_codes"] = ";".join(dict.fromkeys(COURSE_RE.findall(merged_text)))
            current["rule_type"] = "ANY_N"

            flags = [
                flag for flag in str(current.get("issue_flags", "")).split(";")
                if flag and flag.lower() != "nan"
            ]
            flags.append("MERGED_ADJACENT_ELECTIVE_OPTION")
            current["issue_flags"] = ";".join(dict.fromkeys(flags))

            repaired.append(current)
            index += 2
        else:
            repaired.append(current)
            index += 1

    return repaired



def split_compressed_criminal_justice_stack_row(row: dict[str, str]) -> list[dict[str, str]] | None:
    """Split compressed CJ course stacks with parenthetical/equivalent options.

    Handles rows like:
        CRIJ 1301 (or CJSA 1322) ... OR *CJCR 1374 ...
        CRIJ 1306 (or CJSA 1313) ...
    """

    text = clean_text(row.get("raw_requirement_text", ""))
    issue_flags = str(row.get("issue_flags", ""))

    if "COMPRESSED_MULTI_COURSE_ROW" not in issue_flags:
        return None

    if not re.search(r"\b(?:CRIJ|CJSA|CJCR)\s+\d{4}\b", text):
        return None

    raw_hours_text = (
        row.get("raw_credit_hours_text")
        or row.get("raw_hours_text")
        or row.get("credit_hours")
        or ""
    )
    parsed_hours = parse_hours(str(raw_hours_text))

    course_matches = list(COURSE_RE.finditer(text))
    if len(course_matches) < 2:
        return None

    fragments: list[str] = []
    for index, match in enumerate(course_matches):
        start = match.start()
        end = course_matches[index + 1].start() if index + 1 < len(course_matches) else len(text)
        fragments.append(clean_text(text[start:end]))

    grouped: list[str] = []
    current = ""

    for fragment in fragments:
        if not current:
            current = fragment
            continue

        should_continue = (
            re.search(r"\(\s*or\s*\*?\s*$", current, re.I)
            or re.search(r"\bOR\s+\*\s*$", current, re.I)
            or re.search(r"\bAND\s+\*\s*$", current, re.I)
            or re.search(r"\bOR\s*$", current, re.I)
        )

        if should_continue:
            current = clean_text(f"{current} {fragment}")
        else:
            grouped.append(current)
            current = fragment

    if current:
        grouped.append(current)

    regrouped: list[str] = []
    for fragment in grouped:
        tail_match = re.search(
            r"\s+((?:CRIJ|CJSA|CJCR)(?:/(?:CRIJ|CJSA|CJCR))+\s+elective\s+OR\s+.+)$",
            fragment,
            re.I,
        )
        if tail_match:
            prefix = clean_text(fragment[:tail_match.start()])
            suffix = clean_text(tail_match.group(1))
            if prefix:
                regrouped.append(prefix)
            if suffix:
                regrouped.append(suffix)
        else:
            regrouped.append(fragment)

    grouped = regrouped

    if len(grouped) < 2:
        return None

    if len(parsed_hours) < len(grouped):
        return None

    hour_values = parsed_hours[:len(grouped)]

    # Avoid taking semester/program totals as requirement hours.
    if len(hour_values) != len(grouped):
        return None

    base_sequence_raw = row.get("requirement_sequence", 0)
    try:
        base_sequence = int(float(base_sequence_raw))
    except (TypeError, ValueError):
        base_sequence = 0

    out: list[dict[str, str]] = []

    for offset, fragment in enumerate(grouped):
        new_row = dict(row)
        new_row["requirement_sequence"] = f"{base_sequence}.{offset + 1}"
        new_row["raw_requirement_text"] = fragment
        new_row["credit_hours"] = str(hour_values[offset])
        new_row["course_codes"] = ";".join(dict.fromkeys(COURSE_RE.findall(fragment)))

        if (
            re.search(r"\(\s*or\s*\*?\s*[A-Z]{3,4}\s+\d{4}\)", fragment, re.I)
            or re.search(r"\bOR\s+\*", fragment, re.I)
        ):
            new_row["rule_type"] = "ANY_N"
        elif re.search(r"\bAND\s+\*", fragment, re.I):
            new_row["rule_type"] = "ANY_N"
        else:
            new_row["rule_type"] = parse_rule_type(fragment)

        flags = [
            flag for flag in str(new_row.get("issue_flags", "")).split(";")
            if flag and flag.lower() != "nan"
        ]
        flags.append("SPLIT_COMPRESSED_CRIMINAL_JUSTICE_STACK")
        new_row["issue_flags"] = ";".join(dict.fromkeys(flags))

        out.append(new_row)

    return out


def repair_compressed_criminal_justice_stack_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    repaired: list[dict[str, str]] = []

    for row in rows:
        split_rows = split_compressed_criminal_justice_stack_row(row)
        if split_rows:
            repaired.extend(split_rows)
        else:
            repaired.append(row)

    return repaired



def repair_parenthetical_or_split_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Repair DOCX rows split across parenthetical OR course equivalents.

    Example:
        CJSA 1327 (or
        CRIJ 1310) Fundamentals of Criminal Law

    becomes:
        CJSA 1327 (or CRIJ 1310) Fundamentals of Criminal Law
    """

    repaired: list[dict[str, str]] = []
    index = 0

    while index < len(rows):
        current = dict(rows[index])
        next_row = dict(rows[index + 1]) if index + 1 < len(rows) else None

        current_text = clean_text(current.get("raw_requirement_text", ""))
        next_text = clean_text(next_row.get("raw_requirement_text", "")) if next_row else ""

        same_requirement_group = (
            next_row is not None
            and current.get("credential_id") == next_row.get("credential_id")
            and current.get("source_table_index") == next_row.get("source_table_index")
            and current.get("semester_label") == next_row.get("semester_label")
        )

        split_parenthetical_or = (
            same_requirement_group
            and re.search(r"\(\s*or\s*$", current_text, re.I)
            and re.match(r"[A-Z]{3,4}\s+\d{4}\)", next_text)
        )

        if split_parenthetical_or:
            merged_text = clean_text(f"{current_text} {next_text}")
            current["raw_requirement_text"] = merged_text
            current["course_codes"] = ";".join(dict.fromkeys(COURSE_RE.findall(merged_text)))
            current["rule_type"] = "ANY_N" if re.search(r"\(\s*or\s+[A-Z]{3,4}\s+\d{4}\)", merged_text, re.I) else parse_rule_type(merged_text)

            flags = [
                flag for flag in str(current.get("issue_flags", "")).split(";")
                if flag and flag.lower() != "nan"
            ]
            flags.append("REPAIRED_PARENTHETICAL_OR_SPLIT")
            current["issue_flags"] = ";".join(dict.fromkeys(flags))

            repaired.append(current)
            index += 2
        else:
            repaired.append(current)
            index += 1

    # If a repair removed a row from a semester group, realign row-level hours
    # from the original raw hour stream so semester/program totals are not
    # assigned as requirement hours.
    by_group: dict[tuple[str, str, str], list[int]] = {}
    for row_index, row in enumerate(repaired):
        key = (
            str(row.get("credential_id", "")),
            str(row.get("source_table_index", "")),
            str(row.get("semester_label", "")),
        )
        by_group.setdefault(key, []).append(row_index)

    for indexes in by_group.values():
        if not indexes:
            continue

        raw_hours_text = ""
        for row_index in indexes:
            candidate = (
                repaired[row_index].get("raw_credit_hours_text")
                or repaired[row_index].get("raw_hours_text")
                or ""
            )
            if len(parse_hours(str(candidate))) > len(parse_hours(str(raw_hours_text))):
                raw_hours_text = str(candidate)

        parsed_hours = parse_hours(raw_hours_text)

        # Only realign when the group carries a multi-hour stream that also
        # includes semester/program totals after the row-level requirement hours.
        if len(parsed_hours) <= len(indexes):
            continue

        hour_values = parsed_hours[:len(indexes)]

        if len(hour_values) != len(indexes):
            continue

        for offset, row_index in enumerate(indexes):
            repaired[row_index]["credit_hours"] = str(hour_values[offset])

    return repaired



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

    # Disambiguate duplicate credential titles within the same catalog year.
    #
    # Example confirmed from the 2025-2026 catalog:
    #   Graphic Design Certificate of Completion, 24 SCH
    #   Graphic Design Associate of Applied Science, 60 SCH
    #
    # The DOCX heading/table extraction gives both the same title base
    # ("Graphic Design"), so title-only credential IDs collide. For duplicate
    # titles, infer an award suffix from the table's Total Program Hours.
    table_total_hours: dict[str, int] = {}
    for row in all_totals:
        total = row.get("total_program_hours", "")
        if total:
            try:
                table_total_hours[row["source_table_index"]] = int(float(total))
            except ValueError:
                pass

    title_counts: dict[str, int] = {}
    for row in table_map_rows:
        title_counts[row["credential_title"]] = title_counts.get(row["credential_title"], 0) + 1

    duplicate_titles = {title for title, count in title_counts.items() if count > 1}

    if duplicate_titles:
        table_suffixes: dict[str, str] = {}

        for row in table_map_rows:
            if row["credential_title"] not in duplicate_titles:
                continue

            table_index_value = row["source_table_index"]
            total_hours = table_total_hours.get(table_index_value)

            if total_hours is None:
                suffix = f'T{int(table_index_value):03d}'
            elif total_hours >= 60:
                suffix = "AAS"
            else:
                suffix = "CERTIFICATE_OF_COMPLETION"

            table_suffixes[table_index_value] = suffix

        # If a duplicate title has multiple tables with the same inferred suffix,
        # preserve uniqueness by falling back to source-table suffixes for that title.
        title_suffix_counts: dict[tuple[str, str], int] = {}
        for row in table_map_rows:
            if row["credential_title"] not in duplicate_titles:
                continue

            suffix = table_suffixes.get(row["source_table_index"], f'T{int(row["source_table_index"]):03d}')
            key = (row["credential_title"], suffix)
            title_suffix_counts[key] = title_suffix_counts.get(key, 0) + 1

        for row_group in (all_requirements, all_totals, table_map_rows):
            for row in row_group:
                if row["credential_title"] not in duplicate_titles:
                    continue

                table_index_value = row["source_table_index"]
                suffix = table_suffixes.get(table_index_value, f'T{int(table_index_value):03d}')

                if title_suffix_counts.get((row["credential_title"], suffix), 0) > 1:
                    suffix = f'T{int(table_index_value):03d}'

                base_id = f'{slugify(row["credential_title"])}_{suffix}_{record.catalog_year[:4]}'
                row["credential_id"] = base_id


    all_requirements = repair_compressed_criminal_justice_stack_rows(all_requirements)
    all_requirements = repair_simple_compressed_course_stack_rows(all_requirements)
    all_requirements = repair_parenthetical_or_split_rows(all_requirements)
    all_requirements = repair_adjacent_elective_option_rows(all_requirements)
    all_requirements, all_totals = repair_repeated_semester_total_labels(all_requirements, all_totals)
    all_requirements, all_totals = repair_ordinary_seaman_iii_term_sequence(all_requirements, all_totals)
    all_totals = repair_combined_semester_program_total_rows(all_totals)
    all_totals = repair_compact_total_row_semester_hours(all_totals)
    all_requirements = synthesize_requirements_from_compact_total_rows(all_requirements, all_totals)

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













