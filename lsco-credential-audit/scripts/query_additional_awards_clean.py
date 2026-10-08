from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

COMPLETE_PATH = ROOT / "data/processed/all_complete_rows_multiyear.csv"

COURSE_HISTORY_PATH = (
    ROOT / "data/processed/normalized_actual_student_course_history.csv"
)

# Used only as a credential-year -> canonical-lineage mapping source.
MODELED_LINEAGE_PATH = (
    ROOT
    / "data/processed/full_actual_audit/president_report/"
    "complete_rows_with_canonical_lineage.csv"
)

OFFICIAL_AWARDS_PATH = (
    ROOT / "data/raw/institutional_awards/lsco_awards_sample_20260730.xlsx"
)

AWARD_CROSSWALK_PATH = (
    ROOT
    / "data/interim/institutional_awards/"
    "award_program_crosswalk_curated.xlsx"
)

GOVERNED_RELATIONSHIPS_PATH = (
    ROOT
    / "data/interim/institutional_awards/"
    "governed_lineage_relationships_final.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data/processed/reporting/"
    "additional_awards_clean_query_20260803"
)


# =============================================================================
# CONFIGURATION
# =============================================================================

CATALOGS = [
    "2021-2022",
    "2022-2023",
    "2023-2024",
    "2024-2025",
    "2025-2026",
]


# =============================================================================
# HELPERS
# =============================================================================

def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def normalize_id(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    # Prevent Excel numeric identifiers from becoming 123456.0.
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]

    return text


def normalize_catalog(value: object) -> str:
    text = str(value).strip()
    match = re.search(r"(20\d{2})\D+(20\d{2})", text)

    if match:
        return f"{match.group(1)}-{match.group(2)}"

    return text


def catalog_start_year(value: object) -> float:
    match = re.search(r"(20\d{2})", str(value))
    return float(match.group(1)) if match else np.nan


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value

    if pd.isna(value):
        return False

    return normalize_text(value) in {
        "TRUE",
        "T",
        "YES",
        "Y",
        "1",
    }


def parse_term_components(
    term_taken: object,
    term_sort: object,
) -> tuple[float, str]:
    """
    Return:
        calendar_year
        season: FALL, SPRING, SUMMER, OTHER

    Prefer the human-readable term label. Use term_sort suffix only as fallback.
    """

    label = normalize_text(term_taken)

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", label)
    calendar_year = (
        float(year_match.group(1))
        if year_match
        else np.nan
    )

    if "FALL" in label:
        return calendar_year, "FALL"

    if "SPRING" in label:
        return calendar_year, "SPRING"

    if "SUMMER" in label:
        return calendar_year, "SUMMER"

    if "WINTER" in label:
        return calendar_year, "SPRING"

    numeric = pd.to_numeric(
        pd.Series([term_sort]),
        errors="coerce",
    ).iloc[0]

    if pd.notna(numeric):
        numeric_int = int(numeric)
        numeric_text = str(numeric_int)

        if pd.isna(calendar_year) and len(numeric_text) >= 4:
            calendar_year = float(numeric_text[:4])

        suffix = numeric_int % 100

        # LSCO/Banner term-family fallbacks.
        if suffix in {70, 80, 90}:
            return calendar_year, "FALL"

        if suffix in {10, 20}:
            return calendar_year, "SPRING"

        if suffix in {30, 40, 50, 60}:
            return calendar_year, "SUMMER"

    return calendar_year, "OTHER"


def academic_year_from_term(
    term_taken: object,
    term_sort: object,
) -> str:
    year, season = parse_term_components(term_taken, term_sort)

    if pd.isna(year):
        return ""

    year = int(year)

    if season == "FALL":
        return f"{year}-{year + 1}"

    if season in {"SPRING", "SUMMER"}:
        return f"{year - 1}-{year}"

    return ""


def catalog_floor_from_term(
    term_taken: object,
    term_sort: object,
) -> str:
    academic_year = academic_year_from_term(
        term_taken,
        term_sort,
    )

    if academic_year in CATALOGS:
        return academic_year

    # Students whose first successful work predates the modeled five-catalog
    # window receive the earliest available catalog as their modeled floor.
    year, season = parse_term_components(term_taken, term_sort)

    if pd.isna(year):
        return ""

    year = int(year)

    if season == "FALL":
        start_year = year
    elif season in {"SPRING", "SUMMER"}:
        start_year = year - 1
    else:
        return ""

    earliest_start = int(CATALOGS[0][:4])

    if start_year < earliest_start:
        return CATALOGS[0]

    return academic_year


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found:\n{path}")


def require_columns(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> None:
    missing = sorted(required - set(frame.columns))

    if missing:
        raise ValueError(
            f"{label} is missing required columns:\n"
            + "\n".join(missing)
        )


def write_csv(frame: pd.DataFrame, filename: str) -> None:
    path = OUTPUT_DIR / filename
    frame.to_csv(path, index=False)
    print(f"Wrote {len(frame):,} rows: {path.relative_to(ROOT)}")


# =============================================================================
# LOAD
# =============================================================================

def main() -> None:
    print("=" * 100)
    print("CLEAN ADDITIONAL-AWARD QUERY")
    print("=" * 100)

    for path in [
        COMPLETE_PATH,
        COURSE_HISTORY_PATH,
        MODELED_LINEAGE_PATH,
        OFFICIAL_AWARDS_PATH,
        AWARD_CROSSWALK_PATH,
        GOVERNED_RELATIONSHIPS_PATH,
    ]:
        require_file(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    complete = pd.read_csv(
        COMPLETE_PATH,
        dtype={"student_id": "string"},
        low_memory=False,
    )

    courses = pd.read_csv(
        COURSE_HISTORY_PATH,
        dtype={"student_id": "string"},
        low_memory=False,
    )

    modeled_lineage = pd.read_csv(
        MODELED_LINEAGE_PATH,
        dtype={"student_id": "string"},
        low_memory=False,
    )

    official = pd.read_excel(
        OFFICIAL_AWARDS_PATH,
        dtype={"ID": "string"},
    )

    award_crosswalk = pd.read_excel(
        AWARD_CROSSWALK_PATH,
        dtype="string",
    )

    governed = pd.read_csv(
        GOVERNED_RELATIONSHIPS_PATH,
        dtype="string",
        low_memory=False,
    )

    require_columns(
        complete,
        {
            "student_id",
            "catalog_year",
            "credential_id",
            "audit_status",
            "award_term_sort",
            "award_term_taken",
        },
        "Complete rows",
    )

    require_columns(
        courses,
        {
            "student_id",
            "passed",
            "term_sort",
            "term_taken",
        },
        "Course history",
    )

    require_columns(
        modeled_lineage,
        {
            "catalog_year",
            "credential_id",
            "canonical_lineage",
        },
        "Modeled-lineage source",
    )

    require_columns(
        official,
        {
            "ID",
            "Curr1ProgramCode",
            "Major1Code",
            "DegreeCode",
            "StudGradTerm",
            "GradDate",
            "DegreeStat",
        },
        "Official awards",
    )

    require_columns(
        award_crosswalk,
        {
            "Curr1ProgramCode",
            "Major1Code",
            "DegreeCode",
            "canonical_lineage",
        },
        "Award crosswalk",
    )

    require_columns(
        governed,
        {
            "detected_lineage",
            "institutional_lineage",
            "awarded_represents_detected",
            "detected_remains_additional_award",
        },
        "Governed lineage relationships",
    )

    print(f"Complete input rows: {len(complete):,}")
    print(f"Course-history rows: {len(courses):,}")
    print(f"Official-award rows: {len(official):,}")

    # =========================================================================
    # 1. CLEAN COMPLETE UNIVERSE
    # =========================================================================

    complete["student_id"] = complete["student_id"].map(normalize_id)
    complete["catalog_year"] = complete["catalog_year"].map(
        normalize_catalog
    )
    complete["credential_id"] = complete["credential_id"].map(
        normalize_text
    )
    complete["audit_status_normalized"] = complete["audit_status"].map(
        normalize_text
    )

    complete = complete.loc[
        complete["audit_status_normalized"].eq("COMPLETE")
    ].copy()

    complete = complete.drop_duplicates(
        subset=[
            "student_id",
            "catalog_year",
            "credential_id",
        ]
    )

    print(f"Distinct COMPLETE credential-year rows: {len(complete):,}")
    print(
        "Students represented in COMPLETE universe: "
        f"{complete['student_id'].nunique():,}"
    )

    # =========================================================================
    # 2. FIRST SUCCESSFUL TERM / CATALOG FLOOR
    # =========================================================================

    courses["student_id"] = courses["student_id"].map(normalize_id)

    passed_normalized = courses["passed"].map(normalize_text)

    passed_mask = passed_normalized.isin(
        {"TRUE", "T", "YES", "Y", "1", "PASSED"}
    )

    passed_courses = courses.loc[passed_mask].copy()

    passed_courses["term_sort_numeric"] = pd.to_numeric(
        passed_courses["term_sort"],
        errors="coerce",
    )

    passed_courses = passed_courses.loc[
        passed_courses["term_sort_numeric"].notna()
    ].copy()

    passed_courses = passed_courses.sort_values(
        [
            "student_id",
            "term_sort_numeric",
            "term_taken",
        ],
        kind="stable",
    )

    first_success = (
        passed_courses
        .groupby("student_id", as_index=False)
        .first()[
            [
                "student_id",
                "term_sort_numeric",
                "term_taken",
            ]
        ]
        .rename(
            columns={
                "term_sort_numeric": "first_successful_term_sort",
                "term_taken": "first_successful_term_taken",
            }
        )
    )

    first_success["initial_catalog_year"] = first_success.apply(
        lambda row: catalog_floor_from_term(
            row["first_successful_term_taken"],
            row["first_successful_term_sort"],
        ),
        axis=1,
    )

    first_success["initial_catalog_start_year"] = (
        first_success["initial_catalog_year"].map(catalog_start_year)
    )

    write_csv(
        first_success,
        "01_student_catalog_floors.csv",
    )

    # =========================================================================
    # 3. APPLY CATALOG FLOOR TO COMPLETE ROWS
    # =========================================================================

    qualified = complete.merge(
        first_success,
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    qualified["candidate_catalog_start_year"] = (
        qualified["catalog_year"].map(catalog_start_year)
    )

    qualified["catalog_floor_resolved"] = (
        qualified["initial_catalog_start_year"].notna()
        & qualified["candidate_catalog_start_year"].notna()
    )

    qualified["meets_catalog_floor"] = (
        qualified["catalog_floor_resolved"]
        & (
            qualified["candidate_catalog_start_year"]
            >= qualified["initial_catalog_start_year"]
        )
    )

    floor_excluded = qualified.loc[
        ~qualified["meets_catalog_floor"]
    ].copy()

    qualified = qualified.loc[
        qualified["meets_catalog_floor"]
    ].copy()

    write_csv(
        floor_excluded,
        "02_complete_rows_excluded_by_catalog_floor.csv",
    )

    write_csv(
        qualified,
        "03_complete_rows_after_catalog_floor.csv",
    )

    print(
        "COMPLETE rows retained after catalog floor: "
        f"{len(qualified):,}"
    )
    print(
        "COMPLETE rows excluded by catalog floor/unresolved floor: "
        f"{len(floor_excluded):,}"
    )

    # =========================================================================
    # 4. ATTACH CANONICAL MODELED LINEAGE
    # =========================================================================

    modeled_lineage["catalog_year"] = (
        modeled_lineage["catalog_year"].map(normalize_catalog)
    )
    modeled_lineage["credential_id"] = (
        modeled_lineage["credential_id"].map(normalize_text)
    )
    modeled_lineage["canonical_lineage"] = (
        modeled_lineage["canonical_lineage"].map(normalize_text)
    )

    lineage_map = (
        modeled_lineage[
            [
                "catalog_year",
                "credential_id",
                "canonical_lineage",
            ]
        ]
        .dropna(subset=["canonical_lineage"])
        .loc[
            lambda frame:
            frame["canonical_lineage"].ne("")
        ]
        .drop_duplicates()
    )

    lineage_ambiguity = (
        lineage_map
        .groupby(
            [
                "catalog_year",
                "credential_id",
            ]
        )["canonical_lineage"]
        .nunique()
        .reset_index(name="canonical_lineage_count")
        .loc[
            lambda frame:
            frame["canonical_lineage_count"] > 1
        ]
    )

    if not lineage_ambiguity.empty:
        write_csv(
            lineage_ambiguity,
            "ERROR_modeled_lineage_ambiguities.csv",
        )
        raise RuntimeError(
            "A credential-year maps to multiple canonical lineages. "
            "Review ERROR_modeled_lineage_ambiguities.csv."
        )

    qualified = qualified.merge(
        lineage_map,
        on=[
            "catalog_year",
            "credential_id",
        ],
        how="left",
        validate="many_to_one",
    )

    missing_modeled_lineage = qualified.loc[
        qualified["canonical_lineage"].isna()
        | qualified["canonical_lineage"].eq("")
    ].copy()

    write_csv(
        missing_modeled_lineage,
        "04_complete_rows_missing_modeled_lineage.csv",
    )

    if not missing_modeled_lineage.empty:
        raise RuntimeError(
            f"{len(missing_modeled_lineage):,} qualified COMPLETE rows "
            "lack canonical lineage. Review output 04 before continuing."
        )

    # =========================================================================
    # 5. COMPLETION YEAR AND PRIMARY CATALOG SELECTION
    # =========================================================================

    qualified["award_term_sort_numeric"] = pd.to_numeric(
        qualified["award_term_sort"],
        errors="coerce",
    )

    qualified["completion_academic_year"] = qualified.apply(
        lambda row: academic_year_from_term(
            row["award_term_taken"],
            row["award_term_sort_numeric"],
        ),
        axis=1,
    )

    qualified["completion_calendar_year"] = qualified.apply(
        lambda row: parse_term_components(
            row["award_term_taken"],
            row["award_term_sort_numeric"],
        )[0],
        axis=1,
    )

    qualified["completion_calendar_year"] = (
        pd.to_numeric(
            qualified["completion_calendar_year"],
            errors="coerce",
        )
        .astype("Int64")
    )

    # Catalog cannot generate a modeled completion before its opening year.
    qualified["catalog_opening_year"] = (
        qualified["candidate_catalog_start_year"].astype("Int64")
    )

    qualified["completion_predates_catalog"] = (
        qualified["completion_calendar_year"].notna()
        & qualified["catalog_opening_year"].notna()
        & (
            qualified["completion_calendar_year"]
            < qualified["catalog_opening_year"]
        )
    )

    # We retain the audit's completion term but move these cases to the
    # catalog's opening academic year for query allocation.
    qualified["query_completion_academic_year"] = np.where(
        qualified["completion_predates_catalog"],
        qualified["catalog_year"],
        qualified["completion_academic_year"],
    )

    qualified["completion_term_selection_sort"] = np.where(
        qualified["completion_predates_catalog"],
        qualified["candidate_catalog_start_year"] * 100,
        qualified["award_term_sort_numeric"],
    )

    qualified["catalog_alternative_rank"] = (
        qualified
        .sort_values(
            [
                "student_id",
                "canonical_lineage",
                "completion_term_selection_sort",
                "candidate_catalog_start_year",
                "credential_id",
            ],
            kind="stable",
            na_position="last",
        )
        .groupby(
            [
                "student_id",
                "canonical_lineage",
            ]
        )
        .cumcount()
        + 1
    )

    selected = qualified.loc[
        qualified["catalog_alternative_rank"].eq(1)
    ].copy()

    alternative_summary = (
        qualified
        .sort_values(
            [
                "student_id",
                "canonical_lineage",
                "catalog_alternative_rank",
            ]
        )
        .groupby(
            [
                "student_id",
                "canonical_lineage",
            ],
            as_index=False,
        )
        .agg(
            completing_catalog_count=(
                "catalog_year",
                "nunique",
            ),
            completing_catalogs=(
                "catalog_year",
                lambda values: " | ".join(
                    dict.fromkeys(values.astype(str))
                ),
            ),
            completing_credential_ids=(
                "credential_id",
                lambda values: " | ".join(
                    dict.fromkeys(values.astype(str))
                ),
            ),
        )
    )

    selected = selected.merge(
        alternative_summary,
        on=[
            "student_id",
            "canonical_lineage",
        ],
        how="left",
        validate="one_to_one",
    )

    write_csv(
        qualified,
        "05_all_eligible_catalog_alternatives.csv",
    )

    write_csv(
        selected,
        "06_selected_student_lineage_completions_before_awards.csv",
    )

    print(
        "Selected student-lineage completions before award exclusion: "
        f"{len(selected):,}"
    )

    # =========================================================================
    # 6. NORMALIZE OFFICIAL AWARDS
    # =========================================================================

    official["student_id"] = official["ID"].map(normalize_id)

    key_columns = [
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
    ]

    for column in key_columns:
        official[column] = official[column].map(normalize_text)
        award_crosswalk[column] = (
            award_crosswalk[column].map(normalize_text)
        )

    award_crosswalk["canonical_lineage"] = (
        award_crosswalk["canonical_lineage"].map(normalize_text)
    )

    crosswalk_columns = key_columns + [
        "canonical_lineage",
    ]

    optional_crosswalk_columns = [
        "award_level",
        "stack_behavior",
        "reconciliation_key",
        "credential_id",
        "match_status",
    ]

    crosswalk_columns.extend(
        column
        for column in optional_crosswalk_columns
        if column in award_crosswalk.columns
    )

    crosswalk_clean = (
        award_crosswalk[crosswalk_columns]
        .drop_duplicates()
    )

    crosswalk_ambiguity = (
        crosswalk_clean
        .groupby(key_columns)["canonical_lineage"]
        .nunique()
        .reset_index(name="canonical_lineage_count")
        .loc[
            lambda frame:
            frame["canonical_lineage_count"] > 1
        ]
    )

    if not crosswalk_ambiguity.empty:
        write_csv(
            crosswalk_ambiguity,
            "ERROR_official_crosswalk_ambiguities.csv",
        )
        raise RuntimeError(
            "An official award code combination maps to multiple "
            "canonical lineages."
        )

    official_normalized = official.merge(
        crosswalk_clean,
        on=key_columns,
        how="left",
        validate="many_to_one",
    )

    official_normalized["institutional_lineage"] = (
        official_normalized["canonical_lineage"].map(normalize_text)
    )

    official_unmapped = official_normalized.loc[
        official_normalized["institutional_lineage"].eq("")
    ].copy()

    official_mapped = official_normalized.loc[
        official_normalized["institutional_lineage"].ne("")
    ].copy()

    write_csv(
        official_unmapped,
        "07_official_awards_unmapped.csv",
    )

    write_csv(
        official_mapped,
        "08_official_awards_normalized.csv",
    )

    print(
        "Mapped official award rows: "
        f"{len(official_mapped):,}"
    )
    print(
        "Unmapped official award rows: "
        f"{len(official_unmapped):,}"
    )

    official_student_lineages = (
        official_mapped[
            [
                "student_id",
                "institutional_lineage",
            ]
        ]
        .drop_duplicates()
    )

    # =========================================================================
    # 7. BUILD GOVERNED REPRESENTATION PAIRS
    # =========================================================================

    governed["detected_lineage"] = (
        governed["detected_lineage"].map(normalize_text)
    )
    governed["institutional_lineage"] = (
        governed["institutional_lineage"].map(normalize_text)
    )

    governed["awarded_represents_detected_bool"] = (
        governed["awarded_represents_detected"].map(parse_bool)
    )

    governed["detected_remains_additional_award_bool"] = (
        governed["detected_remains_additional_award"].map(parse_bool)
    )

    consuming_relationships = governed.loc[
        governed["awarded_represents_detected_bool"]
        & ~governed["detected_remains_additional_award_bool"],
        [
            "detected_lineage",
            "institutional_lineage",
            "relationship_type",
            "governance_status",
            "governance_note",
        ],
    ].drop_duplicates()

    # Exact same-lineage awards always represent the modeled lineage.
    exact_pairs = official_student_lineages.rename(
        columns={
            "institutional_lineage": "detected_lineage",
        }
    )

    exact_pairs["institutional_lineage"] = (
        exact_pairs["detected_lineage"]
    )
    exact_pairs["representation_basis"] = "EXACT_CANONICAL_LINEAGE"
    exact_pairs["relationship_type"] = "EXACT"
    exact_pairs["governance_status"] = "EXACT"
    exact_pairs["governance_note"] = ""

    governed_pairs = official_student_lineages.merge(
        consuming_relationships,
        on="institutional_lineage",
        how="inner",
        validate="many_to_many",
    )

    governed_pairs["representation_basis"] = (
        "GOVERNED_LINEAGE_RELATIONSHIP"
    )

    representation_pairs = pd.concat(
        [
            exact_pairs[
                [
                    "student_id",
                    "detected_lineage",
                    "institutional_lineage",
                    "representation_basis",
                    "relationship_type",
                    "governance_status",
                    "governance_note",
                ]
            ],
            governed_pairs[
                [
                    "student_id",
                    "detected_lineage",
                    "institutional_lineage",
                    "representation_basis",
                    "relationship_type",
                    "governance_status",
                    "governance_note",
                ]
            ],
        ],
        ignore_index=True,
    ).drop_duplicates(
        subset=[
            "student_id",
            "detected_lineage",
        ]
    )

    write_csv(
        representation_pairs,
        "09_official_award_representation_pairs.csv",
    )

    # =========================================================================
    # 8. ANTI-JOIN: ADDITIONAL AWARDS
    # =========================================================================

    selected = selected.rename(
        columns={
            "canonical_lineage": "detected_lineage",
        }
    )

    reconciled = selected.merge(
        representation_pairs,
        on=[
            "student_id",
            "detected_lineage",
        ],
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    reconciled["already_represented_by_official_award"] = (
        reconciled["_merge"].eq("both")
    )

    already_awarded = reconciled.loc[
        reconciled["already_represented_by_official_award"]
    ].copy()

    additional = reconciled.loc[
        ~reconciled["already_represented_by_official_award"]
    ].copy()

    additional["additional_award_flag"] = 1

    write_csv(
        already_awarded,
        "10_selected_completions_already_represented.csv",
    )

    write_csv(
        additional,
        "11_additional_awards_student_detail.csv",
    )

    # =========================================================================
    # 9. AGGREGATIONS
    # =========================================================================

    additional_by_catalog_lineage_year = (
        additional
        .groupby(
            [
                "catalog_year",
                "detected_lineage",
                "query_completion_academic_year",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
        )
        .sort_values(
            [
                "query_completion_academic_year",
                "catalog_year",
                "detected_lineage",
            ]
        )
    )

    additional_by_catalog = (
        additional
        .groupby(
            "catalog_year",
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            credential_lineages=(
                "detected_lineage",
                "nunique",
            ),
        )
        .sort_values("catalog_year")
    )

    additional_by_lineage = (
        additional
        .groupby(
            "detected_lineage",
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            selected_catalogs=(
                "catalog_year",
                "nunique",
            ),
            first_completion_year=(
                "query_completion_academic_year",
                "min",
            ),
            last_completion_year=(
                "query_completion_academic_year",
                "max",
            ),
        )
        .sort_values(
            [
                "additional_awards",
                "detected_lineage",
            ],
            ascending=[
                False,
                True,
            ],
        )
    )

    additional_by_completion_year = (
        additional
        .groupby(
            "query_completion_academic_year",
            dropna=False,
            as_index=False,
        )
        .agg(
            additional_awards=(
                "additional_award_flag",
                "sum",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            credential_lineages=(
                "detected_lineage",
                "nunique",
            ),
        )
        .sort_values("query_completion_academic_year")
    )

    write_csv(
        additional_by_catalog_lineage_year,
        "12_additional_awards_by_catalog_lineage_completion_year.csv",
    )

    write_csv(
        additional_by_catalog,
        "13_additional_awards_by_catalog.csv",
    )

    write_csv(
        additional_by_lineage,
        "14_additional_awards_by_credential_lineage.csv",
    )

    write_csv(
        additional_by_completion_year,
        "15_additional_awards_by_completion_year.csv",
    )

    # =========================================================================
    # 10. FUNNEL AND CONSOLE RESULTS
    # =========================================================================

    funnel = pd.DataFrame(
        [
            {
                "stage_order": 1,
                "stage": "Raw COMPLETE credential-year rows",
                "rows": len(complete),
                "distinct_students": complete["student_id"].nunique(),
                "distinct_student_lineages": np.nan,
            },
            {
                "stage_order": 2,
                "stage": "COMPLETE rows after catalog floor",
                "rows": len(qualified),
                "distinct_students": qualified["student_id"].nunique(),
                "distinct_student_lineages": (
                    qualified[
                        [
                            "student_id",
                            "canonical_lineage",
                        ]
                    ]
                    .drop_duplicates()
                    .shape[0]
                ),
            },
            {
                "stage_order": 3,
                "stage": "Selected student-lineage completions",
                "rows": len(selected),
                "distinct_students": selected["student_id"].nunique(),
                "distinct_student_lineages": len(selected),
            },
            {
                "stage_order": 4,
                "stage": "Already represented by official award",
                "rows": len(already_awarded),
                "distinct_students": already_awarded[
                    "student_id"
                ].nunique(),
                "distinct_student_lineages": len(already_awarded),
            },
            {
                "stage_order": 5,
                "stage": "Additional awards",
                "rows": len(additional),
                "distinct_students": additional[
                    "student_id"
                ].nunique(),
                "distinct_student_lineages": len(additional),
            },
        ]
    )

    write_csv(
        funnel,
        "00_query_funnel.csv",
    )

    print()
    print("=" * 100)
    print("RESULT")
    print("=" * 100)
    print(
        f"Additional awards: {len(additional):,}"
    )
    print(
        "Students with at least one additional award: "
        f"{additional['student_id'].nunique():,}"
    )
    print(
        "Additional credential lineages represented: "
        f"{additional['detected_lineage'].nunique():,}"
    )

    print()
    print("ADDITIONAL AWARDS BY COMPLETION YEAR")
    print(
        additional_by_completion_year.to_string(index=False)
        if not additional_by_completion_year.empty
        else "No additional awards found."
    )

    print()
    print("ADDITIONAL AWARDS BY CATALOG")
    print(
        additional_by_catalog.to_string(index=False)
        if not additional_by_catalog.empty
        else "No additional awards found."
    )

    print()
    print(f"Output directory:\n{OUTPUT_DIR}")


if __name__ == "__main__":
    main()