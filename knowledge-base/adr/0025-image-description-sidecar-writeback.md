# ADR-0025: Image-description write-back uses a sidecar file, not in-place governance-JSON edits

**Status:** Accepted
**Date:** 2026-08-18
**Relates to:** gts-283i (epic), gts-283i.1 (this design spike), gts-283i.4 (embedded image
extraction implementer), docs/procedure-exporter.md §19.3 (image block contract), §15.1 (export
folder isolation / `Meta Json`)

## Context

docs/procedure-exporter.md §19.3 defines an `image` block with a `description` field the exporter
itself always writes as `null` (§17 principle 2 — the exporter never fabricates content). A
separate, out-of-band local tool later reads each extracted image file, sends it to a
vision-capable LLM, and produces a description for a flowchart/diagram's entities and their
relationships. §19.3 explicitly left open **where that description gets written back to**: in
place into the same governance JSON already sitting in the export folder, or a sidecar file keyed
by `image_ref`/`inline_object_id` that a RAG ingestion step merges at read time. This ADR resolves
that open question.

`getExportFolder_`'s Export Index sheet (§15.1) already carries a `Meta Json` column described as
"deliberately open-ended for other small per-export metadata (e.g. a future image-description
cache index, §19.3)" — written before this ADR, as a forward hint that a cache/sidecar shape was
the anticipated direction, not a mutation of the governance JSON itself.

## Decision

**Sidecar file.** The local analysis tool writes a separate JSON file into the same per-export
images subfolder (`<document-name>-images/`, §19.3) — `<document-name>-image-descriptions.json` —
mapping `image_ref` to `{ description, model, generated_at }`. It never opens or rewrites the
governance JSON (`<document-name>-governance.json`) that the exporter produced. A downstream RAG
ingestion step joins the two files by `image_ref` (falling back to `inline_object_id` as a
verification key) at read time, populating the `description` field the exporter left `null`.

## Rationale

- **Keeps the exporter's output deterministic and single-owner.** §17 principle 8 requires
  baseline/proposed derivation to stay deterministic so different LLMs receive the same source
  representation. A governance JSON that a second, independent tool mutates after the fact is no
  longer purely the exporter's deterministic output — two different re-runs of "export, then
  describe" could interleave differently depending on when the local tool ran. A sidecar keeps the
  exporter's artifact exactly what `Procedure-Exporter.js` wrote, full stop.
- **Avoids re-paying vision-LLM cost on re-export.** `image_ref` is derived the same way as
  `makeBlockId_` — tab ID + structural start index — so it is stable across re-exports of an
  unchanged document (§19.3). A sidecar keyed by that same stable ID is a natural cache: an
  unchanged image's description survives a re-export without re-invoking the vision LLM, whereas
  in-place editing of the governance JSON would need its own merge-forward logic to avoid losing
  (or needlessly regenerating) prior descriptions every time the exporter re-runs.
- **Matches the already-planned cache-index hint.** §15.1's `Meta Json` field on the Export Index
  sheet was already described as reserved for "a future image-description cache index, §19.3" —
  this decision operationalizes that hint rather than introducing an inconsistent second mechanism.
- **No write access needed to a file another process may be reading.** The governance JSON is the
  canonical interchange format (§1) that other consumers (a human reviewer, a first-pass RAG
  ingest) may already be reading immediately after export, before the (slower, LLM-backed)
  description pass completes. A sidecar means the description pass never risks a concurrent
  read/write race on the primary artifact.

## Consequences

- The RAG ingestion step (out of scope for the exporter itself, §19.3's own scoping note) must
  merge two files, not one: read `<document-name>-governance.json`, read
  `<document-name>-image-descriptions.json` if present, and for each `image` block look up its
  `description` by `image_ref` (verify against `inline_object_id` when both are available).
  Missing sidecar entries — description pass hasn't run yet, or ran and failed for that image —
  leave `description: null`, which is already a valid, expected value per §19.3; this is not an
  error condition for the ingestion step to raise on.
- Sidecar entries with no matching `image_ref` in the current governance JSON (document re-exported
  after an image was removed or shifted enough to change its `image_ref`) are orphaned and should
  be ignored by the ingestion step, not treated as a data-integrity failure — same "absence means
  none found" posture as §7.5/§13.4's other optional-field conventions.
- The exporter itself (`Procedure-Exporter.js`) needs no change for this decision — it already
  writes `description: null` unconditionally per §19.3's existing contract. This ADR only fixes the
  shape/location of the write-back artifact for the not-yet-built local analysis tool and the
  not-yet-built RAG ingestion step, both still out of scope per §19.3's closing scope note.

## Open question this ADR does not resolve

Retry/regeneration policy for the local analysis tool (e.g. re-run only images with no sidecar
entry, or force-refresh all) is left to that tool's own design — out of scope for the exporter
contract this ADR amends.
