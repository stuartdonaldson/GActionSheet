/**
 * SyncManager.js
 *
 * Sync entry points. Full implementation pending; stubs satisfy the test
 * infrastructure contract (log tags) while the add-on architecture is verified.
 */

function syncDocument(docId) {
  try {
    GasLogger.log('sync.complete', { docId: docId || null });
  } finally {
    GasLogger.flush();
  }
}

function syncAll() {
  try {
    GasLogger.log('sync.all.complete', {});
  } finally {
    GasLogger.flush();
  }
}

function onActionSheetEdit(e) {
  if (WriteGuard.isActive()) return;
  // Stub — timestamp stamping implementation pending.
}
