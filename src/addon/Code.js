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
        .addWidget(
          CardService.newTextButton()
            .setText('Test Docs API')
            .setOnClickAction(CardService.newAction().setFunctionName('onSmokeDocsApi'))
        )
    )
    .build();
}

function smokeDocsApi() {
  var docId = DocumentApp.getActiveDocument().getId();
  var url = 'https://docs.googleapis.com/v1/documents/' + docId;
  var resp = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  if (code !== 200) throw new Error('Expected 200, got ' + code + ': ' + resp.getContentText());
  return code;
}

function onSmokeDocsApi() {
  var code = smokeDocsApi();
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText('Docs API: HTTP ' + code))
    .build();
}

function onPing() {
  var ts = new Date().toISOString();
  PropertiesService.getUserProperties().setProperty('lastPing', ts);
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
    .build();
}
