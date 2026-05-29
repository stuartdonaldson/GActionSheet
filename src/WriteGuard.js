/**
 * WriteGuard.js
 *
 * Suppresses onActionSheetEdit during programmatic writes to the sheet.
 *
 * TESTED 2026-05-29: WebApp doPost writes do NOT trigger the installable
 * onActionSheetEdit trigger. A chip-tap queued a sheet write; after
 * upsert.complete logged the write, no trigger execution appeared. GAS
 * installable onEdit triggers appear to fire only on user-initiated edits,
 * not programmatic sheet writes from a separate execution context.
 *
 * As a result the cross-execution layer (SYNC_IN_PROGRESS_UNTIL_MS script
 * property) is DISABLED. wrapPersistent() is kept as an alias for wrap() so
 * call sites in WebApp.js compile unchanged. If Dirty re-set symptoms
 * reappear, re-enable wrapPersistent() by restoring the property write and
 * updating isActive() to check it.
 *
 * The in-process layer (_active flag) remains active — it still suppresses
 * onActionSheetEdit when the trigger fires within the same execution as the
 * write (e.g. onActionSheetEdit's own Dirty stamp calling _syncSheetRowToDoc,
 * which wraps its return writes).
 */
var WriteGuard = (function () {
  var _active = false;

  // --- Cross-execution layer (DISABLED) -----------------------------------
  // var _PROP     = 'SYNC_IN_PROGRESS_UNTIL_MS';
  // var WINDOW_MS = 20000;
  //
  // To re-enable: uncomment _PROP and WINDOW_MS, restore the setProperty call
  // in wrapPersistent(), and restore the property check in isActive().
  // Also update DESIGN.md §Programmatic Write Suppression accordingly.
  // -------------------------------------------------------------------------

  return {
    activate:   function () { _active = true; },
    deactivate: function () { _active = false; },

    isActive: function () {
      return _active;
      // Cross-execution check (disabled — see header comment):
      // if (_active) return true;
      // try {
      //   var until = PropertiesService.getScriptProperties().getProperty(_PROP);
      //   if (!until) return false;
      //   if (Date.now() < parseInt(until, 10)) return true;
      //   PropertiesService.getScriptProperties().deleteProperty(_PROP);
      // } catch (e) {}
      // return false;
    },

    /** In-process guard. Use for all programmatic sheet writes. */
    wrap: function (fn) {
      WriteGuard.activate();
      try {
        fn();
      } finally {
        WriteGuard.deactivate();
      }
    },

    /**
     * Alias for wrap(). Originally implemented a cross-execution guard via
     * SYNC_IN_PROGRESS_UNTIL_MS script property, but testing confirmed WebApp
     * doPost writes do not trigger onActionSheetEdit — the property write was
     * unnecessary and caused false suppression of user edits. Kept as an alias
     * so WebApp.js call sites remain unchanged if the guard needs re-enabling.
     */
    wrapPersistent: function (fn) {
      WriteGuard.wrap(fn);
    }
  };
})();
