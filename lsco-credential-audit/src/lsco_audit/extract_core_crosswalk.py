import re

import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


PAGES_CSV = INTERIM_DIR / "catalog_pages.csv"
OUTPUT_CSV = PROCESSED_DIR / "core_crosswalk.csv"

CORE_PAGE_MIN = 119
CORE_PAGE_MAX = 123

COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\s+\d{4}\b")

BUCKET_HEADINGS = {
    "COMMUNICATION": "COMMUNICATION_CORE",
    "MATHEMATICS": "MATHEMATICS_CORE",
    "LIFE AND PHYSICAL SCIENCES": "LIFE_AND_PHYSICAL_SCIENCES_CORE",
    "LANGUAGE, PHILOSOPHY AND CULTURE": "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",
    "LANGUAGE, PHILOSOPHY, AND CULTURE": "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",
    "CREATIVE ARTS": "CREATIVE_ARTS_CORE",
    "AMERICAN HISTORY": "AMERICAN_HISTORY_CORE",
    "GOVERNMENT/POLITICAL SCIENCE": "GOVERNMENT_POLITICAL_SCIENCE_CORE",
    "SOCIAL AND BEHAVIORAL SCIENCES": "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE",
    "SOCIAL AND BEHAVIORAL SCIENCE": "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE",
    "COMPONENT AREA OPTION": "COMPONENT_AREA_OPTION_CORE",
}


def find_bucket(line: str) -> str | None:
    upper = line.upper()

    for heading, bucket_name in BUCKET_HEADINGS.items():
        if heading in upper:
            return bucket_name

    return None


def extract_course_codes(line: str) -> list[str]:
    return COURSE_PATTERN.findall(line)


def extract_core_crosswalk() -> None:
    pages = pd.read_csv(PAGES_CSV)

    core_pages = pages[
        (pages["page_number"] >= CORE_PAGE_MIN)
        & (pages["page_number"] <= CORE_PAGE_MAX)
    ]

    rows = []
    current_bucket = None

    for _, page in core_pages.iterrows():
        page_number = int(page["page_number"])
        lines = str(page["text"]).splitlines()

        for line_number, line in enumerate(lines, start=1):
            bucket = find_bucket(line)

            if bucket:
                current_bucket = bucket

            course_codes = extract_course_codes(line)

            for course_code in course_codes:
                if current_bucket is None:
                    continue

                rows.append(
                    {
                        "bucket_name": current_bucket,
                        "course_code": course_code,
                        "source_page": page_number,
                        "source_line": line_number,
                    }
                )

    crosswalk = pd.DataFrame(rows).drop_duplicates(
        subset=["bucket_name", "course_code"]
    )

    crosswalk.to_csv(OUTPUT_CSV, index=False)

    print(f"Extracted {len(crosswalk)} core crosswalk rows")
    print(f"Wrote {OUTPUT_CSV}")
    print(crosswalk.groupby("bucket_name").size())


if __name__ == "__main__":
    extract_core_crosswalk()