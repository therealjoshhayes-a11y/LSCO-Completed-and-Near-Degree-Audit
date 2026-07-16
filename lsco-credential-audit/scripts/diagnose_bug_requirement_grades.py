import pandas as pd
import re

census = pd.read_csv(r"data\processed\reporting\requirement_matchability_census.csv", dtype=str)
census["miss_rate"] = census["miss_rate"].astype(float)
census["codes_in_banner"] = census["codes_in_banner"].astype(int)
bug = census[(census["codes_in_banner"] > 0) & (census["miss_rate"] >= 0.999)]

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
bug_reqs = reqs[reqs["requirement_id"].isin(bug["requirement_id"])]
bug_codes = set(
    bug_reqs[bug_reqs["option_type"].str.upper().eq("COURSE")]["option_value"].str.strip()
)
print("Distinct course codes behind the 330 bug requirements:", len(bug_codes))

audit_input = pd.read_csv(
    r"data\processed\normalized_actual_student_course_history.csv",
    dtype=str, usecols=["course_code"],
)
audit_codes = set(audit_input["course_code"].dropna().str.strip())

missing_from_audit = sorted(bug_codes - audit_codes)
present_in_audit = sorted(bug_codes & audit_codes)
print("Bug codes ABSENT from the audit's passed-only input:", len(missing_from_audit))
print("Bug codes PRESENT in the audit's input (deeper bug):", len(present_in_audit))
print()
if present_in_audit:
    print("Present-but-still-missing codes (these need individual investigation):")
    print(present_in_audit)
    print()

attempts = pd.read_csv(
    r"data\processed\all_student_course_attempts_normalized.csv",
    dtype=str, usecols=["course_code", "final_grade"],
).fillna("")
sub = attempts[attempts["course_code"].isin(missing_from_audit)]
print("Grade distribution for the absent codes (why nobody 'passed'):")
print(sub["final_grade"].replace("", "<blank>").value_counts().to_string())
print()
print("Per-code grade profile, top 25 codes by attempt volume:")
profile = sub.groupby("course_code")["final_grade"].apply(
    lambda s: dict(s.replace("", "<blank>").value_counts())
)
for code, dist in profile.head(25).items():
    print(f"{code}: {dist}")
