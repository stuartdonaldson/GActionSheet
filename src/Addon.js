/**
 * Addon.js
 *
 * Workspace Add-on card builder and button handlers.
 * Entry point: buildHomepageCard() — registered as homepageTrigger in appsscript.json.
 */

function buildHomepageCard() {
  var section = CardService.newCardSection();

  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    section.addWidget(
      CardService.newTextParagraph().setText('Open a Google Doc to use Action Sync.')
    );
  } else {
    section
      .addWidget(CardService.newTextParagraph().setText(doc.getName()))
      .addWidget(
        CardService.newTextButton()
          .setText('Sync now')
          .setOnClickAction(CardService.newAction().setFunctionName('onSyncNow'))
      );
  }

  section.addWidget(CardService.newTextParagraph().setText(BUILD_INFO.version));

  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('Action Sync'))
    .addSection(section)
    .build();
}

function onSyncNow() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }
  try {
    syncDocument(doc.getId());
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Sync complete'))
      .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
      .build();
  } catch (e) {
    GasLogger.log('addon.sync.error', { msg: e.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('Sync failed: ' + e.message))
      .build();
  }
}

// Smoke-test helpers (retained for diagnostics)

function smokeDocsApi() {
  var docId = DocumentApp.getActiveDocument().getId();
  var url   = 'https://docs.googleapis.com/v1/documents/' + docId;
  var resp  = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  if (code !== 200) throw new Error('Expected 200, got ' + code + ': ' + resp.getContentText());
  return code;
}
