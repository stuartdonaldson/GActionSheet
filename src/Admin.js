/**
 * Admin.js — admin-only routes, gated by a set-once shared secret
 * (gts-79dw.4.18). Deliberately modeled on ../NUUC-Dispatch/src/Admin.js's
 * pattern (same action names, same bootstrap-then-gate shape) so both repos
 * stay operable with the same mental model and the same CLI ergonomics —
 * this is meant to be extended/reused, not a throwaway for this one bead.
 *
 * ADMIN_SECRET is a DISTINCT, higher-privilege credential from WEBAPP_SECRET
 * (production add-on auth) and TEST_TOKEN (per-deployment ATDD auth,
 * src/TestWebApp.js) — it is never accepted from either of those gates, and
 * routes here never accept a testToken as authorization. It is never typed
 * into the Apps Script editor by hand: a one-time `bootstrapSecret` call
 * sets it (refuses to run again once set — see _adminBootstrapSecret), and
 * every other admin action must echo it back in the POST body (never the
 * query string, so it never lands in access logs / curl history).
 *
 * Call via `node tools/call-webapp.js <action>` (mirrors NUUC-Dispatch's
 * tools/call-webapp.js exactly) — that tool reads adminSecret and the
 * webapp URLs from local.settings.json (gitignored), so admin calls never
 * need a hand-built curl/fetch with a hardcoded deployment URL.
 *
 * Routed from doPost (src/WebApp.js) via payload.action, BEFORE the
 * TEST_TOKEN and WEBAPP_SECRET gates -- this file owns its own gate
 * (_requireAdminSecret) rather than composing with either of those.
 *
 * Never logs the admin secret or any Script Property VALUE it sets — only
 * the property names/keys.
 */

/**
 * @param {Object} payload
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleAdminAction(payload) {
  if (payload.action === 'bootstrapSecret') {
    return _jsonResponse(_adminBootstrapSecret(payload.secret));
  }

  var forbidden = _requireAdminSecret(payload);
  if (forbidden) return _jsonResponse(forbidden);

  if (payload.action === 'setScriptProperties') {
    var properties = payload.properties || {};
    var keys = Object.keys(properties);
    PropertiesService.getScriptProperties().setProperties(properties);
    GasLogger.log('admin.setScriptProperties', { keys: keys });
    GasLogger.flush();
    return _jsonResponse({ ok: true, keysSet: keys });
  }

  return _jsonResponse({ ok: false, error: 'unknown_action' });
}

/**
 * One-time bootstrap: sets ADMIN_SECRET the very first time, before any
 * secret exists to gate the call. Refuses to run again once ADMIN_SECRET is
 * already set (chicken-and-egg solved the same way NUUC-Dispatch solves it
 * for ADMIN_SHARED_SECRET) -- rotating the secret afterward requires
 * deleting the property via the Apps Script editor first, an explicit,
 * out-of-band step, not a route any caller can trigger.
 *
 * @param {string} secret
 * @returns {{ok: boolean, error?: string}}
 */
function _adminBootstrapSecret(secret) {
  if (!secret || String(secret).length < 16) {
    return { ok: false, error: 'secret must be at least 16 characters' };
  }
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('ADMIN_SECRET')) {
    return { ok: false, error: 'already_bootstrapped' };
  }
  props.setProperty('ADMIN_SECRET', String(secret));
  GasLogger.log('admin.bootstrapped', {});
  GasLogger.flush();
  return { ok: true };
}

/**
 * @param {Object} payload
 * @returns {{ok: false, error: string}|null} null when authorized.
 */
function _requireAdminSecret(payload) {
  var stored = PropertiesService.getScriptProperties().getProperty('ADMIN_SECRET');
  if (!stored || payload.adminSecret !== stored) {
    GasLogger.log('admin.forbidden', { action: payload.action });
    GasLogger.flush();
    return { ok: false, error: 'forbidden' };
  }
  return null;
}
