/**
 * Addon.js
 *
 * Workspace Add-on card builder and button handlers.
 * Entry point: buildHomepageCard() — registered as homepageTrigger in appsscript.json.
 */

function buildHomepageCard(eventOrVerificationResult) {
  var section = CardService.newCardSection();
  var verificationResult = _isVerificationResult(eventOrVerificationResult)
    ? eventOrVerificationResult
    : null;

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
          .setOnClickAction(_buildSidebarAction('onSyncNow'))
      )
      .addWidget(
        CardService.newTextButton()
          .setText('VerifySync')
          .setOnClickAction(_buildSidebarAction('onVerifySync'))
      );
  }

  section.addWidget(CardService.newTextParagraph().setText(BUILD_INFO.version));

  var card = CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('Action Sync'))
    .addSection(section);

  if (verificationResult) {
    card.addSection(_buildVerificationSection(verificationResult));
  }

  return card.build();
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

function onVerifySync() {
  var doc = DocumentApp.getActiveDocument();
  if (!doc) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('No active document'))
      .build();
  }

  try {
    var verificationResult = verifyDocumentSync(doc.getId());
    var message = verificationResult.ok
      ? 'VerifySync complete: no issues found'
      : 'VerifySync complete: ' + verificationResult.issues.length + ' issue(s) found';

    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText(message))
      .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard(verificationResult)))
      .build();
  } catch (e) {
    GasLogger.log('addon.verify.error', { msg: e.message });
    GasLogger.flush();
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('VerifySync failed: ' + e.message))
      .build();
  }
}

function _buildVerificationSection(verificationResult) {
  var section = CardService.newCardSection().setHeader('VerifySync Results');
  var summary = [
    verificationResult.ok ? 'Status: OK' : 'Status: issues found',
    'Floating actions: ' + verificationResult.counts.floating,
    'Tracker rows: ' + verificationResult.counts.tracker,
    'ActionSheet rows: ' + verificationResult.counts.sheet,
    'Matched actions: ' + verificationResult.counts.matched
  ];
  section.addWidget(
    CardService.newTextParagraph().setText('<b>Summary</b><br>' + _htmlLines(summary))
  );

  if (verificationResult.progress && verificationResult.progress.length) {
    section.addWidget(
      CardService.newTextParagraph().setText('<b>Progress</b><br>' + _htmlLines(verificationResult.progress))
    );
  }

  if (verificationResult.issues && verificationResult.issues.length) {
    section.addWidget(
      CardService.newTextParagraph().setText('<b>Findings</b><br>' + _htmlLines(_limitVerificationLines(verificationResult.issues, 20)))
    );
  }

  return section;
}

function _limitVerificationLines(lines, maxLines) {
  if (lines.length <= maxLines) {
    return lines;
  }

  var limited = lines.slice(0, maxLines);
  limited.push('... ' + (lines.length - maxLines) + ' more');
  return limited;
}

function _htmlLines(lines) {
  var escaped = [];
  for (var i = 0; i < lines.length; i++) {
    escaped.push(_escapeAddonHtml(lines[i]));
  }
  return escaped.join('<br>');
}

function _escapeAddonHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function _isVerificationResult(value) {
  return !!(
    value &&
    value.counts &&
    typeof value.counts.floating !== 'undefined' &&
    typeof value.counts.tracker !== 'undefined' &&
    typeof value.counts.sheet !== 'undefined' &&
    typeof value.counts.matched !== 'undefined'
  );
}

function _buildSidebarAction(functionName) {
  var action = CardService.newAction().setFunctionName(functionName);
  if (action.setLoadIndicator && CardService.LoadIndicator) {
    action.setLoadIndicator(CardService.LoadIndicator.SPINNER);
  }
  return action;
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
