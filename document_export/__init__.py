"""document_export — local Python pipeline that builds the LLM-ingestion export
JSON from a downloaded .docx (ADR-0026). See docs/interfaces/document-export-contract.md
(schema 3.0) for the frozen contract this package is authored against.

Sibling to scn/, not nested under it — this pipeline shares no runtime code with
the pytest scenario harness, only tests/helpers/download.py's acquisition helper
(see acquire.py).
"""
