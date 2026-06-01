# ADR-0005: Workspace Add-on with Automation Sidecar

Status: Superseded by ADR-0008
Date: 2026-05-23
Supersedes: ADR-0001
Superseded: 2026-05-29

> Superseded by ADR-0008. Two of this record's decisions were not adopted: (a) the two-project
> "automation sidecar" — the system is a single dual-deployed project (ADR-0007); and (b)
> REST named-range identity — action identity is an in-text `AI-N:` token (ADR-0008). The
> `SYNC_IN_PROGRESS` cross-execution guard described here is also unused (see ADR-0008
> consequences). The decision below is retained for history.

## Context

The original container-bound-on-Sheet approach (ADR-0001) required the sync engine to run as the sheet owner, making it impossible to access the active document's cursor position, selection, or PERSON chip content through the normal GAS DocumentApp API. Smart-chip Task Tracker chips — which would have provided native task identity anchoring — are inaccessible to all server-side APIs (DocumentApp, REST, Apps Script). The system needed a way to:

1. Detect chip-led checklist items in the active document.
2. Create stable named-range anchors on those paragraphs.
3. Write rows to the ActionSheet (a restricted resource).
4. Stamp `Last Modified` on edited rows without interfering with programmatic writes.
5. Sweep all tracked documents on a time-based trigger.

The chip-led detection requirement is the decisive constraint: DocumentApp exposes PERSON chip elements ergonomically via `Paragraph.getChild()` type inspection, but only when running in the context of the document. A container-bound-on-Sheet script cannot open a Doc and read its chips without the doc owner granting explicit permission to a service account.

## Decision

Deploy two GAS projects:

**Add-on project (standalone, Workspace Add-on for Docs)**
- Provides a sidebar card in the active Google Doc.
- Scans the doc via DocumentApp to find chip-led checklist items.
- Creates named-range anchors via the Docs REST API `batchUpdate`.
- Proxies all ActionSheet writes through the Web App endpoint (doPost) to avoid requiring end users to have sheet-edit access.

**Automation project (container-bound to the ActionSheet)**
- Owns the ActionSheet as its container.
- `onEdit` installable trigger stamps `Last Modified` on user edits.
- Time-based sweep trigger iterates all tracked docs and reconciles them.
- Archive job moves Closed + 30-day rows to the archive sheet.
- `SYNC_IN_PROGRESS` script property suppresses `onEdit` stamps during programmatic writes.

The two projects share no code. The ActionSheet schema (including `NamedRangeId` as the cross-doc identity key) is the shared contract.

## Rationale

| Alternative | Why rejected |
|---|---|
| Container-bound-on-Sheet (ADR-0001) | Cannot detect PERSON chips; no sidebar for per-doc UI |
| Container-bound on each Doc | Requires per-document trigger setup; unmanageable at scale |
| Standalone script | No container binding means no `onEdit` trigger on the sheet; sidebar card requires Workspace Add-on registration |
| Smart-chip Task Tracker chips as identity | Task Tracker chips are not accessible via any API (REST or GAS); confirmed in GDocTools/DocsAPI findings |
| Named ranges via DocumentApp | DocumentApp's NamedRange API cannot create ranges from GAS with the stable REST `namedRangeId` needed for identity; REST API is required for write-side anchoring |

## Consequences

- **Identity is `namedRangeId`** — each action paragraph is anchored by a named range created via the Docs REST API. The ActionSheet stores `NamedRangeId` as the first column. Orphan detection and re-anchoring use this ID as the canonical key.
- **Two deployment IDs to maintain** — the add-on project has a Workspace Add-on deployment ID; the automation project has no public deployment. Both must be kept in sync via `clasp push`.
- **Proxy-write pattern** — add-on → `UrlFetchApp.fetch(WEBAPP_URL)` → Web App `doPost` → ActionSheet. `WEBAPP_SECRET` must be set in both projects' script properties.
- **Add-on requires per-user install** — end users must install the Workspace Add-on from the Marketplace or test-deploy link. Managed domain installs are possible but require additional admin approval.
- **Docs REST API quota** — named-range creation and batchUpdate calls count against the Docs API quota. At the expected scale (single-congregation use) this is not a concern.
- **`SYNC_IN_PROGRESS` guard required** — the automation project's `onEdit` must check this flag before stamping `Last Modified`, otherwise programmatic writes from the sweep trigger create false timestamps.
