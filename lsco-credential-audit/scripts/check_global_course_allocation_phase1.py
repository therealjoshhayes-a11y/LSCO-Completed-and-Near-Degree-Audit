from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from lsco_audit.audit_multiyear_sample import (
    completed_course_lookup,
    load_compound_requirement_alternatives,
    load_core_lookup,
    normalize_bucket_name,
    normalize_course_code,
)

HISTORY = Path('data/processed/normalized_actual_student_course_history.csv')
SUMMARY = Path('data/processed/full_actual_audit/full_actual_credential_summary.csv')
REQUIREMENTS = Path('data/processed/catalogs/requirements_master_multiyear.csv')
ELIGIBILITY = Path('data/processed/student_catalog_eligibility.csv')

OUTPUT_DIR = Path('data/processed/reporting') / (
    'global_allocation_shadow_check_' + datetime.now().strftime('%Y%m%d_%H%M%S')
)
SAFE_OUTPUT = OUTPUT_DIR / 'FERPA_SAFE_Global_Allocation_Shadow_Check.xlsx'
RESTRICTED_OUTPUT = OUTPUT_DIR / 'RESTRICTED_Global_Allocation_Shadow_Check.xlsx'

MAX_MISSING = 3
MAX_ALTERNATIVES_PER_REQUIREMENT = 5000


def truthy(value: object) -> bool:
    return str(value).strip().upper() in {'TRUE', '1', 'YES', 'Y', 'ELIGIBLE'}


def build_requirement_alternatives(
    requirement_id: str,
    catalog_year: str,
    group: pd.DataFrame,
    passed_courses: set[str],
    core_lookup: dict[tuple[str, str], set[str]],
    compound_alternatives: dict[str, list[list[str]]],
) -> tuple[list[tuple[str, ...]], str]:
    requirement_id = str(requirement_id)

    if requirement_id in compound_alternatives:
        feasible = []
        for alternative in compound_alternatives[requirement_id]:
            normalized = tuple(normalize_course_code(c) for c in alternative)
            if set(normalized).issubset(passed_courses):
                feasible.append(normalized)
        return sorted(set(feasible)), 'COMPOUND'

    option_types = {
        str(value).strip().upper()
        for value in group['option_type'].dropna()
        if str(value).strip()
    }

    if 'ELECTIVE' in option_types or str(group.iloc[0]['rule_type']).strip().upper() == 'ELECTIVE':
        return [], 'ELECTIVE_EXCLUDED'

    candidates: set[str] = set()

    for _, option in group.iterrows():
        option_type = str(option['option_type']).strip().upper()
        option_value = normalize_course_code(option['option_value'])

        if option_type == 'COURSE':
            if option_value in passed_courses:
                candidates.add(option_value)

        elif option_type == 'CORE_BUCKET':
            bucket_name = normalize_bucket_name(option_value)
            if bucket_name is None:
                return [], 'UNRESOLVED_CORE_LABEL'

            lookup_key = (str(catalog_year), str(bucket_name))
            if lookup_key not in core_lookup:
                return [], 'MISSING_CORE_LOOKUP'

            candidates.update(passed_courses.intersection(core_lookup[lookup_key]))

    required = int(float(group.iloc[0]['min_required']))

    if required <= 0:
        return [tuple()], 'ZERO_REQUIRED'

    if len(candidates) < required:
        return [], 'INSUFFICIENT_CANDIDATES'

    import math
    if math.comb(len(candidates), required) > MAX_ALTERNATIVES_PER_REQUIREMENT:
        return [], 'TOO_MANY_ALTERNATIVES'

    alternatives = [
        tuple(combo)
        for combo in itertools.combinations(sorted(candidates), required)
    ]
    return alternatives, 'STANDARD'


def solve_disjoint_requirement_assignment(
    requirement_alternatives: dict[str, list[tuple[str, ...]]]
) -> dict[str, tuple[str, ...]] | None:
    ordered = sorted(
        requirement_alternatives,
        key=lambda requirement_id: (
            len(requirement_alternatives[requirement_id]),
            min((len(option) for option in requirement_alternatives[requirement_id]), default=999999),
            requirement_id,
        ),
    )

    assignment: dict[str, tuple[str, ...]] = {}

    def search(index: int, used: set[str]) -> bool:
        if index >= len(ordered):
            return True

        requirement_id = ordered[index]

        for option in requirement_alternatives[requirement_id]:
            option_set = set(option)
            if option_set.isdisjoint(used):
                assignment[requirement_id] = option
                if search(index + 1, used | option_set):
                    return True
                assignment.pop(requirement_id, None)

        return False

    if search(0, set()):
        return assignment
    return None


def main() -> None:
    for path in [HISTORY, SUMMARY, REQUIREMENTS, ELIGIBILITY]:
        if not path.exists():
            raise FileNotFoundError(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(SUMMARY, dtype=str, low_memory=False).fillna('')
    eligibility = pd.read_csv(ELIGIBILITY, dtype=str, low_memory=False).fillna('')
    requirements = pd.read_csv(REQUIREMENTS, dtype=str, low_memory=False).fillna('')
    history = pd.read_csv(HISTORY, dtype=str, low_memory=False).fillna('')

    summary['requirements_missing_numeric'] = pd.to_numeric(
        summary['requirements_missing'], errors='coerce'
    )

    eligible_pairs = eligibility[
        eligibility['catalog_eligible'].map(truthy)
    ][['student_id', 'catalog_year']].drop_duplicates()

    targets = summary[
        summary['requirements_missing_numeric'].between(1, MAX_MISSING, inclusive='both')
    ].merge(eligible_pairs, on=['student_id', 'catalog_year'], how='inner')

    print('=' * 100)
    print('GLOBAL ALLOCATION SHADOW CHECK — PHASE 1')
    print('=' * 100)
    print(f'Eligible 1-{MAX_MISSING} missing student-credential rows: {len(targets):,}')
    print(f"Distinct students: {targets['student_id'].nunique():,}")
    print()

    requirements_by_credential = {
        (str(catalog_year), str(credential_id)): credential_rows.copy()
        for (catalog_year, credential_id), credential_rows in requirements.groupby(
            ['catalog_year', 'credential_id'], sort=False
        )
    }

    core_lookup = load_core_lookup()
    compound_alternatives = load_compound_requirement_alternatives()

    target_students = set(targets['student_id'])
    history = history[history['student_id'].isin(target_students)].copy()

    course_lookup_by_student = {}
    for student_id, student_rows in history.groupby('student_id', sort=False):
        course_lookup_by_student[str(student_id)] = completed_course_lookup(student_rows)

    results = []
    exclusion_counts = defaultdict(int)

    for index, row in enumerate(targets.itertuples(index=False), start=1):
        student_id = str(row.student_id)
        catalog_year = str(row.catalog_year)
        credential_id = str(row.credential_id)

        credential_rows = requirements_by_credential.get((catalog_year, credential_id))
        course_lookup = course_lookup_by_student.get(student_id, {})
        passed_courses = set(course_lookup)

        if credential_rows is None:
            exclusion_counts['MISSING_CREDENTIAL_REQUIREMENTS'] += 1
            continue

        requirement_alternatives: dict[str, list[tuple[str, ...]]] = {}
        excluded_reason = ''

        for requirement_id, group in credential_rows.groupby('requirement_id', sort=False):
            alternatives, reason = build_requirement_alternatives(
                requirement_id=str(requirement_id),
                catalog_year=catalog_year,
                group=group,
                passed_courses=passed_courses,
                core_lookup=core_lookup,
                compound_alternatives=compound_alternatives,
            )

            if reason in {
                'ELECTIVE_EXCLUDED',
                'UNRESOLVED_CORE_LABEL',
                'MISSING_CORE_LOOKUP',
                'TOO_MANY_ALTERNATIVES',
            }:
                excluded_reason = reason
                break

            if not alternatives:
                excluded_reason = 'AT_LEAST_ONE_REQUIREMENT_HAS_NO_FEASIBLE_OPTION'
                break

            requirement_alternatives[str(requirement_id)] = alternatives

        if excluded_reason:
            exclusion_counts[excluded_reason] += 1
            continue

        assignment = solve_disjoint_requirement_assignment(requirement_alternatives)

        if assignment is None:
            results.append({
                'student_id': student_id,
                'catalog_year': catalog_year,
                'credential_id': credential_id,
                'current_audit_status': str(row.audit_status),
                'current_requirements_missing': int(row.requirements_missing_numeric),
                'shadow_result': 'NO_GLOBAL_SOLUTION',
                'requirement_count': len(requirement_alternatives),
                'assigned_course_count': '',
                'assignment_text': '',
            })
        else:
            assignment_text = ' | '.join(
                f"{requirement_id}: {', '.join(courses)}"
                for requirement_id, courses in sorted(assignment.items())
            )
            assigned_course_count = len({
                course
                for courses in assignment.values()
                for course in courses
            })

            results.append({
                'student_id': student_id,
                'catalog_year': catalog_year,
                'credential_id': credential_id,
                'current_audit_status': str(row.audit_status),
                'current_requirements_missing': int(row.requirements_missing_numeric),
                'shadow_result': 'GLOBALLY_SATISFIABLE',
                'requirement_count': len(requirement_alternatives),
                'assigned_course_count': assigned_course_count,
                'assignment_text': assignment_text,
            })

        if index % 500 == 0:
            print(f'Processed targets: {index:,}/{len(targets):,}')

    result_df = pd.DataFrame(results)
    if result_df.empty:
        result_df = pd.DataFrame(columns=[
            'student_id', 'catalog_year', 'credential_id', 'current_audit_status',
            'current_requirements_missing', 'shadow_result', 'requirement_count',
            'assigned_course_count', 'assignment_text'
        ])

    satisfiable = result_df[result_df['shadow_result'].eq('GLOBALLY_SATISFIABLE')].copy()

    by_credential = (
        satisfiable.groupby(['catalog_year', 'credential_id'], dropna=False)
        .agg(
            candidate_rows=('student_id', 'size'),
            distinct_students=('student_id', 'nunique'),
            max_current_missing=('current_requirements_missing', 'max'),
        )
        .reset_index()
        .sort_values(['candidate_rows', 'catalog_year', 'credential_id'], ascending=[False, True, True])
    )

    exclusions = pd.DataFrame([
        {'exclusion_reason': reason, 'rows': count}
        for reason, count in sorted(exclusion_counts.items())
    ])

    kpis = pd.DataFrame([
        {'metric': 'Eligible target rows', 'value': len(targets)},
        {'metric': 'Rows fully evaluated', 'value': len(result_df)},
        {'metric': 'Globally satisfiable despite current missing requirements', 'value': len(satisfiable)},
        {'metric': 'Distinct students globally satisfiable', 'value': satisfiable['student_id'].nunique()},
        {'metric': 'No global solution', 'value': int(result_df['shadow_result'].eq('NO_GLOBAL_SOLUTION').sum())},
    ])

    with pd.ExcelWriter(RESTRICTED_OUTPUT, engine='xlsxwriter') as writer:
        result_df.to_excel(writer, sheet_name='Student Results', index=False)
        satisfiable.to_excel(writer, sheet_name='Satisfiable Only', index=False)

    with pd.ExcelWriter(SAFE_OUTPUT, engine='xlsxwriter') as writer:
        kpis.to_excel(writer, sheet_name='KPI Summary', index=False)
        by_credential.to_excel(writer, sheet_name='By Credential', index=False)
        exclusions.to_excel(writer, sheet_name='Exclusions', index=False)

    print()
    print('=' * 100)
    print('RESULT')
    print('=' * 100)
    print(f'Rows fully evaluated: {len(result_df):,}')
    print(f'Globally satisfiable despite current missing requirements: {len(satisfiable):,}')
    print(f"Distinct students globally satisfiable: {satisfiable['student_id'].nunique():,}")
    print(f"No global solution: {int(result_df['shadow_result'].eq('NO_GLOBAL_SOLUTION').sum()):,}")
    print()
    print('Exclusions:')
    for reason, count in sorted(exclusion_counts.items()):
        print(f'  {reason}: {count:,}')
    print()
    print(f'RESTRICTED workbook: {RESTRICTED_OUTPUT}')
    print(f'FERPA-SAFE workbook: {SAFE_OUTPUT}')
    print()
    print('UPLOAD ONLY THE FERPA-SAFE WORKBOOK.')
    print('PHASE-1 GATE: PASSED')


if __name__ == '__main__':
    main()
