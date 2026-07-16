import pandas as pd

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
lookup = pd.read_csv(r"data\processed\core_bucket_lookup_multicatalog.csv", dtype=str).fillna("")
hist = pd.read_csv(r"data\processed\normalized_actual_student_course_history.csv", dtype=str, usecols=["student_id","course_code"])
held = hist.groupby("student_id")["course_code"].apply(lambda s: set(s.str.strip())).to_dict()
lookup["bucket_name"] = lookup["bucket_name"].str.strip().str.upper()
lookup["catalog_year"] = lookup["catalog_year"].str.strip()
bucket_courses = lookup.groupby(["catalog_year","bucket_name"])["course_code"].apply(lambda s: set(s.str.strip())).to_dict()

def norm_bucket(value):
    t = str(value).upper()
    if " OR " in t:
        lpc = ("LANGUAGE" in t or "LANG" in t) and ("PHILOSOPHY" in t or "PHIL" in t)
        arts = "CREATIVE ARTS" in t or "FINE ARTS" in t
        if lpc and arts: return "LANGUAGE_PHILOSOPHY_AND_CULTURE_OR_CREATIVE_ARTS"
        if "COMMUNICATION" in t and "COMPONENT AREA OPTION" in t: return "COMMUNICATION_OR_COMPONENT_AREA_OPTION"
    if "COMMUNICATION" in t: return "COMMUNICATION_CORE"
    if "MATH" in t: return "MATHEMATICS_CORE"
    if "LIFE AND PHYSICAL SCIENCE" in t: return "LIFE_AND_PHYSICAL_SCIENCES_CORE"
    if "LANGUAGE" in t and "PHILOSOPHY" in t: return "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE"
    if "CREATIVE ARTS" in t or "ARTS CORE" in t: return "CREATIVE_ARTS_CORE"
    if "AMERICAN HISTORY" in t: return "AMERICAN_HISTORY_CORE"
    if "GOVERNMENT" in t or "POLITICAL SCIENCE" in t: return "GOVERNMENT_POLITICAL_SCIENCE_CORE"
    if "SOCIAL" in t and "BEHAVIORAL" in t: return "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE"
    if "COMPONENT AREA OPTION" in t or "OPTION CORE" in t: return "COMPONENT_AREA_OPTION_CORE"
    if t == "PHYSICAL SCIENCE": return "PHYSICAL_SCIENCE"
    if t in {"LIFE OR PHYSICAL SCIENCE","LIFE OR PHYSICAL SCIENCES"}: return "LIFE_OR_PHYSICAL_SCIENCES"
    if t == "LIFE SCIENCE CORE 030": return "LIFE_SCIENCE_CORE_030"
    if t == "PHYSICAL SCIENCE CORE 030": return "PHYSICAL_SCIENCE_CORE_030"
    return None

TARGET_CREDS = [
    "PROCESS_OPERATING_TECHNOLOGY_2023",
    "SAFETY_HEALTH_AND_ENVIRONMENT_CERTIFICATE_OF_COMPLETION_2023",
    "BUSINESS_MANAGEMENT_2023",
    "CYBERSECURITY_SPECIALIST_2022",
    "INSTRUMENTATION_AAS_2022",
]

def audit_one(cred_id, courses):
    g = reqs[reqs["credential_id"] == cred_id]
    cy = g["catalog_year"].iloc[0].strip()
    results = []
    for rid, rg in g.groupby("requirement_id"):
        rtype = rg["rule_type"].iloc[0].strip().upper()
        need = int(float(rg["min_required"].iloc[0] or 1))
        opts, label = set(), []
        for _, o in rg.iterrows():
            ot = o["option_type"].strip().upper()
            if ot == "COURSE":
                opts.add(o["option_value"].strip()); label.append(o["option_value"].strip())
            elif ot == "CORE_BUCKET":
                b = norm_bucket(o["option_value"])
                if b: opts |= bucket_courses.get((cy, b), set()); label.append(f"[{b}]")
        if rtype == "ELECTIVE" or not opts:
            results.append((rid, "ELECTIVE(assumed)", "", "")); continue
        hits = sorted(courses & opts)
        status = "MET" if len(hits) >= need else "UNMET"
        results.append((rid, status, "; ".join(hits[:need]) if hits else "", " / ".join(label[:4])))
    return results

rows_out = []
for cred in TARGET_CREDS:
    completers, near = [], []
    for sid, courses in held.items():
        res = audit_one(cred, courses)
        unmet = [r for r in res if r[1] == "UNMET"]
        if not unmet: completers.append((sid, res))
        elif len(unmet) == 1: near.append((sid, res, unmet[0]))
    print("=" * 100)
    print(f"{cred}: {len(completers)} simulated completers, {len(near)} one-requirement-short")
    if completers:
        sid, res = completers[0]
        rows_out.append((cred, "COMPLETER", sid))
        print(f"--- Sample COMPLETER (student A, id in local csv) ---")
        for rid, st, hit, lab in res:
            print(f"  {st:20s} {rid:55s} via {hit}" if st=="MET" else f"  {st:20s} {rid}")
    if near:
        sid, res, miss = near[0]
        rows_out.append((cred, "NEAR", sid))
        print(f"--- Sample NEAR (student B, id in local csv) ---")
        print(f"  MISSING: {miss[0]}  (accepts: {miss[3]})")

pd.DataFrame(rows_out, columns=["credential_id","kind","student_id"]).to_csv(
    r"data\processed\reporting\spot_check_sample_ids.csv", index=False)
print()
print("Full student IDs written LOCALLY to data\\processed\\reporting\\spot_check_sample_ids.csv")
print("Look them up in DegreeWorks/Banner to verify. Do not paste IDs back to chat.")
