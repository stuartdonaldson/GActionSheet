// ActionToken.js — shared action-token constant and helpers (ADR-0023).
//
// ACT-N: is canonical for all new writes. AI-N: remains valid on read,
// indefinitely — no migration pass rewrites existing documents. N is one
// shared namespace across both prefixes (an AI-3: and an ACT-3: in the same
// document are the same identity slot, never two actions).

/** Prefix written by every emit site (add-on create-action flow, sheet-triggered doc rewrite, REST flush). */
var _ACTION_TOKEN_PREFIX = 'ACT';

/** Prefixes accepted on read, legacy-first-compatible; both stay valid permanently. */
var _ACTION_TOKEN_READ_PREFIXES = ['ACT', 'AI'];

/** Matches either spelling at paragraph start (or immediately after a soft return): captures the integer N. */
var _ACTION_TOKEN_REGEX = new RegExp('(?:' + _ACTION_TOKEN_READ_PREFIXES.join('|') + ')-(\\d+):');

/** Anchored form of _ACTION_TOKEN_REGEX for match-at-start checks. */
var _ACTION_TOKEN_REGEX_ANCHORED = new RegExp('^(?:' + _ACTION_TOKEN_READ_PREFIXES.join('|') + ')-(\\d+):');

/** Anchored, prefix-capturing form — group 1 is the prefix actually found ('ACT' or 'AI'), group 2 is N. */
var _ACTION_TOKEN_REGEX_ANCHORED_CAPTURED = new RegExp('^(' + _ACTION_TOKEN_READ_PREFIXES.join('|') + ')-(\\d+):');

/**
 * ADR-0027 rule 6 / gts-xvlu — "looks like an action" check: the same prefix
 * and number as _ACTION_TOKEN_REGEX_ANCHORED, WITHOUT requiring the trailing
 * colon. Used only to detect a paragraph that started the token grammar and
 * failed to complete it (colon missing, e.g. the gts-tis pipe-delimited
 * spelling 'ACT-2 | someone | do the thing') so it can be reported instead of
 * silently dropped — never to accept it as a parsed action.
 */
var _ACTION_TOKEN_LOOKS_LIKE_REGEX_ANCHORED = new RegExp('^(?:' + _ACTION_TOKEN_READ_PREFIXES.join('|') + ')-\\d+');

/** Builds the canonical write-form token text for N, e.g. 'ACT-3: '. */
function _actionTokenText(n) {
  return _ACTION_TOKEN_PREFIX + '-' + n + ': ';
}

/** Builds the canonical write-form token, no trailing space/colon-space, e.g. 'ACT-3:'. */
function _actionTokenPrefix(n) {
  return _ACTION_TOKEN_PREFIX + '-' + n + ':';
}

/** Builds the canonical bare actionId form (no colon), e.g. 'ACT-3'. Used in globalId/chip contexts. */
function _actionTokenId(n) {
  return _ACTION_TOKEN_PREFIX + '-' + n;
}

/**
 * Returns the integer N if text starts with a valid action token (either
 * prefix), else null. Mirrors the anchored-at-paragraph-start match used by
 * token-paragraph detection across SyncManager.js/EditorAddonCard.js.
 */
function _matchActionTokenN(text) {
  var m = _ACTION_TOKEN_REGEX_ANCHORED.exec(text || '');
  return m ? parseInt(m[1], 10) : null;
}

/**
 * Returns {prefix, N, match} if text starts with a valid action token (either
 * prefix), else null. `match` is the full matched token text (e.g. 'ACT-3:'),
 * useful for slicing it off the front of the paragraph text.
 */
function _matchActionTokenPrefixed(text) {
  var m = _ACTION_TOKEN_REGEX_ANCHORED_CAPTURED.exec(text || '');
  if (!m) return null;
  return { prefix: m[1], N: parseInt(m[2], 10), match: m[0] };
}

/**
 * Bare (unnumbered) trigger a user types to request a new auto-numbered
 * action — e.g. 'AI: text' or 'ACT: text'. Distinct from the numbered token
 * grammar above; both spellings are accepted as triggers, matching read
 * compatibility for the numbered form.
 */
var _ACTION_TOKEN_BARE_TRIGGER_REGEX_ANCHORED = new RegExp('^(' + _ACTION_TOKEN_READ_PREFIXES.join('|') + '):');

/** Returns {prefix, match} if text starts with a bare trigger (either spelling), else null. */
function _matchActionTokenBareTrigger(text) {
  var m = _ACTION_TOKEN_BARE_TRIGGER_REGEX_ANCHORED.exec(text || '');
  if (!m) return null;
  return { prefix: m[1], match: m[0] };
}

/**
 * Text-assignee grammar (ADR-0027 rule 1), anchored at the start of the
 * action body: an optional leading '@' sigil followed by a bare email
 * address. The sigil is syntax only — group 1 is the address, and that is
 * what assignee_email stores, so '@jane@example.com' and 'jane@example.com'
 * are the same assignee.
 *
 * Lives here beside the token literals because it is part of the same frozen
 * paragraph grammar; _parseActionHeaderLineTracked (SyncManager.js) is the
 * single consumer for the paragraph body.
 */
var _ASSIGNEE_TEXT_REGEX = /^@?([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i;

/** Same grammar, tolerating leading whitespace — for a Text child scanned beside a PERSON chip. */
var _ASSIGNEE_TEXT_REGEX_LEADING_WS = /^\s*@?([\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+)\s*/i;
