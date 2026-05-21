/**
 * WriteGuard.js
 *
 * Suppresses the onEdit trigger during programmatic writes to the sheet.
 * Any sheet write performed by the sync script should be wrapped in
 * WriteGuard.wrap() so that onActionSheetEdit ignores the resulting events.
 *
 * Usage:
 *   WriteGuard.wrap(function() { sheet.appendRow(row); });
 */
var WriteGuard = (function () {
  var _active = false;

  return {
    activate: function () { _active = true; },
    deactivate: function () { _active = false; },
    isActive: function () { return _active; },

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
