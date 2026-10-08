from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT = ROOT / "LOCAL_CATALOG_AWARD_LEVEL_EVIDENCE.txt"

AWARD_PHRASES = [
    "Associate of Arts Degree",
    "Associate of Science Degree",
    "Associate of Applied Science Degree",
    "Associate of Arts in Teaching",
    "Certificate of Completion",
    "Basic Certificate",
    "Institutional Award",
]

CATALOG_SUFFIXES = {
    ".pdf",
    ".docx",
}


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
    matches = sorted(
        [
            path
            for path in REPORTING.glob(pattern)
            if (
                path.is_dir()
                and (
                    path
                    / required_name
                ).exists()
            )
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return matches[0]


def normalize_space(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def year_tokens(catalog_year: str) -> list[str]:
    match = re.match(
        r"(\d{4})-(\d{4})",
        txt(catalog_year),
    )

    if not match:
        return []

    first = match.group(1)
    second = match.group(2)

    return [
        f"{first}-{second}",
        f"{first}_{second}",
        f"{first} {second}",
        first,
        second,
    ]


def likely_catalog_file(path: Path) -> bool:
    if path.suffix.lower() not in CATALOG_SUFFIXES:
        return False

    lowered = path.name.lower()

    return (
        "catalog"
        in lowered
        or "catalog"
        in str(path.parent).lower()
    )


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(
            "word/document.xml"
        )

    root = ET.fromstring(
        raw
    )

    chunks = []

    for node in root.iter():
        if (
            node.tag.endswith("}t")
            and node.text
        ):
            chunks.append(
                node.text
            )

    return "\n".join(
        chunks
    )


def pdf_text(path: Path) -> tuple[str, str]:
    reader_cls = None
    backend = ""

    try:
        from pypdf import PdfReader
        reader_cls = PdfReader
        backend = "pypdf"
    except Exception:
        try:
            from PyPDF2 import PdfReader
            reader_cls = PdfReader
            backend = "PyPDF2"
        except Exception:
            return "", "NO_PDF_READER_AVAILABLE"

    try:
        reader = reader_cls(
            str(path)
        )

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            try:
                extracted = (
                    page.extract_text()
                    or ""
                )
            except Exception:
                extracted = ""

            if extracted:
                pages.append(
                    f"\n[[PAGE {page_number}]]\n"
                    + extracted
                )

        return (
            "\n".join(
                pages
            ),
            backend,
        )
    except Exception as exc:
        return "", f"PDF_READ_ERROR:{type(exc).__name__}"


def load_catalog_text(
    path: Path,
) -> tuple[str, str]:
    suffix = path.suffix.lower()

    if suffix == ".docx":
        try:
            return docx_text(
                path
            ), "DOCX_XML"
        except Exception as exc:
            return "", f"DOCX_READ_ERROR:{type(exc).__name__}"

    if suffix == ".pdf":
        return pdf_text(
            path
        )

    return "", "UNSUPPORTED"


def evidence_for_target(
    text: str,
    title: str,
) -> list[dict[str, object]]:
    if not text:
        return []

    normalized = normalize_space(
        text
    )

    title_norm = normalize_space(
        title
    )

    if not title_norm:
        return []

    pattern = re.compile(
        re.escape(
            title_norm
        ),
        flags=re.IGNORECASE,
    )

    hits = []

    for match in pattern.finditer(
        normalized
    ):
        start = max(
            0,
            match.start()
            - 120,
        )

        end = min(
            len(
                normalized
            ),
            match.end()
            + 650,
        )

        snippet = normalized[
            start:end
        ]

        phrase_hits = [
            phrase
            for phrase in AWARD_PHRASES
            if re.search(
                re.escape(
                    phrase
                ),
                snippet,
                flags=re.IGNORECASE,
            )
        ]

        hits.append(
            {
                "snippet": snippet,
                "award_phrases": phrase_hits,
                "position": match.start(),
            }
        )

    # Prefer actual program headings that have explicit award language nearby.
    hits.sort(
        key=lambda row: (
            0
            if row[
                "award_phrases"
            ]
            else 1,
            row[
                "position"
            ],
        )
    )

    return hits


def main() -> None:
    gap_dir = latest_dir(
        "multiple_award_gap_probe_*",
        "FERPA_SAFE_candidate_metadata_gaps.csv",
    )

    metadata_path = (
        gap_dir
        / "FERPA_SAFE_candidate_metadata_gaps.csv"
    )

    associate_path = (
        gap_dir
        / "FERPA_SAFE_associate_degree_code_gaps.csv"
    )

    metadata = pd.read_csv(
        metadata_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    associate = pd.read_csv(
        associate_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    targets = []

    for frame, reason in [
        (
            metadata,
            "CERTIFICATE_VS_IA_GAP",
        ),
        (
            associate[
                associate.get(
                    "modern_2025plus_rule",
                    ""
                )
                .astype(str)
                .str.upper()
                .isin(
                    {
                        "TRUE",
                        "T",
                        "YES",
                        "Y",
                        "1",
                    }
                )
            ].copy()
            if not associate.empty
            else associate,
            "MODERN_ASSOCIATE_EXACT_DEGREE_CODE_GAP",
        ),
    ]:
        if frame.empty:
            continue

        for row in frame.itertuples(
            index=False
        ):
            catalog_year = txt(
                getattr(
                    row,
                    "catalog_year",
                    "",
                )
            )

            credential_id = txt(
                getattr(
                    row,
                    "credential_id",
                    "",
                )
            )

            title = txt(
                getattr(
                    row,
                    "credential_title",
                    "",
                )
            ) or txt(
                getattr(
                    row,
                    "awardability_credential_title",
                    "",
                )
            )

            targets.append(
                {
                    "reason": reason,
                    "catalog_year":
                        catalog_year,
                    "credential_id":
                        credential_id,
                    "title":
                        title,
                }
            )

    unique_targets = []

    seen = set()

    for target in targets:
        key = (
            target[
                "reason"
            ],
            target[
                "catalog_year"
            ],
            target[
                "credential_id"
            ],
            target[
                "title"
            ],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_targets.append(
            target
        )

    catalog_files = sorted(
        {
            path
            for path in ROOT.rglob("*")
            if (
                path.is_file()
                and likely_catalog_file(
                    path
                )
            )
        }
    )

    # Prefer files outside reporting / transient outputs.
    catalog_files.sort(
        key=lambda path: (
            1
            if "processed/reporting"
            in str(
                path
            ).replace(
                "\\",
                "/",
            ).lower()
            else 0,
            str(
                path
            ).lower(),
        )
    )

    cache: dict[
        Path,
        tuple[
            str,
            str,
        ],
    ] = {}

    with OUT.open(
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            "LOCAL CATALOG AWARD-LEVEL EVIDENCE\n"
        )
        handle.write(
            f"Generated: {datetime.now().astimezone().isoformat()}\n"
        )
        handle.write(
            "FERPA-SAFE: credential/catalog metadata only; no student rows.\n\n"
        )

        handle.write(
            f"Gap source: {gap_dir}\n"
        )
        handle.write(
            f"Unique targets: {len(unique_targets):,}\n"
        )
        handle.write(
            f"Catalog-like PDF/DOCX files found: {len(catalog_files):,}\n\n"
        )

        handle.write(
            "="
            * 110
            + "\nCATALOG FILE INVENTORY\n"
            + "="
            * 110
            + "\n"
        )

        for path in catalog_files:
            handle.write(
                f"{path.relative_to(ROOT)}\n"
            )

        handle.write(
            "\n"
        )

        for target in unique_targets:
            handle.write(
                "="
                * 110
                + "\n"
            )
            handle.write(
                f"REASON: {target['reason']}\n"
            )
            handle.write(
                f"CATALOG YEAR: {target['catalog_year']}\n"
            )
            handle.write(
                f"CREDENTIAL ID: {target['credential_id']}\n"
            )
            handle.write(
                f"TITLE: {target['title']}\n"
            )
            handle.write(
                "-"
                * 110
                + "\n"
            )

            tokens = year_tokens(
                target[
                    "catalog_year"
                ]
            )

            # Same-year-looking files first, then all other catalogs.
            ranked_files = sorted(
                catalog_files,
                key=lambda path: (
                    0
                    if any(
                        token.lower()
                        in path.name.lower()
                        for token in tokens
                    )
                    else 1,
                    str(
                        path
                    ).lower(),
                ),
            )

            direct_evidence = []

            for path in ranked_files:
                if path not in cache:
                    cache[
                        path
                    ] = load_catalog_text(
                        path
                    )

                body, backend = cache[
                    path
                ]

                if not body:
                    continue

                hits = evidence_for_target(
                    body,
                    target[
                        "title"
                    ],
                )

                if not hits:
                    continue

                best = hits[
                    0
                ]

                direct_evidence.append(
                    {
                        "path": path,
                        "backend": backend,
                        "same_year_name":
                            any(
                                token.lower()
                                in path.name.lower()
                                for token in tokens
                            ),
                        "award_phrases":
                            best[
                                "award_phrases"
                            ],
                        "snippet":
                            best[
                                "snippet"
                            ],
                    }
                )

            # Favor direct same-year program heading evidence.
            direct_evidence.sort(
                key=lambda row: (
                    0
                    if (
                        row[
                            "same_year_name"
                        ]
                        and row[
                            "award_phrases"
                        ]
                    )
                    else (
                        1
                        if row[
                            "award_phrases"
                        ]
                        else 2
                    ),
                    str(
                        row[
                            "path"
                        ]
                    ).lower(),
                )
            )

            if not direct_evidence:
                handle.write(
                    "NO DIRECT TITLE MATCH IN LOCAL CATALOG FILES.\n\n"
                )
                continue

            # Keep output compact: at most 5 strongest source hits per target.
            for evidence in direct_evidence[
                :5
            ]:
                handle.write(
                    f"FILE: {evidence['path'].relative_to(ROOT)}\n"
                )
                handle.write(
                    f"BACKEND: {evidence['backend']}\n"
                )
                handle.write(
                    f"SAME-YEAR FILE NAME: {evidence['same_year_name']}\n"
                )
                handle.write(
                    "AWARD PHRASES NEAR TITLE: "
                    + (
                        " | ".join(
                            evidence[
                                "award_phrases"
                            ]
                        )
                        or "NONE"
                    )
                    + "\n"
                )
                handle.write(
                    "SNIPPET:\n"
                )
                handle.write(
                    evidence[
                        "snippet"
                    ]
                    + "\n\n"
                )

    print("=" * 100)
    print("CATALOG AWARD-LEVEL GAP PROBE — COMPLETE")
    print("=" * 100)
    print(
        f"Unique targets:                 {len(unique_targets):,}"
    )
    print(
        f"Catalog-like files searched:    {len(catalog_files):,}"
    )
    print(
        f"Wrote: {OUT}"
    )
    print(
        "FERPA-safe: no student rows were emitted."
    )


if __name__ == "__main__":
    main()
