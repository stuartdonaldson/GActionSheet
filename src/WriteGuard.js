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

    /**
     * In-process guard. Use for all programmatic sheet writes.
     *
     * gts-5kyu (Stage 1 Actions-sheet snapshot, AC4/AC9): every writer that
     * mutates the Actions sheet already routes through here, so this is the
     * single choke point that invalidates ActionSnapshot.js's per-execution
     * memo -- a writer never has to remember to do it itself, and a future
     * writer gets it for free. Nulling on EVERY wrap() (not only
     * Actions-sheet writes) is deliberate: over-invalidation just costs one
     * extra rebuild on next read, never a wrong answer, and this function has
     * no way to know which sheet fn() touched.
     *
     * CAVEAT (gts-tz3j static review, AC4-2/AC5-2, since no live red/green
     * proof was possible against the shared TEST target -- see gts-hztp):
     * invalidation fires ONCE, in finally, after fn() returns -- NOT after
     * each individual write inside fn(). A memo-backed read issued from
     * INSIDE a wrap()/wrapPersistent() body, after a write earlier in that
     * same body, sees stale data. No call site does this today (verified by
     * exhaustive enumeration of Actions-sheet write sites), but nothing
     * prevents a future writer from adding one. If you add a memo-backed
     * read inside a wrap body after a write, invalidate manually first via
     * _invalidateActionsSnapshot(), don't rely on this finally.
     */
    wrap: function (fn) {
      WriteGuard.activate();
      try {
        fn();
      } finally {
        WriteGuard.deactivate();
        _invalidateActionsSnapshot();
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
