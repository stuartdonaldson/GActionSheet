function doPost(e) {
  var payload = JSON.parse(e.postData.contents);
  var expected = PropertiesService.getScriptProperties().getProperty('WEBAPP_SECRET');
  if (!expected || payload.secret !== expected) {
    return ContentService.createTextOutput('unauthorized').setMimeType(ContentService.MimeType.TEXT);
  }
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  sheet.appendRow([new Date(), payload.email, payload.message]);
  return ContentService.createTextOutput('ok');
}
