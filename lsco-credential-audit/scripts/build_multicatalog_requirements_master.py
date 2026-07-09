from pathlib import Path

import pandas as pd


INPUT_GLOB = "data/processed/catalogs/*/requirements_docx_draft.csv"
VALIDATION_PATH = Path("data/interim/catalogs/requirement_total_validation.csv")
OUTPUT_PATH = Path("data/processed/catalogs/requirements_master_multicatalog.csv")


REQUIRED_COLUMNS = [
    "catalog_year",
    "credential_id",
    "credential_title",
    "source_table_index",
    "source_row_index",
    "requirement_sequence",
    "semester_label",
    "raw_requirement_text",
    "credit_hours",
    "raw_credit_hours_text",
    "rule_type",
    "course_codes",
    "issue_flags",
]


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_requirement_id(row: pd.Series) -> str:
    credential_id = normalize_text(row["credential_id"])
    seq = normalize_text(row["requirement_sequence"]).replace(".", "_")
    return f"{credential_id}_R{seq}"


def normalize_rule_type(row: pd.Series) -> str:
    """
    Apply final rule-type QA normalization after DOCX extraction.
    Only rescues NON_COURSE rows that are semantically core buckets.
    Do not override valid EXACT, ANY_N, or ELECTIVE rules.
    """

    rule_type = normalize_text(row.get("rule_type"))
    text = normalize_text(row.get("raw_requirement_text")).upper()

    if rule_type != "NON_COURSE":
        return rule_type

    core_bucket_phrases = [
        "COMMUNICATION",
        "AMERICAN HISTORY",
        "MATHEMATICS",
        "PHYSICAL SCIENCE",
        "LIFE OR PHYSICAL SCIENCE",
        "LIFE AND PHYSICAL SCIENCE",
        "LIFE AND PHYSICAL SCIENCES",
        "SOCIAL AND BEHAVIORAL SCIENCE",
        "SOCIAL AND BEHAVIORAL SCIENCES",
        "LANGUAGE, PHILOSOPHY",
        "CREATIVE ARTS",
        "COMPONENT AREA OPTION",
        "CORE 010",
        "CORE 020",
        "CORE 030",
        "CORE 040",
        "CORE 050",
        "CORE 060",
        "CORE 070",
        "CORE 080",
        "CORE 090",
    ]

    if any(phrase in text for phrase in core_bucket_phrases):
        return "CORE_BUCKET"

    return rule_type


def apply_documented_corrections(master: pd.DataFrame) -> pd.DataFrame:
    """
    Apply authorized, documented post-extraction corrections.

    Corrections here are for isolated catalog/extraction artifacts that are
    confirmed during QA and should not be generalized into parser behavior.
    """

    master = master.copy()

    # Authorized correction:
    # 2024-2025 Welding Fabrication Technology contains one malformed extracted
    # course code/text row: "WLDG 153 Intermediate Layout and Fabrication".
    # The intended 4 SCH course is WLDG 1453 Intermediate Layout and Fabrication.
    # This row was the only remaining NON_COURSE row after rule-type QA.
    mask = (
        master["catalog_year"].eq("2024-2025")
        & master["credential_id"].eq("WELDING_FABRICATION_TECHNOLOGY_2024")
        & master["raw_requirement_text"].eq("WLDG 153 Intermediate Layout and Fabrication")
        & master["credit_hours"].eq(4)
    )

    master.loc[mask, "correction_note"] = (
        "AUTHORIZED_CORRECTION: corrected malformed extracted course text "
        "from 'WLDG 153 Intermediate Layout and Fabrication' to "
        "'WLDG 1453 Intermediate Layout and Fabrication'."
    )
    master.loc[mask, "raw_requirement_text"] = "WLDG 1453 Intermediate Layout and Fabrication"
    master.loc[mask, "course_codes"] = "WLDG 1453"
    master.loc[mask, "rule_type"] = "EXACT"

    return master


def main() -> None:
    paths = sorted(Path(".").glob(INPUT_GLOB))

    if not paths:
        raise FileNotFoundError(f"No files found for {INPUT_GLOB}")

    frames = []

    for path in paths:
        df = pd.read_csv(path)

        missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"{path} missing columns: {missing}")

        df = df[REQUIRED_COLUMNS].copy()
        df["source_file"] = str(path)

        frames.append(df)

    master = pd.concat(frames, ignore_index=True)

    # Normalize important text fields.
    for col in [
        "catalog_year",
        "credential_id",
        "credential_title",
        "semester_label",
        "raw_requirement_text",
        "raw_credit_hours_text",
        "rule_type",
        "course_codes",
        "issue_flags",
        "source_file",
    ]:
        master[col] = master[col].apply(normalize_text)

    # Final semantic rule-type normalization.
    master["original_rule_type"] = master["rule_type"]
    master["rule_type"] = master.apply(normalize_rule_type, axis=1)

    # Documented QA corrections.
    master["correction_note"] = ""
    master = apply_documented_corrections(master)

    # Numeric cleanup.
    master["credit_hours"] = pd.to_numeric(master["credit_hours"], errors="coerce")

    # Stable unique requirement identifier.
    master["requirement_id"] = master.apply(build_requirement_id, axis=1)

    # Useful matching helpers.
    master["catalog_year_start"] = master["catalog_year"].str.slice(0, 4)
    master["credential_family"] = (
        master["credential_id"]
        .str.replace(r"_[0-9]{4}$", "", regex=True)
        .str.strip()
    )

    # Attach credential-level validation summary.
    if VALIDATION_PATH.exists():
        validation = pd.read_csv(VALIDATION_PATH)

        if "classified_status" in validation.columns:
            unresolved = validation[
                ~validation["classified_status"].astype(str).str.startswith("OK", na=False)
            ]

            if not unresolved.empty:
                raise ValueError(
                    f"Validation has unresolved rows. Resolve before building master: {len(unresolved)}"
                )

            credential_validation = (
                validation
                .groupby(["catalog_year", "credential_id"], dropna=False)
                .agg(
                    validation_rows=("classified_status", "size"),
                    validation_statuses=("classified_status", lambda s: ";".join(sorted(set(map(str, s))))),
                    validation_notes=("validation_note", lambda s: " | ".join(sorted(set(map(str, s))))),
                )
                .reset_index()
            )

            master = master.merge(
                credential_validation,
                on=["catalog_year", "credential_id"],
                how="left",
            )
        else:
            print("WARNING: validation file exists but has no classified_status column.")
    else:
        print(f"WARNING: validation file not found: {VALIDATION_PATH}")

    # Put ID columns first.
    first_cols = [
        "requirement_id",
        "catalog_year",
        "catalog_year_start",
        "credential_family",
        "credential_id",
        "credential_title",
        "requirement_sequence",
        "semester_label",
        "rule_type",
        "original_rule_type",
        "credit_hours",
        "correction_note",
        "course_codes",
        "raw_requirement_text",
    ]

    remaining_cols = [c for c in master.columns if c not in first_cols]
    master = master[first_cols + remaining_cols]

    # Basic quality checks.
    duplicate_ids = master["requirement_id"].duplicated().sum()
    missing_hours = master["credit_hours"].isna().sum()
    missing_rule_type = (master["rule_type"] == "").sum()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(master)} requirement rows to {OUTPUT_PATH}")
    print()
    print("Catalog years:")
    print(master["catalog_year"].value_counts().sort_index())
    print()
    print("Rule types:")
    print(master["rule_type"].value_counts().sort_index())
    print()
    print("Quality checks:")
    print(f"Duplicate requirement_id rows: {duplicate_ids}")
    print(f"Missing credit_hours rows: {missing_hours}")
    print(f"Missing rule_type rows: {missing_rule_type}")
    print()
    print("Credential counts by catalog year:")
    print(
        master.groupby("catalog_year")["credential_id"]
        .nunique()
        .sort_index()
        .to_string()
    )


if __name__ == "__main__":
    main()
    