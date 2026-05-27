/**
 * EditorChipPoc.js
 *
 * POC: Docs editor add-on action-chip (branch poc/editor-addon-action-chip).
 *
 * ISOLATION CONTRACT
 * ------------------
 * - All experimental functions are prefixed `_poc_` (private helpers) or
 *   declared here as named top-level trigger entry points.
 * - Entry points required by appsscript.json (createActionTrigger, onLinkPreview)
 *   MUST remain top-level globals — GAS does not support namespaced triggers.
 * - No existing src/ file is modified by POC work. If a shared utility is
 *   needed, call it read-only; do not alter it.
 * - Remove this file and its appsscript.json entries before merging to master.
 *
 * ENTRY POINTS (stubs — wired in GTaskSheet-6ov.3 and GTaskSheet-6ov.5)
 * -----------------------------------------------------------------------
 */

/**
 * createActionTrigger
 * Docs @action menu item. Registered via appsscript.json createActionTrigger.
 * Full implementation: GTaskSheet-6ov.3
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 */
function createActionTrigger(e) { // eslint-disable-line no-unused-vars
  // stub — GTaskSheet-6ov.3
}

/**
 * onLinkPreview
 * Smart-chip link preview for action resource URLs.
 * Registered via appsscript.json linkPreviewTriggers.
 * Full implementation: GTaskSheet-6ov.5
 *
 * @param {GoogleAppsScript.Addons.EventObject} e
 */
function onLinkPreview(e) { // eslint-disable-line no-unused-vars
  // stub — GTaskSheet-6ov.5
}
