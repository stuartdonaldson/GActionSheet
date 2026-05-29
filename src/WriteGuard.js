/**
 * WriteGuard.js
 *
 * Suppresses onActionSheetEdit during programmatic writes to the sheet.
 * Two layers:
 *
 *   In-process  — _active flag, covers same-execution callers (Sync Now, sweep, archive).
 *   Cross-execution — SYNC_IN_PROGRESS_UNTIL_MS script property, covers WebApp doPost
 *                     which runs in a separate execution from the onActionSheetEdit trigger.
 *                     activate() sets the property to Date.now() + WINDOW_MS.
 *                     The property is not deleted on deactivate; it expires naturally.
 *                     Any user edit within WINDOW_MS of a WebApp write is suppressed —
 *                     accepted POC tradeoff for simplicity.
 *
 * Usage:
 *   WriteGuard.wrap(function() { sheet.appendRow(row); });
 */
var WriteGuard = (function () {
  var _active   = false;
  var _PROP     = 'SYNC_IN_PROGRESS_UNTIL_MS';
  var WINDOW_MS = 20000;

  return {
    activate: function () {
      _active = true;
      try {
        PropertiesService.getScriptProperties()
          .setProperty(_PROP, String(Date.now() + WINDOW_MS));
      } catch (e) { /* non-fatal — in-process guard still active */ }
    },

    deactivate: function () {
      _active = false;
      // Intentionally does not delete the property — lets the cross-execution
      // window remain active for WINDOW_MS so any trigger firing after this
      // execution ends is still suppressed.
    },

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

    /**
     * Activates the guard, runs fn(), then deactivates.
     * Deactivation is guaranteed even if fn() throws.
     *
     * @param {Function} fn  Zero-argument function to execute under the guard.
     */
    wrap: function (fn) {
      WriteGuard.activate();
      try {
        fn();
      } finally {
        WriteGuard.deactivate();
      }
    }
  };
})();
