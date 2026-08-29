#!/usr/bin/env python3
"""
export_document.py — thin shim over document_export.cli:main (contract §7.3).

Builds the LLM-ingestion export JSON from a Google Doc or a Drive-hosted
native .docx, parsed locally in Python from a downloaded .docx (ADR-0026,
schema 3.0) rather than via the Docs API. See
docs/interfaces/document-export-contract.md for the full contract, and
scripts/export_gas.py for the older schema-2.4 GAS-side exporter,
preserved frozen as the differential-oracle baseline (ADR-0026 Decision 7).

Usage:
    python scripts/export_document.py [DOC_ID] [--docx PATH] [--out-dir DIR]
                                       [--no-images] [--whole-document-views] [--json-only]

Examples:
    python scripts/export_document.py 1aK1jDQY6kfGs4op1t8hZrpN-pzrAMPNF
    python scripts/export_document.py --docx document_export/fixtures/golden.docx --out-dir /tmp/export-test
"""
import pathlib
import sys

# scripts/ is not the project root -- see export_gas.py's identical
# guard for why this must be inserted before the document_export import.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from document_export.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
