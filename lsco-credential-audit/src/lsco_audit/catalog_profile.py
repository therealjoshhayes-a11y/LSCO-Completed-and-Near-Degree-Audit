import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


INPUT_CSV = INTERIM_DIR / "catalog_pages.csv"
OUTPUT_CSV = PROCESSED_DIR / "catalog_page_inventory.csv"


KEYWORDS = {
    "aas_hits": "Associate of Applied Science",
    "aa_as_hits": "Associate of Arts",
    "certificate_hits": "Certificate",
    "core_hits": "Core Curriculum",
    "degree_plan_hits": "Degree Plan",
    "semester_credit_hour_hits": "Semester Credit Hour",
    "total_hours_hits": "Total Hours",
}


def classify_catalog_section(page_number: int) -> str:
    if 119 <= page_number <= 123:
        return "core_curriculum"
    if 129 <= page_number <= 270:
        return "credential_plan"
    if 271 <= page_number <= 321:
        return "course_description"
    if 322 <= page_number <= 328:
        return "personnel_back_matter"
    return "front_matter_policy"


def count_keyword(text: str, keyword: str) -> int:
    return str(text).lower().count(keyword.lower())


def profile_catalog_pages() -> None:
    df = pd.read_csv(INPUT_CSV)

    inventory = df[["page_number", "text"]].copy()
    inventory["catalog_section"] = inventory["page_number"].apply(classify_catalog_section)
    inventory["text_length"] = inventory["text"].fillna("").str.len()

    for column, keyword in KEYWORDS.items():
        inventory[column] = inventory["text"].apply(
            lambda value: count_keyword(value, keyword)
        )

    hit_columns = list(KEYWORDS.keys())

    inventory["keyword_candidate"] = inventory[hit_columns].sum(axis=1) > 0
    inventory["credential_plan_page"] = inventory["catalog_section"] == "credential_plan"

    inventory = inventory.drop(columns=["text"])

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(OUTPUT_CSV, index=False)

    print(f"Profiled {len(inventory)} pages")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    profile_catalog_pages()