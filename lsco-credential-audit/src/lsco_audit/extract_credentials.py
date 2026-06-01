import re

import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


INPUT_CSV = INTERIM_DIR / "catalog_pages.csv"
OUTPUT_CSV = PROCESSED_DIR / "credentials.csv"
ISSUES_CSV = PROCESSED_DIR / "credential_extraction_issues.csv"

AWARD_TYPES = [
    "Associate of Applied Science Degree",
    "Associate of Arts Degree",
    "Associate of Science Degree",
    "Certificate of Completion",
    "Institutional Award",
]


def clean_line(line: str) -> str:
    return line.strip().replace("  ", " ")


def extract_total_hours(text: str) -> int | None:
    match = re.search(r"Total Program Hours\s+(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def extract_credential_from_page(page_number: int, text: str) -> dict | None:
    lines = [clean_line(line) for line in str(text).splitlines()]
    lines = [line for line in lines if line]

    for idx, line in enumerate(lines):
        if line in AWARD_TYPES:
            credential_name = lines[idx - 1] if idx > 0 else None

            return {
                "credential_id": None,
                "credential_name": credential_name,
                "award_type": line,
                "pathway": None,
                "total_hours": extract_total_hours(text),
                "catalog_year": "2025-2026",
                "source_page": page_number,
            }

    return None


def make_credential_id(row: pd.Series) -> str:
    name = str(row["credential_name"]).upper()
    award = str(row["award_type"]).upper()

    name_part = re.sub(r"[^A-Z0-9]+", "_", name).strip("_")

    if "APPLIED SCIENCE" in award:
        award_part = "AAS"
    elif "ARTS DEGREE" in award:
        award_part = "AA"
    elif "SCIENCE DEGREE" in award:
        award_part = "AS"
    elif "CERTIFICATE" in award:
        award_part = "CERT"
    elif "INSTITUTIONAL" in award:
        award_part = "IA"
    else:
        award_part = "AWARD"

    return f"{name_part}_{award_part}_2025"


def flag_issue(row: pd.Series) -> str | None:
    name = str(row["credential_name"])

    if pd.isna(row["total_hours"]):
        return "missing_total_hours"

    if "(" in name or ")" in name:
        return "suspect_parenthetical_name"

    if "offered" in name.lower():
        return "suspect_offered_note_as_name"

    if len(name.strip()) < 3:
        return "suspect_short_name"

    return None


def extract_credentials() -> None:
    pages = pd.read_csv(INPUT_CSV)

    rows = []

    credential_pages = pages[
        (pages["page_number"] >= 129) & (pages["page_number"] <= 270)
    ]

    for _, row in credential_pages.iterrows():
        result = extract_credential_from_page(
            page_number=int(row["page_number"]),
            text=row["text"],
        )

        if result:
            rows.append(result)

    credentials = pd.DataFrame(rows)

    if not credentials.empty:
        credentials["credential_id"] = credentials.apply(make_credential_id, axis=1)
        credentials["extraction_issue"] = credentials.apply(flag_issue, axis=1)

    issues = credentials[credentials["extraction_issue"].notna()].copy()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    credentials.to_csv(OUTPUT_CSV, index=False)
    issues.to_csv(ISSUES_CSV, index=False)

    print(f"Extracted {len(credentials)} credentials")
    print(f"Flagged {len(issues)} issues")
    print(f"Wrote {OUTPUT_CSV}")
    print(f"Wrote {ISSUES_CSV}")
    print(issues[["credential_name", "award_type", "total_hours", "source_page", "extraction_issue"]])


if __name__ == "__main__":
    extract_credentials()