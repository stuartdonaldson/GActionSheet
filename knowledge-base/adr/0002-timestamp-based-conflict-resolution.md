# ADR-0002: Timestamp-Based Conflict Resolution

Status: Accepted
Date: 2026-05-19

## Context
Both the Google Sheet and Google Docs can be edited independently between sync runs. A conflict occurs when the same action record has different values on each side. A deterministic, simple rule is needed that non-technical users can reason about.

## Decision
Use `Date Modified` (UTC ISO 8601) as the sole conflict-resolution key: the side with the later timestamp wins. Tie-breaking rules: (1) sheet row wins on equal timestamps with differing content; (2) the side with a timestamp wins when the other has none; (3) the tracked-actions table row wins when neither side has a timestamp.

## Consequences
- Simple and predictable; users can force a "win" by making any edit (which updates `Date Modified`).
- Sheet edits made via the installable `onEdit` trigger automatically update `Date Modified`, giving sheet changes a fresh timestamp that will win on next sync.
- Clock skew between a user's local time and GAS execution time is unlikely but possible; the difference is at most a few seconds and will self-correct on the following sync.
- No three-way merge, no operational transformation; complex concurrent edits (both sides changed different fields) result in one side's full record overwriting the other.
