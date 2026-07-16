import pandas as pd

# --- pick three unexplained bug requirements across years ---
PROBES = [
    ("2025-2026", "ACCOUNTING_SERVICES_2025", "ACCOUNTING_SERVICES_2025_R1_3"),
    ("2023-2024", "SAFETY_HEALTH_AND_ENVIRONMENT_2023", "SAFETY_HEALTH_AND_ENVIRONMENT_2023_R2_1"),
    ("2021-2022", "ORDINARY_SEAMAN_II_2021", "ORDINARY_SEAMAN_II_2021_R6_0"),
]

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
inp = pd.read_csv(r"data\processed\normalized_actual_student_course_history.csv",
                  dtype=str, usecols=["student_id", "course_code"])
inp["course_code"] = inp["course_code"].str.strip()

path = r"data\processed\full_actual_audit\full_actual_audit_results.csv"

for cat, cred, rid in PROBES:
    course = reqs[(reqs["requirement_id"] == rid)]["option_value"].str.strip().iloc[0]
    holders = set(inp[inp["course_code"] == course]["student_id"])
    print("=" * 90)
    print(f"PROBE {rid}  course={course}")
    print(f"Students holding {course} (passed):", len(holders))

    status_counts = {}
    matched_by_req = {}
    for chunk in pd.read_csv(path, dtype=str,
                             usecols=["student_id","catalog_year","credential_id",
                                      "requirement_id","status","matched_options"],
                             chunksize=500000):
        sub = chunk[(chunk["credential_id"] == cred) & (chunk["catalog_year"] == cat)]
        sub = sub[sub["student_id"].isin(holders)]
        if sub.empty:
            continue
        probe_rows = sub[sub["requirement_id"] == rid]
        for s, n in probe_rows["status"].value_counts().items():
            status_counts[s] = status_counts.get(s, 0) + n
        hit = sub[sub["matched_options"].fillna("").str.contains(course, regex=False)]
        for r, n in hit["requirement_id"].value_counts().items():
            matched_by_req[r] = matched_by_req.get(r, 0) + n

    print(f"Status of {rid} among holders:", status_counts if status_counts else "NO ROWS FOUND")
    print(f"Requirements in {cred} whose matched_options contain {course}:")
    print("   ", matched_by_req if matched_by_req else "NONE - course never matched anywhere in this credential")
