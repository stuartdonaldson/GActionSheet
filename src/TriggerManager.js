/**
 * TriggerManager.js
 *
 * Manages installable triggers for GActionSheet. Safe to run multiple times —
 * existing matching triggers are deleted before new ones are created.
 */

/**
 * Idempotent trigger installer.
 * Installs exactly one onEdit trigger (handler: onActionSheetEdit), one
 * 30-minute time-based trigger (handler: syncAll), and one daily 1am
 * time-based trigger (handler: nightlyAdminScanAllTeams, src/AdminDocScan.js)
 * that scans every team's registered folders for untracked action-bearing
 * docs. Running this function a second time will NOT create duplicate
 * triggers.
 *
 * The 30-min syncAll trigger can collide with an in-flight test/user sync for
 * the same doc (gts-li3g) and, less commonly, with GAS's execution quota
 * during a heavy pytest run (observed 2026-07-30). Disabling the trigger was
 * considered and rejected (gts-li3g DESIGN): a test run that dies before
 * re-enabling it would leave scheduled sync permanently off in that
 * environment (fails open). The real fix is a per-docId lock around
 * syncDocument() (gts-li3g), not removing the trigger.
 */
function initializeTriggers() {
  var installed = 0;
  try {
    var existing = ScriptApp.getProjectTriggers();

    // Remove any existing onEdit and 30-min time-based triggers so we can
    // recreate them cleanly (idempotency guarantee).
    for (var i = 0; i < existing.length; i++) {
      var t = existing[i];
      var eventType = t.getEventType();
      var handlerFunc = t.getHandlerFunction();

      var isTargetOnEdit = (eventType === ScriptApp.EventType.ON_EDIT)
        && (handlerFunc === 'onActionSheetEdit');

      var isTargetTimeBased = (eventType === ScriptApp.EventType.CLOCK)
        && (handlerFunc === 'syncAll');

      var isTargetNightlyScan = (eventType === ScriptApp.EventType.CLOCK)
        && (handlerFunc === 'nightlyAdminScanAllTeams');

      if (isTargetOnEdit || isTargetTimeBased || isTargetNightlyScan) {
        ScriptApp.deleteTrigger(t);
      }
    }

    // Install onEdit trigger bound to the active spreadsheet.
    ScriptApp.newTrigger('onActionSheetEdit')
      .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
      .onEdit()
      .create();
    installed++;

    // Install 30-minute time-based trigger.
    ScriptApp.newTrigger('syncAll')
      .timeBased()
      .everyMinutes(30)
      .create();
    installed++;

    // Install the nightly all-teams untracked-doc scan (src/AdminDocScan.js).
    // atHour(1) fires once between 1:00 and 1:59am in the script's timezone
    // — GAS time-based triggers don't guarantee the exact minute.
    ScriptApp.newTrigger('nightlyAdminScanAllTeams')
      .timeBased()
      .atHour(1)
      .everyDays(1)
      .create();
    installed++;

    GasLogger.log('triggers.initialized', { onEditCount: 1, timeBasedCount: 2, count: installed });
  } catch (e) {
    // gts-u947 (stage regression-verify): the prior try/finally had no catch,
    // so an exception thrown mid-install (ScriptApp trigger-quota/contention,
    // observed under a heavy full-sweep pytest run with the live 30-min
    // syncAll trigger firing concurrently) skipped the GasLogger.log() call
    // above and left ZERO telemetry -- not delayed telemetry, none at all --
    // making a real failure indistinguishable from Axiom ingestion lag from
    // the test side. Log then rethrow: the caller still sees the failure
    // (no swallowing), but now with a diagnosable trail.
    GasLogger.log('triggers.initializeFailed', { message: String(e && e.message || e), installed: installed });
    throw e;
  } finally {
    GasLogger.flush();
  }
}
