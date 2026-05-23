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
        .addWidget(
          CardService.newTextInput()
            .setFieldName('poc_input')
            .setTitle('POC: proxy write message')
        )
        .addWidget(
          CardService.newTextButton()
            .setText('Test Proxy Write')
            .setOnClickAction(CardService.newAction().setFunctionName('relayPocToSheet'))
        )
    )
    .build();
}

function onPing() {
  var ts = new Date().toISOString();
  PropertiesService.getUserProperties().setProperty('lastPing', ts);
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
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

function relayPocToSheet(e) {
  var webAppUrl = PropertiesService.getScriptProperties().getProperty('WEBAPP_URL');
  if (!webAppUrl) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText('FAIL: set WEBAPP_URL in script properties first'))
      .build();
  }
  var secret = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  UrlFetchApp.fetch(webAppUrl, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({
      secret: secret,
      email: Session.getActiveUser().getEmail(),
      message: e.formInput.poc_input || '(empty)'
    })
  });
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText('Proxy write sent — check ActionSheet'))
    .build();
}
