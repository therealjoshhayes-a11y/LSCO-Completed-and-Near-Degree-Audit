import re

import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


PAGES_CSV = INTERIM_DIR / "catalog_pages.csv"
CREDENTIALS_CSV = PROCESSED_DIR / "credentials.csv"
OUTPUT_CSV = PROCESSED_DIR / "requirements_pattern_c.csv"

COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\s+\d{4}\b")


def is_stop_line(line: str) -> bool:
    return "Total Program Hours" in line


def is_ignored_line(line: str) -> bool:
    ignored = [
        "Semester Hours",
        "Credit",
        "Hours",
        "First Semester",
        "Second Semester",
        "Third Semester",
        "Fourth Semester",
    ]
    return any(x.lower() in line.lower() for x in ignored)


def extract_course_code(line: str) -> str | None:
    match = COURSE_PATTERN.search(line)
    return match.group(0) if match else None


def is_core_line(line: str) -> bool:
    return "CORE" in line.upper()


def is_elective_line(line: str) -> bool:
    return "ELECTIVE" in line.upper()


def clean_option(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^OR\s+", "", line, flags=re.IGNORECASE)
    line = re.sub(r"\.{2,}.*$", "", line)
    line = re.sub(r"\s+\d+$", "", line)
    return line.strip()


def make_requirement_id(credential_id: str, sequence: int) -> str:
    return f"{credential_id}_R{sequence:03}"


def get_option(line: str) -> tuple[str, str] | None:
    course_code = extract_course_code(line)

    if course_code:
        return course_code, "COURSE"

    if is_core_line(line):
        return clean_option(line), "CORE_BUCKET"

    if is_elective_line(line):
        return clean_option(line), "ELECTIVE"

    return None


def extract_requirements() -> None:
    pages = pd.read_csv(PAGES_CSV)
    credentials = pd.read_csv(CREDENTIALS_CSV)

    candidates = credentials[
        credentials["award_type"].isin(
            [
                "Associate of Arts Degree",
                "Associate of Science Degree",
            ]
        )
        & credentials["total_hours"].notna()
    ].copy()

    rows = []

    for _, credential in candidates.iterrows():
        credential_id = credential["credential_id"]
        source_page = int(credential["source_page"])

        page_text = pages.loc[
            pages["page_number"] == source_page,
            "text",
        ].iloc[0]

        lines = str(page_text).splitlines()
        sequence = 1
        pending_requirement = None

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            if is_stop_line(line):
                break

            if not line or is_ignored_line(line):
                continue

            option = get_option(line)

            if option is None:
                continue

            is_or_line = line.upper().startswith("OR ")

            if is_or_line and pending_requirement is not None:
                option_value, option_type = option

                rows.append(
                    {
                        "requirement_id": pending_requirement["requirement_id"],
                        "credential_id": credential_id,
                        "sequence": pending_requirement["sequence"],
                        "rule_type": "ANY_N",
                        "min_required": 1,
                        "group_name": pending_requirement["group_name"],
                        "option_value": option_value,
                        "option_type": option_type,
                        "source_page": source_page,
                        "source_line": line_number,
                    }
                )

                continue

            option_value, option_type = option
            requirement_id = make_requirement_id(credential_id, sequence)

            if option_type == "COURSE":
                group_name = "Required Course"
                rule_type = "EXACT"
            elif option_type == "CORE_BUCKET":
                group_name = option_value
                rule_type = "ANY_N"
            else:
                group_name = option_value
                rule_type = "ANY_N"

            rows.append(
                {
                    "requirement_id": requirement_id,
                    "credential_id": credential_id,
                    "sequence": sequence,
                    "rule_type": rule_type,
                    "min_required": 1,
                    "group_name": group_name,
                    "option_value": option_value,
                    "option_type": option_type,
                    "source_page": source_page,
                    "source_line": line_number,
                }
            )

            pending_requirement = {
                "requirement_id": requirement_id,
                "sequence": sequence,
                "group_name": group_name,
            }

            sequence += 1

    requirements = pd.DataFrame(rows)

    any_n_ids = requirements.loc[
        requirements.duplicated("requirement_id", keep=False),
        "requirement_id",
    ].unique()

    requirements.loc[
        requirements["requirement_id"].isin(any_n_ids),
        "rule_type",
    ] = "ANY_N"

    requirements.to_csv(OUTPUT_CSV, index=False)

    print(f"Extracted {len(requirements)} Pattern C requirement options")
    print(f"Covered {requirements['credential_id'].nunique()} credentials")
    print(f"Wrote {OUTPUT_CSV}")
    print(requirements.head(60))


if __name__ == "__main__":
    extract_requirements()