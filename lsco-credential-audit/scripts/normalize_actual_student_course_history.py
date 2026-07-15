from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/raw/student_exports/banner_course_history_actual.csv")
OUTPUT_PATH = Path("data/processed/normalized_actual_student_course_history.csv")
QA_OUTPUT_PATH = Path("data/processed/normalized_actual_student_course_history_qa.csv")


PASSING_GRADES = {"A", "B", "C", "D", "S", "P", "CR", "TA", "TB", "TC", "TD", "TS", "T"}

def is_passing_grade(grade: str) -> bool:
    """
    LSCO grade interpretation for audit-completion purposes.

    Count:
      A/B/C/D
      S
      P/CR if present
      T transfer work when the carried grade is passing:
        T, TA, TB, TC, TD, TS

    Do not count:
      F, U, TF, TU
      I
      Q, QL, W
      blank/current-term grades
      numeric grades not rolled to academic history
      NG

    E credit-by-exam grades are not currently expected in this extract.
    They are left out until explicitly approved for completion logic.
    """
    g = str(grade).strip().upper()

    if g == "":
        return False

    # Numeric grades have not rolled to academic history.
    if g.isdigit():
        return False

    if g in {"A", "B", "C", "D", "S", "P", "CR"}:
        return True

    if g in {"T", "TA", "TB", "TC", "TD", "TS"}:
        return True

    return False



GRADE_RANK = {
    "A": 4,
    "TA": 4,
    "B": 3,
    "TB": 3,
    "C": 2,
    "TC": 2,
    "D": 1,
    "TD": 1,
    "P": 1,
    "CR": 1,
    "S": 1,
}


def normalize_course_code(subject: str, number: str) -> str:
    subject = str(subject).strip().upper()
    number = str(number).strip()

    if subject in {"", "NAN"} or number in {"", "NAN"}:
        return ""

    number = number.split(".")[0].zfill(4)
    return f"{subject} {number}"


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    raw = pd.read_csv(INPUT_PATH, dtype=str).fillna("")

    required = [
        "StudenID",
        "StudentMajor",
        "Subject",
        "CrseNumb",
        "FinalGrade",
        "Term",
        "DualCreditIndicator",
        "HighSchool",
        "LastTermDualCredit",
    ]

    missing = [col for col in required if col not in raw.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = pd.DataFrame()
    df["student_id"] = raw["StudenID"].astype(str).str.strip()
    df["student_major"] = raw["StudentMajor"].astype(str).str.strip()
    df["subject"] = raw["Subject"].astype(str).str.strip().str.upper()
    df["course_number"] = raw["CrseNumb"].astype(str).str.strip()
    df["course_code"] = [
        normalize_course_code(subject, number)
        for subject, number in zip(df["subject"], df["course_number"])
    ]
    df["final_grade"] = raw["FinalGrade"].astype(str).str.strip().str.upper()
    df["term_taken"] = raw["Term"].astype(str).str.strip()
    df["term_sort"] = pd.to_numeric(df["term_taken"], errors="coerce")
    df["dual_credit_indicator"] = raw["DualCreditIndicator"].astype(str).str.strip()
    df["high_school"] = raw["HighSchool"].astype(str).str.strip()
    df["last_term_dual_credit"] = raw["LastTermDualCredit"].astype(str).str.strip()

    df["is_passing"] = df["final_grade"].map(is_passing_grade)
    df["grade"] = df["final_grade"]
    df["passed"] = df["is_passing"]
    df["grade_rank"] = df["final_grade"].map(GRADE_RANK).fillna(0).astype(int)

    before = len(df)

    df = df[df["student_id"].ne("")]
    df = df[df["course_code"].ne("")]
    df = df[df["term_sort"].notna()]
    df = df[df["term_sort"].ge(197000)]
    df = df[df["is_passing"]].copy()

    after_filter = len(df)

    # Keep one usable attempt per student/course:
    # highest grade rank, then latest term.
    df = df.sort_values(
        ["student_id", "course_code", "grade_rank", "term_sort"],
        ascending=[True, True, False, False],
        kind="mergesort",
    ).copy()

    df = df.drop_duplicates(
        subset=["student_id", "course_code"],
        keep="first",
    ).copy()

    after_dedupe = len(df)

    output_cols = [
        "student_id",
        "student_major",
        "course_code",
        "subject",
        "course_number",
        "final_grade",
        "grade",
        "passed",
        "grade_rank",
        "term_taken",
        "term_sort",
        "dual_credit_indicator",
        "high_school",
        "last_term_dual_credit",
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df[output_cols].to_csv(OUTPUT_PATH, index=False)

    qa_rows = [
        {"metric": "raw_rows", "value": before},
        {"metric": "passing_valid_rows", "value": after_filter},
        {"metric": "deduped_student_course_rows", "value": after_dedupe},
        {"metric": "unique_students", "value": df["student_id"].nunique()},
        {"metric": "unique_course_codes", "value": df["course_code"].nunique()},
        {"metric": "unique_terms", "value": df["term_taken"].nunique()},
        {"metric": "unique_student_majors", "value": df["student_major"].nunique()},
    ]

    qa = pd.DataFrame(qa_rows)
    qa.to_csv(QA_OUTPUT_PATH, index=False)

    print(f"Wrote {after_dedupe} normalized rows to {OUTPUT_PATH}")
    print(f"Wrote QA summary to {QA_OUTPUT_PATH}")
    print()
    print("QA SUMMARY")
    print(qa.to_string(index=False))
    print()
    print("GRADE COUNTS, RAW")
    print(raw["FinalGrade"].astype(str).str.strip().str.upper().value_counts(dropna=False).sort_index())
    print()
    print("TERM COUNTS, NORMALIZED")
    print(df["term_taken"].value_counts().sort_index())
    print()
    print("TOP 25 COURSE CODES, NORMALIZED")
    print(df["course_code"].value_counts().head(25))


if __name__ == "__main__":
    main()