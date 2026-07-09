from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/processed/catalogs/requirements_master_multicatalog.csv")
OUTPUT_PATH = Path("data/processed/catalogs/elective_rules_multicatalog.csv")


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify_elective(text: str) -> tuple[str, str]:
    """
    Classify elective requirement text into a machine-resolvable family.

    resolver_type is intentionally broad. The audit engine can later map these
    families to allowed course pools.
    """

    upper = text.upper()

    if any(token in upper for token in ["CRIMINAL JUSTICE ELECTIVE", "CRIJ", "CJSA", "CJCR"]):
        return "RUBRIC_ELECTIVE", "CRIJ;CJSA;CJCR"

    if "INFORMATION TECHNOLOGY ELECTIVE" in upper:
        return "RUBRIC_ELECTIVE", "ITSC;ITSE;ITSW;ITNW;ITCC;ITDF"

    if "BUSI, BMGT, ACCT, MRKG, COSC" in upper:
        return "RUBRIC_ELECTIVE", "BUSI;BMGT;ACCT;MRKG;COSC"

    if "ACCT, ACNT, BMGT, BUSI, COSC, OR MRKG" in upper:
        return "RUBRIC_ELECTIVE", "ACCT;ACNT;BMGT;BUSI;COSC;MRKG"

    if "BUSINESS ELECTIVE" in upper or "BUSI ELECTIVE" in upper:
        return "BUSINESS_ELECTIVE", "BUSI;BMGT;ACCT;MRKG;COSC"

    if "AGRIBUSINESS ELECTIVE" in upper or "ANIMAL SCIENCE ELECTIVE" in upper:
        return "AG_BUSINESS_ELECTIVE", "AGRI;ANSC;BUSI;BMGT"

    if "SCIENCE MAJOR ELECTIVE" in upper:
        return "SCIENCE_MAJOR_ELECTIVE", ""

    if "SCIENCE ELECTIVE" in upper or "ACADEMIC ELECTIVE (SCIENCE)" in upper:
        return "SCIENCE_ELECTIVE", ""

    if "LANG, PHIL, CULTURE OR CREATIVE ARTS ELECTIVE" in upper:
        return "CORE_AREA_ELECTIVE", "CORE_040;CORE_050"

    if "LANGUAGE, PHILOSOPHY, CULTURE OR CREATIVE ARTS ELECTIVE" in upper:
        return "CORE_AREA_ELECTIVE", "CORE_040;CORE_050"

    if "ACADEMIC SUBJECT AREA ELECTIVE" in upper:
        return "SUBJECT_AREA_ELECTIVE", ""

    if "APPROVED ACADEMIC ELECTIVE" in upper:
        return "GENERAL_ACADEMIC_ELECTIVE", ""

    if "ACADEMIC ELECTIVE" in upper or "ACDEMIC ELECTIVE" in upper:
        return "GENERAL_ACADEMIC_ELECTIVE", ""

    if "APPROVED ELECTIVE" in upper:
        return "GENERAL_APPROVED_ELECTIVE", ""

    if "ELECTIVE" in upper:
        return "GENERAL_ELECTIVE", ""

    return "UNCLASSIFIED_ELECTIVE", ""


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    master = pd.read_csv(INPUT_PATH)

    required_cols = [
        "requirement_id",
        "catalog_year",
        "credential_id",
        "credential_title",
        "semester_label",
        "rule_type",
        "credit_hours",
        "raw_requirement_text",
    ]

    missing = [col for col in required_cols if col not in master.columns]
    if missing:
        raise ValueError(f"Master file missing required columns: {missing}")

    electives = master[master["rule_type"].eq("ELECTIVE")].copy()

    rows = []

    for _, row in electives.iterrows():
        raw_text = normalize_text(row["raw_requirement_text"])
        resolver_type, allowed_rubrics = classify_elective(raw_text)

        rows.append(
            {
                "requirement_id": row["requirement_id"],
                "catalog_year": row["catalog_year"],
                "credential_id": row["credential_id"],
                "credential_title": row["credential_title"],
                "semester_label": row["semester_label"],
                "credit_hours": row["credit_hours"],
                "raw_requirement_text": raw_text,
                "resolver_type": resolver_type,
                "allowed_rubrics": allowed_rubrics,
                "resolution_note": "",
            }
        )

    rules = pd.DataFrame(rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rules.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(rules)} elective rules to {OUTPUT_PATH}")
    print()
    print("Resolver types:")
    print(rules["resolver_type"].value_counts().sort_index())

    unclassified = rules[rules["resolver_type"].eq("UNCLASSIFIED_ELECTIVE")]

    print()
    print(f"UNCLASSIFIED_ELECTIVE rows: {len(unclassified)}")

    if not unclassified.empty:
        print()
        print(unclassified[[
            "catalog_year",
            "credential_id",
            "credential_title",
            "raw_requirement_text",
            "credit_hours",
        ]].to_string(index=False))


if __name__ == "__main__":
    main()