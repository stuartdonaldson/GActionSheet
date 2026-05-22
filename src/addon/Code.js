/**
 * Workspace Add-on walking skeleton for GActionSheet.
 * Validates the install-and-trigger lifecycle before any business logic is added.
 */

// ── Card UI ────────────────────────────────────────────────────────────────

function buildHomepageCard() {
  var lastPing = PropertiesService.getUserProperties().getProperty('lastPing');
  var statusText = lastPing ? 'Last ping: ' + lastPing : 'GActionSheet sidebar — alive';

  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('GActionSheet'))
    .addSection(
      CardService.newCardSection()
        .addWidget(CardService.newTextParagraph().setText(statusText))
        .addWidget(
          CardService.newTextButton()
            .setText('Ping')
            .setOnClickAction(CardService.newAction().setFunctionName('onPing'))
        )
    )
    .build();
}

function onPing() {
  var ts = new Date().toISOString();
  PropertiesService.getUserProperties().setProperty('lastPing', ts);
  GasLogger.log('addon.ping', { ts: ts });
  try { GasLogger.flush(); } catch (e) { Logger.log('GasLogger.flush error: ' + e); }
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
    .build();
}

// ── GasLogger (standalone copy — add-on shares no code with automation) ───

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
