from pathlib import Path
import re
import pandas as pd

ROOT = Path.cwd()

D_DETAIL = (
    ROOT / "data/processed/reporting/"
    "educ1300_d_certificate_award_check_20260811/"
    "EDUC1300_D_OFFICIAL_CERTIFICATE_DETAIL.csv"
)

REQS = (
    ROOT / "data/processed/catalogs/"
    "requirements_master_multiyear.csv"
)

LINEAGE_MAP = (
    ROOT / "data/processed/full_actual_audit/president_report/"
    "complete_rows_with_canonical_lineage.csv"
)

COURSES = (
    ROOT / "data/processed/"
    "normalized_actual_student_course_history.csv"
)

OUTDIR = (
    ROOT / "data/processed/reporting/"
    "educ1300_d_certificate_award_check_20260811"
)

OUT_DETAIL = OUTDIR / "EDUC1300_D_DEPENDENCY_DETAIL.csv"
OUT_SUMMARY = OUTDIR / "EDUC1300_D_DEPENDENCY_BY_MAJOR.csv"

OUTDIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# HELPERS
# =============================================================================

def norm(v):
    if pd.isna(v):
        return ""
    return str(v).strip().upper()


def course_norm(v):
    return re.sub(r"[^A-Z0-9]", "", norm(v))


def normalize_lineage(v):
    return re.sub(r"[^A-Z0-9]+", "_", norm(v)).strip("_")


def find_col(cols, candidates, required=True):
    lookup = {str(c).strip().lower(): c for c in cols}

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    if required:
        raise RuntimeError(
            f"Could not find one of {candidates}. "
            f"Available columns: {list(cols)}"
        )

    return None


def term_num(v):
    s = re.sub(r"\D", "", str(v))
    return int(s) if s else None


def extract_course_codes(text):
    if pd.isna(text):
        return set()

    return {
        course_norm(f"{a} {b}")
        for a, b in re.findall(
            r"\b([A-Z]{3,5})\s*[- ]?\s*(\d{4})\b",
            str(text).upper()
        )
    }


def join_unique(values):
    vals = sorted({
        str(x).strip()
        for x in values
        if str(x).strip()
    })
    return " | ".join(vals)


# =============================================================================
# LOAD D CASES
# =============================================================================

d = pd.read_csv(
    D_DETAIL,
    dtype=str,
    low_memory=False
).fillna("")

d = d[
    d["educ1300_status"].eq(
        "D_IS_HIGHEST_EDUC_1300_GRADE_AT_AWARD"
    )
].copy()

d["canonical_lineage"] = (
    d["canonical_lineage"]
    .map(normalize_lineage)
)

d["_student_id"] = d["student_id"].astype(str).str.strip()

print("=" * 110)
print("EDUC 1300 D — OFFICIAL CERTIFICATE DEPENDENCY TEST")
print("=" * 110)
print(f"Official certificate awards in D group: {len(d):,}")
print(f"Distinct students: {d['_student_id'].nunique():,}")


# =============================================================================
# LOAD REQUIREMENT MASTER + CREDENTIAL/LINAGE MAP
# =============================================================================

req = pd.read_csv(
    REQS,
    dtype=str,
    low_memory=False
).fillna("")

lin = pd.read_csv(
    LINEAGE_MAP,
    dtype=str,
    low_memory=False
).fillna("")

lin["canonical_lineage"] = (
    lin["canonical_lineage"]
    .map(normalize_lineage)
)

credential_map = (
    lin[
        [
            "catalog_year",
            "credential_id",
            "canonical_lineage",
        ]
    ]
    .drop_duplicates()
)

affected_lineages = set(d["canonical_lineage"])

credential_map = credential_map[
    credential_map["canonical_lineage"].isin(
        affected_lineages
    )
].copy()


# =============================================================================
# CLASSIFY EDUC 1300'S ROLE IN EACH CATALOG VERSION
# =============================================================================

version_rows = []

for _, cm in credential_map.iterrows():

    year = cm["catalog_year"]
    cred = cm["credential_id"]
    lineage = cm["canonical_lineage"]

    r = req[
        req["credential_id"].eq(cred)
    ].copy()

    if r.empty:
        continue

    educ_groups = []

    for requirement_id, group in r.groupby(
        "requirement_id",
        dropna=False
    ):

        codes = set()

        # Structured option values
        if "option_value" in group.columns:
            for value in group["option_value"]:
                code = course_norm(value)
                if re.fullmatch(r"[A-Z]{3,5}\d{4}", code):
                    codes.add(code)

        # Raw text fallback
        if "raw_requirement_text" in group.columns:
            for text in group["raw_requirement_text"]:
                codes |= extract_course_codes(text)

        if "EDUC1300" not in codes:
            continue

        other_courses = sorted(
            codes - {"EDUC1300"}
        )

        raw_text = " ".join(
            group.get(
                "raw_requirement_text",
                pd.Series(dtype=str)
            ).astype(str)
        ).upper()

        rule_types = set(
            group.get(
                "rule_type",
                pd.Series(dtype=str)
            )
            .astype(str)
            .str.upper()
        )

        alternative = (
            bool(other_courses)
            and (
                "ANY_N" in rule_types
                or " OR " in f" {raw_text} "
            )
        )

        educ_groups.append({
            "requirement_id": requirement_id,
            "role": (
                "ALTERNATIVE"
                if alternative
                else "STANDALONE"
            ),
            "alternatives": other_courses,
        })

    if not educ_groups:
        role = "NOT_EXPLICITLY_REQUIRED"
        alternatives = ""

    else:
        roles = {x["role"] for x in educ_groups}

        if roles == {"STANDALONE"}:
            role = "STANDALONE"
        elif roles == {"ALTERNATIVE"}:
            role = "ALTERNATIVE"
        else:
            role = "MIXED_WITHIN_CREDENTIAL"

        alternatives = join_unique(
            course
            for g in educ_groups
            for course in g["alternatives"]
        )

    version_rows.append({
        "catalog_year": year,
        "credential_id": cred,
        "canonical_lineage": lineage,
        "educ_role": role,
        "alternative_courses": alternatives,
    })


versions = pd.DataFrame(version_rows)


# =============================================================================
# SUMMARIZE ROLE ACROSS ALL MODELED CATALOG VERSIONS FOR EACH LINEAGE
# =============================================================================

lineage_role_rows = []

for lineage, group in versions.groupby(
    "canonical_lineage"
):

    roles = set(group["educ_role"])

    if roles == {"STANDALONE"}:
        overall_role = "STANDALONE_ALL_MODELED_CATALOGS"

    elif roles <= {"NOT_EXPLICITLY_REQUIRED"}:
        overall_role = "NOT_REQUIRED_IN_MODELED_CREDENTIAL"

    elif roles <= {"ALTERNATIVE"}:
        overall_role = "ALTERNATIVE_ALL_MODELED_CATALOGS"

    elif (
        "STANDALONE" in roles
        and len(roles) > 1
    ):
        overall_role = "MIXED_STANDALONE_AND_OTHER"

    else:
        overall_role = "MIXED_OR_UNRESOLVED"

    role_by_year = " | ".join(
        f"{row.catalog_year}:{row.educ_role}"
        for row in group.sort_values(
            "catalog_year"
        ).itertuples()
    )

    alternatives = join_unique(
        group["alternative_courses"]
    )

    lineage_role_rows.append({
        "canonical_lineage": lineage,
        "overall_educ_role": overall_role,
        "catalog_role_detail": role_by_year,
        "alternative_courses": alternatives,
    })


lineage_roles = pd.DataFrame(
    lineage_role_rows
)

d = d.merge(
    lineage_roles,
    on="canonical_lineage",
    how="left",
    validate="many_to_one"
)

d["overall_educ_role"] = (
    d["overall_educ_role"]
    .fillna("NO_MODELED_LINEAGE_MATCH")
)

d["alternative_courses"] = (
    d["alternative_courses"]
    .fillna("")
)

d["catalog_role_detail"] = (
    d["catalog_role_detail"]
    .fillna("")
)


# =============================================================================
# LOAD ACTUAL COURSE HISTORY
# =============================================================================

c = pd.read_csv(
    COURSES,
    dtype=str,
    low_memory=False
).fillna("")

sid_col = find_col(
    c.columns,
    [
        "student_id",
        "StudentID",
        "StudenID",
        "ID",
    ]
)

course_col = find_col(
    c.columns,
    [
        "course",
        "course_code",
        "CourseCode",
        "course_id",
        "CourseID",
    ],
    required=False
)

subject_col = find_col(
    c.columns,
    [
        "subject",
        "Subject",
        "course_subject",
        "CourseSubject",
    ],
    required=False
)

number_col = find_col(
    c.columns,
    [
        "course_number",
        "CourseNumber",
        "number",
        "Number",
    ],
    required=False
)

grade_col = find_col(
    c.columns,
    [
        "grade",
        "Grade",
        "final_grade",
        "FinalGrade",
        "grade_code",
        "GradeCode",
    ]
)

term_col = find_col(
    c.columns,
    [
        "term",
        "Term",
        "term_taken",
        "TermTaken",
        "term_code",
        "TermCode",
    ],
    required=False
)

c["_student_id"] = (
    c[sid_col]
    .astype(str)
    .str.strip()
)

if course_col:
    c["_course"] = c[course_col].map(
        course_norm
    )
elif subject_col and number_col:
    c["_course"] = (
        c[subject_col].map(norm)
        + c[number_col].map(norm)
    ).map(course_norm)
else:
    raise RuntimeError(
        "Could not determine course code."
    )

c["_grade"] = c[grade_col].map(norm)

if term_col:
    c["_term"] = c[term_col].map(term_num)
else:
    c["_term"] = None

PASSING = {
    "A",
    "B",
    "C",
    "D",
    "S",
    "P",
    "CR",
}


# =============================================================================
# TEST WHETHER AN ALTERNATIVE WAS AVAILABLE/PASSED BY AWARD
# =============================================================================

results = []

for _, row in d.iterrows():

    sid = row["_student_id"]
    role = row["overall_educ_role"]

    alternative_codes = {
        x.strip()
        for x in row["alternative_courses"].split("|")
        if x.strip()
    }

    history = c[
        c["_student_id"].eq(sid)
    ].copy()

    award_term = term_num(
        row.get("award_term", "")
    )

    if (
        award_term is not None
        and term_col is not None
    ):
        history = history[
            history["_term"].notna()
            & (history["_term"] <= award_term)
        ].copy()

    passed_alt = history[
        history["_course"].isin(
            alternative_codes
        )
        & history["_grade"].isin(
            PASSING
        )
    ]

    passed_alt_codes = sorted(
        set(passed_alt["_course"])
    )

    # --------------------------------------------------------------
    # EMPIRICAL CLASSIFICATION
    # --------------------------------------------------------------

    if role == "NOT_REQUIRED_IN_MODELED_CREDENTIAL":
        empirical = (
            "EDUC_D_INCIDENTAL_NOT_REQUIRED"
        )

    elif role == "STANDALONE_ALL_MODELED_CATALOGS":
        empirical = (
            "D_WAS_NEEDED_FOR_PUBLISHED_REQUIREMENT"
        )

    elif role == "ALTERNATIVE_ALL_MODELED_CATALOGS":
        if passed_alt_codes:
            empirical = (
                "OTHER_ALLOWED_ALTERNATIVE_SATISFIED"
            )
        else:
            empirical = (
                "D_APPEARS_NEEDED_NO_ALTERNATIVE_FOUND"
            )

    elif role == "MIXED_STANDALONE_AND_OTHER":
        if passed_alt_codes:
            empirical = (
                "MIXED_CATALOG_HISTORY_ALT_FOUND"
            )
        else:
            empirical = (
                "MIXED_CATALOG_HISTORY_NO_ALT_FOUND"
            )

    else:
        empirical = "UNRESOLVED"

    results.append({
        **row.to_dict(),
        "passed_alternative_courses":
            " | ".join(passed_alt_codes),
        "empirical_dependency_class":
            empirical,
    })


result = pd.DataFrame(results)


# =============================================================================
# SUMMARY BY OFFICIAL MAJOR
# =============================================================================

summary = (
    result.groupby(
        [
            "Major1Code",
            "canonical_lineage",
            "overall_educ_role",
            "catalog_role_detail",
            "alternative_courses",
        ],
        dropna=False
    )
    .agg(
        official_awards_with_educ_d=(
            "_student_id",
            "size"
        ),
        distinct_students=(
            "_student_id",
            "nunique"
        ),
        d_needed_for_published_requirement=(
            "empirical_dependency_class",
            lambda s: int(
                s.isin([
                    "D_WAS_NEEDED_FOR_PUBLISHED_REQUIREMENT",
                    "D_APPEARS_NEEDED_NO_ALTERNATIVE_FOUND",
                ]).sum()
            )
        ),
        other_allowed_alternative_satisfied=(
            "empirical_dependency_class",
            lambda s: int(
                s.eq(
                    "OTHER_ALLOWED_ALTERNATIVE_SATISFIED"
                ).sum()
            )
        ),
        educ_d_incidental_not_required=(
            "empirical_dependency_class",
            lambda s: int(
                s.eq(
                    "EDUC_D_INCIDENTAL_NOT_REQUIRED"
                ).sum()
            )
        ),
        mixed_or_unresolved=(
            "empirical_dependency_class",
            lambda s: int(
                s.isin([
                    "MIXED_CATALOG_HISTORY_ALT_FOUND",
                    "MIXED_CATALOG_HISTORY_NO_ALT_FOUND",
                    "UNRESOLVED",
                ]).sum()
            )
        ),
    )
    .reset_index()
    .sort_values(
        [
            "d_needed_for_published_requirement",
            "official_awards_with_educ_d",
        ],
        ascending=[False, False]
    )
)


# =============================================================================
# VALIDATION — BUSINESS OPERATIONS MUST REPRODUCE OUR PRIOR TEST
# =============================================================================

bo = result[
    result["canonical_lineage"]
    .eq("BUSINESS_OPERATIONS")
]

if len(bo) == 1:
    print()
    print("BUSINESS OPERATIONS VALIDATION")
    print(
        "Passed alternative:",
        bo.iloc[0][
            "passed_alternative_courses"
        ]
    )
    print(
        "Classification:",
        bo.iloc[0][
            "empirical_dependency_class"
        ]
    )


# =============================================================================
# OUTPUT
# =============================================================================

result.to_csv(
    OUT_DETAIL,
    index=False
)

summary.to_csv(
    OUT_SUMMARY,
    index=False
)

print()
print("=" * 110)
print("RESULTS — STUDENT BLIND")
print("=" * 110)

display_cols = [
    "Major1Code",
    "canonical_lineage",
    "overall_educ_role",
    "official_awards_with_educ_d",
    "d_needed_for_published_requirement",
    "other_allowed_alternative_satisfied",
    "educ_d_incidental_not_required",
    "mixed_or_unresolved",
]

print(
    summary[display_cols]
    .to_string(index=False)
)

print()
print("=" * 110)
print("TOTALS")
print("=" * 110)

print(
    "Official certificate awards with EDUC 1300 D:",
    len(result)
)

print(
    "D was needed for the published requirement:",
    int(
        result[
            "empirical_dependency_class"
        ].isin([
            "D_WAS_NEEDED_FOR_PUBLISHED_REQUIREMENT",
            "D_APPEARS_NEEDED_NO_ALTERNATIVE_FOUND",
        ]).sum()
    )
)

print(
    "Other allowed alternative satisfied:",
    int(
        result[
            "empirical_dependency_class"
        ].eq(
            "OTHER_ALLOWED_ALTERNATIVE_SATISFIED"
        ).sum()
    )
)

print(
    "EDUC 1300 not required by the credential:",
    int(
        result[
            "empirical_dependency_class"
        ].eq(
            "EDUC_D_INCIDENTAL_NOT_REQUIRED"
        ).sum()
    )
)

print(
    "Mixed / unresolved:",
    int(
        result[
            "empirical_dependency_class"
        ].isin([
            "MIXED_CATALOG_HISTORY_ALT_FOUND",
            "MIXED_CATALOG_HISTORY_NO_ALT_FOUND",
            "UNRESOLVED",
        ]).sum()
    )
)

print()
print("WROTE:")
print(OUT_SUMMARY.resolve())
print(OUT_DETAIL.resolve())
print()
print(
    "FERPA: dependency DETAIL contains student IDs; "
    "keep it local."
)
