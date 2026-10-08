"""READ-ONLY single-student historical reconstruction diagnostic.

Run from LSCO audit project root:
    python diagnose_teacher_education_prior_award.py

Requires pandas and lsco_audit importable (typically the project's active .venv).
Never modifies source, pipeline or award output files.
"""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path.cwd()
PROCESSED = ROOT / 'data' / 'processed'
STAGE = PROCESSED / 'reporting' / 'second_associate_stage1_current_20261008_120811' / 'RESTRICTED_second_associate_stage1_current.csv'
ATTEMPTS = PROCESSED / 'reporting' / 'current_awardability_screen_20261008_103622' / 'RESTRICTED_current_attempt_state_candidate_students.csv'
REQUIREMENTS = PROCESSED / 'catalogs' / 'staging_six_year' / 'requirements_master_multiyear.csv'
STUDENT = 'R80055159'
PRIOR_PROGRAM = 'AAT_AATP'
CATALOG = '2025-2026'
MODEL = 'TEACHER_EDUCATION_AAS_2025'  # historical parser ID; not the official AAT award designation
# Term 202590 assumed to be Fall 2025; require manual confirmation in printed output.
EXPECTED_AWARD_TERM = '202590'


def read(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def main():
    # Locate existing audited code; don't execute its all-student audit entrypoint.
    sys.path.insert(0, str(ROOT / 'src'))
    from lsco_audit import audit_multiyear_sample_path_candidate as engine

    stage = read(STAGE)
    prior = stage.loc[(stage.student_id == STUDENT) & (stage.first_prior_program_code == PRIOR_PROGRAM)].copy()
    if prior.empty:
        raise RuntimeError('STOP: no official Teacher Education prior-award record found')
    terms = sorted(set(prior.first_prior_grad_term))
    if terms != [EXPECTED_AWARD_TERM]:
        raise RuntimeError(f'STOP: prior term does not match expected: {terms}')
    official_degree = sorted(set(prior.first_prior_degree_code))
    if official_degree != ['AAT']:
        raise RuntimeError(f'STOP: prior degree code not AAT: {official_degree}')
    print('STUDENT:', STUDENT, 'OFFICIAL PROGRAM:', PRIOR_PROGRAM, 'DEGREE:', official_degree[0])
    print('OFFICIAL PRIOR AWARD TERM:', terms[0], '(confirm term 202590 means Fall 2025)')
    print('CATALOG:', CATALOG, '(confirm catalog 2025-26 effective at award)')

    requirements = read(REQUIREMENTS)
    req = requirements.loc[(requirements.catalog_year == CATALOG) & (requirements.credential_id == MODEL)].copy()
    if len(req) != 19 or req.requirement_id.nunique() != 19:
        raise RuntimeError(f'STOP: unexpected model requirement count: {len(req)} / {req.requirement_id.nunique()}')
    print('PARSED MODEL ID:', MODEL, '(name is misleading; retain for requirement/policy lookups)')

    all_attempts = read(ATTEMPTS)
    raw = all_attempts.loc[all_attempts.student_id == STUDENT].copy()
    if len(raw) != 41:
        raise RuntimeError(f'STOP: expected 41 attempt rows, got {len(raw)}')
    raw['term_numeric'] = pd.to_numeric(raw.term_sort, errors='coerce')
    if raw.term_numeric.isna().any():
        raise RuntimeError('STOP: unparseable attempt terms')
    at_award = raw.loc[raw.term_numeric <= int(terms[0])].copy()
    print('ATTEMPTS:', len(raw), 'BY AWARD TERM:', len(at_award))
    print('GRADES BY AWARD TERM (aggregate only):', at_award.final_grade.str.upper().str.strip().value_counts().to_dict())

    # Reproduce the prior historical normalizer pass semantics explicitly,
    # not the generic audit module fallback which treats grade E as passing.
    # Flag ambiguous/unexpected grades rather than silently classify them.
    pass_grades = {'A', 'B', 'C', 'D', 'S', 'P', 'CR', 'TA', 'TB', 'TC', 'TD', 'TS', 'T'}
    nonpass_grades = {'F', 'U', 'TF', 'TU', 'I', 'Q', 'QL', 'W', '', 'NG'}
    grades = set(at_award.final_grade.str.upper().str.strip())
    unexpected = sorted(grades - pass_grades - nonpass_grades)
    if unexpected:
        raise RuntimeError(f'STOP: unsupported/ambiguous grade codes: {unexpected}')
    at_award['grade'] = at_award.final_grade.str.upper().str.strip()
    at_award['course_code'] = at_award.course_code.map(engine.normalize_course_code)
    if (at_award.course_code == '').any():
        raise RuntimeError('STOP: blank course codes in attempt history')
    at_award['passed'] = at_award.grade.isin(pass_grades).map({True: 'TRUE', False: 'FALSE'})
    course_lookup = engine.completed_course_lookup(at_award)
    print('DISTINCT SUCCESSFUL COURSES AS OF AWARD:', len(course_lookup))

    core_lookup = engine.load_core_lookup()
    elective_rules = engine.load_elective_rules()
    academic_courses = engine.load_academic_course_lookup()
    compound_alternatives = engine.load_compound_requirement_alternatives()
    # Diagnostic-only: use the staged six-year alternative-path policy.
    engine.ALTERNATIVE_REQUIREMENT_PATHS = (
        PROCESSED
        / "catalogs"
        / "staging_six_year"
        / "semantic_policies"
        / "alternative_requirement_paths.csv"
    )
    alt_paths = engine.load_alternative_requirement_paths()
    # Validate only the target credential, so unrelated model defects cannot derail the case.
    target_paths = alt_paths.loc[(alt_paths.catalog_year.astype(str) == CATALOG) & (alt_paths.credential_id.astype(str) == MODEL)].copy() if not alt_paths.empty else alt_paths
    engine.validate_alternative_requirement_paths(target_paths, req)
    lookup = engine.build_alternative_path_lookup(target_paths)
    print('ALTERNATIVE-PATH POLICY ROWS:', len(target_paths))

    result = engine.audit_student_credential(
        student_id=STUDENT,
        catalog_year=CATALOG,
        credential_id=MODEL,
        credential_requirements=req,
        course_lookup=course_lookup,
        core_lookup=core_lookup,
        elective_rules=elective_rules,
        academic_course_lookup=academic_courses,
        compound_alternatives=compound_alternatives,
        alternative_path_lookup=lookup,
    )
    detail = pd.DataFrame(result)
    if detail.empty:
        raise RuntimeError('STOP: evaluator returned no rows')
    selected = detail.loc[detail.path_selected.astype(str).isin(['', 'TRUE'])].copy() if 'path_selected' in detail else detail
    print('\nSELECTED REQUIREMENT RESULTS:')
    shown = [c for c in ['requirement_id','status','matched_course_codes','matched_courses','matched_course','path_id','path_selected'] if c in selected.columns]
    print(selected[shown].to_string(index=False, max_colwidth=64))
    print("\n=== ALLOCATION TRACE: ALL 19 REQUIREMENTS ===")
    print("AVAILABLE DETAIL COLUMNS:", list(selected.columns))
    trace_cols = [
        c for c in selected.columns
        if c in {"requirement_id", "status", "group_name", "rule_type"}
        or any(word in c.lower() for word in
               ["matched", "selected_course", "used_course", "consumed"])
    ]
    print(selected[trace_cols].to_string(index=False, max_colwidth=120))

    print("\n=== FIVE UNMET REQUIREMENTS ===")
    missing_ids = [
        "TEACHER_EDUCATION_AAS_2025_R4",
        "TEACHER_EDUCATION_AAS_2025_R5",
        "TEACHER_EDUCATION_AAS_2025_R13",
        "TEACHER_EDUCATION_AAS_2025_R18",
        "TEACHER_EDUCATION_AAS_2025_R19",
    ]
    for rid in missing_ids:
        model_rows = req.loc[req.requirement_id == rid]
        result_rows = selected.loc[selected.requirement_id == rid]
        print("\n", rid)
        print("MODEL:", model_rows[
            ["rule_type", "group_name", "option_type", "option_value"]
        ].to_dict("records"))
        print("RESULT:", result_rows.to_dict("records"))

    print("\n=== RELEVANT HISTORICAL ATTEMPTS ===")
    relevant = at_award.loc[
        at_award.course_code.str.match(
            r"^(MATH|GEOG|BIOL|CHEM|PHYS|GEOL|ENVR|ASTR)\s",
            na=False
        )
    ].copy()
    relevant = relevant.sort_values(["course_code", "term_numeric"])
    print(relevant[
        ["course_code", "term_taken", "final_grade", "passed"]
    ].to_string(index=False))

    print("\n=== SUCCESSFUL COURSES NOT USED IN THE FIVE UNMET REQUIREMENTS ===")
    print("All successful courses available to allocator:")
    for code, metadata in sorted(course_lookup.items()):
        print(code, metadata["grade"], metadata["term_sort"])
    statuses = selected['status'].astype(str).str.upper().str.strip()
    met = int((statuses == 'MET').sum())
    missing = int((statuses != 'MET').sum())
    unresolved = int(statuses.str.contains('UNRESOLVED|REVIEW').sum())
    status = engine.get_audit_status(missing, unresolved)
    print('\nRESULT:', status, '| MET:', met, '| OTHER:', missing, '| UNRESOLVED:', unresolved)
    print('No pipeline files written. Official degree remains authoritative regardless of result.')
    print('This is NOT a determination of 15 additional resident SCH.')


if __name__ == '__main__':
    main()
