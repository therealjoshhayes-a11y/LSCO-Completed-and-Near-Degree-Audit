from pathlib import Path

import pandas as pd


DETAIL_PATH = Path("data/processed/multiyear_sample_audit_results.csv")
SUMMARY_PATH = Path("data/processed/multiyear_sample_credential_summary.csv")
MASTER_PATH = Path("data/processed/catalogs/requirements_master_multicatalog.csv")
ELECTIVE_RULES_PATH = Path("data/processed/catalogs/elective_rules_multicatalog.csv")

OUTPUT_PATH = Path("data/processed/labeled_audit_opportunities.csv")


STALE_LONG_SEMESTER_GAP_THRESHOLD = 12


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for path in [DETAIL_PATH, SUMMARY_PATH, MASTER_PATH, ELECTIVE_RULES_PATH]:
        if not path.exists():
            raise FileNotFoundError(path)

    detail = pd.read_csv(DETAIL_PATH)
    summary = pd.read_csv(SUMMARY_PATH)
    master = pd.read_csv(MASTER_PATH)
    elective_rules = pd.read_csv(ELECTIVE_RULES_PATH).fillna("")

    return detail, summary, master, elective_rules


def make_requirement_lookup(master: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "requirement_id",
        "catalog_year",
        "credential_id",
        "credential_title",
        "credential_family",
        "semester_label",
        "rule_type",
        "credit_hours",
        "raw_requirement_text",
    ]

    available = [col for col in cols if col in master.columns]

    lookup = (
        master[available]
        .drop_duplicates(subset=["requirement_id"])
        .copy()
    )

    return lookup


def summarize_missing_requirements(
    detail: pd.DataFrame,
    requirement_lookup: pd.DataFrame,
    elective_rules: pd.DataFrame,
) -> pd.DataFrame:
    missing = detail[detail["status"].ne("MET")].copy()

    missing = missing.merge(
        requirement_lookup,
        on=["requirement_id", "catalog_year", "credential_id", "rule_type"],
        how="left",
        suffixes=("", "_master"),
    )

    missing = missing.merge(
        elective_rules[["requirement_id", "resolver_type", "allowed_rubrics"]],
        on="requirement_id",
        how="left",
    )

    missing["required_options"] = missing["required_options"].map(normalize_text)
    missing["raw_requirement_text"] = missing["raw_requirement_text"].map(normalize_text)
    missing["resolver_type"] = missing["resolver_type"].fillna("").map(normalize_text)
    missing["allowed_rubrics"] = missing["allowed_rubrics"].fillna("").map(normalize_text)

    # Prefer source requirement text for display because required_options is option-row shaped.
    # Example: "BUSI 2304 or EDUC 1300" should display as one missing requirement,
    # not as two separate missing courses.
    missing["display_requirement"] = missing["raw_requirement_text"]
    missing.loc[
        missing["display_requirement"].eq("") & missing["required_options"].ne(""),
        "display_requirement",
    ] = missing["required_options"]

    missing["missing_course_text"] = ""
    missing.loc[
        missing["status"].eq("UNMET"),
        "missing_course_text",
    ] = missing["display_requirement"]

    missing["unresolved_elective_text"] = ""
    missing.loc[
        missing["status"].astype(str).str.startswith("UNRESOLVED"),
        "unresolved_elective_text",
    ] = missing["display_requirement"]

    grouped = []

    group_cols = ["student_id", "catalog_year", "credential_id"]

    for keys, group in missing.groupby(group_cols, dropna=False):
        student_id, catalog_year, credential_id = keys

        unmet = group[group["status"].eq("UNMET")].copy()
        unresolved = group[group["status"].astype(str).str.startswith("UNRESOLVED")].copy()

        missing_courses = [
            value
            for value in unmet["missing_course_text"].dropna().astype(str).tolist()
            if value.strip()
        ]

        unresolved_electives = [
            value
            for value in unresolved["unresolved_elective_text"].dropna().astype(str).tolist()
            if value.strip()
        ]

        unresolved_resolver_types = [
            value
            for value in unresolved["resolver_type"].dropna().astype(str).tolist()
            if value.strip()
        ]

        missing_summary_parts = []
        if missing_courses:
            missing_summary_parts.append("Missing: " + "; ".join(missing_courses))
        if unresolved_electives:
            missing_summary_parts.append("Review electives: " + "; ".join(unresolved_electives))

        grouped.append(
            {
                "student_id": student_id,
                "catalog_year": catalog_year,
                "credential_id": credential_id,
                "missing_courses": "; ".join(missing_courses),
                "unresolved_electives": "; ".join(unresolved_electives),
                "unresolved_resolver_types": "; ".join(sorted(set(unresolved_resolver_types))),
                "missing_requirement_summary": " | ".join(missing_summary_parts),
            }
        )

    return pd.DataFrame(grouped)


def classify_opportunity(row: pd.Series) -> tuple[str, str, int]:
    missing = int(row.get("requirements_missing", 0))
    unresolved = int(row.get("requirements_unresolved", 0))
    met = int(row.get("requirements_met", 0))
    total = int(row.get("requirements_total", 0))

    stale_gap = pd.to_numeric(
        row.get("max_missed_long_semesters_between_earned_terms", 0),
        errors="coerce",
    )

    if pd.isna(stale_gap):
        stale_gap = 0

    has_stale_history = bool(stale_gap >= STALE_LONG_SEMESTER_GAP_THRESHOLD)

    if row.get("audit_status") == "COMPLETE":
        if has_stale_history:
            return "REQUIREMENT_COMPLETE_REVIEW", "REQUIREMENT_COMPLETE_REVIEW", 90
        return "REQUIREMENT_COMPLETE", "REQUIREMENT_COMPLETE", 100

    if met == 0:
        return "NO_MATCH", "NO_ACTION", 5

    if unresolved > 0:
        if missing <= 3:
            if has_stale_history:
                return "ELECTIVE_REVIEW_STALE_HISTORY", "ELECTIVE_REVIEW", 70
            return "ELECTIVE_REVIEW_REQUIRED", "ELECTIVE_REVIEW", 80

        if has_stale_history:
            return "IN_PROGRESS_ELECTIVE_REVIEW_STALE_HISTORY", "IN_PROGRESS_REVIEW", 35
        return "IN_PROGRESS_ELECTIVE_REVIEW", "IN_PROGRESS_REVIEW", 45

    if missing <= 3 and met > 0:
        if has_stale_history:
            return "NEAR_REQUIREMENT_COMPLETE_REVIEW", "NEAR_REQUIREMENT_COMPLETE_REVIEW", 75
        return "NEAR_REQUIREMENT_COMPLETE", "NEAR_REQUIREMENT_COMPLETE", 85

    progress_ratio = met / total if total else 0

    if progress_ratio >= 0.5:
        if has_stale_history:
            return "IN_PROGRESS_HIGH_STALE_HISTORY", "IN_PROGRESS_REVIEW", 40
        return "IN_PROGRESS_HIGH", "IN_PROGRESS_REVIEW", 50

    return "IN_PROGRESS_LOW", "NO_ACTION", 15


def add_labels(summary: pd.DataFrame, missing_summary: pd.DataFrame) -> pd.DataFrame:
    labeled = summary.merge(
        missing_summary,
        on=["student_id", "catalog_year", "credential_id"],
        how="left",
    )

    for col in [
        "missing_courses",
        "unresolved_electives",
        "unresolved_resolver_types",
        "missing_requirement_summary",
    ]:
        labeled[col] = labeled[col].fillna("")

    labels = labeled.apply(classify_opportunity, axis=1, result_type="expand")
    labeled["opportunity_label"] = labels[0]
    labeled["action_band"] = labels[1]
    labeled["opportunity_score"] = labels[2].astype(int)

    labeled["requires_elective_review"] = labeled["requirements_unresolved"].astype(int) > 0
    labeled["requires_continuity_review"] = (
        pd.to_numeric(
            labeled["max_missed_long_semesters_between_earned_terms"],
            errors="coerce",
        ).fillna(0)
        >= STALE_LONG_SEMESTER_GAP_THRESHOLD
    )
    labeled["requires_degreeworks_review"] = labeled["action_band"].isin(
        ["REQUIREMENT_COMPLETE", "REQUIREMENT_COMPLETE_REVIEW", "NEAR_REQUIREMENT_COMPLETE", "NEAR_REQUIREMENT_COMPLETE_REVIEW", "ELECTIVE_REVIEW"]
    )
    labeled["requires_catalog_policy_review"] = labeled["requires_continuity_review"]
    labeled["requires_substitution_review"] = False

    labeled["eligible_for_audit"] = True
    labeled["eligibility_reason"] = "Included in current audit universe"
    labeled["catalog_eligibility_basis"] = "Student-course-history x catalog-credential universe"

    labeled["progress_ratio"] = (
        labeled["requirements_met"].astype(float)
        / labeled["requirements_total"].replace(0, pd.NA).astype(float)
    ).fillna(0)

    labeled = labeled.sort_values(
        [
            "student_id",
            "opportunity_score",
            "requirements_missing",
            "requirements_unresolved",
            "requirements_met",
            "catalog_year",
            "credential_id",
        ],
        ascending=[True, False, True, True, False, False, True],
        kind="mergesort",
    ).copy()

    labeled["student_overall_rank"] = (
        labeled.groupby("student_id").cumcount() + 1
    )

    labeled["student_catalog_rank"] = (
        labeled.groupby(["student_id", "catalog_year"]).cumcount() + 1
    )

    if "credential_family" in labeled.columns:
        labeled["credential_family_rank"] = (
            labeled.groupby(["student_id", "credential_family"]).cumcount() + 1
        )
    else:
        labeled["credential_family_rank"] = ""

    return labeled


def main() -> None:
    detail, summary, master, elective_rules = load_inputs()

    requirement_lookup = make_requirement_lookup(master)
    missing_summary = summarize_missing_requirements(
        detail=detail,
        requirement_lookup=requirement_lookup,
        elective_rules=elective_rules,
    )

    labeled = add_labels(summary=summary, missing_summary=missing_summary)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    labeled.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(labeled)} labeled audit opportunity rows to {OUTPUT_PATH}")
    print()
    print("Opportunity labels:")
    print(labeled["opportunity_label"].value_counts().sort_index())
    print()
    print("Action bands:")
    print(labeled["action_band"].value_counts().sort_index())
    print()
    print("Top opportunity per student:")
    top = labeled[labeled["student_overall_rank"].eq(1)].copy()
    print(
        top[
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "opportunity_label",
                "action_band",
                "opportunity_score",
                "requirements_met",
                "requirements_total",
                "requirements_missing",
                "requirements_unresolved",
                "missing_requirement_summary",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
    