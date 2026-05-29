/**
 * WriteGuard.js
 *
 * Suppresses onActionSheetEdit during programmatic writes to the sheet.
 * Two layers:
 *
 *   In-process  — _active flag; covers same-execution callers (Sync Now, sweep,
 *                 archive, onActionSheetEdit's own Dirty stamp).
 *                 Use: WriteGuard.wrap(fn)
 *
 *   Cross-execution — SYNC_IN_PROGRESS_UNTIL_MS script property; covers WebApp
 *                     doPost, which runs in a separate execution from the
 *                     onActionSheetEdit trigger. The property is not deleted on
 *                     deactivate — it expires naturally after WINDOW_MS.
 *                     Any user edit within WINDOW_MS of a WebApp write is
 *                     suppressed; accepted POC tradeoff.
 *                     Use: WriteGuard.wrapPersistent(fn)  — WebApp.js only.
 *
 * isActive() checks both layers; onActionSheetEdit calls it at entry.
 */
var WriteGuard = (function () {
  var _active   = false;
  var _PROP     = 'SYNC_IN_PROGRESS_UNTIL_MS';
  var WINDOW_MS = 20000;

  return {
    activate: function () { _active = true; },

    deactivate: function () { _active = false; },

    isActive: function () {
      if (_active) return true;
      try {
        var until = PropertiesService.getScriptProperties().getProperty(_PROP);
        if (!until) return false;
        if (Date.now() < parseInt(until, 10)) return true;
        // Expired — clean up so stale entries don't accumulate.
        PropertiesService.getScriptProperties().deleteProperty(_PROP);
      } catch (e) { /* treat read failure as inactive */ }
      return false;
    },

    /** In-process only. Use for trigger-context writes (sweep, archive, onEdit stamp). */
    wrap: function (fn) {
      WriteGuard.activate();
      try {
        fn();
      } finally {
        WriteGuard.deactivate();
      }
    },

    /**
     * Cross-execution variant. Sets SYNC_IN_PROGRESS_UNTIL_MS before running fn
     * so the onActionSheetEdit trigger (separate execution) sees the guard.
     * Use only from WebApp doPost context.
     */
    wrapPersistent: function (fn) {
      try {
        PropertiesService.getScriptProperties()
          .setProperty(_PROP, String(Date.now() + WINDOW_MS));
      } catch (e) { /* non-fatal */ }
      WriteGuard.activate();
      try {
        fn();
      } finally {
        WriteGuard.deactivate();
        // Intentionally does not delete the property — lets the window remain
        // active so triggers firing after this execution ends are still suppressed.
      }
    }
  };
})();
