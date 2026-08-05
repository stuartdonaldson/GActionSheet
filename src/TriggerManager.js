/**
 * TriggerManager.js
 *
 * Manages installable triggers for GActionSheet. Safe to run multiple times —
 * existing matching triggers are deleted before new ones are created.
 */

/**
 * Idempotent trigger installer.
 * Installs exactly one onEdit trigger (handler: onActionSheetEdit) and one
 * 30-minute time-based trigger (handler: syncAll).
 * Running this function a second time will NOT create duplicate triggers.
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

      if (isTargetOnEdit || isTargetTimeBased) {
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

    GasLogger.log('triggers.initialized', { onEditCount: 1, timeBasedCount: 1, count: installed });
  } finally {
    GasLogger.flush();
  }
}
