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
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(buildHomepageCard()))
    .build();
}
