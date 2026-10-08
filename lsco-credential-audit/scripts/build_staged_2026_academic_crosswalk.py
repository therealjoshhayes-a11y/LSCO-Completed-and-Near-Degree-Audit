from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
from docx import Document


CATALOG_YEAR = "2026-2027"

SOURCE_DOCX = Path(
    "data/raw/catalogs/2026-2027/"
    "2026-2027_Catalog.docx"
)

BASELINE = Path(
    "config/"
    "catalog_academic_course_crosswalk_final.csv"
)

OUTPUT = Path(
    "data/processed/catalogs/staging_2026/"
    "catalog_academic_course_crosswalk_2026_staged.csv"
)

COURSE_HEADER_RE = re.compile(
    r"^([A-Z]{2,5})\s+(\d{4})\b"
)

MARKER_RE = re.compile(
    r"(?:^|[\s.;:])"
    r"(AC|TEC|CP)"
    r"(?:[\s.;:]|$)",
    flags=re.IGNORECASE,
)


def clean(value: object) -> str:
    return " ".join(
        str(value).strip().split()
    )


def extract_catalog_courses(
    path: Path,
) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise SystemExit(
            f"ABORT: source catalog missing: {path}"
        )

    doc = Document(path)

    start = None

    for i, paragraph in enumerate(
        doc.paragraphs
    ):
        if clean(paragraph.text) == (
            "Course Descriptions"
        ):
            start = i
            break

    if start is None:
        raise SystemExit(
            "ABORT: Course Descriptions heading "
            "not found."
        )

    records: dict[
        str,
        dict[str, str],
    ] = {}

    current_code = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_code
        nonlocal current_parts

        if not current_code:
            return

        if current_code in records:
            raise SystemExit(
                "ABORT: duplicate course description "
                f"header: {current_code}"
            )

        text = clean(
            " ".join(current_parts)
        )

        markers = [
            match.upper()
            for match in MARKER_RE.findall(
                text
            )
        ]

        marker = (
            markers[-1]
            if markers
            else ""
        )

        rubric, number = (
            current_code.split()
        )

        records[current_code] = {
            "course_code": current_code,
            "rubric": rubric,
            "course_number": number,
            "marker": marker,
            "source_text": text,
        }

        current_code = None
        current_parts = []

    for paragraph in doc.paragraphs[
        start + 1:
    ]:
        text = clean(
            paragraph.text
        )

        match = COURSE_HEADER_RE.match(
            text
        )

        if match:
            flush()

            current_code = (
                f"{match.group(1)} "
                f"{match.group(2)}"
            )

            current_parts = []
            continue

        if current_code and text:
            current_parts.append(
                text
            )

    flush()

    if not records:
        raise SystemExit(
            "ABORT: no catalog courses extracted."
        )

    return records


def main() -> None:
    if not BASELINE.exists():
        raise SystemExit(
            f"ABORT: baseline missing: {BASELINE}"
        )

    baseline = pd.read_csv(
        BASELINE,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    expected_columns = [
        "catalog_year",
        "course_code",
        "rubric",
        "course_number",
        "academic_elective_eligible",
        "final_course_family",
        "final_resolution_status",
        "resolution_note",
        "original_course_family",
        "original_crosswalk_status",
        "source_file",
    ]

    if list(baseline.columns) != (
        expected_columns
    ):
        raise SystemExit(
            "ABORT: baseline schema does not "
            "match expected 11-column schema."
        )

    prior = baseline[
        baseline[
            "catalog_year"
        ].eq(
            "2025-2026"
        )
    ].copy()

    if len(prior) != 559:
        raise SystemExit(
            "ABORT: expected 559 rows in "
            f"2025-2026 baseline; found "
            f"{len(prior)}."
        )

    if prior[
        "course_code"
    ].duplicated().any():
        raise SystemExit(
            "ABORT: duplicate 2025-2026 "
            "course codes."
        )

    prior_lookup = (
        prior.set_index(
            "course_code",
            drop=False,
        )
    )

    courses = extract_catalog_courses(
        SOURCE_DOCX
    )

    rows = []
    carried = []
    added = []

    for course_code in sorted(
        courses
    ):
        source = courses[
            course_code
        ]

        if course_code in (
            prior_lookup.index
        ):
            old = prior_lookup.loc[
                course_code
            ].to_dict()

            old[
                "catalog_year"
            ] = CATALOG_YEAR

            old[
                "rubric"
            ] = source["rubric"]

            old[
                "course_number"
            ] = source[
                "course_number"
            ]

            old[
                "source_file"
            ] = str(
                SOURCE_DOCX
            )

            rows.append(old)

            carried.append(
                course_code
            )

            continue

        marker = source[
            "marker"
        ]

        if marker == "AC":
            family = "ACADEMIC"
            eligible = "True"
            final_status = (
                "RESOLVED_FROM_CATALOG_MARKER"
            )
            original_status = "RESOLVED"

        elif marker == "TEC":
            family = "TECHNICAL"
            eligible = "False"
            final_status = (
                "RESOLVED_NOT_ACADEMIC"
            )
            original_status = "RESOLVED"

        elif marker == "CP":
            family = (
                "COLLEGE_PREPARATORY"
            )
            eligible = "False"
            final_status = (
                "RESOLVED_NOT_ACADEMIC"
            )
            original_status = "RESOLVED"

        else:
            raise SystemExit(
                "ABORT: new 2026 course has "
                "no authoritative AC/TEC/CP "
                f"marker: {course_code}"
            )

        rows.append(
            {
                "catalog_year":
                    CATALOG_YEAR,
                "course_code":
                    course_code,
                "rubric":
                    source["rubric"],
                "course_number":
                    source[
                        "course_number"
                    ],
                "academic_elective_eligible":
                    eligible,
                "final_course_family":
                    family,
                "final_resolution_status":
                    final_status,
                "resolution_note":
                    "",
                "original_course_family":
                    family,
                "original_crosswalk_status":
                    original_status,
                "source_file":
                    str(SOURCE_DOCX),
            }
        )

        added.append(
            course_code
        )

    result = pd.DataFrame(
        rows,
        columns=expected_columns,
    )

    if len(result) != 584:
        raise SystemExit(
            "ABORT: expected 584 2026 "
            f"courses; found {len(result)}."
        )

    if result[
        "course_code"
    ].duplicated().any():
        raise SystemExit(
            "ABORT: duplicate 2026 "
            "course codes."
        )

    removed = sorted(
        set(prior["course_code"])
        - set(result["course_code"])
    )

    if len(carried) != 553:
        raise SystemExit(
            "ABORT: expected 553 carried "
            f"courses; found {len(carried)}."
        )

    if len(added) != 31:
        raise SystemExit(
            "ABORT: expected 31 added "
            f"courses; found {len(added)}."
        )

    if len(removed) != 6:
        raise SystemExit(
            "ABORT: expected 6 removed "
            f"courses; found {len(removed)}."
        )

    # The eight previously adjudicated
    # continuing courses must retain their
    # prior classifications exactly.
    special_codes = {
        "ARTC 2333",
        "ARTC 2348",
        "HAMG 1321",
        "HAMG 2301",
        "HAMG 2305",
        "HAMG 2307",
        "BIOL 1411",
        "PHYS 2426",
    }

    present_special = set(
        result.loc[
            result[
                "course_code"
            ].isin(
                special_codes
            ),
            "course_code",
        ]
    )

    if present_special != special_codes:
        raise SystemExit(
            "ABORT: expected adjudicated "
            "continuing-course set is not "
            "fully present."
        )

    # Every newly introduced course must
    # resolve directly from an explicit
    # catalog marker.
    new_rows = result[
        result[
            "course_code"
        ].isin(
            added
        )
    ]

    if not new_rows[
        "final_resolution_status"
    ].isin(
        {
            "RESOLVED_FROM_CATALOG_MARKER",
            "RESOLVED_NOT_ACADEMIC",
        }
    ).all():
        raise SystemExit(
            "ABORT: new-course resolution "
            "status outside allowed set."
        )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT,
        index=False,
    )

    print("=" * 80)
    print(
        "STAGED 2026 ACADEMIC "
        "COURSE CROSSWALK"
    )
    print("=" * 80)

    print("ROWS:", len(result))
    print(
        "CARRIED FROM FINAL 2025:",
        len(carried),
    )
    print(
        "NEW 2026 COURSES:",
        len(added),
    )
    print(
        "REMOVED SINCE 2025:",
        len(removed),
    )

    print()
    print(
        "FINAL FAMILY COUNTS:"
    )
    print(
        result[
            "final_course_family"
        ].value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        "FINAL STATUS COUNTS:"
    )
    print(
        result[
            "final_resolution_status"
        ].value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        "ACADEMIC ELIGIBLE TRUE:",
        result[
            "academic_elective_eligible"
        ]
        .str.upper()
        .eq("TRUE")
        .sum(),
    )

    print()
    print("NEW COURSES:")
    print(
        new_rows[
            [
                "course_code",
                "final_course_family",
                "final_resolution_status",
            ]
        ].to_string(
            index=False
        )
    )

    print()
    print("REMOVED COURSES:")
    print(
        "\n".join(
            removed
        )
    )

    print()
    print(
        "OUTPUT:",
        OUTPUT,
    )
    print(
        "CANONICAL CONFIG MODIFIED: NO"
    )
    print(
        "PRODUCTION FILES MODIFIED: NO"
    )


if __name__ == "__main__":
    main()
