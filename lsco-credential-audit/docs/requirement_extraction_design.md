# Requirement Extraction Design

## Purpose

Convert LSCO catalog credential pages into machine-readable requirement records that can be audited against student course history.

Every extracted requirement must retain provenance back to the catalog page and, where possible, the catalog line number.

The parser is responsible for extracting requirements.

The audit engine is responsible for evaluating student records against those requirements.

These responsibilities must remain separate.

---

# Design Principles

## Traceability

Every requirement must be traceable to:

```text
Catalog PDF
    ↓
Catalog Page
    ↓
Requirement Record
```

No requirement should exist without a source page reference.

---

## Reproducibility

Catalog parsing should be deterministic.

Running the parser twice against the same catalog should produce identical outputs.

---

## Separation of Concerns

The parser records requirements.

The audit engine evaluates requirements.

The parser should not attempt to determine whether a student satisfies a requirement.

---

## Incremental Development

Parser development proceeds in phases:

```text
Pattern A
    ↓
Pattern B
    ↓
Pattern C
```

A later pattern must not break a previously functioning pattern.

---

# Current Catalog Structures

Analysis of pages 130, 131, and 133 indicates at least three major credential layouts.

---

# Pattern A – Pure Certificate

## Example

Audio Visual Technology Certificate

Catalog page 130.

## Characteristics

One credential per page.

Requirements are organized by semester.

Every requirement is a specific course.

No OR logic.

No core curriculum buckets.

No electives.

## Example

```text
RTVB 1317
RTVB 1302
RTVB 1321
RTVB 1345
RTVB 2335
FLMC 1304
RTVB 2337
FLMC 2308
```

## Parser Behavior

Match course lines.

Create one requirement record per course.

Ignore:

```text
Semester Hours
Total Program Hours
```

Stop processing after:

```text
Total Program Hours
```

## Output

```text
rule_type = EXACT
option_type = COURSE
min_required = 1
```

---

# Pattern B – Career AAS

## Example

Audio Visual Technology AAS

Catalog page 131.

## Characteristics

Contains exact course requirements.

Contains OR course choices.

Contains core curriculum bucket references.

Contains OR choices between core buckets.

## Example

```text
BUSI 1301
OR
BUSG 1301
```

## Example

```text
LANGUAGE, PHILOSOPHY, AND CULTURE CORE
OR
CREATIVE ARTS CORE
```

## Parser Behavior

Individual courses become EXACT requirements.

OR-linked courses become ANY_N requirements.

Core buckets become bucket options.

OR-linked buckets become ANY_N requirements containing multiple bucket options.

## Output

```text
rule_type = EXACT
rule_type = ANY_N
```

---

# Pattern C – Transfer Degree

## Example

Communication AA

Catalog page 133.

## Characteristics

Contains exact courses.

Contains core curriculum buckets.

Contains approved academic electives.

Contains explanatory transfer guidance after the requirement section.

Contains suggested core course lists after Total Program Hours.

## Example

```text
APPROVED ACADEMIC ELECTIVE
```

## Example

```text
SOCIAL AND BEHAVIORAL SCIENCE CORE
```

## Parser Behavior

Parse only requirements above:

```text
Total Program Hours
```

Ignore:

```text
Suggested Core Classes
See core curriculum for complete list
Transfer guidance text
```

Exact courses become EXACT requirements.

Core buckets become bucket options.

Academic electives become elective options.

---

# Rule Types

Rule types describe how options are evaluated.

Only two rule types are currently required.

## EXACT

A single option must be satisfied.

Examples:

```text
RTVB 1317
ENGL 1301
COMM 1307
```

Evaluation:

```text
Required = 1
Options = 1
```

---

## ANY_N

Choose N from available options.

Examples:

```text
BUSI 1301
OR
BUSG 1301
```

```text
LANGUAGE, PHILOSOPHY, AND CULTURE CORE
OR
CREATIVE ARTS CORE
```

Evaluation:

```text
Required = N
Options >= N
```

---

# Option Types

Option types describe what satisfies a requirement.

---

## COURSE

A specific course.

Examples:

```text
ENGL 1301
RTVB 2335
COMM 2311
```

---

## CORE_BUCKET

A THECB core curriculum component area.

Examples:

```text
COMMUNICATION CORE
MATHEMATICS CORE
CREATIVE ARTS CORE
SOCIAL AND BEHAVIORAL SCIENCE CORE
```

Important:

The parser records the bucket.

The audit engine later determines which courses belong to the bucket.

---

## ELECTIVE

An elective placeholder.

Examples:

```text
APPROVED ACADEMIC ELECTIVE
PROGRAM ELECTIVE
TECHNICAL ELECTIVE
```

The parser records the elective reference.

The audit engine later applies elective logic.

---

# Core Design Decision

CORE_BUCKET is an option type.

CORE_BUCKET is not a rule type.

Example:

```text
LANGUAGE, PHILOSOPHY, AND CULTURE CORE
OR
CREATIVE ARTS CORE
```

Should be represented as:

```text
rule_type = ANY_N
min_required = 1

options:

CORE_BUCKET
    LANGUAGE_PHILOSOPHY_CULTURE

CORE_BUCKET
    CREATIVE_ARTS
```

This keeps evaluation logic simple.

---

# Requirement Output Table

Target output:

```text
data/processed/requirements.csv
```

## Columns

```text
requirement_id
credential_id
sequence
rule_type
min_required
group_name
option_value
option_type
source_page
source_line
```

---

# Credential Output Table

Produced separately.

Target output:

```text
data/processed/credentials.csv
```

## Columns

```text
credential_id
credential_name
award_type
pathway
total_hours
catalog_year
source_page
```

---

# Known Parsing Boundaries

The parser should ignore:

```text
Semester Hours
Suggested Core Classes
Transfer Guidance
Program Descriptions
Faculty Lists
Catalog Navigation Pages
```

The parser should stop at:

```text
Total Program Hours
```

unless a future pattern explicitly requires otherwise.

---

# Exception Handling

Records that cannot be parsed confidently should be flagged.

Examples:

```text
Missing total hours
Missing credential name
Unexpected page structure
Parenthetical non-credential headings
```

Flagged records are written to:

```text
credential_extraction_issues.csv
```

Future requirement extraction should produce a similar exception report.

---

# Initial Parser Scope

The first automated requirement parser supports Pattern A only.

Pattern A is intentionally narrow:

```text
Course requirements only
No OR logic
No buckets
No electives
```

Success criteria:

Generate machine-readable requirements from simple certificate pages.

Once Pattern A is stable:

```text
Pattern B
    ↓
Pattern C
```

will be implemented.

---

# Long-Term Goal

```text
Catalog PDF
    ↓
Credential Extraction
    ↓
Requirement Extraction
    ↓
Audit Engine
    ↓
Completed
Near Complete
Incomplete
```

for every student and every credential in the catalog.
