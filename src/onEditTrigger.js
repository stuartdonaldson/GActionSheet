/**
 * onEditTrigger.js
 *
 * Installable onEdit trigger handler for the "Actions" sheet.
 *
 * Bound via initializeTriggers() to the tracking spreadsheet (requirements §12.4,
 * §17).  When a user directly edits the Actions sheet, this handler clears
 * the "Synced" cell in the edited row to indicate a pending change.
 *
 * The handler does nothing when WriteGuard is active (programmatic write in
 * progress) or when the edit is on any sheet other than "Actions".
 *
 * Column indices (1-based):
 *   1=ID, 2=Assignee Email, 3=Assignee Name, 4=Action, 5=Status,
 *   6=Document, 7=Date Created, 8=Date Modified, 9=Synced
 */

var SYNCED_COL = 9;       // 1-based column index of "Synced"
var HEADER_ROW = 1;       // Row number of the header

/**
 * Entry-point: called by the installable onEdit trigger.
 *
 * @param {GoogleAppsScript.Events.SheetsOnEdit} e  Apps Script edit event.
 */
function onActionSheetEdit(e) {
  try {
    // Ignore programmatic writes from the sync script.
    if (WriteGuard.isActive()) { return; }

    // Ignore edits outside the Actions sheet.
    var sheet = e.source.getActiveSheet();
    if (sheet.getName() !== 'Actions') { return; }

    var range = e.range;
    var row = range.getRow();

    // Ignore the header row.
    if (row <= HEADER_ROW) { return; }

    // Clear the Synced cell for the edited row.
    // offset(rowOffset, colOffset) — both 0-based relative to the edited cell.
    var editedCol = range.getColumn();
    var syncedColOffset = SYNCED_COL - editedCol;

    range.offset(0, syncedColOffset, 1, 1).clearContent();

    GasLogger.log('onedit.synced.cleared', { row: row });
  } catch (err) {
    GasLogger.log('onedit.error', { message: err.message, stack: err.stack || '' });
    throw err;
  } finally {
    GasLogger.flush();
  }
}
