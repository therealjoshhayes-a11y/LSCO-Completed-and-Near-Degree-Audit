# LSCO Credential Rule Model

## Purpose

Represent catalog credential requirements in a machine-readable format that can be audited against student course history.

---

## Credential Table

One record per credential.

### Fields

| Field           | Description                    |
| --------------- | ------------------------------ |
| credential_id   | Unique identifier              |
| credential_name | Catalog credential name        |
| award_type      | Certificate, AAS, AA, AS, etc. |
| pathway         | Catalog pathway                |
| total_hours     | Published program hours        |
| catalog_year    | Catalog year                   |

### Example

| credential_id | credential_name         | award_type  |
| ------------- | ----------------------- | ----------- |
| AV_CERT_2025  | Audio Visual Technology | Certificate |
| AV_AAS_2025   | Audio Visual Technology | AAS         |

---

## Requirement Table

One record per requirement group.

### Fields

| Field          | Description                         |
| -------------- | ----------------------------------- |
| requirement_id | Unique identifier                   |
| credential_id  | Parent credential                   |
| sequence       | Display order                       |
| rule_type      | EXACT, ANY_N, CORE_BUCKET, ELECTIVE |
| min_required   | Number required                     |
| group_name     | Human-readable description          |

### Example

| requirement_id | credential_id | rule_type   | min_required |
| -------------- | ------------- | ----------- | ------------ |
| R001           | AV_AAS_2025   | EXACT       | 1            |
| R002           | AV_AAS_2025   | ANY_N       | 1            |
| R003           | AV_AAS_2025   | CORE_BUCKET | 1            |

---

## Requirement Option Table

Courses or options satisfying a requirement.

### Fields

| Field          | Description           |
| -------------- | --------------------- |
| requirement_id | Parent requirement    |
| option_value   | Course or bucket      |
| option_type    | COURSE or CORE_BUCKET |

### EXACT Example

Requirement:

EXACT

Options:

RTVB 1317

---

### ANY_N Example

Requirement:

Choose 1

Options:

BUSI 1301

BUSG 1301

---

### CORE_BUCKET Example

Requirement:

CORE_BUCKET

Options:

SOCIAL AND BEHAVIORAL SCIENCE CORE

---

### ELECTIVE Example

Requirement:

ELECTIVE

Options:

APPROVED ACADEMIC ELECTIVE

---

## Supported Rule Types

### EXACT

Specific course required.

Examples:

ENGL 1301

RTVB 1317

---

### ANY_N

Choose N from listed options.

Examples:

BUSI 1301 OR BUSG 1301

LANGUAGE, PHILOSOPHY, AND CULTURE CORE OR CREATIVE ARTS CORE

---

### CORE_BUCKET

Requirement satisfied by any course belonging to a THECB core component area.

Examples:

SOCIAL AND BEHAVIORAL SCIENCE CORE

MATHEMATICS CORE

---

### ELECTIVE

Requirement satisfied by approved elective logic defined outside the catalog parser.

Examples:

APPROVED ACADEMIC ELECTIVE

PROGRAM ELECTIVE

TECHNICAL ELECTIVE

---

## Audit Result Model

Each requirement evaluates independently.

Status:

MET

UNMET

Requirement results aggregate upward to credential completion status.
