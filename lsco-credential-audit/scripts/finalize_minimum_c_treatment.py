from pathlib import Path
import pandas as pd

ROOT = Path.cwd()
OUT = ROOT / "data" / "processed" / "full_actual_audit" / "evidence" / "awardability"

SOURCE = OUT / "selected_awards_awardability_screen.csv"
FINAL = OUT / "selected_awards_awardability_screen_finalized.csv"
SUMMARY = OUT / "awardability_screen_summary_finalized.csv"
REMAINING = OUT / "remaining_minimum_c_reviews.csv"

if not SOURCE.exists():
    raise FileNotFoundError(f"Missing input: {SOURCE}")

df = pd.read_csv(SOURCE, dtype=str, low_memory=False)

title = df["credential_title"].fillna("").str.upper()
credential_id = df["credential_id"].fillna("").str.upper()

general_academic = (
    title.str.contains("GENERAL STUDIES", regex=False)
    | title.str.contains("LIBERAL ARTS", regex=False)
    | credential_id.str.contains("GENERAL_STUDIES", regex=False)
    | credential_id.str.contains("LIBERAL_ARTS", regex=False)
)

change_mask = (
    general_academic
    & df["minimum_c_status"].fillna("").str.upper().eq("REVIEW")
)

changed_count = int(change_mask.sum())
df.loc[change_mask, "minimum_c_status"] = "NOT_APPLICABLE"

def remove_reason(value):
    parts = [p.strip() for p in str(value or "").split("|") if p.strip()]
    parts = [p for p in parts if p != "ESTIMATED_MAJOR_COURSES_UNRESOLVED"]
    return " | ".join(sorted(set(parts)))

df.loc[change_mask, "awardability_reasons"] = (
    df.loc[change_mask, "awardability_reasons"].map(remove_reason)
)

def recompute_overall(row):
    statuses = [
        str(row["residency_status"]),
        str(row["minimum_c_status"]),
    ]

    if str(row["credential_type"]) == "ASSOCIATE":
        statuses.append(str(row["institutional_gpa_status"]))
    else:
        statuses.append(str(row["certificate_plan_gpa_status"]))

    if "FAIL" in statuses:
        return "ACADEMIC_COMPLETE_SCREEN_FAIL"
    if "REVIEW" in statuses:
        return "ACADEMIC_COMPLETE_POLICY_REVIEW"
    return "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"

df["awardability_status"] = df.apply(recompute_overall, axis=1)
df.to_csv(FINAL, index=False)

summary_rows = []
for column in [
    "credential_type",
    "residency_status",
    "institutional_gpa_status",
    "certificate_plan_gpa_status",
    "minimum_c_status",
    "awardability_status",
]:
    for value, count in df[column].fillna("BLANK").value_counts().items():
        summary_rows.append(
            {"metric": column, "value": value, "count": int(count)}
        )

pd.DataFrame(summary_rows).to_csv(SUMMARY, index=False)

remaining = df[
    df["minimum_c_status"].fillna("").str.upper().eq("REVIEW")
].copy()
remaining.to_csv(REMAINING, index=False)

print("=" * 100)
print("FINALIZED MINIMUM-C TREATMENT")
print("=" * 100)
print(f"Rows changed to NOT_APPLICABLE: {changed_count:,}")

print("\nMinimum-C status:")
print(df["minimum_c_status"].value_counts(dropna=False).to_string())

print("\nOverall awardability:")
print(df["awardability_status"].value_counts(dropna=False).to_string())

print("\nRemaining minimum-C reviews by credential:")
if remaining.empty:
    print("None")
else:
    print(
        remaining.groupby(
            ["catalog_year", "credential_id", "credential_title"],
            dropna=False,
        )
        .size()
        .reset_index(name="review_count")
        .sort_values("review_count", ascending=False)
        .to_string(index=False)
    )

print("\nOutputs:")
print(FINAL)
print(SUMMARY)
print(REMAINING)
