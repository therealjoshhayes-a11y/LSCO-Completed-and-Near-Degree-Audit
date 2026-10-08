from pathlib import Path
import argparse
import csv


RUNTIME_COLUMNS = [
    "catalog_year",
    "credential_id",
    "credential_title",
    "requirement_id",
    "rule_type",
    "min_required",
    "credit_hours_values",
    "elective_class",
    "explicit_course_count",
    "explicit_courses",
    "rubric_count",
    "allowed_rubrics",
    "source_requirement_text",
    "group_names",
    "option_types",
    "option_values",
    "combined_semantic_text",
    "static_row_count",
    "issue_flags",
    "unresolved_rows_rechecked",
    "distinct_students",
    "safe_now_satisfied",
    "permissive_now_satisfied",
    "still_unmet_or_semantic_review",
    "maximum_eligible_course_count",
    "average_eligible_course_count",
    "review_text",
    "semantic_pattern",
    "review_priority",
    "unresolved_rows_rechecked_num",
    "safe_now_satisfied_num",
    "classification_text",
    "controlled_class",
    "controlled_scope",
    "allowed_rubrics_override",
    "approval_required",
    "resolution_policy",
    "classification_confidence",
    "prior_classification_rejected",
    "override_reason",
]


CONFIGS = {
    "2025-2026": {
        "dir": Path(
            "data/processed/catalogs/"
            "controlled_recovery_2025"
        ),
        "recovery_flag":
            "CONTROLLED_SOURCE_RECOVERY_2025",
    },
    "2026-2027": {
        "dir": Path(
            "data/processed/catalogs/"
            "controlled_recovery_2026"
        ),
        "recovery_flag":
            "CONTROLLED_SOURCE_RECOVERY_2026",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Expand the compact Logistics Management "
            "(Maritime) elective policy into the "
            "40-column audit-runtime schema."
        )
    )

    parser.add_argument(
        "--catalog-year",
        choices=sorted(CONFIGS),
        default="2026-2027",
    )

    return parser.parse_args()


def read_single_row(path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if len(rows) != 1:
        raise SystemExit(
            f"ABORT: expected exactly 1 row in {path}; "
            f"found {len(rows)}"
        )

    return rows[0]


def main():
    args = parse_args()
    config = CONFIGS[args.catalog_year]

    compact_path = (
        config["dir"]
        / "logistics_management_maritime_elective_policy.csv"
    )

    output_path = (
        config["dir"]
        / "logistics_management_maritime_elective_runtime_overlay.csv"
    )

    if not compact_path.exists():
        raise SystemExit(
            f"ABORT: missing compact policy: {compact_path}"
        )

    source = read_single_row(
        compact_path
    )

    required = {
        "requirement_id",
        "catalog_year",
        "credential_id",
        "credential_title",
        "semester_label",
        "credit_hours",
        "raw_requirement_text",
        "resolver_type",
        "allowed_rubrics",
        "resolution_note",
        "policy_status",
    }

    missing = sorted(
        required - set(source)
    )

    if missing:
        raise SystemExit(
            "ABORT: compact policy schema missing: "
            + ", ".join(missing)
        )

    if source["catalog_year"] != args.catalog_year:
        raise SystemExit(
            "ABORT: compact policy catalog year mismatch."
        )

    if source["resolver_type"] != "RUBRIC_ELECTIVE":
        raise SystemExit(
            "ABORT: expected RUBRIC_ELECTIVE."
        )

    if source["raw_requirement_text"] != "BUSI Elective":
        raise SystemExit(
            "ABORT: expected exact source text "
            "'BUSI Elective'."
        )

    if source["allowed_rubrics"] != "BUSI":
        raise SystemExit(
            "ABORT: expected BUSI-only rubric scope."
        )

    if (
        source["policy_status"]
        != "AUTHORIZED_FROM_CATALOG_TEXT_AND_HUMAN_REVIEW"
    ):
        raise SystemExit(
            "ABORT: compact policy lacks approved status."
        )

    try:
        hours = float(
            source["credit_hours"]
        )
    except ValueError as exc:
        raise SystemExit(
            "ABORT: invalid credit_hours."
        ) from exc

    if hours != 2.0:
        raise SystemExit(
            f"ABORT: expected 2 applied SCH; found {hours}"
        )

    raw = source[
        "raw_requirement_text"
    ]

    rubrics = [
        x.strip()
        for x in source[
            "allowed_rubrics"
        ].split("|")
        if x.strip()
    ]

    if rubrics != ["BUSI"]:
        raise SystemExit(
            "ABORT: Logistics BUSI elective scope changed."
        )

    row = {
        "catalog_year":
            source["catalog_year"],

        "credential_id":
            source["credential_id"],

        "credential_title":
            source["credential_title"],

        "requirement_id":
            source["requirement_id"],

        "rule_type":
            "ELECTIVE",

        "min_required":
            "1",

        "credit_hours_values":
            f"{hours:.1f}",

        "elective_class":
            "RUBRIC_RESTRICTED",

        "explicit_course_count":
            "0",

        "explicit_courses":
            "",

        "rubric_count":
            str(len(rubrics)),

        "allowed_rubrics":
            source["allowed_rubrics"],

        "source_requirement_text":
            raw,

        "group_names":
            raw,

        "option_types":
            "ELECTIVE",

        "option_values":
            raw,

        "combined_semantic_text":
            f"{raw} | ELECTIVE",

        "static_row_count":
            "1",

        "issue_flags": (
            f"{config['recovery_flag']};"
            "HUMAN_REVIEW_CONFIRMED_BUSI_RUBRIC_ONLY"
        ),

        "unresolved_rows_rechecked":
            "",

        "distinct_students":
            "",

        "safe_now_satisfied":
            "",

        "permissive_now_satisfied":
            "",

        "still_unmet_or_semantic_review":
            "",

        "maximum_eligible_course_count":
            "",

        "average_eligible_course_count":
            "",

        "review_text":
            "",

        "semantic_pattern":
            "BUSI ELECTIVE ELECTIVE BUSI ELECTIVE ELECTIVE",

        "review_priority":
            "",

        "unresolved_rows_rechecked_num":
            "",

        "safe_now_satisfied_num":
            "",

        "classification_text":
            f"{raw} | ELECTIVE | {raw} | BUSI",

        "controlled_class":
            "RUBRIC_RESTRICTED",

        "controlled_scope":
            "",

        "allowed_rubrics_override":
            "BUSI",

        "approval_required":
            "NO",

        "resolution_policy":
            "COUNT_UNUSED_PASSED_ALLOWED_RUBRIC",

        "classification_confidence":
            "HIGH",

        "prior_classification_rejected":
            "False",

        "override_reason":
            source["resolution_note"],
    }

    if set(row) != set(RUNTIME_COLUMNS):
        raise SystemExit(
            "ABORT: runtime row schema mismatch."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=RUNTIME_COLUMNS,
        )

        writer.writeheader()
        writer.writerow(row)

    print(
        "WROTE:",
        output_path,
    )

    print(
        "CATALOG YEAR:",
        row["catalog_year"],
    )

    print(
        "REQUIREMENT:",
        row["requirement_id"],
    )

    print(
        "CONTROLLED CLASS:",
        row["controlled_class"],
    )

    print(
        "ALLOWED RUBRICS:",
        row["allowed_rubrics_override"],
    )

    print(
        "RESOLUTION POLICY:",
        row["resolution_policy"],
    )


if __name__ == "__main__":
    main()
