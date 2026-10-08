from pathlib import Path
import pandas as pd

ROOT = Path.cwd()

REPORT = ROOT / "data/processed/reporting/additional_awards_clean_query_20260803"
RESID = REPORT / "11_additional_awards_student_detail.csv"
AWARDS = REPORT / "08_official_awards_normalized.csv"
META = ROOT / "data/processed/catalogs/credential_metadata_multiyear.csv"
CROSSWALK = ROOT / "data/interim/institutional_awards/award_program_crosswalk_curated.xlsx"

r = pd.read_csv(RESID, dtype=str, low_memory=False).fillna("")
a = pd.read_csv(AWARDS, dtype=str, low_memory=False).fillna("")
m = pd.read_csv(META, dtype=str, low_memory=False).fillna("")
cw = pd.read_excel(CROSSWALK, sheet_name="Crosswalk Draft", dtype=str).fillna("")

student_col = next(
    c for c in ["student_id", "RNUM", "rnum", "student_key"]
    if c in r.columns and c in a.columns
)
r_lineage = next(
    c for c in ["detected_lineage", "canonical_lineage"]
    if c in r.columns
)

award_type_series = m["award_type"] if "award_type" in m.columns else pd.Series("", index=m.index)
m["_award_type"] = award_type_series.astype(str).str.strip().str.upper()

associate_types = {"AA", "AS", "AAS", "AAT", "ASSOCIATE"}
meta_assoc_ids = set(
    m.loc[m["_award_type"].isin(associate_types), "credential_id"]
) if "credential_id" in m.columns else set()

# Known multiyear metadata exception already established in this audit.
known_associate_ids = {
    cid for cid in r["credential_id"]
    if str(cid).startswith("LIBERAL_ARTS_")
}

associate_ids = meta_assoc_ids | known_associate_ids
assoc = r[r["credential_id"].isin(associate_ids)].copy()

award_level_series = cw["award_level"] if "award_level" in cw.columns else pd.Series("", index=cw.index)
cw["_award_level"] = award_level_series.astype(str).str.strip().str.upper()

associate_codes = set(
    cw.loc[cw["_award_level"].eq("ASSOCIATE"), "Curr1ProgramCode"]
) if "Curr1ProgramCode" in cw.columns else set()

official_assoc = a[
    a["Curr1ProgramCode"].isin(associate_codes)
].copy()

official_assoc_students = set(official_assoc[student_col])
assoc_students = set(assoc[student_col])

potential_second = assoc_students & official_assoc_students
first_assoc = assoc_students - official_assoc_students

print("=" * 105)
print("SECOND-ASSOCIATE DEGREE — INITIAL UNIVERSE")
print("=" * 105)
print()
print("Detected-unawarded associate rows:", len(assoc))
print("Detected-unawarded associate students:", len(assoc_students))
print("Students with NO prior LSCO associate:", len(first_assoc))
print("Students WITH prior LSCO associate:", len(potential_second))

print()
print("DETECTED ASSOCIATE CANDIDATES BY CREDENTIAL")
print("-" * 105)

if assoc.empty:
    print("NONE")
else:
    z = (
        assoc.groupby([r_lineage, "credential_id"], dropna=False)
        .agg(
            candidate_rows=(student_col, "size"),
            students=(student_col, "nunique"),
        )
        .reset_index()
        .sort_values("candidate_rows", ascending=False)
    )
    print(z.to_string(index=False))

print()
print("PRIOR ASSOCIATE AWARDS HELD BY POTENTIAL SECOND-DEGREE STUDENTS")
print("-" * 105)

x = official_assoc[official_assoc[student_col].isin(potential_second)].copy()

if x.empty:
    print("NONE")
else:
    cols = [
        c for c in [
            "institutional_lineage",
            "Curr1ProgramCode",
            "Major1Code",
            "DegreeCode",
        ]
        if c in x.columns
    ]
    z = (
        x.groupby(cols, dropna=False)
        .agg(
            award_rows=(student_col, "size"),
            students=(student_col, "nunique"),
        )
        .reset_index()
        .sort_values("students", ascending=False)
    )
    print(z.to_string(index=False))

print()
print("=" * 105)
print("CONTROL")
print("=" * 105)
print("Associate students = first-associate + potential second-associate:")
print(f"{len(assoc_students)} = {len(first_assoc)} + {len(potential_second)}")
assert len(assoc_students) == len(first_assoc) + len(potential_second)
print("PASS")
