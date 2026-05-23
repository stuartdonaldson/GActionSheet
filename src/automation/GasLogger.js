/**
 * Structured server-side logger. Buffers entries in memory and flushes to a
 * Drive folder as NDJSON on demand or when the buffer threshold is reached.
 *
 * Setup: set script property GAS_LOGGER_FOLDER_ID to a Drive folder ID that is
 * mapped locally via Drive for Desktop (used by tests to poll log files).
 *
 * Usage:
 *   GasLogger.log('sync.complete', { docId, changes: 3 });
 *   GasLogger.flush();  // call in finally block of every entry-point function
 */
var GasLogger = (function () {
  var _folder = null;
  var _entries = [];
  var _enabled = true;
  var FLUSH_THRESHOLD = 25;

  function _getFolder() {
    if (_folder) return _folder;
    var folderId = PropertiesService.getScriptProperties().getProperty('GAS_LOGGER_FOLDER_ID');
    if (folderId) {
      _folder = DriveApp.getFolderById(folderId);
      return _folder;
    }
    var root = DriveApp.getRootFolder();
    var iter = root.getFoldersByName('GActionSheet-Logs');
    _folder = iter.hasNext() ? iter.next() : root.createFolder('GActionSheet-Logs');
    return _folder;
  }

  return {
    enable: function () { _enabled = true; },
    disable: function () { _enabled = false; },

    log: function (tag, data) {
      var entry = { ts: new Date().toISOString(), tag: tag, data: data || {} };
      Logger.log(JSON.stringify(entry));
      if (!_enabled) return;
      _entries.push(entry);
      if (_entries.length >= FLUSH_THRESHOLD) this.flush();
    },

    flush: function () {
      if (_entries.length === 0) return;
      var name = new Date().getTime() + '-' + Utilities.getUuid() + '.log';
      _getFolder().createFile(
        name,
        _entries.map(function (e) { return JSON.stringify(e); }).join('\n'),
        MimeType.PLAIN_TEXT
      );
      _entries = [];
    },
  };
})();
