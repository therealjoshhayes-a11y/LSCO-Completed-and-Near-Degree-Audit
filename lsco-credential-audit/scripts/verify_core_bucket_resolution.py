import pandas as pd
import re

def normalize_bucket_name(value):
    text = str(value).upper()
    if "COMMUNICATION" in text: return "COMMUNICATION_CORE"
    if "MATH" in text: return "MATHEMATICS_CORE"
    if "LIFE AND PHYSICAL SCIENCE" in text: return "LIFE_AND_PHYSICAL_SCIENCES_CORE"
    if "LANGUAGE" in text and "PHILOSOPHY" in text: return "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE"
    if "CREATIVE ARTS" in text or "ARTS CORE" in text: return "CREATIVE_ARTS_CORE"
    if "AMERICAN HISTORY" in text: return "AMERICAN_HISTORY_CORE"
    if "GOVERNMENT" in text or "POLITICAL SCIENCE" in text: return "GOVERNMENT_POLITICAL_SCIENCE_CORE"
    if "SOCIAL" in text and "BEHAVIORAL" in text: return "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE"
    if "COMPONENT AREA OPTION" in text or "OPTION CORE" in text: return "COMPONENT_AREA_OPTION_CORE"
    if text == "PHYSICAL SCIENCE": return "PHYSICAL_SCIENCE"
    if text in {"LIFE OR PHYSICAL SCIENCE", "LIFE OR PHYSICAL SCIENCES"}: return "LIFE_OR_PHYSICAL_SCIENCES"
    if text == "LIFE SCIENCE CORE 030": return "LIFE_SCIENCE_CORE_030"
    if text == "PHYSICAL SCIENCE CORE 030": return "PHYSICAL_SCIENCE_CORE_030"
    return None

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
lookup = pd.read_csv(r"data\processed\core_bucket_lookup_multicatalog.csv", dtype=str).fillna("")
lookup["catalog_year"] = lookup["catalog_year"].str.strip()
lookup["bucket_name"] = lookup["bucket_name"].str.strip().str.upper()
lookup_keys = set(zip(lookup["catalog_year"], lookup["bucket_name"]))
lookup_sizes = lookup.groupby(["catalog_year","bucket_name"]).size()

cb = reqs[reqs["option_type"].str.strip().str.upper().eq("CORE_BUCKET")].copy()
print("CORE_BUCKET option rows:", len(cb))

cb["bucket"] = cb["option_value"].map(normalize_bucket_name)
unrecognized = cb[cb["bucket"].isna()]
print()
print("FAILURE MODE 1 - option_value not recognized by normalize_bucket_name (engine SILENTLY skips these):", len(unrecognized))
if len(unrecognized):
    print(unrecognized["option_value"].value_counts().head(20).to_string())
    print()
    print("Affected credentials:")
    print(unrecognized.groupby(["catalog_year","credential_id"]).size().head(25).to_string())

resolved = cb[cb["bucket"].notna()].copy()
resolved["key_exists"] = list(zip(resolved["catalog_year"].str.strip(), resolved["bucket"]))
resolved["key_exists"] = resolved["key_exists"].isin(lookup_keys)
missing_key = resolved[~resolved["key_exists"]]
print()
print("FAILURE MODE 2 - recognized bucket with NO (catalog_year, bucket) key in lookup (engine returns UNRESOLVED):", len(missing_key))
if len(missing_key):
    print(missing_key.groupby(["catalog_year","bucket"]).size().to_string())

print()
print("Lookup coverage - courses per (catalog_year, bucket):")
print(lookup_sizes.unstack(0).fillna(0).astype(int).to_string())

# ELECTIVE side: every ELECTIVE requirement should have a rule in the overrides file
el = reqs[reqs["rule_type"].str.strip().str.upper().eq("ELECTIVE")]
try:
    rules = pd.read_csv(r"data\processed\full_actual_audit\evidence\rule_logic_review\ELECTIVE_controlled_semantic_overrides_final.csv", dtype=str).fillna("")
    rule_ids = set(rules["requirement_id"])
    el_ids = set(el["requirement_id"])
    print()
    print("ELECTIVE requirements:", len(el_ids), "| with a rule:", len(el_ids & rule_ids), "| WITHOUT a rule:", len(el_ids - rule_ids))
    missing_rules = sorted(el_ids - rule_ids)
    if missing_rules:
        print("First 20 without rules (note: post-split IDs like the new SHE credentials will legitimately be missing until rules are re-keyed):")
        print(missing_rules[:20])
except FileNotFoundError as err:
    print()
    print("ELECTIVE rules file not found at expected path:", err)
