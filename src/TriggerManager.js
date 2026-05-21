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
