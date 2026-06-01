import re

import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


PAGES_CSV = INTERIM_DIR / "catalog_pages.csv"
CREDENTIALS_CSV = PROCESSED_DIR / "credentials.csv"
OUTPUT_CSV = PROCESSED_DIR / "requirements_pattern_a.csv"

COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\s+\d{4}\b")


def is_ignored_line(line: str) -> bool:
    ignored_phrases = [
        "Semester Hours",
        "Total Program Hours",
        "Credit",
        "Hours",
        "First Semester",
        "Second Semester",
        "Third Semester",
        "Fourth Semester",
    ]

    return any(phrase.lower() in line.lower() for phrase in ignored_phrases)


def extract_course_code(line: str) -> str | None:
    match = COURSE_PATTERN.search(line)
    if match:
        return match.group(0)
    return None


def page_has_complex_logic(text: str) -> bool:
    upper_text = str(text).upper()

    complex_markers = [
        " OR ",
        "CORE",
        "ELECTIVE",
    ]

    return any(marker in upper_text for marker in complex_markers)


def extract_requirements() -> None:
    pages = pd.read_csv(PAGES_CSV)
    credentials = pd.read_csv(CREDENTIALS_CSV)

    candidates = credentials[
        credentials["award_type"].eq("Certificate of Completion")
        & credentials["total_hours"].notna()
    ].copy()

    rows = []

    for _, credential in candidates.iterrows():
        source_page = int(credential["source_page"])
        credential_id = credential["credential_id"]

        page_text = pages.loc[
            pages["page_number"] == source_page,
            "text",
        ].iloc[0]

        if page_has_complex_logic(page_text):
            continue

        sequence = 1

        for line_number, line in enumerate(str(page_text).splitlines(), start=1):
            if is_ignored_line(line):
                continue

            course_code = extract_course_code(line)

            if not course_code:
                continue

            requirement_id = f"{credential_id}_R{sequence:03}"

            rows.append(
                {
                    "requirement_id": requirement_id,
                    "credential_id": credential_id,
                    "sequence": sequence,
                    "rule_type": "EXACT",
                    "min_required": 1,
                    "group_name": "Required Course",
                    "option_value": course_code,
                    "option_type": "COURSE",
                    "source_page": source_page,
                    "source_line": line_number,
                }
            )

            sequence += 1

    requirements = pd.DataFrame(rows)
    requirements.to_csv(OUTPUT_CSV, index=False)

    print(f"Extracted {len(requirements)} Pattern A requirements")
    print(f"Wrote {OUTPUT_CSV}")
    print(requirements.head(30))


if __name__ == "__main__":
    extract_requirements()