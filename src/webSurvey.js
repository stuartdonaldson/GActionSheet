/**
 * webSurvey.js
 *
 * doGet ?cmd=survey — self-contained survey webapp. Respondents enter their
 * name, drag-reorder a shared list of topics (sourced from the "Survey"
 * sheet's Topics column, with new items addable inline), and submit a
 * numeric ranking that is written back as a per-respondent column on the
 * same sheet. Re-entering a name already used pulls in that respondent's
 * last ranking for re-ordering.
 *
 * Entry point: _handleSurvey(e), wired from WebApp.js doGet (cmd === 'survey').
 * All other functions here are either internal helpers or RPCs called from
 * webSurvey.html via google.script.run.
 */

var _SURVEY_SHEET_NAME = 'Survey';
var _SURVEY_LOCK_TIMEOUT_MS = 30000;
// Row 2, column A is reserved for this marker; that row holds each
// respondent's free-text comment (column-aligned with their name header),
// never a topic. Topics occupy row 3+.
var _SURVEY_COMMENT_MARKER = '__comment__';
var _SURVEY_COMMENT_ROW = 2;
var _SURVEY_TOPICS_FIRST_ROW = 3;

/**
 * doGet ?cmd=survey entry point — the only survey entry point. All survey
 * interactions (page render, read, add, submit) are dispatched here via
 * e.parameter.action so they remain reachable over plain HTTP (test
 * coverage, scripted calls) in addition to the page's own google.script.run
 * calls.
 *
 * ?cmd=survey                                        — render the page
 * ?cmd=survey&action=data&name=<name>                — read ranking/topics
 * ?cmd=survey&action=add&phrase=<phrase>              — append a topic
 * ?cmd=survey&action=submit&name=<name>&order=<json>  — save a ranking
 *
 * @param {Object} e doGet event.
 * @return {HtmlOutput|TextOutput}
 */
function _handleSurvey(e) {
  var params = (e && e.parameter) || {};
  var action = params.action || 'page';

  GasLogger.log('webapp.survey', { action: action, parameter: JSON.stringify(params) });
  GasLogger.flush();

  if (action === 'page') {
    // GAS wraps webapp output in an outer frame that only reliably honors a
    // mobile viewport when set via addMetaTag — a plain <meta viewport> tag
    // inside the page's own HTML is not enough; without this, phones render
    // the page as a zoomed-out desktop layout.
    return HtmlService.createHtmlOutputFromFile('webSurveyPage')
      .setTitle('Northlake Topic and Ideas Survey')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1, maximum-scale=1');
  }

  try {
    switch (action) {
      case 'data':
        return _surveyJsonResponse(getSurveyForName(params.name));
      case 'add':
        return _surveyJsonResponse(addSurveyTopic(params.phrase));
      case 'submit':
        return _surveyJsonResponse(submitSurveyRanking(params.name, JSON.parse(params.order || '[]'), params.comment));
      default:
        return _surveyJsonResponse({ error: 'Unknown survey action: ' + action });
    }
  } catch (err) {
    return _surveyJsonResponse({ error: String(err && err.message ? err.message : err) });
  }
}

/**
 * Wraps a plain object as a JSON TextOutput.
 *
 * @param {Object} obj
 * @return {TextOutput}
 */
function _surveyJsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Returns the Survey sheet, creating it with a "Topics" header and reserved
 * comment-marker row if absent. Migrates a pre-existing sheet (from before
 * the comment feature) by inserting the marker row without disturbing
 * already-saved topics or rankings.
 *
 * @param {Spreadsheet} ss
 * @return {Sheet}
 */
function _getOrCreateSurveySheet(ss) {
  var sheet = ss.getSheetByName(_SURVEY_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(_SURVEY_SHEET_NAME);
    sheet.getRange(1, 1).setValue('Topics');
    sheet.getRange(_SURVEY_COMMENT_ROW, 1).setValue(_SURVEY_COMMENT_MARKER);
    sheet.setFrozenRows(1);
    return sheet;
  }

  var marker = String(sheet.getRange(_SURVEY_COMMENT_ROW, 1).getValue() || '').trim();
  if (marker !== _SURVEY_COMMENT_MARKER) {
    sheet.insertRowBefore(_SURVEY_COMMENT_ROW);
    sheet.getRange(_SURVEY_COMMENT_ROW, 1).setValue(_SURVEY_COMMENT_MARKER);
  }
  return sheet;
}

/**
 * Reads the Topics column (A, rows 3+), skipping blanks.
 *
 * @param {Sheet} sheet
 * @return {Array<{row: number, topic: string}>}
 */
function _readSurveyTopicRows(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < _SURVEY_TOPICS_FIRST_ROW) return [];
  var values = sheet.getRange(_SURVEY_TOPICS_FIRST_ROW, 1, lastRow - _SURVEY_TOPICS_FIRST_ROW + 1, 1).getValues();
  var out = [];
  for (var i = 0; i < values.length; i++) {
    var topic = String(values[i][0] || '').trim();
    if (topic) out.push({ row: i + _SURVEY_TOPICS_FIRST_ROW, topic: topic });
  }
  return out;
}

/**
 * Reads a respondent's saved comment, if any.
 *
 * @param {Sheet} sheet
 * @param {number} colIndex 1-based column, or -1 if the respondent has no column yet.
 * @return {string}
 */
function _getSurveyComment(sheet, colIndex) {
  if (colIndex === -1) return '';
  return String(sheet.getRange(_SURVEY_COMMENT_ROW, colIndex).getValue() || '');
}

/**
 * Finds the 1-based column for a respondent's name in row 1 (columns B+),
 * matching case-insensitively on trimmed text.
 *
 * @param {Sheet} sheet
 * @param {string} name
 * @return {number} 1-based column index, or -1 if not found.
 */
function _findSurveyNameColumn(sheet, name) {
  var lastCol = sheet.getLastColumn();
  if (lastCol < 2) return -1;
  var headers = sheet.getRange(1, 2, 1, lastCol - 1).getValues()[0];
  var target = String(name).trim().toLowerCase();
  for (var i = 0; i < headers.length; i++) {
    if (String(headers[i] || '').trim().toLowerCase() === target) return i + 2;
  }
  return -1;
}

/**
 * RPC: returns the topic list and saved comment for the survey, ordered by
 * the named respondent's previous ranking if one exists, else in sheet
 * order.
 *
 * @param {string} name
 * @return {{topics: Array<string>, comment: string}}
 */
function getSurveyForName(name) {
  name = String(name || '').trim();

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = _getOrCreateSurveySheet(ss);
  var topicRows = _readSurveyTopicRows(sheet);

  GasLogger.log('survey.getForName', { name: name, topicCount: topicRows.length });
  GasLogger.flush();

  if (!name) {
    return { topics: topicRows.map(function (t) { return t.topic; }), comment: '' };
  }

  var colIndex = _findSurveyNameColumn(sheet, name);
  if (colIndex === -1) {
    return { topics: topicRows.map(function (t) { return t.topic; }), comment: '' };
  }

  var lastRow = sheet.getLastRow();
  var ranks = lastRow >= _SURVEY_TOPICS_FIRST_ROW
    ? sheet.getRange(_SURVEY_TOPICS_FIRST_ROW, colIndex, lastRow - _SURVEY_TOPICS_FIRST_ROW + 1, 1).getValues()
    : [];
  var withRank = topicRows.map(function (t) {
    var raw = ranks[t.row - _SURVEY_TOPICS_FIRST_ROW] ? ranks[t.row - _SURVEY_TOPICS_FIRST_ROW][0] : '';
    var rank = Number(raw);
    return { topic: t.topic, rank: isNaN(rank) ? Infinity : rank };
  });
  withRank.sort(function (a, b) { return a.rank - b.rank; });

  return {
    topics: withRank.map(function (t) { return t.topic; }),
    comment: _getSurveyComment(sheet, colIndex)
  };
}

/**
 * RPC: appends a new topic to the end of the shared list.
 *
 * @param {string} phrase
 * @return {{topic: string}}
 */
function addSurveyTopic(phrase) {
  phrase = String(phrase || '').trim();
  if (!phrase) throw new Error('Item cannot be empty.');

  var lock = LockService.getScriptLock();
  lock.waitLock(_SURVEY_LOCK_TIMEOUT_MS);
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = _getOrCreateSurveySheet(ss);
    var nextRow = sheet.getLastRow() + 1;
    sheet.getRange(nextRow, 1).setValue(phrase);

    GasLogger.log('survey.addTopic', { topic: phrase, row: nextRow });
    GasLogger.flush();

    return { topic: phrase };
  } finally {
    lock.releaseLock();
  }
}

/**
 * RPC: saves a respondent's ranking and comment. Reuses that respondent's
 * existing column if one exists (so re-submission overwrites rather than
 * accumulating duplicate columns), else appends a new column.
 *
 * @param {string} name
 * @param {Array<string>} orderedTopics topics in preference order, most
 *   preferred first.
 * @param {string=} comment free-text comment; overwrites any previously
 *   saved comment for this respondent.
 * @return {{ok: boolean}}
 */
function submitSurveyRanking(name, orderedTopics, comment) {
  name = String(name || '').trim();
  if (!name) throw new Error('Name is required.');
  if (!orderedTopics || !orderedTopics.length) throw new Error('Ranking cannot be empty.');

  var lock = LockService.getScriptLock();
  lock.waitLock(_SURVEY_LOCK_TIMEOUT_MS);
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = _getOrCreateSurveySheet(ss);
    var topicRows = _readSurveyTopicRows(sheet);

    var rankByTopic = {};
    orderedTopics.forEach(function (topic, idx) {
      rankByTopic[String(topic).trim()] = idx + 1;
    });

    var colIndex = _findSurveyNameColumn(sheet, name);
    if (colIndex === -1) {
      colIndex = sheet.getLastColumn() + 1;
      sheet.getRange(1, colIndex).setValue(name);
    }

    topicRows.forEach(function (t) {
      var rank = rankByTopic.hasOwnProperty(t.topic) ? rankByTopic[t.topic] : '';
      sheet.getRange(t.row, colIndex).setValue(rank);
    });

    sheet.getRange(_SURVEY_COMMENT_ROW, colIndex).setValue(String(comment || '').trim());

    GasLogger.log('survey.submitRanking', { name: name, topicCount: topicRows.length, column: colIndex });
    GasLogger.flush();

    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}
