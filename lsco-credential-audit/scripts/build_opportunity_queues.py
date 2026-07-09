from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/processed/labeled_audit_opportunities.csv")

OUTPUT_DIR = Path("data/processed")
TOP_PER_STUDENT_OUTPUT = OUTPUT_DIR / "opportunity_queue_top_per_student.csv"
NEAR_COMPLETE_OUTPUT = OUTPUT_DIR / "opportunity_queue_near_complete.csv"
REVIEW_REQUIRED_OUTPUT = OUTPUT_DIR / "opportunity_queue_review_required.csv"
LOW_PRIORITY_REVIEW_OUTPUT = OUTPUT_DIR / "opportunity_queue_low_priority_review.csv"
FULL_RANKED_OUTPUT = OUTPUT_DIR / "opportunity_queue_full_ranked.csv"


DISPLAY_COLUMNS = [
    "student_id",
    "student_overall_rank",
    "student_catalog_rank",
    "catalog_year",
    "credential_id",
    "opportunity_label",
    "action_band",
    "opportunity_score",
    "requirements_met",
    "requirements_total",
    "requirements_missing",
    "requirements_unresolved",
    "progress_ratio",
    "requires_degreeworks_review",
    "requires_elective_review",
    "requires_continuity_review",
    "requires_catalog_policy_review",
    "missing_courses",
    "unresolved_electives",
    "missing_requirement_summary",
    "award_term_sort",
    "award_term_taken",
    "continuity_break",
    "max_missed_long_semesters_between_earned_terms",
]


def write_queue(df: pd.DataFrame, path: Path) -> None:
    cols = [col for col in DISPLAY_COLUMNS if col in df.columns]
    df[cols].to_csv(path, index=False)
    print(f"Wrote {len(df)} rows to {path}")


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    df = pd.read_csv(INPUT_PATH)

    ranked = df.sort_values(
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

    top_per_student = ranked[ranked["student_overall_rank"].eq(1)].copy()

    near_complete = ranked[
        ranked["action_band"].isin(["NEAR_COMPLETE", "NEAR_COMPLETE_REVIEW"])
    ].copy()

    review_required = ranked[
        ranked["action_band"].eq("HUMAN_REVIEW")
        | ranked["requires_elective_review"].astype(bool)
    ].copy()

    low_priority_review = ranked[
        ranked["action_band"].eq("LOW_PRIORITY_REVIEW")
    ].copy()

    write_queue(ranked, FULL_RANKED_OUTPUT)
    write_queue(top_per_student, TOP_PER_STUDENT_OUTPUT)
    write_queue(near_complete, NEAR_COMPLETE_OUTPUT)
    write_queue(review_required, REVIEW_REQUIRED_OUTPUT)
    write_queue(low_priority_review, LOW_PRIORITY_REVIEW_OUTPUT)

    print()
    print("Queue counts:")
    print(f"full_ranked:         {len(ranked)}")
    print(f"top_per_student:     {len(top_per_student)}")
    print(f"near_complete:       {len(near_complete)}")
    print(f"review_required:     {len(review_required)}")
    print(f"low_priority_review: {len(low_priority_review)}")

    print()
    print("Top per student:")
    print(
        top_per_student[
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