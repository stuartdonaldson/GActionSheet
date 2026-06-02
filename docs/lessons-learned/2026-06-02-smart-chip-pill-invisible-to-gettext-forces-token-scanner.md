# LL: Smart-chip/rich-link pill elements are invisible to getText(), requiring token-based detection

Date: 2026-06-02
Domain: platform | editor-addon | architecture

## Observation
ADR-0005 designed action detection around named ranges and person-chip elements: a floating
action was a checklist item whose first child element was a PERSON smart-chip, with the action
identity anchored by a Docs named range. This design assumed chip elements were readable via
the Docs API.

During 6ov implementation, `getText()` on a paragraph containing a smart-chip pill returns
only the text content — the chip element (person chip, rich link pill, @mention) is not
represented in the text string. It is invisible to the Apps Script text scanner. Named-range
lookup via the REST API can locate the anchor position, but the chip identity itself cannot
be reliably inferred from the surrounding text after the fact.

As a result, ADR-0005 was superseded by ADR-0008: action identification shifted to a
text-token scanner. A floating action is now any paragraph whose text starts with `AI-N:`
(an optional leading inline image is permitted and ignored). The durable identity is embedded
in the token text (`AI-{N}`) and stored as `globalId = {docId}/AI-{N}` in the ActionSheet.
Named ranges are no longer used for detection.

## Why Chain

Why 1 — The original person-chip + named-range design could not be implemented as specified.
Why 2 — `getText()` strips chip elements; the only reliable text-accessible anchor is inline
         text the author types, not chip elements they insert.
Why 3 — There is no Docs API equivalent of `querySelectorAll('[data-type=person-chip]')`;
         the paragraph element tree can be walked, but programmatic chip insertion is the
         only way to guarantee a chip is present — scanning documents you don't control cannot
         rely on chip presence.
Why 4 — Named-range anchoring works for documents under add-on control but not for arbitrary
         documents where the action was typed by hand or copied from another source.

Root cause: The Docs text model strips chip elements from `getText()`. Any detection scheme
that relies on chip presence as a text-parseable signal will fail. Text-token-based detection
is the only scanner design compatible with arbitrary Docs documents.

## Guidance (gas-addon-guide.md target)

- **Smart-chip elements are invisible to `getText()`**: person chips, @mentions, and rich-link
  pill elements do not appear in the text string returned by paragraph.getText(). Do not design
  detection logic that looks for chip elements via text scanning — it will not work.
- **Named-range anchoring for detection requires write access**: named ranges can anchor known
  positions, but using them as detection signals requires the add-on to have written them. For
  documents you do not control (collaborative editing, external authors), named ranges are not
  a reliable detection mechanism.
- **Text-token detection is the correct pattern**: embed a unique text token (e.g. `AI-N:`)
  in the paragraph text as the durable anchor. The token is author-visible, scanner-readable,
  and survives copy-paste and document export. This is how GActionSheet's floating action
  detection works (ADR-0008).

## Initial Candidates

b: add a "Docs text model constraints" section to `gas-addon-guide.md` — note chip invisibility
   to getText(), the implication for detection design, and the text-token pattern as the
   recommended alternative

b: update ADR-0008 cross-reference to confirm it supersedes ADR-0005 for this reason (chip
   invisibility, not just design preference)
