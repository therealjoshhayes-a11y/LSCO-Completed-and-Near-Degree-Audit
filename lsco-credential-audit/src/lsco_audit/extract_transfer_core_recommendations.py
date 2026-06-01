import re

import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


PAGES_CSV = INTERIM_DIR / "catalog_pages.csv"
CREDENTIALS_CSV = PROCESSED_DIR / "credentials.csv"
OUTPUT_CSV = PROCESSED_DIR / "transfer_core_recommendations.csv"

COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\s+\d{4}\b")

BUCKET_LABELS = {
    "Communication": "COMMUNICATION_CORE",
    "Mathematics": "MATHEMATICS_CORE",
    "Life and Physical Sciences": "LIFE_AND_PHYSICAL_SCIENCES_CORE",
    "Language, Philosophy, and Culture": "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",
    "Creative Arts": "CREATIVE_ARTS_CORE",
    "American History": "AMERICAN_HISTORY_CORE",
    "Government/Political Science": "GOVERNMENT_POLITICAL_SCIENCE_CORE",
    "Social and Behavioral Science": "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE",
    "Component Area Option": "COMPONENT_AREA_OPTION_CORE",
}


def identify_bucket(line: str) -> str | None:
    for label, bucket_name in BUCKET_LABELS.items():
        if line.startswith(label):
            return bucket_name
    return None


def extract_courses(line: str) -> list[str]:
    return COURSE_PATTERN.findall(line)


def extract_transfer_core_recommendations() -> None:
    pages = pd.read_csv(PAGES_CSV)
    credentials = pd.read_csv(CREDENTIALS_CSV)

    transfer_credentials = credentials[
        credentials["award_type"].isin(
            [
                "Associate of Arts Degree",
                "Associate of Science Degree",
            ]
        )
    ].copy()

    rows = []

    for _, credential in transfer_credentials.iterrows():
        credential_id = credential["credential_id"]
        source_page = int(credential["source_page"])

        page_text = pages.loc[
            pages["page_number"] == source_page,
            "text",
        ].iloc[0]

        lines = str(page_text).splitlines()

        in_recommendations = False

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            if "Suggested Core Classes for this Degree" in line:
                in_recommendations = True
                continue

            if not in_recommendations:
                continue

            if "See core curriculum" in line:
                break

            bucket_name = identify_bucket(line)

            if bucket_name is None:
                continue

            course_codes = extract_courses(line)

            for course_code in course_codes:
                rows.append(
                    {
                        "credential_id": credential_id,
                        "bucket_name": bucket_name,
                        "course_code": course_code,
                        "source_page": source_page,
                        "source_line": line_number,
                    }
                )

    recommendations = pd.DataFrame(rows).drop_duplicates()

    recommendations.to_csv(OUTPUT_CSV, index=False)

    print(f"Extracted {len(recommendations)} transfer core recommendation rows")
    print(f"Covered {recommendations['credential_id'].nunique()} credentials")
    print(f"Wrote {OUTPUT_CSV}")
    print(recommendations.groupby("bucket_name").size())


if __name__ == "__main__":
    extract_transfer_core_recommendations()