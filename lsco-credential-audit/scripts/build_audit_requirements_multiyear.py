from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/processed/catalogs/requirements_master_multicatalog.csv")
OUTPUT_PATH = Path("data/processed/catalogs/requirements_master_multiyear.csv")


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def split_course_codes(value) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def build_rows(master: pd.DataFrame) -> list[dict]:
    rows = []

    for _, row in master.iterrows():
        rule_type = normalize_text(row["rule_type"])
        course_codes = split_course_codes(row.get("course_codes"))
        raw_text = normalize_text(row["raw_requirement_text"])

        base = {
            "catalog_year": row["catalog_year"],
            "credential_id": row["credential_id"],
            "credential_title": row["credential_title"],
            "requirement_id": row["requirement_id"],
            "sequence": row["requirement_sequence"],
            "rule_type": rule_type,
            "min_required": 1,
            "group_name": raw_text,
            "credit_hours": row["credit_hours"],
            "semester_label": row["semester_label"],
            "source_requirement_text": raw_text,
        }

        if rule_type == "EXACT":
            if len(course_codes) == 1:
                rows.append({
                    **base,
                    "option_type": "COURSE",
                    "option_value": course_codes[0],
                })
            elif len(course_codes) > 1:
                # Some catalog rows are semantically "one of these courses"
                # even when upstream classified them as EXACT, e.g.
                # "CRIJ 1301 (or CJSA 1322) Introduction to Criminal Justice".
                for code in course_codes:
                    rows.append({
                        **base,
                        "rule_type": "ANY_N",
                        "option_type": "COURSE",
                        "option_value": code,
                    })
            else:
                raise ValueError(
                    f"EXACT requirement has no course code: "
                    f"{row['requirement_id']} {raw_text} {course_codes}"
                )

        elif rule_type == "ANY_N":
            if course_codes:
                for code in course_codes:
                    rows.append({
                        **base,
                        "option_type": "COURSE",
                        "option_value": code,
                    })

                if "ELECTIVE" in raw_text.upper():
                    rows.append({
                        **base,
                        "option_type": "ELECTIVE",
                        "option_value": raw_text,
                    })
            elif "ELECTIVE" in raw_text.upper():
                rows.append({
                    **base,
                    "rule_type": "ELECTIVE",
                    "option_type": "ELECTIVE",
                    "option_value": raw_text,
                })
            else:
                raise ValueError(
                    f"ANY_N requirement has no course/elective option: "
                    f"{row['requirement_id']} {raw_text} {course_codes}"
                )

        elif rule_type == "CORE_BUCKET":
            if course_codes:
                # Some core rows name a specific course and its core bucket.
                # Preserve the direct course option so the existing audit engine can match it.
                for code in course_codes:
                    rows.append({
                        **base,
                        "option_type": "COURSE",
                        "option_value": code,
                    })
            else:
                rows.append({
                    **base,
                    "option_type": "CORE_BUCKET",
                    "option_value": raw_text,
                })

        elif rule_type == "ELECTIVE":
            rows.append({
                **base,
                "option_type": "ELECTIVE",
                "option_value": raw_text,
            })

        else:
            raise ValueError(f"Unsupported rule_type: {rule_type}")

    return rows


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    master = pd.read_csv(INPUT_PATH)

    required_cols = [
        "catalog_year",
        "credential_id",
        "credential_title",
        "requirement_id",
        "requirement_sequence",
        "rule_type",
        "credit_hours",
        "semester_label",
        "raw_requirement_text",
        "course_codes",
    ]

    missing = [col for col in required_cols if col not in master.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    rows = build_rows(master)
    audit_requirements = pd.DataFrame(rows)

    duplicate_options = audit_requirements.duplicated(
        subset=[
            "catalog_year",
            "credential_id",
            "requirement_id",
            "option_type",
            "option_value",
        ]
    ).sum()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    audit_requirements.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(audit_requirements)} audit requirement option rows to {OUTPUT_PATH}")
    print()
    print("Option types:")
    print(audit_requirements["option_type"].value_counts().sort_index())
    print()
    print("Rule types:")
    print(audit_requirements["rule_type"].value_counts().sort_index())
    print()
    print(f"Duplicate option rows: {duplicate_options}")
    print()
    print("Credential-year count:")
    print(
        audit_requirements[["catalog_year", "credential_id"]]
        .drop_duplicates()
        ["catalog_year"]
        .value_counts()
        .sort_index()
    )


if __name__ == "__main__":
    main()