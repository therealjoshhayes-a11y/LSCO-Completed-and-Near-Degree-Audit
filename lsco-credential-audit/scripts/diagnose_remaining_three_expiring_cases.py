from pathlib import Path
import re
import pandas as pd
from datetime import datetime

ROOT = Path.cwd()

RECON = (
    ROOT / "data/processed/reporting/"
    "expiring_2021_2022_student_reconciliation_20260811/"
    "2021_2022_EXPIRING_STUDENT_AWARD_RECONCILIATION.xlsx"
)

RAW_AWARDS = (
    ROOT / "data/raw/institutional_awards/"
    "lsco_awards_sample_20260730.xlsx"
)

CROSSWALK = (
    ROOT / "data/interim/institutional_awards/"
    "award_program_crosswalk_curated.xlsx"
)

MODELED = (
    ROOT / "data/processed/full_actual_audit/president_report/"
    "complete_rows_with_canonical_lineage.csv"
)

QUERY_DIR = (
    ROOT / "data/processed/reporting/"
    "additional_awards_clean_query_20260803"
)

NORM_AWARDS = QUERY_DIR / "08_official_awards_normalized.csv"
REP_PAIRS   = QUERY_DIR / "09_official_award_representation_pairs.csv"

COURSES = (
    ROOT / "data/processed/"
    "normalized_actual_student_course_history.csv"
)

OUT = (
    ROOT / "data/processed/reporting/"
    "expiring_2021_2022_student_reconciliation_20260811/"
    "REMAINING_THREE_DEEP_DIVE_LOCAL.csv"
)


# =============================================================================
# HELPERS
# =============================================================================

def norm(v):
    if pd.isna(v):
        return ""
    return str(v).strip().upper()


def norm_id(v):
    s = norm(v)
    s = re.sub(r"\.0$", "", s)
    return s


def course_norm(v):
    return re.sub(r"[^A-Z0-9]", "", norm(v))


def find_col(cols, candidates, required=True):
    lookup = {str(c).strip().lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lookup:
            return lookup[name.lower()]
    if required:
        raise RuntimeError(
            f"Missing one of {candidates}; columns={list(cols)}"
        )
    return None


def fmt_time(path):
    return datetime.fromtimestamp(
        path.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")


TARGET_MAP = {
    "ORDINARY SEAMAN I": "ORDINARY_SEAMAN_I",
    "INDUSTRIAL TECHNOLOGY": "INDUSTRIAL_TECHNOLOGY",
}


# =============================================================================
# FILE CHECK
# =============================================================================

for p in [
    RECON,
    RAW_AWARDS,
    CROSSWALK,
    MODELED,
    NORM_AWARDS,
    REP_PAIRS,
    COURSES,
]:
    if not p.exists():
        raise FileNotFoundError(p)


print("=" * 110)
print("REMAINING THREE — DEEP DIVE")
print("=" * 110)

print()
print("DERIVED-FILE FRESHNESS")
print("-" * 110)

for p in [
    CROSSWALK,
    MODELED,
    NORM_AWARDS,
    REP_PAIRS,
]:
    print(f"{p.name:50} {fmt_time(p)}")

source_mtime = max(
    CROSSWALK.stat().st_mtime,
    MODELED.stat().st_mtime,
)

derived_mtime = min(
    NORM_AWARDS.stat().st_mtime,
    REP_PAIRS.stat().st_mtime,
)

DERIVED_STALE = derived_mtime < source_mtime

print()
print(
    "08/09 older than current lineage inputs:",
    "YES — RERUN CLEAN QUERY FIRST"
    if DERIVED_STALE
    else "NO"
)


# =============================================================================
# RECONCILIATION CASES
# =============================================================================

rec = pd.read_excel(
    RECON,
    sheet_name="STUDENT_RECONCILIATION",
    dtype=str,
).fillna("")

rid = find_col(
    rec.columns,
    ["Banner ID", "student_id", "Student ID"]
)

unawarded_col = find_col(
    rec.columns,
    ["Unawarded"]
)

known_col = find_col(
    rec.columns,
    ["Known Awards"],
    required=False,
)

remaining = rec[
    rec[unawarded_col].str.strip().ne("")
].copy()

remaining["_student_id"] = remaining[rid].map(norm_id)

if len(remaining) != 3:
    print(
        f"\nWARNING: expected 3 remaining rows; found {len(remaining)}"
    )


# =============================================================================
# RAW + NORMALIZED AWARDS
# =============================================================================

raw = pd.read_excel(
    RAW_AWARDS,
    dtype=str,
).fillna("")

raw_id = find_col(
    raw.columns,
    ["ID", "student_id", "Banner ID"]
)

raw["_student_id"] = raw[raw_id].map(norm_id)

keys = [
    "Curr1ProgramCode",
    "Major1Code",
    "DegreeCode",
]

for k in keys:
    if k not in raw.columns:
        raise RuntimeError(f"Raw awards missing {k}")
    raw[k] = raw[k].map(norm)


xw = pd.read_excel(
    CROSSWALK,
    sheet_name="Crosswalk Draft",
    dtype=str,
).fillna("")

for k in keys:
    xw[k] = xw[k].map(norm)

xw["canonical_lineage"] = (
    xw["canonical_lineage"].map(norm)
)

xw_small = (
    xw[
        keys
        + [
            "MajorDesc",
            "DegreeDesc",
            "canonical_lineage",
        ]
    ]
    .drop_duplicates()
)

raw_mapped = raw.merge(
    xw_small,
    on=keys,
    how="left",
    validate="many_to_one",
    suffixes=("", "_crosswalk"),
)

raw_mapped["canonical_lineage"] = (
    raw_mapped["canonical_lineage"]
    .fillna("")
    .map(norm)
)


norm_aw = pd.read_csv(
    NORM_AWARDS,
    dtype=str,
    low_memory=False,
).fillna("")

norm_sid = find_col(
    norm_aw.columns,
    ["student_id"]
)

norm_aw["_student_id"] = (
    norm_aw[norm_sid].map(norm_id)
)

inst_col = find_col(
    norm_aw.columns,
    ["institutional_lineage", "canonical_lineage"]
)

norm_aw["_institutional_lineage"] = (
    norm_aw[inst_col].map(norm)
)


pairs = pd.read_csv(
    REP_PAIRS,
    dtype=str,
    low_memory=False,
).fillna("")

pair_sid = find_col(
    pairs.columns,
    ["student_id"]
)

pairs["_student_id"] = (
    pairs[pair_sid].map(norm_id)
)

pairs["detected_lineage"] = (
    pairs["detected_lineage"].map(norm)
)

pairs["institutional_lineage"] = (
    pairs["institutional_lineage"].map(norm)
)


# =============================================================================
# COURSE HISTORY — IDENTIFY THE EDUC 1300 APPEAL CASE
# =============================================================================

courses = pd.read_csv(
    COURSES,
    dtype=str,
    low_memory=False,
).fillna("")

csid = find_col(
    courses.columns,
    ["student_id", "StudentID", "ID"]
)

courses["_student_id"] = (
    courses[csid].map(norm_id)
)

course_col = find_col(
    courses.columns,
    [
        "course",
        "course_code",
        "CourseCode",
        "course_id",
        "CourseID",
    ],
    required=False,
)

subject_col = find_col(
    courses.columns,
    ["subject", "Subject"],
    required=False,
)

number_col = find_col(
    courses.columns,
    ["course_number", "CourseNumber", "number"],
    required=False,
)

grade_col = find_col(
    courses.columns,
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
    courses.columns,
    ["term", "Term", "term_code", "TermCode"],
    required=False,
)

if course_col:
    courses["_course"] = (
        courses[course_col].map(course_norm)
    )
elif subject_col and number_col:
    courses["_course"] = (
        courses[subject_col].map(norm)
        + courses[number_col].map(norm)
    ).map(course_norm)
else:
    raise RuntimeError("Cannot construct course code.")

courses["_grade"] = courses[grade_col].map(norm)

GRADE_RANK = {
    "A": 5,
    "B": 4,
    "C": 3,
    "D": 2,
    "F": 1,
}


def educ_summary(student_id):
    e = courses[
        courses["_student_id"].eq(student_id)
        & courses["_course"].eq("EDUC1300")
    ].copy()

    if e.empty:
        return "", ""

    grades = list(e["_grade"])

    ranked = [
        g for g in grades
        if g in GRADE_RANK
    ]

    best = (
        max(ranked, key=lambda g: GRADE_RANK[g])
        if ranked
        else ""
    )

    if term_col:
        events = " | ".join(
            (
                e[term_col].astype(str)
                + ":"
                + e["_grade"]
            ).tolist()
        )
    else:
        events = " | ".join(grades)

    return best, events


# =============================================================================
# RELEVANT CROSSWALK GOVERNANCE
# =============================================================================

print()
print("=" * 110)
print("RELEVANT CROSSWALK ROWS")
print("=" * 110)

relevant_xw = xw[
    xw["canonical_lineage"].isin(
        [
            "INDUSTRIAL_TECHNOLOGY",
            "ORDINARY_SEAMAN_I",
        ]
    )
][
    keys
    + [
        "MajorDesc",
        "DegreeDesc",
        "canonical_lineage",
    ]
].drop_duplicates()

print(
    relevant_xw.to_string(index=False)
)


# =============================================================================
# CASE-BY-CASE DIAGNOSIS
# =============================================================================

local_rows = []
blind_rows = []

osi_counter = 0

for _, r in remaining.iterrows():

    sid = r["_student_id"]
    title = norm(r[unawarded_col])

    target_lineage = TARGET_MAP.get(
        title,
        re.sub(r"[^A-Z0-9]+", "_", title).strip("_")
    )

    best_educ, educ_events = educ_summary(sid)

    if title == "ORDINARY SEAMAN I":
        osi_counter += 1
        if best_educ == "D":
            case = "ORDINARY SEAMAN I — EDUC 1300 D / APPEAL CASE"
        else:
            case = f"ORDINARY SEAMAN I — OTHER CASE"
    else:
        case = "INDUSTRIAL TECHNOLOGY"

    raw_student = raw_mapped[
        raw_mapped["_student_id"].eq(sid)
    ].copy()

    norm_student = norm_aw[
        norm_aw["_student_id"].eq(sid)
    ].copy()

    pair_student = pairs[
        pairs["_student_id"].eq(sid)
    ].copy()

    raw_target = raw_student[
        raw_student["canonical_lineage"]
        .eq(target_lineage)
    ]

    norm_target = norm_student[
        norm_student["_institutional_lineage"]
        .eq(target_lineage)
    ]

    pair_target = pair_student[
        pair_student["detected_lineage"]
        .eq(target_lineage)
    ]

    raw_award_map = []

    for rr in raw_student.itertuples():
        code = (
            f"{getattr(rr, 'Curr1ProgramCode')} / "
            f"{getattr(rr, 'Major1Code')} / "
            f"{getattr(rr, 'DegreeCode')}"
        )

        lineage = getattr(
            rr,
            "canonical_lineage",
            "",
        )

        raw_award_map.append(
            f"{code} => {lineage or 'UNMAPPED'}"
        )

    raw_award_map_text = (
        " | ".join(raw_award_map)
        if raw_award_map
        else "NONE"
    )

    normalized_lineages = sorted(
        set(
            norm_student[
                "_institutional_lineage"
            ]
            .loc[
                norm_student[
                    "_institutional_lineage"
                ].ne("")
            ]
        )
    )

    represented_targets = sorted(
        set(
            pair_student[
                "detected_lineage"
            ]
            .loc[
                pair_student[
                    "detected_lineage"
                ].ne("")
            ]
        )
    )

    known_awards = (
        str(r[known_col])
        if known_col
        else ""
    )

    if not pair_target.empty:
        diagnosis = (
            "RECONCILIATION FALSE POSITIVE: "
            "09 already contains a representation pair "
            "for this target lineage."
        )

    elif not norm_target.empty:
        diagnosis = (
            "REPRESENTATION-PAIR FAILURE OR STALE 09: "
            "08 contains an exact target-lineage award, "
            "so 09 should contain an exact representation pair."
        )

    elif not raw_target.empty:
        diagnosis = (
            "NORMALIZATION OUTPUT STALE OR FAILED: "
            "the raw official award maps to the target lineage "
            "under the current crosswalk, but 08 does not contain it."
        )

    elif (
        title == "ORDINARY SEAMAN I"
        and best_educ == "D"
    ):
        diagnosis = (
            "EDUC 1300 D APPEAL CASE: "
            "no official Ordinary Seaman I award is present "
            "in the current award extract."
        )

    elif title == "ORDINARY SEAMAN I":
        diagnosis = (
            "REGISTRAR-SAYS-AWARDED CASE: "
            "no target-lineage award is present in the current "
            "official extract. Check award code, award date, "
            "or whether the source snapshot predates the award."
        )

    elif title == "INDUSTRIAL TECHNOLOGY":
        diagnosis = (
            "INDUSTRIAL LINEAGE DISCREPANCY: "
            "current extract/crosswalk does not produce an "
            "Industrial Technology representation pair for this student. "
            "Inspect the raw award code shown below against the "
            "Registrar's claimed lineage."
        )

    else:
        diagnosis = "UNRESOLVED"

    blind_rows.append({
        "Case": case,
        "Target Lineage": target_lineage,
        "Best EDUC 1300 Letter Grade": best_educ,
        "Raw Award Maps": raw_award_map_text,
        "Normalized Official Lineages":
            " | ".join(normalized_lineages) or "NONE",
        "Target Present in Raw + Current Crosswalk":
            "YES" if not raw_target.empty else "NO",
        "Target Present in 08":
            "YES" if not norm_target.empty else "NO",
        "Target Representation Present in 09":
            "YES" if not pair_target.empty else "NO",
        "Diagnosis": diagnosis,
    })

    local_rows.append({
        "student_id": sid,
        "unawarded_credential": r[unawarded_col],
        "target_lineage": target_lineage,
        "known_awards_from_reconciliation": known_awards,
        "educ1300_best_letter_grade": best_educ,
        "educ1300_grade_events": educ_events,
        "raw_award_maps": raw_award_map_text,
        "normalized_official_lineages":
            " | ".join(normalized_lineages),
        "representation_detected_lineages":
            " | ".join(represented_targets),
        "diagnosis": diagnosis,
    })


blind = pd.DataFrame(blind_rows)
local = pd.DataFrame(local_rows)

local.to_csv(
    OUT,
    index=False,
)

print()
print("=" * 110)
print("THREE CASES — STUDENT BLIND")
print("=" * 110)

for row in blind.to_dict("records"):
    print()
    print("-" * 110)
    for k, v in row.items():
        print(f"{k}: {v}")

print()
print("=" * 110)
print("LOCAL DETAIL")
print("=" * 110)
print(OUT.resolve())
print("FERPA: local detail contains student IDs. Keep local.")
