from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
import re

import pandas as pd


ROOT = Path.cwd()

QUERY_DIR = (
    ROOT / "data/processed/reporting/"
    "additional_awards_clean_query_20260803"
)

ADDITIONAL_PATH = (
    QUERY_DIR / "11_additional_awards_student_detail.csv"
)

SELECTED_PATH = (
    QUERY_DIR / "06_selected_student_lineage_completions_before_awards.csv"
)

ALTERNATIVES_PATH = (
    QUERY_DIR / "05_all_eligible_catalog_alternatives.csv"
)

OFFICIAL_PATH = (
    QUERY_DIR / "08_official_awards_normalized.csv"
)

REPRESENTATION_PATH = (
    QUERY_DIR / "09_official_award_representation_pairs.csv"
)

MODELED_LINEAGE_PATH = (
    ROOT
    / "data/processed/full_actual_audit/president_report/"
    "complete_rows_with_canonical_lineage.csv"
)

REQ_CANDIDATES = [
    ROOT / "data/processed/catalogs/requirements_master_multiyear.csv",
    ROOT / "data/processed/catalogs/requirements_master_multicatalog.csv",
]

OUT_DIR = (
    ROOT
    / "data/processed/reporting/"
    "certificate_lineage_bruteforce_review_20260811"
)

OUT_XLSX = (
    OUT_DIR
    / "CERTIFICATE_LINEAGE_BRUTE_FORCE_REVIEW.xlsx"
)

COURSE_RE = re.compile(
    r"\b([A-Z]{2,5})\s*[- ]?\s*(\d{4})\b",
    re.I,
)

ASSOCIATE_RE = re.compile(
    r"\b(ASSOCIATE|AAS|AA|AS|AAT)\b"
    r"|_AAS(?:_|$)"
    r"|_AA(?:_|$)"
    r"|_AS(?:_|$)"
    r"|_AAT(?:_|$)",
    re.I,
)


# =============================================================================
# HELPERS
# =============================================================================

def text(value):
    return "" if pd.isna(value) else str(value).strip()


def norm(value):
    return text(value).upper()


def norm_id(value):
    return re.sub(r"\.0$", "", norm(value))


def normalize_course(value):
    match = COURSE_RE.search(norm(value))

    if not match:
        return ""

    return (
        f"{match.group(1).upper()} "
        f"{match.group(2)}"
    )


def split_courses(value):
    return {
        f"{m.group(1).upper()} {m.group(2)}"
        for m in COURSE_RE.finditer(norm(value))
    }


def rubric(course):
    course = normalize_course(course)
    return course.split()[0] if course else ""


def first_nonblank(values):
    for value in values:
        value = text(value)

        if value:
            return value

    return ""


def join_unique(values):
    return " | ".join(
        sorted(
            {
                text(v)
                for v in values
                if text(v)
            }
        )
    )


def set_from_pipe(value):
    return {
        x.strip()
        for x in text(value).split("|")
        if x.strip()
    }


def jaccard(a, b):
    if not a and not b:
        return 0.0

    union = a | b

    return (
        len(a & b) / len(union)
        if union
        else 0.0
    )


def coverage(a, b):
    """
    Share of A covered by B.
    """
    if not a:
        return 0.0

    return len(a & b) / len(a)


def title_tokens(value):
    words = re.findall(
        r"[A-Z0-9]+",
        norm(value),
    )

    stop = {
        "CERTIFICATE",
        "CERT",
        "OF",
        "COMPLETION",
        "PROGRAM",
        "LEVEL",
        "BASIC",
        "INTERMEDIATE",
        "ADVANCED",
    }

    return {
        word
        for word in words
        if word not in stop
    }


def title_similarity(a, b):
    a_text = " ".join(
        sorted(title_tokens(a))
    )

    b_text = " ".join(
        sorted(title_tokens(b))
    )

    if not a_text or not b_text:
        return 0.0

    return SequenceMatcher(
        None,
        a_text,
        b_text,
    ).ratio()


def is_associate(*values):
    combined = " | ".join(
        norm(v)
        for v in values
        if text(v)
    )

    return bool(
        ASSOCIATE_RE.search(combined)
    )


def find_column(
    frame,
    candidates,
    required=True,
):
    lookup = {
        str(c).strip().lower(): c
        for c in frame.columns
    }

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    if required:
        raise RuntimeError(
            f"Could not find any of {candidates}. "
            f"Columns: {list(frame.columns)}"
        )

    return None


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)

    return pd.read_csv(
        path,
        dtype=str,
        low_memory=False,
    ).fillna("")


def choose_requirements_path():
    for path in REQ_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Could not find requirements_master_multiyear.csv "
        "or requirements_master_multicatalog.csv"
    )


# =============================================================================
# OPTIONAL COURSE-CIP LOOKUP
#
# CIP IS A REVIEW SIGNAL ONLY.
# IT DOES NOT CONTROL LINEAGE.
# =============================================================================

def discover_course_cip_lookup():

    candidates = []

    for base in [
        ROOT / "data/processed",
        ROOT / "data/interim",
    ]:

        if not base.exists():
            continue

        for path in base.rglob("*.csv"):

            ptext = str(path).lower()

            # Do not waste time opening the giant audit/report forests.
            if any(
                token in ptext
                for token in [
                    "audit_results",
                    "combined_detail",
                    "reporting\\additional_awards_clean_query",
                    "reporting/additional_awards_clean_query",
                ]
            ):
                continue

            try:
                columns = list(
                    pd.read_csv(
                        path,
                        nrows=0,
                    ).columns
                )

            except Exception:
                continue

            lower = {
                str(c).lower(): c
                for c in columns
            }

            course_cols = [
                original
                for lowered, original
                in lower.items()
                if (
                    lowered in {
                        "course_code",
                        "course",
                        "normalized_course_code",
                        "course_id",
                        "course_number_full",
                        "option_value",
                    }
                    or (
                        "course" in lowered
                        and "code" in lowered
                    )
                )
            ]

            cip_cols = [
                original
                for lowered, original
                in lower.items()
                if (
                    lowered == "cip"
                    or "cip_code" in lowered
                    or lowered.endswith("_cip")
                    or lowered.startswith("cip_")
                )
            ]

            if course_cols and cip_cols:
                candidates.append(
                    (
                        path,
                        course_cols[0],
                        cip_cols[0],
                    )
                )

    best = pd.DataFrame(
        columns=[
            "course_code",
            "course_cip",
        ]
    )

    best_source = ""

    for path, course_col, cip_col in candidates:

        try:
            frame = pd.read_csv(
                path,
                usecols=[
                    course_col,
                    cip_col,
                ],
                dtype=str,
                low_memory=False,
            ).fillna("")

        except Exception:
            continue

        frame["course_code"] = (
            frame[course_col]
            .map(normalize_course)
        )

        frame["course_cip"] = (
            frame[cip_col]
            .map(text)
        )

        frame = (
            frame[
                frame["course_code"].ne("")
                & frame["course_cip"].ne("")
            ][
                [
                    "course_code",
                    "course_cip",
                ]
            ]
            .drop_duplicates()
        )

        if len(frame) > len(best):
            best = frame
            best_source = str(path)

    return best, best_source


# =============================================================================
# CREDENTIAL SIGNATURES FROM CATALOG REQUIREMENTS
# =============================================================================

def build_signatures(
    requirements,
    modeled,
    course_cip,
):

    required = {
        "catalog_year",
        "credential_id",
    }

    missing = (
        required
        - set(requirements.columns)
    )

    if missing:
        raise RuntimeError(
            "Requirements file missing: "
            + ", ".join(
                sorted(missing)
            )
        )

    lineage_col = find_column(
        modeled,
        [
            "canonical_lineage",
            "credential_lineage",
        ],
    )

    lineage_map = (
        modeled[
            [
                "catalog_year",
                "credential_id",
                lineage_col,
            ]
        ]
        .rename(
            columns={
                lineage_col:
                    "canonical_lineage"
            }
        )
        .drop_duplicates()
    )

    conflicts = (
        lineage_map
        .groupby(
            [
                "catalog_year",
                "credential_id",
            ]
        )["canonical_lineage"]
        .nunique()
    )

    if (conflicts > 1).any():
        raise RuntimeError(
            "Modeled credential-year maps "
            "to multiple canonical lineages."
        )

    lineage_map = (
        lineage_map
        .drop_duplicates(
            [
                "catalog_year",
                "credential_id",
            ],
            keep="first",
        )
    )

    cip_map = defaultdict(set)

    for row in course_cip.itertuples(
        index=False
    ):
        cip_map[
            text(row.course_code)
        ].add(
            text(row.course_cip)
        )

    course_source_columns = [
        column
        for column in [
            "option_value",
            "course_codes",
            "raw_requirement_text",
            "source_requirement_text",
        ]
        if column in requirements.columns
    ]

    if not course_source_columns:
        raise RuntimeError(
            "Requirements file contains no "
            "recognizable course-code source columns."
        )

    work = requirements.copy()

    def row_courses(row):

        found = set()

        for column in course_source_columns:
            found |= split_courses(
                row.get(column, "")
            )

        return found

    work["_courses"] = (
        work.apply(
            row_courses,
            axis=1,
        )
    )

    title_col = find_column(
        work,
        [
            "credential_title",
            "program_title",
            "title",
        ],
        required=False,
    )

    rows = []

    for (
        year,
        credential_id,
    ), group in work.groupby(
        [
            "catalog_year",
            "credential_id",
        ],
        dropna=False,
    ):

        courses = set()

        for item in group["_courses"]:
            courses |= set(item)

        rubrics = {
            rubric(course)
            for course in courses
            if rubric(course)
        }

        cips = set()

        for course in courses:
            cips |= cip_map.get(
                course,
                set(),
            )

        title = (
            first_nonblank(
                group[title_col]
            )
            if title_col
            else ""
        )

        rows.append(
            {
                "catalog_year":
                    text(year),

                "credential_id":
                    text(credential_id),

                "credential_title":
                    title,

                "course_universe":
                    " | ".join(
                        sorted(courses)
                    ),

                "rubric_universe":
                    " | ".join(
                        sorted(rubrics)
                    ),

                "cip_universe":
                    " | ".join(
                        sorted(cips)
                    ),

                "course_count":
                    len(courses),

                "rubric_count":
                    len(rubrics),

                "cip_count":
                    len(cips),
            }
        )

    signatures = (
        pd.DataFrame(rows)
        .merge(
            lineage_map,
            on=[
                "catalog_year",
                "credential_id",
            ],
            how="left",
            validate="one_to_one",
        )
    )

    signatures[
        "canonical_lineage"
    ] = (
        signatures[
            "canonical_lineage"
        ]
        .fillna("")
        .map(norm)
    )

    return signatures


# =============================================================================
# STRUCTURAL COMPARISON
# =============================================================================

def compare_signature_rows(
    target,
    candidate,
):

    target_courses = set_from_pipe(
        target.get(
            "course_universe",
            "",
        )
    )

    candidate_courses = set_from_pipe(
        candidate.get(
            "course_universe",
            "",
        )
    )

    target_rubrics = set_from_pipe(
        target.get(
            "rubric_universe",
            "",
        )
    )

    candidate_rubrics = set_from_pipe(
        candidate.get(
            "rubric_universe",
            "",
        )
    )

    target_cips = set_from_pipe(
        target.get(
            "cip_universe",
            "",
        )
    )

    candidate_cips = set_from_pipe(
        candidate.get(
            "cip_universe",
            "",
        )
    )

    return {
        "course_jaccard":
            round(
                jaccard(
                    target_courses,
                    candidate_courses,
                ),
                4,
            ),

        "target_course_coverage":
            round(
                coverage(
                    target_courses,
                    candidate_courses,
                ),
                4,
            ),

        "candidate_course_coverage":
            round(
                coverage(
                    candidate_courses,
                    target_courses,
                ),
                4,
            ),

        "rubric_jaccard":
            round(
                jaccard(
                    target_rubrics,
                    candidate_rubrics,
                ),
                4,
            ),

        "cip_jaccard":
            round(
                jaccard(
                    target_cips,
                    candidate_cips,
                ),
                4,
            ),

        "shared_courses":
            " | ".join(
                sorted(
                    target_courses
                    & candidate_courses
                )
            ),

        "target_only_courses":
            " | ".join(
                sorted(
                    target_courses
                    - candidate_courses
                )
            ),

        "candidate_only_courses":
            " | ".join(
                sorted(
                    candidate_courses
                    - target_courses
                )
            ),

        "shared_cips":
            " | ".join(
                sorted(
                    target_cips
                    & candidate_cips
                )
            ),

        "title_similarity":
            round(
                title_similarity(
                    target.get(
                        "credential_title",
                        "",
                    ),
                    candidate.get(
                        "credential_title",
                        "",
                    ),
                ),
                4,
            ),
    }


def best_lineage_match(
    target,
    candidate_lineage,
    signatures,
):

    pool = signatures[
        signatures[
            "canonical_lineage"
        ]
        .map(norm)
        .eq(
            norm(candidate_lineage)
        )
    ]

    if pool.empty:
        return {
            "best_candidate_catalog_year": "",
            "best_candidate_credential_id": "",
            "best_candidate_title": "",
            "course_jaccard": 0.0,
            "target_course_coverage": 0.0,
            "candidate_course_coverage": 0.0,
            "rubric_jaccard": 0.0,
            "cip_jaccard": 0.0,
            "title_similarity": 0.0,
            "shared_courses": "",
            "target_only_courses":
                text(
                    target.get(
                        "course_universe",
                        "",
                    )
                ),
            "candidate_only_courses": "",
            "shared_cips": "",
        }

    scored = []

    for _, candidate in pool.iterrows():

        metrics = (
            compare_signature_rows(
                target,
                candidate,
            )
        )

        ranking = (
            metrics["course_jaccard"],
            metrics[
                "target_course_coverage"
            ],
            metrics[
                "candidate_course_coverage"
            ],
            metrics["rubric_jaccard"],
            metrics["cip_jaccard"],
            metrics["title_similarity"],
        )

        scored.append(
            (
                ranking,
                candidate,
                metrics,
            )
        )

    _, candidate, metrics = max(
        scored,
        key=lambda x: x[0],
    )

    return {
        "best_candidate_catalog_year":
            text(
                candidate[
                    "catalog_year"
                ]
            ),

        "best_candidate_credential_id":
            text(
                candidate[
                    "credential_id"
                ]
            ),

        "best_candidate_title":
            text(
                candidate[
                    "credential_title"
                ]
            ),

        **metrics,
    }


def review_bucket(
    target_lineage,
    official_lineage,
    metrics,
):

    if (
        norm(target_lineage)
        == norm(official_lineage)
    ):
        return (
            "00_EXACT_LINEAGE_"
            "SHOULD_HAVE_DEDUPED"
        )

    course_j = float(
        metrics.get(
            "course_jaccard",
            0,
        )
        or 0
    )

    target_cov = float(
        metrics.get(
            "target_course_coverage",
            0,
        )
        or 0
    )

    candidate_cov = float(
        metrics.get(
            "candidate_course_coverage",
            0,
        )
        or 0
    )

    rubric_j = float(
        metrics.get(
            "rubric_jaccard",
            0,
        )
        or 0
    )

    cip_j = float(
        metrics.get(
            "cip_jaccard",
            0,
        )
        or 0
    )

    title_sim = float(
        metrics.get(
            "title_similarity",
            0,
        )
        or 0
    )

    if (
        course_j >= 0.80
        and target_cov >= 0.80
        and candidate_cov >= 0.80
    ):
        return (
            "10_HIGH_SAME_LINEAGE_CANDIDATE"
        )

    if (
        target_cov >= 0.90
        and candidate_cov < 0.80
    ):
        return (
            "20_POSSIBLE_TARGET_"
            "NESTED_IN_AWARD"
        )

    if (
        candidate_cov >= 0.90
        and target_cov < 0.80
    ):
        return (
            "21_POSSIBLE_AWARD_"
            "NESTED_IN_TARGET"
        )

    if (
        course_j >= 0.50
        or rubric_j >= 0.70
        or cip_j >= 0.60
        or title_sim >= 0.75
    ):
        return "30_RELATED_REVIEW"

    return "90_LOW_SIMILARITY"


# =============================================================================
# EXCEL FORMATTING
# =============================================================================

def write_sheet(
    writer,
    name,
    frame,
    human_review=False,
):

    frame.to_excel(
        writer,
        sheet_name=name,
        index=False,
    )

    worksheet = (
        writer.sheets[name]
    )

    workbook = writer.book

    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#00573F",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )

    body = workbook.add_format(
        {
            "border": 1,
            "valign": "top",
        }
    )

    wrap = workbook.add_format(
        {
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )

    review = workbook.add_format(
        {
            "border": 1,
            "text_wrap": True,
            "valign": "top",
            "bg_color": "#FFF2CC",
        }
    )

    worksheet.freeze_panes(
        1,
        0,
    )

    if len(frame.columns):
        worksheet.autofilter(
            0,
            0,
            max(
                len(frame),
                1,
            ),
            len(frame.columns) - 1,
        )

    worksheet.set_row(
        0,
        34,
        header,
    )

    review_columns = {
        "human_decision",
        "canonical_lineage_to_use",
        "awarded_represents_detected",
        "detected_remains_additional_award",
        "relationship_type",
        "review_note",
    }

    for index, column in enumerate(
        frame.columns
    ):

        sample = (
            frame[column]
            .astype(str)
            .head(1000)
        )

        lengths = (
            sample
            .fillna("")
            .astype(str)
            .str.len()
        )

        q_raw = lengths.quantile(0.90)

        q = (
            10
            if pd.isna(q_raw)
            else int(q_raw)
        )

        width = min(
            max(
                len(column) + 2,
                q + 2,
                10,
            ),
            42,
        )

        cell_format = (
            review
            if (
                human_review
                and column
                in review_columns
            )
            else (
                wrap
                if width >= 28
                else body
            )
        )

        worksheet.set_column(
            index,
            index,
            width,
            cell_format,
        )

    if (
        human_review
        and "human_decision"
        in frame.columns
        and len(frame)
    ):

        column = (
            frame.columns.get_loc(
                "human_decision"
            )
        )

        worksheet.data_validation(
            1,
            column,
            len(frame),
            column,
            {
                "validate": "list",
                "source": [
                    "SAME_CANONICAL_LINEAGE",
                    "AWARD_REPRESENTS_DETECTED",
                    "NESTED_BOTH_REMAIN_AWARDABLE",
                    "SEPARATE_CREDENTIALS",
                    "NEEDS_REVIEW",
                ],
            },
        )


# =============================================================================
# MAIN
# =============================================================================

def main():

    print("=" * 118)
    print(
        "CERTIFICATE LINEAGE — "
        "BRUTE FORCE HUMAN REVIEW"
    )
    print("=" * 118)

    requirements_path = (
        choose_requirements_path()
    )

    additional = read_csv(
        ADDITIONAL_PATH
    )

    selected = read_csv(
        SELECTED_PATH
    )

    alternatives = read_csv(
        ALTERNATIVES_PATH
    )

    official = read_csv(
        OFFICIAL_PATH
    )

    representation = read_csv(
        REPRESENTATION_PATH
    )

    modeled = read_csv(
        MODELED_LINEAGE_PATH
    )

    requirements = read_csv(
        requirements_path
    )

    for frame in [
        additional,
        selected,
        alternatives,
        official,
        representation,
        modeled,
    ]:

        if "student_id" in frame.columns:
            frame["student_id"] = (
                frame["student_id"]
                .map(norm_id)
            )

    additional_lineage_col = (
        find_column(
            additional,
            [
                "detected_lineage",
                "canonical_lineage",
                "credential_lineage",
            ],
        )
    )

    selected_lineage_col = (
        find_column(
            selected,
            [
                "canonical_lineage",
                "detected_lineage",
                "credential_lineage",
            ],
        )
    )

    alternatives_lineage_col = (
        find_column(
            alternatives,
            [
                "canonical_lineage",
                "detected_lineage",
                "credential_lineage",
            ],
        )
    )

    additional["target_lineage"] = (
        additional[
            additional_lineage_col
        ].map(norm)
    )

    selected["detected_lineage"] = (
        selected[
            selected_lineage_col
        ].map(norm)
    )

    alternatives[
        "detected_lineage"
    ] = (
        alternatives[
            alternatives_lineage_col
        ].map(norm)
    )

    official[
        "institutional_lineage"
    ] = (
        official[
            "institutional_lineage"
        ].map(norm)
    )

    representation[
        "detected_lineage"
    ] = (
        representation[
            "detected_lineage"
        ].map(norm)
    )

    print(
        "Current downstream detected-"
        f"unawarded rows: {len(additional):,}"
    )

    print(
        "Students in downstream detected-"
        "unawarded set: "
        f"{additional['student_id'].nunique():,}"
    )

    # -------------------------------------------------------------------------
    # CIP
    # -------------------------------------------------------------------------

    course_cip, cip_source = (
        discover_course_cip_lookup()
    )

    print(
        "Course-CIP lookup: "
        + (
            cip_source
            if cip_source
            else (
                "NONE FOUND — "
                "continuing without CIP"
            )
        )
    )

    print(
        "Course-CIP rows available: "
        f"{len(course_cip):,}"
    )

    signatures = build_signatures(
        requirements,
        modeled,
        course_cip,
    )

    # -------------------------------------------------------------------------
    # TARGET METADATA
    # -------------------------------------------------------------------------

    signature_join = (
        signatures.rename(
            columns={
                "canonical_lineage":
                    "signature_lineage",
                "credential_title":
                    "signature_title",
            }
        )
    )

    additional = additional.merge(
        signature_join,
        on=[
            "catalog_year",
            "credential_id",
        ],
        how="left",
        validate="many_to_one",
    )

    if (
        "credential_title"
        not in additional.columns
    ):
        additional[
            "credential_title"
        ] = ""

    additional[
        "credential_title"
    ] = (
        additional[
            "credential_title"
        ].where(
            additional[
                "credential_title"
            ].map(text).ne(""),
            additional[
                "signature_title"
            ].fillna(""),
        )
    )

    if (
        "credential_type"
        not in additional.columns
    ):
        additional[
            "credential_type"
        ] = ""

    additional[
        "is_associate"
    ] = [
        is_associate(
            title,
            credential_id,
            lineage,
            credential_type,
        )
        for (
            title,
            credential_id,
            lineage,
            credential_type,
        ) in zip(
            additional[
                "credential_title"
            ],
            additional[
                "credential_id"
            ],
            additional[
                "target_lineage"
            ],
            additional[
                "credential_type"
            ],
        )
    ]

    excluded_associates = (
        additional[
            additional[
                "is_associate"
            ]
        ].copy()
    )

    targets = (
        additional[
            ~additional[
                "is_associate"
            ]
        ].copy()
    )

    print(
        "Associate/degree targets "
        "set aside for now: "
        f"{len(excluded_associates):,}"
    )

    print(
        "Non-associate targets carried "
        "into certificate review: "
        f"{len(targets):,}"
    )

    # -------------------------------------------------------------------------
    # BRING FORWARD ALL COMPLETED CATALOG YEARS
    # -------------------------------------------------------------------------

    alt_catalogs = (
        alternatives
        .groupby(
            [
                "student_id",
                "detected_lineage",
            ],
            dropna=False,
        )
        .agg(
            all_completed_catalog_years=(
                "catalog_year",
                join_unique,
            ),
            all_completed_credential_ids=(
                "credential_id",
                join_unique,
            ),
        )
        .reset_index()
    )

    targets = targets.merge(
        alt_catalogs.rename(
            columns={
                "detected_lineage":
                    "target_lineage"
            }
        ),
        on=[
            "student_id",
            "target_lineage",
        ],
        how="left",
        validate="many_to_one",
    )

    # -------------------------------------------------------------------------
    # OFFICIAL CERTIFICATE-LIKE AWARDS
    # -------------------------------------------------------------------------

    for column in [
        "award_level",
        "DegreeCode",
        "DegreeDesc",
        "MajorDesc",
    ]:
        if column not in official.columns:
            official[column] = ""

    official[
        "is_associate"
    ] = [
        is_associate(
            level,
            degree_code,
            degree_desc,
            lineage,
        )
        for (
            level,
            degree_code,
            degree_desc,
            lineage,
        ) in zip(
            official[
                "award_level"
            ],
            official[
                "DegreeCode"
            ],
            official[
                "DegreeDesc"
            ],
            official[
                "institutional_lineage"
            ],
        )
    ]

    official_cert = (
        official[
            ~official[
                "is_associate"
            ]
        ].copy()
    )

    def aggregate_if_present(
        group,
        column,
    ):
        return (
            join_unique(
                group[column]
            )
            if column
            in group.columns
            else ""
        )

    official_rows = []

    for (
        student_id,
        lineage,
    ), group in official_cert.groupby(
        [
            "student_id",
            "institutional_lineage",
        ],
        dropna=False,
    ):

        official_rows.append(
            {
                "student_id":
                    student_id,

                "institutional_lineage":
                    lineage,

                "official_award_level":
                    aggregate_if_present(
                        group,
                        "award_level",
                    ),

                "official_program_codes":
                    aggregate_if_present(
                        group,
                        "Curr1ProgramCode",
                    ),

                "official_major_codes":
                    aggregate_if_present(
                        group,
                        "Major1Code",
                    ),

                "official_degree_codes":
                    aggregate_if_present(
                        group,
                        "DegreeCode",
                    ),

                "official_major_titles":
                    aggregate_if_present(
                        group,
                        "MajorDesc",
                    ),

                "official_degree_titles":
                    aggregate_if_present(
                        group,
                        "DegreeDesc",
                    ),

                "official_grad_terms":
                    aggregate_if_present(
                        group,
                        "StudGradTerm",
                    ),

                "official_grad_dates":
                    aggregate_if_present(
                        group,
                        "GradDate",
                    ),
            }
        )

    official_collapsed = (
        pd.DataFrame(
            official_rows
        )
    )

    # Was this official lineage ALSO detected
    # for this student, and in which catalogs?

    official_detected_history = (
        alt_catalogs.rename(
            columns={
                "detected_lineage":
                    "institutional_lineage",

                "all_completed_catalog_years":
                    "official_lineage_"
                    "detected_catalog_years",

                "all_completed_credential_ids":
                    "official_lineage_"
                    "detected_credential_ids",
            }
        )
    )

    official_collapsed = (
        official_collapsed.merge(
            official_detected_history,
            on=[
                "student_id",
                "institutional_lineage",
            ],
            how="left",
            validate="one_to_one",
        )
    )

    official_collapsed[
        "official_lineage_"
        "detected_for_student"
    ] = (
        official_collapsed[
            "official_lineage_"
            "detected_catalog_years"
        ]
        .fillna("")
        .ne("")
    )

    # -------------------------------------------------------------------------
    # TARGET × OFFICIAL CERTIFICATE EVIDENCE
    # -------------------------------------------------------------------------

    evidence_rows = []

    official_by_student = {
        student_id:
            group.copy()

        for (
            student_id,
            group,
        ) in official_collapsed.groupby(
            "student_id"
        )
    }

    for _, target in targets.iterrows():

        student_id = (
            target[
                "student_id"
            ]
        )

        awards = (
            official_by_student.get(
                student_id
            )
        )

        base = {
            "student_id":
                student_id,

            "target_catalog_year":
                text(
                    target.get(
                        "catalog_year",
                        "",
                    )
                ),

            "target_all_completed_catalog_years":
                text(
                    target.get(
                        "all_completed_catalog_years",
                        "",
                    )
                ),

            "target_credential_id":
                text(
                    target.get(
                        "credential_id",
                        "",
                    )
                ),

            "target_all_completed_credential_ids":
                text(
                    target.get(
                        "all_completed_credential_ids",
                        "",
                    )
                ),

            "target_title":
                text(
                    target.get(
                        "credential_title",
                        "",
                    )
                ),

            "target_lineage":
                text(
                    target.get(
                        "target_lineage",
                        "",
                    )
                ),

            "target_completion_academic_year":
                text(
                    target.get(
                        "query_completion_academic_year",
                        target.get(
                            "completion_academic_year",
                            "",
                        ),
                    )
                ),

            "target_course_universe":
                text(
                    target.get(
                        "course_universe",
                        "",
                    )
                ),

            "target_cip_universe":
                text(
                    target.get(
                        "cip_universe",
                        "",
                    )
                ),
        }

        if (
            awards is None
            or awards.empty
        ):

            evidence_rows.append(
                {
                    **base,

                    "institutional_lineage":
                        "",

                    "official_major_titles":
                        "",

                    "official_program_codes":
                        "",

                    "official_major_codes":
                        "",

                    "official_degree_codes":
                        "",

                    "official_grad_terms":
                        "",

                    "official_grad_dates":
                        "",

                    "official_lineage_"
                    "detected_for_student":
                        False,

                    "official_lineage_"
                    "detected_catalog_years":
                        "",

                    "best_candidate_catalog_year":
                        "",

                    "best_candidate_credential_id":
                        "",

                    "best_candidate_title":
                        "",

                    "course_jaccard":
                        0.0,

                    "target_course_coverage":
                        0.0,

                    "candidate_course_coverage":
                        0.0,

                    "rubric_jaccard":
                        0.0,

                    "cip_jaccard":
                        0.0,

                    "title_similarity":
                        0.0,

                    "shared_courses":
                        "",

                    "target_only_courses":
                        text(
                            target.get(
                                "course_universe",
                                "",
                            )
                        ),

                    "candidate_only_courses":
                        "",

                    "shared_cips":
                        "",

                    "review_bucket":
                        "99_NO_OFFICIAL_"
                        "CERTIFICATE_ON_STUDENT",
                }
            )

            continue

        for _, award in awards.iterrows():

            metrics = (
                best_lineage_match(
                    target,
                    award[
                        "institutional_lineage"
                    ],
                    signatures,
                )
            )

            bucket = review_bucket(
                target[
                    "target_lineage"
                ],
                award[
                    "institutional_lineage"
                ],
                metrics,
            )

            evidence_rows.append(
                {
                    **base,

                    "institutional_lineage":
                        award[
                            "institutional_lineage"
                        ],

                    "official_award_level":
                        award.get(
                            "official_award_level",
                            "",
                        ),

                    "official_major_titles":
                        award.get(
                            "official_major_titles",
                            "",
                        ),

                    "official_degree_titles":
                        award.get(
                            "official_degree_titles",
                            "",
                        ),

                    "official_program_codes":
                        award.get(
                            "official_program_codes",
                            "",
                        ),

                    "official_major_codes":
                        award.get(
                            "official_major_codes",
                            "",
                        ),

                    "official_degree_codes":
                        award.get(
                            "official_degree_codes",
                            "",
                        ),

                    "official_grad_terms":
                        award.get(
                            "official_grad_terms",
                            "",
                        ),

                    "official_grad_dates":
                        award.get(
                            "official_grad_dates",
                            "",
                        ),

                    "official_lineage_"
                    "detected_for_student":
                        award.get(
                            "official_lineage_"
                            "detected_for_student",
                            False,
                        ),

                    "official_lineage_"
                    "detected_catalog_years":
                        award.get(
                            "official_lineage_"
                            "detected_catalog_years",
                            "",
                        ),

                    "official_lineage_"
                    "detected_credential_ids":
                        award.get(
                            "official_lineage_"
                            "detected_credential_ids",
                            "",
                        ),

                    **metrics,

                    "review_bucket":
                        bucket,
                }
            )

    student_evidence = (
        pd.DataFrame(
            evidence_rows
        )
    )

    # -------------------------------------------------------------------------
    # AGGREGATED HUMAN REVIEW:
    # TARGET LINEAGE × EXISTING OFFICIAL LINEAGE
    # -------------------------------------------------------------------------

    pair_source = (
        student_evidence[
            student_evidence[
                "institutional_lineage"
            ].ne("")
        ].copy()
    )

    if pair_source.empty:

        pair_review = (
            pd.DataFrame()
        )

    else:

        pair_review = (
            pair_source
            .groupby(
                [
                    "target_lineage",
                    "institutional_lineage",
                ],
                dropna=False,
            )
            .agg(
                cooccurring_students=(
                    "student_id",
                    "nunique",
                ),

                target_catalog_years=(
                    "target_catalog_year",
                    join_unique,
                ),

                target_all_completed_catalog_years=(
                    "target_all_completed_catalog_years",
                    join_unique,
                ),

                target_titles=(
                    "target_title",
                    join_unique,
                ),

                target_credential_ids=(
                    "target_credential_id",
                    join_unique,
                ),

                official_major_titles=(
                    "official_major_titles",
                    join_unique,
                ),

                official_program_codes=(
                    "official_program_codes",
                    join_unique,
                ),

                official_major_codes=(
                    "official_major_codes",
                    join_unique,
                ),

                official_degree_codes=(
                    "official_degree_codes",
                    join_unique,
                ),

                official_grad_terms=(
                    "official_grad_terms",
                    join_unique,
                ),

                official_detected_catalog_years=(
                    "official_lineage_"
                    "detected_catalog_years",
                    join_unique,
                ),

                best_candidate_catalog_years=(
                    "best_candidate_catalog_year",
                    join_unique,
                ),

                best_candidate_titles=(
                    "best_candidate_title",
                    join_unique,
                ),

                max_course_jaccard=(
                    "course_jaccard",
                    "max",
                ),

                max_target_course_coverage=(
                    "target_course_coverage",
                    "max",
                ),

                max_candidate_course_coverage=(
                    "candidate_course_coverage",
                    "max",
                ),

                max_rubric_jaccard=(
                    "rubric_jaccard",
                    "max",
                ),

                max_cip_jaccard=(
                    "cip_jaccard",
                    "max",
                ),

                max_title_similarity=(
                    "title_similarity",
                    "max",
                ),

                shared_courses=(
                    "shared_courses",
                    join_unique,
                ),

                shared_cips=(
                    "shared_cips",
                    join_unique,
                ),

                review_bucket=(
                    "review_bucket",
                    "min",
                ),
            )
            .reset_index()
        )

        # These are intentionally blank.
        # HUMAN fills them.
        pair_review[
            "human_decision"
        ] = ""

        pair_review[
            "canonical_lineage_to_use"
        ] = ""

        pair_review[
            "awarded_represents_detected"
        ] = ""

        pair_review[
            "detected_remains_additional_award"
        ] = ""

        pair_review[
            "relationship_type"
        ] = ""

        pair_review[
            "review_note"
        ] = ""

        pair_review = (
            pair_review
            .sort_values(
                [
                    "review_bucket",
                    "cooccurring_students",
                    "max_course_jaccard",
                    "max_target_course_coverage",
                ],
                ascending=[
                    True,
                    False,
                    False,
                    False,
                ],
            )
            .reset_index(
                drop=True
            )
        )

    # -------------------------------------------------------------------------
    # ALL DETECTED CERTIFICATES FOR TARGET STUDENTS
    #
    # THIS INCLUDES ONES ALREADY REPRESENTED BY AN OFFICIAL AWARD.
    # -------------------------------------------------------------------------

    selected = selected.merge(
        signatures.rename(
            columns={
                "canonical_lineage":
                    "signature_lineage"
            }
        ),
        on=[
            "catalog_year",
            "credential_id",
        ],
        how="left",
        validate="many_to_one",
        suffixes=(
            "",
            "_sig",
        ),
    )

    if (
        "credential_title"
        not in selected.columns
    ):
        selected[
            "credential_title"
        ] = ""

    if (
        "credential_title_sig"
        in selected.columns
    ):

        selected[
            "credential_title"
        ] = (
            selected[
                "credential_title"
            ].where(
                selected[
                    "credential_title"
                ].map(text).ne(""),
                selected[
                    "credential_title_sig"
                ].fillna(""),
            )
        )

    if (
        "credential_type"
        not in selected.columns
    ):
        selected[
            "credential_type"
        ] = ""

    selected[
        "is_associate"
    ] = [
        is_associate(
            title,
            credential_id,
            lineage,
            credential_type,
        )
        for (
            title,
            credential_id,
            lineage,
            credential_type,
        ) in zip(
            selected[
                "credential_title"
            ],
            selected[
                "credential_id"
            ],
            selected[
                "detected_lineage"
            ],
            selected[
                "credential_type"
            ],
        )
    ]

    selected_cert = (
        selected[
            ~selected[
                "is_associate"
            ]
        ].copy()
    )

    selected_cert = (
        selected_cert.merge(
            alt_catalogs,
            on=[
                "student_id",
                "detected_lineage",
            ],
            how="left",
            validate="many_to_one",
        )
    )

    additional_keys = set(
        zip(
            targets[
                "student_id"
            ],
            targets[
                "target_lineage"
            ],
        )
    )

    represented_keys = set(
        zip(
            representation[
                "student_id"
            ],
            representation[
                "detected_lineage"
            ],
        )
    )

    def stack_status(row):

        key = (
            row["student_id"],
            row["detected_lineage"],
        )

        if key in additional_keys:
            return (
                "DETECTED_UNAWARDED"
            )

        if key in represented_keys:
            return (
                "REPRESENTED_BY_"
                "OFFICIAL_AWARD"
            )

        return (
            "SELECTED_UNCLASSIFIED"
        )

    selected_cert[
        "reconciliation_status"
    ] = selected_cert.apply(
        stack_status,
        axis=1,
    )

    target_students = set(
        targets[
            "student_id"
        ]
    )

    target_stack = (
        selected_cert[
            selected_cert[
                "student_id"
            ].isin(
                target_students
            )
        ].copy()
    )

    target_stack_columns = [
        column
        for column in [
            "student_id",
            "reconciliation_status",
            "catalog_year",
            "all_completed_catalog_years",
            "credential_id",
            "all_completed_credential_ids",
            "credential_title",
            "detected_lineage",
            "completion_academic_year",
            "query_completion_academic_year",
            "course_universe",
            "cip_universe",
        ]
        if column
        in target_stack.columns
    ]

    target_stack = (
        target_stack[
            target_stack_columns
        ]
        .sort_values(
            [
                "student_id",
                "reconciliation_status",
                "detected_lineage",
            ]
        )
    )

    # -------------------------------------------------------------------------
    # ALL STUDENTS WITH >1 DETECTED NON-ASSOCIATE CREDENTIAL
    #
    # THIS IS THE BRUTE FORCE POPULATION.
    # AWARDED STATUS DOES NOT REMOVE THEM.
    # -------------------------------------------------------------------------

    multi_counts = (
        selected_cert
        .groupby(
            "student_id"
        )["detected_lineage"]
        .nunique()
    )

    multi_students = set(
        multi_counts[
            multi_counts > 1
        ].index
    )

    multi_stack = (
        selected_cert[
            selected_cert[
                "student_id"
            ].isin(
                multi_students
            )
        ].copy()
    )

    multi_stack_columns = [
        column
        for column in [
            "student_id",
            "reconciliation_status",
            "catalog_year",
            "all_completed_catalog_years",
            "credential_id",
            "credential_title",
            "detected_lineage",
            "completion_academic_year",
            "course_universe",
            "cip_universe",
        ]
        if column
        in multi_stack.columns
    ]

    multi_stack = (
        multi_stack[
            multi_stack_columns
        ]
        .sort_values(
            [
                "student_id",
                "detected_lineage",
            ]
        )
    )

    # -------------------------------------------------------------------------
    # CO-DETECTED LINEAGE PAIRS
    # -------------------------------------------------------------------------

    pair_counts = defaultdict(
        set
    )

    for (
        student_id,
        group,
    ) in multi_stack.groupby(
        "student_id"
    ):

        lineages = sorted(
            set(
                group[
                    "detected_lineage"
                ]
            )
        )

        for a, b in combinations(
            lineages,
            2,
        ):
            pair_counts[
                (
                    a,
                    b,
                )
            ].add(
                student_id
            )

    comparison_cache = {}

    def compare_lineages(
        lineage_a,
        lineage_b,
    ):

        key = tuple(
            sorted(
                (
                    lineage_a,
                    lineage_b,
                )
            )
        )

        if key in comparison_cache:
            return (
                comparison_cache[
                    key
                ]
            )

        a_pool = signatures[
            signatures[
                "canonical_lineage"
            ].eq(
                lineage_a
            )
        ]

        b_pool = signatures[
            signatures[
                "canonical_lineage"
            ].eq(
                lineage_b
            )
        ]

        if (
            a_pool.empty
            or b_pool.empty
        ):

            result = {
                "best_a_catalog_year": "",
                "best_b_catalog_year": "",
                "best_a_title": "",
                "best_b_title": "",
                "course_jaccard": 0.0,
                "a_course_coverage": 0.0,
                "b_course_coverage": 0.0,
                "rubric_jaccard": 0.0,
                "cip_jaccard": 0.0,
                "shared_courses": "",
                "shared_cips": "",
            }

            comparison_cache[
                key
            ] = result

            return result

        scored = []

        for _, a_row in a_pool.iterrows():

            for _, b_row in b_pool.iterrows():

                metrics = (
                    compare_signature_rows(
                        a_row,
                        b_row,
                    )
                )

                ranking = (
                    metrics[
                        "course_jaccard"
                    ],
                    metrics[
                        "target_course_coverage"
                    ],
                    metrics[
                        "candidate_course_coverage"
                    ],
                    metrics[
                        "rubric_jaccard"
                    ],
                    metrics[
                        "cip_jaccard"
                    ],
                )

                scored.append(
                    (
                        ranking,
                        a_row,
                        b_row,
                        metrics,
                    )
                )

        (
            _,
            a_row,
            b_row,
            metrics,
        ) = max(
            scored,
            key=lambda item:
                item[0],
        )

        result = {
            "best_a_catalog_year":
                a_row[
                    "catalog_year"
                ],

            "best_b_catalog_year":
                b_row[
                    "catalog_year"
                ],

            "best_a_title":
                a_row[
                    "credential_title"
                ],

            "best_b_title":
                b_row[
                    "credential_title"
                ],

            "course_jaccard":
                metrics[
                    "course_jaccard"
                ],

            "a_course_coverage":
                metrics[
                    "target_course_coverage"
                ],

            "b_course_coverage":
                metrics[
                    "candidate_course_coverage"
                ],

            "rubric_jaccard":
                metrics[
                    "rubric_jaccard"
                ],

            "cip_jaccard":
                metrics[
                    "cip_jaccard"
                ],

            "shared_courses":
                metrics[
                    "shared_courses"
                ],

            "shared_cips":
                metrics[
                    "shared_cips"
                ],
        }

        comparison_cache[
            key
        ] = result

        return result

    detected_pair_rows = []

    for (
        lineage_a,
        lineage_b,
    ), students in pair_counts.items():

        metrics = (
            compare_lineages(
                lineage_a,
                lineage_b,
            )
        )

        detected_pair_rows.append(
            {
                "lineage_a":
                    lineage_a,

                "lineage_b":
                    lineage_b,

                "co_detected_students":
                    len(students),

                **metrics,

                "human_decision":
                    "",

                "canonical_lineage_to_use":
                    "",

                "relationship_type":
                    "",

                "review_note":
                    "",
            }
        )

    detected_pairs = (
        pd.DataFrame(
            detected_pair_rows
        )
    )

    if not detected_pairs.empty:

        detected_pairs = (
            detected_pairs
            .sort_values(
                [
                    "course_jaccard",
                    "co_detected_students",
                    "a_course_coverage",
                ],
                ascending=[
                    False,
                    False,
                    False,
                ],
            )
            .reset_index(
                drop=True
            )
        )

    # -------------------------------------------------------------------------
    # CONTROL
    # -------------------------------------------------------------------------

    no_official = (
        student_evidence[
            student_evidence[
                "review_bucket"
            ].eq(
                "99_NO_OFFICIAL_"
                "CERTIFICATE_ON_STUDENT"
            )
        ].copy()
    )

    control = pd.DataFrame(
        [
            [
                "Downstream detected-unawarded rows",
                len(additional),
            ],
            [
                "Downstream detected-unawarded students",
                additional[
                    "student_id"
                ].nunique(),
            ],
            [
                "Associate/degree targets excluded this pass",
                len(
                    excluded_associates
                ),
            ],
            [
                "Non-associate targets reviewed",
                len(targets),
            ],
            [
                "Non-associate target students",
                targets[
                    "student_id"
                ].nunique(),
            ],
            [
                "Target × official certificate evidence rows",
                len(
                    student_evidence
                ),
            ],
            [
                "Distinct target × official lineage review pairs",
                len(
                    pair_review
                ),
            ],
            [
                "Targets with no official non-associate award on student",
                len(
                    no_official
                ),
            ],
            [
                "All students with >1 detected non-associate lineage",
                len(
                    multi_students
                ),
            ],
            [
                "All co-detected lineage pairs",
                len(
                    detected_pairs
                ),
            ],
            [
                "Course-CIP lookup rows",
                len(
                    course_cip
                ),
            ],
            [
                "Course-CIP source",
                cip_source
                or "NONE FOUND",
            ],
            [
                "Requirements source",
                str(
                    requirements_path
                ),
            ],
            [
                "Additional-award source",
                str(
                    ADDITIONAL_PATH
                ),
            ],
            [
                "Official normalized source",
                str(
                    OFFICIAL_PATH
                ),
            ],
        ],
        columns=[
            "metric",
            "value",
        ],
    )

    # -------------------------------------------------------------------------
    # OUTPUT
    # -------------------------------------------------------------------------

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    pair_review.to_csv(
        OUT_DIR
        / "01_PAIR_REVIEW.csv",
        index=False,
    )

    student_evidence.to_csv(
        OUT_DIR
        / "02_STUDENT_PAIR_EVIDENCE.csv",
        index=False,
    )

    target_stack.to_csv(
        OUT_DIR
        / "03_TARGET_STUDENT_DETECTED_STACK.csv",
        index=False,
    )

    detected_pairs.to_csv(
        OUT_DIR
        / "04_ALL_MULTI_DETECTED_LINEAGE_PAIRS.csv",
        index=False,
    )

    multi_stack.to_csv(
        OUT_DIR
        / "05_ALL_MULTI_DETECTED_STUDENT_STACK.csv",
        index=False,
    )

    signatures.to_csv(
        OUT_DIR
        / "06_CREDENTIAL_SIGNATURES.csv",
        index=False,
    )

    excluded_associates.to_csv(
        OUT_DIR
        / "07_ASSOCIATES_SET_ASIDE.csv",
        index=False,
    )

    no_official.to_csv(
        OUT_DIR
        / "08_TARGETS_WITH_NO_OFFICIAL_CERT_ON_STUDENT.csv",
        index=False,
    )

    control.to_csv(
        OUT_DIR
        / "00_CONTROL.csv",
        index=False,
    )

    with pd.ExcelWriter(
        OUT_XLSX,
        engine="xlsxwriter",
    ) as writer:

        write_sheet(
            writer,
            "CONTROL",
            control,
        )

        write_sheet(
            writer,
            "PAIR_REVIEW",
            pair_review,
            human_review=True,
        )

        write_sheet(
            writer,
            "STUDENT_EVIDENCE",
            student_evidence,
        )

        write_sheet(
            writer,
            "TARGET_STUDENT_STACK",
            target_stack,
        )

        write_sheet(
            writer,
            "MULTI_DETECTED_PAIRS",
            detected_pairs,
            human_review=True,
        )

        write_sheet(
            writer,
            "MULTI_DETECTED_STACK",
            multi_stack,
        )

        write_sheet(
            writer,
            "CREDENTIAL_SIGNATURES",
            signatures,
        )

        write_sheet(
            writer,
            "NO_OFFICIAL_CERT",
            no_official,
        )

        write_sheet(
            writer,
            "ASSOCIATES_SET_ASIDE",
            excluded_associates,
        )

    # -------------------------------------------------------------------------
    # STUDENT-BLIND CONSOLE OUTPUT
    # -------------------------------------------------------------------------

    print()
    print("=" * 118)
    print(
        "RESULTS — STUDENT BLIND"
    )
    print("=" * 118)

    print(
        control.to_string(
            index=False
        )
    )

    if not pair_review.empty:

        print()
        print(
            "TOP LINEAGE REVIEW CANDIDATES"
        )
        print("-" * 118)

        show = pair_review[
            [
                "review_bucket",
                "target_lineage",
                "institutional_lineage",
                "cooccurring_students",
                "target_catalog_years",
                "official_detected_catalog_years",
                "max_course_jaccard",
                "max_target_course_coverage",
                "max_candidate_course_coverage",
                "max_cip_jaccard",
            ]
        ].head(40)

        print(
            show.to_string(
                index=False
            )
        )

    print()
    print("OUTPUT")
    print(
        OUT_XLSX.resolve()
    )

    print()
    print(
        "FERPA: STUDENT_EVIDENCE and "
        "student-stack sheets contain "
        "student IDs. Keep local."
    )

    print(
        "READ-ONLY: this script does not "
        "modify the crosswalk or governed "
        "relationship files."
    )


if __name__ == "__main__":
    main()
