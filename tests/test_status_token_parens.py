"""
test_status_token_parens.py — parentheses-in-action-text status-token hardening.

_parseParagraphAsFloatingAction (SyncManager.js) extracts a trailing status
token via /\\(([^)]*)\\)\\s*$/ — only a parenthesised phrase anchored at the
very end of the paragraph qualifies; parentheses earlier in the action text
are left untouched. Covers the three corner cases from the bd filing:
  1. parens mid-text, no trailing status        -> no false status detected
  2. parens mid-text, with a trailing status   -> only the trailing one parsed
  3. parens only at the end (ambiguous)        -> treated as a status (defined
     rule: position, not content, decides — the regex always prefers the
     trailing parenthesised phrase as the status)

Bead: GTaskSheet-28q

Retired gts-dxz9/act-retire (staged plan docdata-litter-apt-speed.md, stage
`apt-format-migration`): all three cases are a specifiable single-sync round
trip (mid-text parens are literal text; a trailing parenthesised phrase is
always the status), now covered by tests/fixtures/status-token-parens.apt.txt
via tests/test_apt_format_lane.py's batched lane. No case here needed a
second live mutation, so nothing stayed behind — this file carries no test
functions of its own anymore.
"""
