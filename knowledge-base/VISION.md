---
framework-version: "2.3.0"
tier: standard
---
# VISION — GActionSheet

## Strategic Themes

### Theme 1: Zero-Friction Action Capture
Action items should be capturable by a document author without ever opening a spreadsheet. The friction of context-switching is the primary reason actions go untracked. GActionSheet eliminates that friction: authors write inline in Docs; the system normalizes, assigns IDs, and propagates — no spreadsheet interaction required.

### Theme 2: Google Workspace Native — No Infrastructure
The system runs entirely within Google Workspace. No servers, no external APIs, no operational burden beyond `initializeTriggers`. Any Google Workspace administrator can deploy and operate the system without engineering support. GAS quota limits are respected by design; the 6-minute execution limit shapes the sync-per-document architecture.

### Theme 3: Aggregate Accountability
Reviewers and managers see a single filtered, searchable view across all documents. The Sheet is the accountability surface; the Docs are the authoring surface. These concerns must remain separated: authors never need the Sheet, reviewers rarely need the Docs.
