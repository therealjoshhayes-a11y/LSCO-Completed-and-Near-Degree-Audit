from pathlib import Path

from lsco_audit.catalog_extract import extract_catalog_pages


def test_extract_catalog_pages_function_exists():
    assert callable(extract_catalog_pages)
