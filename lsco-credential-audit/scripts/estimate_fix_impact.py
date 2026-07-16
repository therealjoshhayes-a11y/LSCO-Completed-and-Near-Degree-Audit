import pandas as pd

# ---------- inputs ----------
reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
lookup = pd.read_csv(r"data\processed\core_bucket_lookup_multicatalog.csv", dtype=str).fillna("")
hist = pd.read_csv(r"data\processed\normalized_actual_student_course_history.csv", dtype=str, usecols=["student_id","course_code"])
old_sum = pd.read_csv(r"data\processed\full_actual_audit\full_actual_credential_summary.csv", dtype=str, usecols=["student_id","catalog_year","credential_id","audit_status"])
elig = pd.read_csv(r"data\processed\student_catalog_eligibility.csv", dtype=str)

held = hist.groupby("student_id")["course_code"].apply(lambda s: set(s.str.strip())).to_dict()

lookup["bucket_name"] = lookup["bucket_name"].str.strip().str.upper()
lookup["catalog_year"] = lookup["catalog_year"].str.strip()
bucket_courses = lookup.groupby(["catalog_year","bucket_name"])["course_code"].apply(lambda s: set(s.str.strip())).to_dict()

# ---------- patched normalize_bucket_name (combo-aware) ----------
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

# ---------- affected credential set ----------
cb = reqs[reqs["option_type"].str.strip().str.upper().eq("CORE_BUCKET")]
combo_creds = set(cb[cb["option_value"].str.upper().str.contains(" OR ")]["credential_id"])
she_creds = set(reqs[reqs["credential_id"].str.contains("SAFETY_HEALTH_AND_ENVIRONMENT_", na=False)]["credential_id"])
affected = combo_creds | she_creds | {"CYBERSECURITY_SPECIALIST_2022"}
aff = reqs[reqs["credential_id"].isin(affected)]
print("Affected credential-years simulated:", aff["credential_id"].nunique())

# ---------- simulate ----------
cred_groups = {}
elective_rows = {}
for (cy, cred), g in aff.groupby(["catalog_year","credential_id"]):
    items = []
    n_elec = 0
    for rid, rg in g.groupby("requirement_id"):
        rtype = rg["rule_type"].iloc[0].strip().upper()
        need = int(float(rg["min_required"].iloc[0] or 1))
        opts = set()
        for _, o in rg.iterrows():
            ot = o["option_type"].strip().upper()
            if ot == "COURSE":
                opts.add(o["option_value"].strip())
            elif ot == "CORE_BUCKET":
                b = norm_bucket(o["option_value"])
                if b: opts |= bucket_courses.get((cy.strip(), b), set())
        if rtype == "ELECTIVE" or not opts:
            n_elec += 1
            continue  # optimistic: assume satisfied
        items.append((need, opts))
    cred_groups[(cy, cred)] = items
    elective_rows[(cy, cred)] = n_elec

rows = []
for (cy, cred), items in cred_groups.items():
    for sid, courses in held.items():
        if all(len(courses & opts) >= need for need, opts in items):
            rows.append((sid, cy, cred))
sim = pd.DataFrame(rows, columns=["student_id","catalog_year","credential_id"])
print("Simulated COMPLETE combos in affected credentials:", len(sim))

# ---------- diff vs old summary ----------
old_c = old_sum[old_sum["audit_status"].str.strip().str.upper().eq("COMPLETE")]
old_keys = set(zip(old_c["student_id"], old_c["catalog_year"], old_c["credential_id"]))
sim["is_new"] = [ (a,b,c) not in old_keys for a,b,c in zip(sim["student_id"],sim["catalog_year"],sim["credential_id"]) ]
new = sim[sim["is_new"]]

# ---------- eligibility filter ----------
ok = elig[elig["catalog_eligible"].str.strip().str.upper().isin({"TRUE","1"})][["student_id","catalog_year"]].drop_duplicates()
new_elig = new.merge(ok, on=["student_id","catalog_year"], how="inner")

print()
print("PREDICTED NEW completions (upper bound), eligible only:", len(new_elig))
print("Distinct students gaining:", new_elig["student_id"].nunique())
print()
summary = new_elig.groupby("credential_id").size().rename("predicted_new").reset_index()
summary["elective_rows_assumed_met"] = summary.apply(lambda r: elective_rows.get((r["credential_id"].rsplit("_",1)[-1] if False else "", r["credential_id"]), ""), axis=1)
# simpler: map elective counts by credential
elec_by_cred = {cred: n for (cy, cred), n in elective_rows.items()}
summary["elective_rows_assumed_met"] = summary["credential_id"].map(elec_by_cred)
print(summary.sort_values("predicted_new", ascending=False).to_string(index=False))
