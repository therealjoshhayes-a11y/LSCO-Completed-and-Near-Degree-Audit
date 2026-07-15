import re

import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


PAGES_CSV = INTERIM_DIR / "catalog_pages.csv"
OUTPUT_CSV = PROCESSED_DIR / "core_crosswalk.csv"

# The actual 2025-2026 course lists begin on page 122.
# Page 123 continues the Component Area Option table.
CORE_PAGE_MIN = 122
CORE_PAGE_MAX = 123

COURSE_PATTERN = re.compile(
    r"\b([A-Z]{4})\s+(\d{4})\b"
)

HEADING_PATTERN = re.compile(
    r"^(?:\d+\s+HOURS?\s+)?"
    r"("
    r"COMMUNICATION"
    r"|MATHEMATICS"
    r"|LIFE AND PHYSICAL SCIENCES"
    r"|LANGUAGE,\s*PHILOSOPHY,\s*AND CULTURE"
    r"|LANGUAGE,\s*PHILOSOPHY AND CULTURE"
    r"|CREATIVE ARTS"
    r"|AMERICAN HISTORY"
    r"|GOVERNMENT/POLITICAL SCIENCE"
    r"|SOCIAL AND BEHAVIORAL SCIENCES?"
    r"|COMPONENT AREA OPTION"
    r")$",
    flags=re.IGNORECASE,
)

BUCKET_HEADINGS = {
    "COMMUNICATION":
        "COMMUNICATION_CORE",

    "MATHEMATICS":
        "MATHEMATICS_CORE",

    "LIFE AND PHYSICAL SCIENCES":
        "LIFE_AND_PHYSICAL_SCIENCES_CORE",

    "LANGUAGE, PHILOSOPHY AND CULTURE":
        "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",

    "LANGUAGE, PHILOSOPHY, AND CULTURE":
        "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",

    "CREATIVE ARTS":
        "CREATIVE_ARTS_CORE",

    "AMERICAN HISTORY":
        "AMERICAN_HISTORY_CORE",

    "GOVERNMENT/POLITICAL SCIENCE":
        "GOVERNMENT_POLITICAL_SCIENCE_CORE",

    "SOCIAL AND BEHAVIORAL SCIENCE":
        "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE",

    "SOCIAL AND BEHAVIORAL SCIENCES":
        "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE",

    "COMPONENT AREA OPTION":
        "COMPONENT_AREA_OPTION_CORE",
}


def normalize_line(value: str) -> str:
    return " ".join(
        str(value).strip().split()
    )


def find_bucket(line: str) -> str | None:
    """
    Recognize only a complete component heading.

    Course titles such as 'Contemporary Mathematics' or
    'Introduction to Mass Communication' must never change the
    active parser bucket.
    """
    normalized = normalize_line(line)

    match = HEADING_PATTERN.fullmatch(
        normalized
    )

    if not match:
        return None

    heading = normalize_line(
        match.group(1)
    ).upper()

    return BUCKET_HEADINGS.get(
        heading
    )


def extract_course_codes(
    line: str,
) -> list[str]:
    return [
        f"{rubric} {number}"
        for rubric, number
        in COURSE_PATTERN.findall(
            str(line).upper()
        )
    ]


def extract_core_crosswalk() -> None:
    pages = pd.read_csv(
        PAGES_CSV,
        dtype=str,
        low_memory=False,
    ).fillna("")

    pages["page_number"] = pd.to_numeric(
        pages["page_number"],
        errors="coerce",
    )

    core_pages = pages[
        pages["page_number"].between(
            CORE_PAGE_MIN,
            CORE_PAGE_MAX,
        )
    ].copy()

    if core_pages.empty:
        raise ValueError(
            "No catalog pages found in the configured "
            f"range {CORE_PAGE_MIN}-{CORE_PAGE_MAX}."
        )

    rows = []
    current_bucket = None

    for _, page in core_pages.sort_values(
        "page_number"
    ).iterrows():
        page_number = int(
            page["page_number"]
        )

        lines = str(
            page["text"]
        ).splitlines()

        for line_number, line in enumerate(
            lines,
            start=1,
        ):
            normalized = normalize_line(
                line
            )

            # The note ends the Component Area Option table.
            if normalized.upper().startswith(
                "NOTE:"
            ):
                current_bucket = None
                continue

            bucket = find_bucket(
                normalized
            )

            if bucket is not None:
                current_bucket = bucket
                continue

            if current_bucket is None:
                continue

            for course_code in extract_course_codes(
                normalized
            ):
                rows.append(
                    {
                        "bucket_name":
                            current_bucket,
                        "course_code":
                            course_code,
                        "source_page":
                            page_number,
                        "source_line":
                            line_number,
                        "source_text":
                            normalized,
                    }
                )

    crosswalk = pd.DataFrame(
        rows
    )

    if crosswalk.empty:
        raise ValueError(
            "No core-course rows were extracted."
        )

    crosswalk = (
        crosswalk
        .drop_duplicates(
            subset=[
                "bucket_name",
                "course_code",
            ],
            keep="first",
        )
        .sort_values(
            [
                "bucket_name",
                "course_code",
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    crosswalk.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    print(
        f"Extracted {len(crosswalk)} "
        "core crosswalk rows"
    )

    print(
        f"Wrote {OUTPUT_CSV}"
    )

    print()

    print(
        crosswalk.groupby(
            "bucket_name"
        ).size().to_string()
    )


if __name__ == "__main__":
    extract_core_crosswalk()
