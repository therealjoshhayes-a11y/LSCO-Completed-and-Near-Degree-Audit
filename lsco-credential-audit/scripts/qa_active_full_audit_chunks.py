#!/usr/bin/env python
from pathlib import Path
from datetime import datetime, timedelta
import re
import pandas as pd

chunk_dir = Path('data/processed/full_actual_audit/chunks')
cutoff = datetime.now() - timedelta(minutes=5)
pat_d = re.compile(r'chunk_(\d{5})_audit_results\.csv$')
pat_s = re.compile(r'chunk_(\d{5})_credential_summary\.csv$')

def collect(pat):
    out = {}
    for p in chunk_dir.glob('chunk_*.csv'):
        m = pat.match(p.name)
        if m:
            out[int(m.group(1))] = p
    return out

details = collect(pat_d)
summaries = collect(pat_s)
paired = sorted(set(details) & set(summaries))
settled = [c for c in paired if datetime.fromtimestamp(details[c].stat().st_mtime) < cutoff and datetime.fromtimestamp(summaries[c].stat().st_mtime) < cutoff]
problems = []

missing_summary = sorted(set(details) - set(summaries))
missing_detail = sorted(set(summaries) - set(details))
if missing_summary:
    problems.append(f'detail without summary: {missing_summary[:20]}')
if missing_detail:
    problems.append(f'summary without detail: {missing_detail[:20]}')

summary_rows = 0
summary_students = set()
summary_counts = {}
for c in settled:
    try:
        df = pd.read_csv(summaries[c], dtype=str, keep_default_na=False)
    except Exception as e:
        problems.append(f'chunk {c:05d} summary unreadable: {e}')
        continue
    if df.empty:
        problems.append(f'chunk {c:05d} summary empty')
        continue
    summary_rows += len(df)
    if 'student_id' not in df.columns:
        problems.append(f'chunk {c:05d} summary missing student_id')
    else:
        students = set(df['student_id']) - {''}
        summary_students |= students
        summary_counts[c] = len(students)
        if c < 514 and len(students) != 25:
            problems.append(f'chunk {c:05d} summary students={len(students)}, expected 25')
    for col in ('credential_id','catalog_year'):
        if col not in df.columns:
            problems.append(f'chunk {c:05d} summary missing {col}')
        elif df[col].eq('').any():
            problems.append(f'chunk {c:05d} summary blank {col}')

# evenly spaced sample up to 10 detail chunks
sample = []
if settled:
    n = min(10, len(settled))
    idxs = sorted({round(i*(len(settled)-1)/(n-1)) for i in range(n)}) if n > 1 else [0]
    sample = [settled[i] for i in idxs]

detail_rows = 0
for c in sample:
    try:
        df = pd.read_csv(details[c], dtype=str, keep_default_na=False)
    except Exception as e:
        problems.append(f'chunk {c:05d} detail unreadable: {e}')
        continue
    if df.empty:
        problems.append(f'chunk {c:05d} detail empty')
        continue
    detail_rows += len(df)
    for col in ('student_id','credential_id','catalog_year','requirement_id','rule_type'):
        if col not in df.columns:
            problems.append(f'chunk {c:05d} detail missing {col}')
        elif df[col].eq('').any():
            problems.append(f'chunk {c:05d} detail blank {col}')
    if 'student_id' in df.columns:
        students = set(df['student_id']) - {''}
        if c < 514 and len(students) != 25:
            problems.append(f'chunk {c:05d} detail students={len(students)}, expected 25')
        if c in summary_counts and len(students) != summary_counts[c]:
            problems.append(f'chunk {c:05d} detail/summary student mismatch')
    if df.duplicated().any():
        problems.append(f'chunk {c:05d} exact duplicate detail rows={int(df.duplicated().sum())}')

print('='*96)
print('ACTIVE FULL-AUDIT CHUNK QA')
print('='*96)
print(f'Settled chunk pairs:       {len(settled)}')
if settled:
    newest = max(settled, key=lambda c: details[c].stat().st_mtime)
    print(f'Settled range:             {settled[0]:05d}-{settled[-1]:05d}')
    print(f'Newest settled chunk:      {newest:05d}')
    print(f'Newest settled timestamp:  {datetime.fromtimestamp(details[newest].stat().st_mtime)}')
print(f'All summary rows checked:  {summary_rows:,}')
print(f'Unique students checked:   {len(summary_students):,}')
print('Detail sample:             ' + ', '.join(f'{c:05d}' for c in sample))
print(f'Sampled detail rows:       {detail_rows:,}')
if problems:
    print('\nQA RESULT: REVIEW REQUIRED')
    for p in problems[:40]:
        print('-', p)
    raise SystemExit(2)
print('\nQA RESULT: PASS')
