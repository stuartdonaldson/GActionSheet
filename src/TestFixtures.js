/**
 * TestFixtures.js
 *
 * GAS entry-point functions for setting up test fixtures and exercising the
 * sync path in isolation. Both functions are selectable in the Apps Script
 * editor function picker and must work when called with no arguments.
 */

/**
 * TABLE_HEADERS order (mirrors DocumentNormalizer.js — 7 columns).
 * Redeclared here as a local constant so TestFixtures.js has no hidden
 * dependency on load order at test time.
 */
var _TF_TABLE_HEADERS = [
  'ID',
  'Assignee Email',
  'Assignee Name',
  'Action',
  'Status',
  'Date Created',
  'Date Modified'
];

/**
 * Holds the structured return value for the most recent setupTestFixtures call.
 * Set by fixture cases that produce meaningful data (e.g. sentinelDateModified).
 * Read by _handleRunFixture in TestWebApp.js to build the HTTP response body.
 * Resets to null at the start of each setupTestFixtures invocation.
 */
var _TF_RESULT = null;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------


/**
 * Clears all data rows (keeps header in row 1) from a named sheet tab.
 * If the tab does not exist, logs a warning and returns.
 *
 * @param {Spreadsheet} ss
 * @param {string}      tabName
 */
function _tfClearSheetTab(ss, tabName) {
  var sheet = ss.getSheetByName(tabName);
  if (!sheet) {
    GasLogger.log('fixture.warn', { msg: 'Tab not found, skipping clear', tab: tabName });
    return;
  }
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    WriteGuard.wrap(function () {
      sheet.getRange(2, 1, lastRow - 1, SHEET_HEADERS.length).clearContent();
    });
  }
}

/**
 * Replaces the test doc body with just the "Floating Actions" heading paragraph
 * using HEADING1 style. All previous content is removed.
 *
 * @param {Body} body  DocumentApp Body object.
 * @returns {Paragraph}  The heading paragraph that was appended.
 */
function _tfResetDocBody(body) {
  body.clear();
  var heading = body.appendParagraph('Floating Actions');
  heading.setHeading(DocumentApp.ParagraphHeading.HEADING1);
  return heading;
}

/**
 * Appends a tracked-actions table (header row only) to the doc body.
 * GAS requires at least one data row when constructing via appendTable([]),
 * so a blank placeholder row is added and is the only data row.
 *
 * @param {Body} body
 * @returns {Table}
 */
function _tfAppendEmptyTable(body) {
  var blank = [];
  for (var i = 0; i < _TF_TABLE_HEADERS.length; i++) {
    blank.push('');
  }
  var table = body.appendTable([_TF_TABLE_HEADERS, blank]);
  var headerRow = table.getRow(0);
  for (var c = 0; c < _TF_TABLE_HEADERS.length; c++) {
    headerRow.getCell(c).setText(_TF_TABLE_HEADERS[c]);
    headerRow.getCell(c).setBackgroundColor('#D9D9D9');
  }
  return table;
}

/**
 * Appends a data row to the tracked-actions table.
 * Cells must be provided in _TF_TABLE_HEADERS order.
 *
 * @param {Table}    table
 * @param {string[]} cells  7-element array matching TABLE_HEADERS order.
 */
function _tfAppendTableRow(table, cells) {
  var row = table.appendTableRow();
  while (row.getNumCells() < _TF_TABLE_HEADERS.length) {
    row.appendTableCell('');
  }
  for (var i = 0; i < _TF_TABLE_HEADERS.length; i++) {
    row.getCell(i).setText(cells[i] || '');
  }
}

/**
 * Inserts a floating-action paragraph at index 0 of the body (before the
 * section heading) using Normal text style.
 *
 * @param {Body}   body
 * @param {string} text  Full floating-action line, e.g. "AI- @x | ... | ..."
 */
function _tfInsertFloatingAction(body, text) {
  var para = body.insertParagraph(0, text);
  para.setHeading(DocumentApp.ParagraphHeading.NORMAL);
}

/**
 * Inserts a chip-led bulleted list item at the start of the document via the
 * Docs REST API batchUpdate.  Must be called AFTER doc.saveAndClose() so the
 * DocumentApp changes are flushed and the REST API sees the current state.
 *
 * The person chip (@mention) is created with insertPerson; the list format is
 * applied with createParagraphBullets.  Both happen in one atomic batchUpdate.
 *
 * @param {string} token     OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId     Document ID
 * @param {string} email     Assignee email — must be in the user's contacts or
 *                           Google Workspace directory, otherwise insertPerson
 *                           will fail with a 400.
 * @param {string} actionText Text to append after the chip on the same line
 */
function _tfInsertPersonChipListItem(token, docId, email, actionText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('Docs GET failed (' + getResp.getResponseCode() + '): ' +
                    getResp.getContentText());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfInsertPersonChipListItem: no paragraph found in doc body');
  }

  // Insert a chip-led bullet item: 'AI: ' placeholder + PERSON chip + action text.
  // _assignPlaceholderTokens (called during sync) converts 'AI: ' → 'AI-N:'.
  var insertAt = lastParaEndIndex - 1;
  var aiPlaceholder = 'AI: ';
  var aiPlaceholderLen = aiPlaceholder.length;
  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex },
        text: aiPlaceholder
      }
    },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + aiPlaceholderLen }
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex + aiPlaceholderLen + 1 },
        text: ' ' + actionText
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('Docs batchUpdate failed (' + batchResp.getResponseCode() + '): ' +
                    batchResp.getContentText());
  }
}

/**
 * Appends a plain-text bullet list item to the end of the document via the
 * Docs REST API, without opening the document through DocumentApp.
 *
 * Strategy: GET the doc to find the last paragraph's endIndex, then split it
 * by inserting \n before its terminal \n, then insert the text and apply
 * createParagraphBullets — all in one batchUpdate.
 *
 * @param {string} token   OAuth token (ScriptApp.getOAuthToken())
 * @param {string} docId   Google Doc ID
 * @param {string} text    Text content of the new list item (no \n needed)
 */
function _tfAppendTextListItem(token, docId, text) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendTextListItem GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendTextListItem: no paragraph found in doc');
  }

  // Split the last paragraph by inserting \n before its terminal \n at
  // (lastParaEndIndex - 1).  After the split, an empty paragraph begins at
  // lastParaEndIndex.  Then fill that paragraph with the text and apply
  // BULLET formatting.  All three requests apply in order within one call.
  var insertAt = lastParaEndIndex - 1;
  var textLen  = text.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { insertText: { location: { index: lastParaEndIndex }, text: text } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + textLen + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendTextListItem batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * Appends an AI-N: token + PERSON chip bulleted list item to the end of the document.
 *
 * Inserts: <aiNPrefix> <chip(email)> <actionText> as a bullet.
 * The scanner reads the PERSON chip's getName() (Google contact resolution) rather
 * than deriving a display name from the email username.
 *
 * @param {string} token      OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId      Document ID
 * @param {string} aiNPrefix  Token prefix, e.g. "AI-9:"
 * @param {string} email      Assignee email (must be in contacts or Workspace directory)
 * @param {string} actionText Text to append after the chip
 */
function _tfAppendAINPersonChipListItem(token, docId, aiNPrefix, email, actionText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendAINPersonChipListItem GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendAINPersonChipListItem: no paragraph found in doc body');
  }

  var insertAt  = lastParaEndIndex - 1;
  var prefix    = aiNPrefix + ' ';   // e.g. "AI-9: "
  var prefixLen = prefix.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex },
        text: prefix
      }
    },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + prefixLen }
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex + prefixLen + 1 },
        text: ' ' + actionText
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendAINPersonChipListItem batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * Appends a chip-led bulleted list item to the END of the document via the
 * Docs REST API, without clearing existing content.
 *
 * Mirrors _tfAppendTextListItem but inserts a PERSON chip before the action text.
 * Must be called AFTER doc.saveAndClose() so the REST API sees current content.
 *
 * @param {string} token      OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId      Document ID
 * @param {string} email      Assignee email (must be in contacts or Workspace directory)
 * @param {string} actionText Text to append after the chip on the same line
 */
function _tfAppendPersonChipListItem(token, docId, email, actionText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendPersonChipListItem GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendPersonChipListItem: no paragraph found in doc');
  }

  // Mirror _tfAppendTextListItem's splitting strategy:
  //   1. Insert \n at (lastParaEndIndex - 1) to split the last (mandatory) paragraph.
  //   2. Apply bullet formatting to the new paragraph starting at lastParaEndIndex.
  //   3. Insert 'AI: ' placeholder text at lastParaEndIndex (_assignPlaceholderTokens converts → AI-N:).
  //   4. Insert the person chip after the placeholder.
  //   5. Insert the action text after the chip.
  var insertAt  = lastParaEndIndex - 1;
  var aiPlaceholder = 'AI: ';
  var aiPlaceholderLen = aiPlaceholder.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { createParagraphBullets: {
        range: { startIndex: lastParaEndIndex, endIndex: lastParaEndIndex + 1 },
        bulletPreset: 'BULLET_DISC_CIRCLE_SQUARE'
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex },
        text: aiPlaceholder
      }
    },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + aiPlaceholderLen }
      }
    },
    { insertText: {
        location: { index: lastParaEndIndex + aiPlaceholderLen + 1 },
        text: ' ' + actionText
      }
    }
  ];

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendPersonChipListItem batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * gts-ogev/gts-mt39: appends ONE plain (non-bulleted) body-level paragraph of
 * the form `[beforeText '\v'] tokenPrefix ' ' <PERSON chip> [' ' afterText]`,
 * via the Docs REST API only (no DocumentApp), so the chip and the soft
 * return are both created with the exact same mechanism the fast-path chip
 * fixtures above use for the chip itself.
 *
 * '\v' (U+000B), not '\n', is the separator between beforeText and the token
 * line: this is what makes it a genuine same-paragraph soft return rather
 * than a new paragraph — see _toSoftReturnText's doc comment in
 * SyncManager.js for why U+000B specifically (InsertTextRequest strips
 * U+000B<0x1F control chars except this one, and treats literal '\n' as a
 * hard paragraph break).
 *
 * Omitting beforeText ('') produces a single-line paragraph with the token at
 * position 0 — the single-token fast path's shape
 * (_parseParagraphAsFloatingAction) — so the SAME helper can seed both sides
 * of a same-chip fast-path-vs-soft-return-path comparison.
 *
 * @param {string} token       OAuth2 access token from ScriptApp.getOAuthToken()
 * @param {string} docId       Document ID
 * @param {string} beforeText  Text on the line(s) before the token; '' for none
 * @param {string} tokenPrefix e.g. 'AI-9:' or 'ACT-3:' (colon included)
 * @param {string} email       Assignee email for the PERSON chip
 * @param {string} afterText   Text after the chip on the token's own line; '' for none
 */
function _tfAppendChipHeaderParagraph(token, docId, beforeText, tokenPrefix, email, afterText) {
  var baseUrl    = 'https://docs.googleapis.com/v1/documents/';
  var authHeader = { 'Authorization': 'Bearer ' + token };

  var getResp = UrlFetchApp.fetch(
    baseUrl + docId + '?fields=body.content',
    { headers: authHeader, muteHttpExceptions: true }
  );
  if (getResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendChipHeaderParagraph GET failed: HTTP ' + getResp.getResponseCode());
  }
  var content = (JSON.parse(getResp.getContentText()).body || {}).content || [];

  var lastParaEndIndex = null;
  for (var ci = content.length - 1; ci >= 0; ci--) {
    if (content[ci].paragraph) {
      lastParaEndIndex = content[ci].endIndex;
      break;
    }
  }
  if (lastParaEndIndex === null) {
    throw new Error('_tfAppendChipHeaderParagraph: no paragraph found in doc body');
  }

  var insertAt = lastParaEndIndex - 1;
  var header    = (beforeText ? beforeText + '\v' : '') + tokenPrefix + ' ';
  var headerLen = header.length;

  var requests = [
    { insertText: { location: { index: insertAt }, text: '\n' } },
    { insertText: { location: { index: lastParaEndIndex }, text: header } },
    { insertPerson: {
        personProperties: { email: email },
        location: { index: lastParaEndIndex + headerLen }
      }
    }
  ];
  if (afterText) {
    requests.push({ insertText: {
      location: { index: lastParaEndIndex + headerLen + 1 },
      text: ' ' + afterText
    }});
  }

  var batchResp = UrlFetchApp.fetch(
    baseUrl + docId + ':batchUpdate',
    {
      method: 'post',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader),
      payload: JSON.stringify({ requests: requests }),
      muteHttpExceptions: true
    }
  );
  if (batchResp.getResponseCode() !== 200) {
    throw new Error('_tfAppendChipHeaderParagraph batchUpdate failed: HTTP ' +
                    batchResp.getResponseCode() + ': ' +
                    batchResp.getContentText().substring(0, 200));
  }
}

/**
 * Test-harness signer for gts-79dw.4.18's assertion verifier
 * (_verifySignedAssertion, src/AccessControl.js). Mirrors NUUC-Dispatch's
 * own Assertion_issue (../NUUC-Dispatch/src/Assertion.js) exactly on the
 * happy path, but exposes every claim as an override so negative tests can
 * construct a deliberately-wrong assertion (bad aud, unknown kid, expired
 * exp, wrong alg, tampered signature) -- all signed with the REAL Script
 * Property secret so a positive-path test proves the verifier actually
 * accepts a correctly-signed token, not just rejects everything.
 *
 * Reads the secret from Script Properties (never accepts one from the
 * caller, never returns it) -- if the named `kid` property doesn't exist
 * yet, returns {ok:false, error:'missing_secret'} so the caller can report
 * that as a blocking provisioning gap rather than silently signing with a
 * fabricated key.
 *
 * @param {Object} opts
 * @param {string}  [opts.sub]
 * @param {string}  [opts.email]
 * @param {boolean} [opts.emailVerified]
 * @param {string}  [opts.aud]              default 'gactionsheet'
 * @param {string}  [opts.iss]              default 'nuuc-dispatch'
 * @param {string}  [opts.kid]              default 'ASSERTION_KEY_GACTIONSHEET_1'
 * @param {string}  [opts.alg]              default 'HS256'
 * @param {number}  [opts.exp]              default now+3600 (Unix seconds)
 * @param {boolean} [opts.tamperSignature]  flips one signature char if true
 * @returns {{ok: true, assertion: string} | {ok: false, error: string, kid: string}}
 */
function _tfMintAssertion(opts) {
  opts = opts || {};
  var kid = opts.kid || 'ASSERTION_KEY_GACTIONSHEET_1';
  var secret = PropertiesService.getScriptProperties().getProperty(kid);
  if (!secret) {
    return { ok: false, error: 'missing_secret', kid: kid };
  }

  var now = Math.floor(Date.now() / 1000);
  var header = {
    alg: opts.alg || 'HS256',
    typ: 'JWT',
    kid: kid
  };
  var payload = {
    iss:            opts.iss !== undefined ? opts.iss : 'nuuc-dispatch',
    sub:            opts.sub || 'test-sub-001',
    email:          opts.email || 'test-assertion@example.com',
    email_verified: opts.emailVerified !== false,
    aud:            opts.aud !== undefined ? opts.aud : 'gactionsheet',
    iat:            now,
    exp:            opts.exp !== undefined ? opts.exp : (now + 3600)
  };

  function b64urlFromString(str) {
    return Utilities.base64EncodeWebSafe(str).replace(/=+$/, '');
  }

  var headerSeg  = b64urlFromString(JSON.stringify(header));
  var payloadSeg = b64urlFromString(JSON.stringify(payload));
  var signingInput = headerSeg + '.' + payloadSeg;
  var sigBytes = Utilities.computeHmacSha256Signature(signingInput, secret);
  var sigSeg = Utilities.base64EncodeWebSafe(sigBytes).replace(/=+$/, '');

  if (opts.tamperSignature) {
    // Flip the first character so the signature provably no longer matches
    // -- exercises the bad-signature negative path without ever needing to
    // know (or guess) the real secret client-side.
    var flipped = sigSeg.charAt(0) === 'A' ? 'B' : 'A';
    sigSeg = flipped + sigSeg.substring(1);
  }

  return { ok: true, assertion: signingInput + '.' + sigSeg };
}

/**
 * Builds a sheet row array in SHEET_HEADERS order.
 *
 * SHEET_HEADERS = [globalId, ID, Assignee Email, Assignee Name, Action,
 *                  Status, Document, Date Created, Date Modified, Sync Status]
 *
 * @param {object} opts
 * @param {string}  opts.globalId  globalId (format: {docId}/AI-{N}); empty until first sync.
 * @param {string|number} opts.id
 * @param {string}  opts.assigneeEmail
 * @param {string}  opts.assigneeName
 * @param {string}  opts.action
 * @param {string}  opts.status
 * @param {string}  opts.docFormula   Full =HYPERLINK(…) formula string.
 * @param {Date}    opts.dateCreated
 * @param {Date}    opts.dateModified
 * @param {string}  opts.syncStatus
 * @returns {Array}  Row array aligned to SHEET_HEADERS.
 */
function _tfSheetRow(opts) {
  var fileId = opts.fileId || (opts.globalId ? parseGlobalId(opts.globalId).docId : '');
  return [
    opts.globalId || '',
    fileId,
    opts.id,
    opts.assigneeEmail || '',
    opts.assigneeName || '',
    opts.action || '',
    opts.status || '',
    opts.docFormula || '',
    opts.dateCreated || '',
    opts.dateModified || '',
    opts.syncStatus || ''
  ];
}

/**
 * Appends a data row to the "Actions" sheet tab using WriteGuard.
 * Logs a warning and skips if the tab does not exist.
 *
 * @param {Spreadsheet} ss
 * @param {Array}       rowData  8-element row array.
 */
function _tfAppendSheetRow(ss, rowData) {
  var sheet = ss.getSheetByName('Actions');
  if (!sheet) {
    GasLogger.log('fixture.warn', { msg: 'Actions tab not found, skipping row insert' });
    return;
  }
  WriteGuard.wrap(function () {
    sheet.appendRow(rowData);
  });
}

// ---------------------------------------------------------------------------
// configFormat test support (gts-d99c / gts-1pk)
// ---------------------------------------------------------------------------

// Fixed reference style applied by the 'seed_styled_action' fixture case —
// deliberately distinct per-range (token vs action text) so a sampling bug
// that reads the wrong offset, or a fixed default that never changes, is
// visible as a mismatch rather than a coincidental pass. Mirrored (not
// re-derived from _sampleActionItemStyle/_configFormatForDoc) in
// tests/test_journey.py's Act 6 assertions — per the no-shared-context rule,
// the Python side hardcodes these same literal values rather than reading
// this file, so a fixture/test drift here would break the assertion instead
// of silently trivializing it.
var _TF_STYLED_AI_TOKEN = Object.freeze({
  fontFamily: 'Georgia', fontSize: 16, color: '#1B5E20',
  bold: true, italic: false, underline: true
});
var _TF_STYLED_ACTION_TEXT = Object.freeze({
  fontFamily: 'Courier New', fontSize: 13, color: '#B71C1C',
  bold: false, italic: true, underline: false
});

/**
 * Converts a Docs REST rgbColor ({red,green,blue} 0..1 floats) back to a
 * '#rrggbb' hex string, for comparing a debug_action_text_style read-back
 * against _TF_STYLED_AI_TOKEN/_TF_STYLED_ACTION_TEXT's literal hex values.
 *
 * @param {{red:number,green:number,blue:number}} rgb
 * @returns {string}
 */
function _tfRgbToHex(rgb) {
  function ch(v) {
    var n = Math.round((v || 0) * 255);
    var s = n.toString(16);
    return s.length === 1 ? '0' + s : s;
  }
  return '#' + ch(rgb.red) + ch(rgb.green) + ch(rgb.blue);
}

/**
 * Simplifies one Docs REST textStyle object down to the same
 * {fontFamily,fontSize,color,bold,italic,underline} shape
 * _sampleActionItemStyle/_readActionFormatConfig use, for direct comparison
 * in a run_fixture response.
 *
 * @param {Object} textStyle
 * @returns {{fontFamily:?string, fontSize:?number, color:?string, bold:boolean, italic:boolean, underline:boolean}}
 */
function _tfSimplifyTextStyle(textStyle) {
  var ts = textStyle || {};
  var fg = ts.foregroundColor && ts.foregroundColor.color && ts.foregroundColor.color.rgbColor;
  return {
    fontFamily: (ts.weightedFontFamily || {}).fontFamily || null,
    fontSize:   ts.fontSize ? ts.fontSize.magnitude : null,
    color:      fg ? _tfRgbToHex(fg) : null,
    bold:       !!ts.bold,
    italic:     !!ts.italic,
    underline:  !!ts.underline
  };
}

/**
 * Finds the 'AI-N:' token paragraph within a Docs REST body.content tree
 * (top-level paragraphs only — the configFormat/flush-styled action items
 * this fixture verifies are never inside a table) and returns the applied
 * textStyle for the token's own text run and for the text run immediately
 * following it (the action-text + status range) — mirrors
 * _collectFlushOccurrences's token-location logic (SyncManager.js) but reads
 * textStyle instead of computing document-index offsets, since this is a
 * read-only verification fixture, not a flush.
 *
 * @param {Array} content  body.content
 * @param {number} N
 * @returns {{ok:boolean, aiToken:?Object, actionText:?Object, error:?string}}
 */
function _tfExtractActionTextStyle(content, N) {
  var candidates = _ACTION_TOKEN_READ_PREFIXES.map(function (p) { return p + '-' + N + ':'; });
  function prefixAt(text, idx) {
    for (var ci = 0; ci < candidates.length; ci++) {
      if (text.substr(idx, candidates[ci].length) === candidates[ci]) return candidates[ci];
    }
    return null;
  }
  for (var ii = 0; ii < content.length; ii++) {
    var item = content[ii];
    if (!item.paragraph) continue;
    var elements = item.paragraph.elements || [];
    var fullText = '';
    var runs = []; // {startTextIdx, len, textStyle}
    for (var jj = 0; jj < elements.length; jj++) {
      var el = elements[jj];
      if (!el.textRun || el.textRun.content === undefined) continue;
      var tc = el.textRun.content || '';
      runs.push({ startTextIdx: fullText.length, len: tc.length, textStyle: el.textRun.textStyle || {} });
      fullText += tc;
    }
    var tokenTextIdx = -1;
    var matchedPrefix = prefixAt(fullText, 0);
    if (matchedPrefix) {
      tokenTextIdx = 0;
    } else {
      for (var si = 0; si < fullText.length; si++) {
        var ch = fullText[si];
        matchedPrefix = (ch === '\n' || ch === '\r' || ch === '\v') ? prefixAt(fullText, si + 1) : null;
        if (matchedPrefix) { tokenTextIdx = si + 1; break; }
      }
    }
    if (tokenTextIdx < 0) continue;

    var prefixEndTextIdx = tokenTextIdx + matchedPrefix.length;
    var tokenRun  = null;
    var actionRun = null;
    for (var ri = 0; ri < runs.length; ri++) {
      var run    = runs[ri];
      var runEnd = run.startTextIdx + run.len;
      if (!tokenRun && tokenTextIdx >= run.startTextIdx && tokenTextIdx < runEnd) {
        tokenRun = run;
      }
      if (!actionRun && run.startTextIdx >= prefixEndTextIdx) {
        actionRun = run;
      }
    }
    if (!tokenRun) continue;
    return {
      ok: true,
      aiToken:    _tfSimplifyTextStyle(tokenRun.textStyle),
      actionText: actionRun ? _tfSimplifyTextStyle(actionRun.textStyle) : null
    };
  }
  return { ok: false, error: candidates[0] + ' token paragraph not found' };
}

// ---------------------------------------------------------------------------
// Public entry-point
// ---------------------------------------------------------------------------

/**
 * Sets up test fixtures for the given scenario.
 * When called from the function picker, scenario defaults to 'default'.
 *
 * @param {string} [scenario] - Name of the fixture scenario to set up.
 * @param {{docId: string}} [data] - Fixture data; docId is required — the doc
 *   to operate on is always a real parameter, never read from a shared
 *   script property (see ADR-0006 §4).
 */
function setupTestFixtures(scenario, data) {
  var resolvedScenario = scenario || 'default';
  data = data || {};
  _TF_RESULT = null; // reset for this invocation
  var _SF = CONTRACT_SCHEMA.sheetAction.columnsByField;
  try {
    // -- docId is a real parameter; TEST_SHEET_ID is still deploy-time config --
    var props = PropertiesService.getScriptProperties();
    var testDocId   = data.docId;
    var testSheetId = props.getProperty('TEST_SHEET_ID');

    if (!testDocId || !testSheetId) {
      GasLogger.log('fixture.error', {
        msg: 'docId parameter and/or TEST_SHEET_ID script property not set'
      });
      return;
    }

    var doc = DocumentApp.openById(testDocId);
    var ss  = SpreadsheetApp.openById(testSheetId);
    var body = doc.getBody();

    var docUrl     = doc.getUrl();
    var docFormula = '=HYPERLINK("' + docUrl + '","Test Doc")';

    // -- Step 1: seed per scenario; track whether doc was already closed ----
    var docAlreadyClosed = false;
    switch (resolvedScenario) {

      case 'uc_a_clear':
        // Flush DocumentApp writes before using the Docs REST API.
        doc.saveAndClose();
        docAlreadyClosed = true;
        var ucaToken  = ScriptApp.getOAuthToken();
        var ucaEmail  = props.getProperty('TEST_ASSIGNEE_EMAIL')
                     || Session.getActiveUser().getEmail();
        var ucaChipOk = false;
        try {
          _tfInsertPersonChipListItem(ucaToken, testDocId, ucaEmail,
                                      'AC1: Review the project budget');
          ucaChipOk = true;
        } catch (chipErr) {
          GasLogger.log('fixture.uc_a_clear', {
            assigneeEmail: ucaEmail,
            msg: 'chip insert failed',
            err: chipErr.message
          });
        }
        if (ucaChipOk) {
          try {
            _tfAppendTextListItem(
              ucaToken, testDocId,
              'jane.smith@example.com AC1: Approve the project proposal (In Progress)'
            );
            GasLogger.log('fixture.uc_a_clear', {
              assigneeEmail: ucaEmail, emailItemInserted: true
            });
          } catch (emailErr) {
            GasLogger.log('fixture.uc_a_clear', {
              assigneeEmail: ucaEmail,
              msg: 'email item append failed',
              err: emailErr.message
            });
          }
        }
        break;

      case 'uc_a_permutations':
        // Items (4 total; 3 produce rows, 1 is a negative case):
        //   1. Chip item WITH explicit "(Done)" status token
        //   2. Email item with NO status token (defaults to Open)
        //   3. Email with underscore username bob_jones@example.com (name → "Bob Jones")
        //   4. Plain-text list item with no chip and no email (no row expected)
        doc.saveAndClose();
        docAlreadyClosed = true;
        var permToken = ScriptApp.getOAuthToken();
        var permEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                     || Session.getActiveUser().getEmail();
        var permChipOk = false;
        try {
          _tfInsertPersonChipListItem(permToken, testDocId, permEmail,
                                      'Perm: Schedule the kickoff (Done)');
          permChipOk = true;
        } catch (permChipErr) {
          GasLogger.log('fixture.uc_a_permutations', {
            msg: 'chip insert failed',
            err: permChipErr.message
          });
        }
        if (permChipOk) {
          var permErrors = [];
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'AI: jane.smith@example.com Perm: Draft the committee agenda');
          } catch (e2) { permErrors.push('email-no-status: ' + e2.message); }
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'AI: bob_jones@example.com Perm: Review the meeting minutes');
          } catch (e3) { permErrors.push('underscore-email: ' + e3.message); }
          try {
            _tfAppendTextListItem(permToken, testDocId,
              'Perm: Write the project documentation');
          } catch (e4) { permErrors.push('plain-text: ' + e4.message); }
          if (permErrors.length > 0) {
            GasLogger.log('fixture.uc_a_permutations', { msg: 'permutation insert failed', err: permErrors.join('; ') });
          } else {
            GasLogger.log('fixture.uc_a_permutations', { itemsInserted: 4 });
          }
        }
        break;

      case 'uc_c_pending_sync_refresh': {
        var ucCPendingToken = ScriptApp.getOAuthToken();
        var ucCPendingEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                          || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCPendingToken, testDocId, ucCPendingEmail,
                                    'UCC-PENDING: Schedule the kickoff meeting (Open)');
        _tfAppendPersonChipListItem(ucCPendingToken, testDocId, ucCPendingEmail,
                                    'UCC-PENDING: Review the project charter (In Review)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        _tfAppendPersonChipListItem(ucCPendingToken, testDocId, ucCPendingEmail,
                                    'UCC-PENDING: Add the follow-up action (Open)');

        GasLogger.log('fixture.uc_c_pending_sync_refresh', { trackerRows: 2, pendingFloatingActions: 3 });
        break;
      }

      case 'uc1_new_floating':
      case 'default':
        // Legacy: AI-prefix floating action — sync assigns id=1.
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Fix the bug | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac1':
        // Legacy: new unnumbered floating action (old naming).
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Test action one | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac2':
        // Legacy: existing ID preserved.
        _tfInsertFloatingAction(
          body,
          'AI-5 @test@example.com | Test action five | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'ac3':
      case 'uc3_doc_wins':
        // Document wins: doc dateModified (2026-05-10) is 1 day newer than
        // the sheet row's dateModified (2026-05-09).
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | UCS-3DW: Fix the bug | Done | 2026-01-01 | 2026-05-10'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-3DW: Fix the bug',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-05-09')
        }));
        break;

      case 'ac4':
      case 'uc3_sheet_wins':
        // Sheet wins: sheet dateModified (2026-05-10) is 1 day newer than
        // the floating action's dateModified (2026-05-09).
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | UCS-3SW: Fix the bug | Open | 2026-01-01 | 2026-05-09'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-3SW: Fix the bug',
          status: 'In Review',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-05-10')
        }));
        break;

      case 'ac5':
      case 'uc_idempotent':
        // Already fully synced: consistent state in floating paragraph, table row,
        // and sheet row — all with the same values and dateModified. Sync is a no-op.
        _tfInsertFloatingAction(
          body,
          'AI-1 @test@example.com | UCSIDM: Completed action | Done | 2026-01-01 | 2026-04-01'
        );
        // Append table with matching data row.
        var tableAc5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableAc5, [
          '1',
          'test@example.com',
          '',
          'UCSIDM: Completed action',
          'Done',
          '2026-01-01',
          '2026-04-01'
        ]);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCSIDM: Completed action',
          status: 'Done',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-04-01')
        }));
        break;

      case 'uc2_new_table_row':
        // User-added data row in table, no ID, no dates — sync should assign id=2
        // (id=1 is pre-existing in the sheet, so next available is 2).
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-2: Fix the bug',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        var tableUc2 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc2, [
          '',
          'test@example.com',
          '',
          'UCS-2: Review the PR',
          '',
          '',
          ''
        ]);
        break;

      case 'uc4_archive':
        // Archive-eligible row (id=1, Closed, old dateModified, no floating action)
        // plus an active row (id=2, Open, table row present).
        var archiveDateUc4 = new Date(Date.now() - 35 * 24 * 60 * 60 * 1000);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-4: Fix the bug',
          status: 'Closed',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: archiveDateUc4
        }));
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 2,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-4: Review the PR',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        var tableUc4 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc4, [
          '2',
          'test@example.com',
          '',
          'UCS-4: Review the PR',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-2 @test@example.com | UCS-4: Review the PR | Open | 2026-01-01 | 2026-01-01'
        );
        break;

      case 'uc5_bare_reference':
        // Bare reference floating action (just ID, no other fields).
        var tableUc5 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc5, [
          '5',
          'test@example.com',
          '',
          'Deploy to staging',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(body, 'AI-5');
        break;

      case 'uc6_revert_local_edit':
        // Floating paragraph diverges from table row (different action and status),
        // same dateModified — table wins and floating action is reverted.
        var tableUc6 = _tfAppendEmptyTable(body);
        _tfAppendTableRow(tableUc6, [
          '3',
          'test@example.com',
          '',
          'UCS-6: Write tests',
          'Open',
          '2026-01-01',
          '2026-01-01'
        ]);
        _tfInsertFloatingAction(
          body,
          'AI-3 @test@example.com | UCS-6: Write tests (locally edited) | Done | 2026-01-01 | 2026-01-01'
        );
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 3,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'UCS-6: Write tests',
          status: 'Open',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        break;

      case 'archive':
        // Archive-eligible row: no floating action, sheet row Status=Closed,
        // Date Modified 35 days before today.
        var archiveDate = new Date(Date.now() - 35 * 24 * 60 * 60 * 1000);
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Archived action',
          status: 'Closed',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: archiveDate
        }));
        break;

      case 'no_section':
        // Doc body has no heading at all — normalizer must auto-create the section.
        body.clear();
        break;

      case 'no_table':
        // Doc has heading but no table — normalizer must auto-create the table.
        break;

      case 'onedit':
        // Row with a known Date Modified — onEdit on a mutable field (Assignee)
        // must stamp Date Modified with the current timestamp.
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Test action',
          status: 'Todo',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        break;

      case 'onedit_id':
        // Row with a known Date Modified — onEdit on the immutable ID column must
        // NOT update Date Modified.
        _tfAppendSheetRow(ss, _tfSheetRow({
          id: 1,
          assigneeEmail: 'test@example.com',
          assigneeName: '',
          action: 'Test action',
          status: 'Todo',
          docFormula: docFormula,
          dateCreated: new Date('2026-01-01'),
          dateModified: new Date('2026-01-01')
        }));
        break;

      case 'force_homepage_error':
        // gts-rvwu AC-5: trip buildHomepageCard's catch branch on the
        // next homepage render. Caller must clear via 'clear_homepage_error_force'.
        // This is a transient toggle (not a memoized cache) — it lives under the
        // '_TEST_' prefix so 'reset_test_state' sweeps it up if a test crashes
        // before reaching its own cleanup. See 'reset_test_state' below.
        PropertiesService.getScriptProperties().setProperty('_TEST_FORCE_HOMEPAGE_ERROR', 'true');
        break;

      case 'clear_homepage_error_force':
        PropertiesService.getScriptProperties().deleteProperty('_TEST_FORCE_HOMEPAGE_ERROR');
        break;

      case 'reset_test_state':
        // Safety net for interrupted test runs (gts-rvwu follow-up): deletes every
        // script property under the '_TEST_' prefix — transient per-test toggles
        // like '_TEST_FORCE_HOMEPAGE_ERROR' that a crashed test can leave set,
        // silently corrupting every later test that shares this GAS deployment.
        // Invoked as a pytest session-start autouse fixture (tests/conftest.py) and
        // available standalone via `call_webapp.py run_fixture reset_test_state`.
        //
        // Deliberately does NOT touch:
        //   - Durable deployment config (no '_' prefix): TEST_SHEET_ID,
        //     TEST_TOKEN, WEBAPP_URL, ADMIN_SECRET, AXIOM_TOKEN, DOC_FOLDER_ID,
        //     ... (no doc-ID property exists to list here — ADR-0006 §4)
        //   - Memoized fixture caches (DISCOVERY_*, TEAMSCOPE_FOLDER_*): these
        //     create-once Drive folders/docs are meant to persist across sessions —
        //     DISCOVERY_STALE_DOC_ID in particular only becomes useful once its doc
        //     is 8+ days old, so clearing it on every run would defeat the fixture.
        // Add new transient (crash-unsafe) toggles under '_TEST_' so this sweep
        // covers them automatically; add new cross-session caches under their own
        // distinct prefix so they're excluded by construction.
        var _rtsProps = PropertiesService.getScriptProperties();
        var _rtsAll = _rtsProps.getProperties();
        var _rtsCleared = [];
        for (var _rtsKey in _rtsAll) {
          if (_rtsKey.indexOf('_TEST_') === 0) {
            _rtsProps.deleteProperty(_rtsKey);
            _rtsCleared.push(_rtsKey);
          }
        }
        GasLogger.log('fixture.reset_test_state', { cleared: _rtsCleared });
        break;

      case 'discovery':
        // Memoized cross-session cache, not a transient toggle — deliberately
        // outside the '_TEST_' prefix so 'reset_test_state' never clears it.
        // DISCOVERY_STALE_DOC_ID only becomes useful once its doc is 8+ days
        // old, so wiping it every pytest session would defeat the fixture.
        var discProps = PropertiesService.getScriptProperties();
        var recentId = discProps.getProperty('DISCOVERY_RECENT_DOC_ID');
        var staleId  = discProps.getProperty('DISCOVERY_STALE_DOC_ID');
        if (!recentId) {
          var recentDoc = DocumentApp.create('GActionSheet Test - Discovery Recent');
          recentId = recentDoc.getId();
          recentDoc.saveAndClose();
          discProps.setProperty('DISCOVERY_RECENT_DOC_ID', recentId);
        }
        if (!staleId) {
          var staleDoc = DocumentApp.create('GActionSheet Test - Discovery Stale');
          staleId = staleDoc.getId();
          staleDoc.saveAndClose();
          discProps.setProperty('DISCOVERY_STALE_DOC_ID', staleId);
          GasLogger.log('fixture.warn', {
            msg: 'Discovery stale doc created now — it will not be stale for 8 days. ' +
                 'Run this scenario again after 8 days or set DISCOVERY_STALE_DOC_ID manually.',
            staleId: staleId
          });
        }
        GasLogger.log('fixture.discovery.ids', {
          recentId: recentId,
          staleId: staleId
        });
        break;

      case 'discovery_subfolder':
        var sfProps = PropertiesService.getScriptProperties();
        var subfolderId = sfProps.getProperty('DISCOVERY_SUBFOLDER_ID');
        var subfolderDocId = sfProps.getProperty('DISCOVERY_SUBFOLDER_DOC_ID');
        var parentFolderId = sfProps.getProperty('DOC_FOLDER_ID');
        if (!parentFolderId) {
          GasLogger.log('fixture.error', { msg: 'DOC_FOLDER_ID script property not set — run ensureSheetStructure first' });
          break;
        }
        if (!subfolderId) {
          var parentFolder = DriveApp.getFolderById(parentFolderId);
          var subFolder = parentFolder.createFolder('GActionSheet Test - Discovery Subfolder');
          subfolderId = subFolder.getId();
          sfProps.setProperty('DISCOVERY_SUBFOLDER_ID', subfolderId);
        }
        if (!subfolderDocId) {
          var sfFolder = DriveApp.getFolderById(subfolderId);
          var sfDoc = DocumentApp.create('GActionSheet Test - Discovery Subfolder Doc');
          DriveApp.getFileById(sfDoc.getId()).moveTo(sfFolder);
          subfolderDocId = sfDoc.getId();
          sfDoc.saveAndClose();
          sfProps.setProperty('DISCOVERY_SUBFOLDER_DOC_ID', subfolderDocId);
        }
        GasLogger.log('fixture.discovery.subfolder.id', { subfolderDocId: subfolderDocId });
        break;

      case 'uc_blank_status':
        // Floating action with blank status — sync must default to Open.
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Fix the bug |  | 2026-01-01 | 2026-01-01'
        );
        break;

      // -----------------------------------------------------------------------
      // UC-B scenarios: update an action from either side and converge.
      //
      // All three build a canonical 7-item doc (6 detected + 1 negative), run
      // an intermediate sync to anchor named ranges and seed the ActionSheet,
      // then apply mutations before returning.  The Python test triggers the
      // final convergence sync and asserts the outcome.
      //
      // Canonical floating action variants:
      //   Var 1: chip + "Review the budget report (Open)"         testAssigneeEmail
      //   Var 2: chip + "Draft the Q3 plan (In Review)"           testAssigneeEmail
      //   Var 3: chip + "Update the meeting notes"  (→ Open)      testAssigneeEmail
      //   Var 4: email + "Schedule the follow-up (Done)"          jane.smith@example.com
      //   Var 5: email + "Approve the budget proposal"  (→ Open)  jane.smith@example.com
      //   Var 6: email + "Review the Q2 report"  (→ Open)         bob_jones@example.com
      //   Var 7: plain text (negative) — never appears in ActionSheet
      //   Var 8: chip + "Prioritize the backlog items (Backlog)"  testAssigneeEmail  → status-other.png
      // -----------------------------------------------------------------------

      case 'uc_b_doc_wins':
      case 'uc_b_sheet_wins':
      case 'uc_b_sheet_assignee_wins':
      case 'uc_b_conflict': {
        // -- Phase 1: build canonical 7-item state ---------------------------
        var ucbPrefix = resolvedScenario === 'uc_b_doc_wins'   ? 'UCB-DW: '
                      : resolvedScenario === 'uc_b_sheet_wins' ? 'UCB-SW: '
                      : resolvedScenario === 'uc_b_sheet_assignee_wins' ? 'UCB-SA: '
                      : 'UCB-CF: ';

        doc.saveAndClose();
        docAlreadyClosed = true;

        var ucbToken = ScriptApp.getOAuthToken();
        var ucbEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                    || Session.getActiveUser().getEmail();

        // Var 1: chip + action text + (Open)
        _tfInsertPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Review the budget report (Open)');
        // Var 2: chip + action text + (In Review)
        _tfAppendPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Draft the Q3 plan (In Review)');
        // Var 3: chip + action text only (no status → Open)
        _tfAppendPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Update the meeting notes');
        // Var 4: email + action text + (Done)
        _tfAppendTextListItem(ucbToken, testDocId,
                              'jane.smith@example.com ' + ucbPrefix + 'Schedule the follow-up (Done)');
        // Var 5: email + action text only (no status → Open)
        _tfAppendTextListItem(ucbToken, testDocId,
                              'jane.smith@example.com ' + ucbPrefix + 'Approve the budget proposal');
        // Var 6: underscore email + action text (no status → Open)
        _tfAppendTextListItem(ucbToken, testDocId,
                              'bob_jones@example.com ' + ucbPrefix + 'Review the Q2 report');
        // Var 8: chip + action text + non-standard status → exercises status-other.png fallback
        _tfAppendPersonChipListItem(ucbToken, testDocId, ucbEmail,
                                    ucbPrefix + 'Prioritize the backlog items (Backlog)');
        // Var 7: plain text (negative — no chip, no email)
        _tfAppendTextListItem(ucbToken, testDocId,
                              ucbPrefix + 'Complete the project documentation');

        // -- Phase 2: intermediate sync to anchor named ranges + seed sheet --
        syncDocument(testDocId);

        // -- Phase 3: apply scenario-specific mutations -----------------------
        if (resolvedScenario === 'uc_b_doc_wins') {
          // Mutate variants 1-3 on the doc side (chip text children).
          // The final sync should propagate these to the ActionSheet.
          var ucbDocMut = DocumentApp.openById(testDocId);
          var ucbBody   = ucbDocMut.getBody();
          var ucbN      = ucbBody.getNumChildren();
          for (var ucbI = 0; ucbI < ucbN; ucbI++) {
            var ucbChild = ucbBody.getChild(ucbI);
            if (ucbChild.getType() !== DocumentApp.ElementType.LIST_ITEM) continue;
            var ucbItem = ucbChild.asListItem();
            if (ucbItem.getNumChildren() === 0) continue;
            if (ucbItem.getChild(0).getType() !== DocumentApp.ElementType.PERSON) continue;
            if ((ucbItem.getChild(0).asPerson().getEmail() || '') !== ucbEmail) continue;
            // Find the TEXT child that carries the action text + status
            for (var ucbJ = 1; ucbJ < ucbItem.getNumChildren(); ucbJ++) {
              if (ucbItem.getChild(ucbJ).getType() !== DocumentApp.ElementType.TEXT) continue;
              var ucbTextEl = ucbItem.getChild(ucbJ).asText();
              var ucbTxt    = ucbTextEl.getText();
              if (ucbTxt.indexOf(ucbPrefix + 'Review the budget report') !== -1) {
                // Var 1: (Open) → (Done)
                ucbTextEl.setText(ucbTxt.replace('(Open)', '(Done)'));
              } else if (ucbTxt.indexOf(ucbPrefix + 'Draft the Q3 plan') !== -1) {
                // Var 2: change action text (preserve status token)
                ucbTextEl.setText(ucbTxt.replace(ucbPrefix + 'Draft the Q3 plan', ucbPrefix + 'Draft the revised Q3 plan'));
              } else if (ucbTxt.indexOf(ucbPrefix + 'Update the meeting notes') !== -1) {
                // Var 3: set (In Progress) status; strip any existing token first
                // (the intermediate sync may have normalized this item to (Open))
                var ucbBase3 = ucbTxt.trim().replace(/\s*\([^)]*\)\s*$/, '');
                ucbTextEl.setText(ucbBase3 + ' (In Progress)');
              }
              break;
            }
          }
          ucbDocMut.saveAndClose();
          GasLogger.log('fixture.uc_b_doc_wins', { mutationsApplied: 3, assigneeEmail: ucbEmail });

        } else if (resolvedScenario === 'uc_b_sheet_wins') {
          // Mutate variants 4-6 on the sheet side.
          // The final sync should propagate these to the doc floating actions.
          var ucbSheet  = ss.getSheetByName('Actions');
          var ucbLastR  = ucbSheet ? ucbSheet.getLastRow() : 1;
          if (ucbSheet && ucbLastR > 1) {
            var ucbData    = ucbSheet.getRange(2, 1, ucbLastR - 1, SHEET_HEADERS.length).getValues();
            // Filter by testDocId (Document column formula) to avoid matching rows from prior
            // test sessions that accumulated in the sheet (accumulate-without-reset design).
            var ucbDocFmls = ucbSheet.getRange(2, _SF.document_formula, ucbLastR - 1, 1).getFormulas();
            for (var ucbRi = 0; ucbRi < ucbData.length; ucbRi++) {
              if (ucbDocFmls[ucbRi][0].indexOf(testDocId) === -1) continue;
              var ucbAssignee = ucbData[ucbRi][_SF.assignee_email - 1];
              var ucbAction   = ucbData[ucbRi][_SF.action_text - 1];
              if (ucbAssignee === 'jane.smith@example.com') {
                if (ucbAction.indexOf(ucbPrefix + 'Schedule the follow-up') !== -1) {
                  // Var 4: Status Done → Closed; set Dirty so sheet wins conflict resolution.
                  var ucbRow4 = ucbRi + 2;
                  WriteGuard.wrap(function () {
                    ucbSheet.getRange(ucbRow4, 7).setValue('Closed');
                    ucbSheet.getRange(ucbRow4, 10).setValue(new Date());
                    ucbSheet.getRange(ucbRow4, 11).setValue('Dirty');
                  });
                } else if (ucbAction.indexOf(ucbPrefix + 'Approve the budget proposal') !== -1) {
                  // Var 5: Action text change; set Dirty so sheet wins conflict resolution.
                  var ucbRow5 = ucbRi + 2;
                  WriteGuard.wrap(function () {
                    ucbSheet.getRange(ucbRow5, 6).setValue(ucbPrefix + 'Approve the revised budget');
                    ucbSheet.getRange(ucbRow5, 10).setValue(new Date());
                    ucbSheet.getRange(ucbRow5, 11).setValue('Dirty');
                  });
                }
              } else if (ucbAssignee === 'bob_jones@example.com' &&
                         ucbAction.indexOf(ucbPrefix + 'Review the Q2 report') !== -1) {
                // Var 6: Status Open → In Review; set Dirty so sheet wins conflict resolution.
                var ucbRow6 = ucbRi + 2;
                WriteGuard.wrap(function () {
                  ucbSheet.getRange(ucbRow6, 7).setValue('In Review');
                  ucbSheet.getRange(ucbRow6, 10).setValue(new Date());
                  ucbSheet.getRange(ucbRow6, 11).setValue('Dirty');
                });
              }
            }
          }
          GasLogger.log('fixture.uc_b_sheet_wins', { mutationsApplied: 3 });

        } else if (resolvedScenario === 'uc_b_sheet_assignee_wins') {
          // Mutate variant 6 assignee on the sheet side only.
          // The final sync should propagate the assignee change to the doc.
          var ucbASheet = ss.getSheetByName('Actions');
          var ucbALastR = ucbASheet ? ucbASheet.getLastRow() : 1;
          if (ucbASheet && ucbALastR > 1) {
            var ucbAData    = ucbASheet.getRange(2, 1, ucbALastR - 1, SHEET_HEADERS.length).getValues();
            var ucbADocFmls = ucbASheet.getRange(2, _SF.document_formula, ucbALastR - 1, 1).getFormulas();
            for (var ucbARi = 0; ucbARi < ucbAData.length; ucbARi++) {
              if (ucbADocFmls[ucbARi][0].indexOf(testDocId) === -1) continue;
              var ucbAAssignee = ucbAData[ucbARi][_SF.assignee_email - 1];
              var ucbAAction   = ucbAData[ucbARi][_SF.action_text - 1];
              if (ucbAAssignee === 'bob_jones@example.com' &&
                  ucbAAction.indexOf(ucbPrefix + 'Review the Q2 report') !== -1) {
                var ucbARow = ucbARi + 2;
                WriteGuard.wrap(function () {
                  ucbASheet.getRange(ucbARow, 4).setValue('jane.smith@example.com');
                  ucbASheet.getRange(ucbARow, 5).setValue('Jane Smith');
                  ucbASheet.getRange(ucbARow, 10).setValue(new Date());
                  ucbASheet.getRange(ucbARow, 11).setValue('Dirty');
                });
                break;
              }
            }
          }
          GasLogger.log('fixture.uc_b_sheet_assignee_wins', { mutationsApplied: 1 });

        } else {
          // uc_b_conflict: one action where the doc is the newer edit (var 1),
          // one where the sheet is the newer edit (var 4).
          var ucbCSheet = ss.getSheetByName('Actions');
          var ucbCLastR = ucbCSheet ? ucbCSheet.getLastRow() : 1;
          if (ucbCSheet && ucbCLastR > 1) {
            var ucbCData    = ucbCSheet.getRange(2, 1, ucbCLastR - 1, SHEET_HEADERS.length).getValues();
            // Filter by testDocId to avoid matching rows from prior sessions in the shared sheet.
            var ucbCDocFmls = ucbCSheet.getRange(2, _SF.document_formula, ucbCLastR - 1, 1).getFormulas();
            for (var ucbCRi = 0; ucbCRi < ucbCData.length; ucbCRi++) {
              if (ucbCDocFmls[ucbCRi][0].indexOf(testDocId) === -1) continue;
              var ucbCAssignee = ucbCData[ucbCRi][_SF.assignee_email - 1];
              var ucbCAction   = ucbCData[ucbCRi][_SF.action_text - 1];
              if (ucbCAssignee === ucbEmail &&
                  ucbCAction.indexOf(ucbPrefix + 'Review the budget report') !== -1) {
                // Stale sheet Date Modified far in the past so the doc edit wins.
                var ucbCRowA = ucbCRi + 2;
                WriteGuard.wrap(function () {
                  ucbCSheet.getRange(ucbCRowA, 10).setValue(new Date('2020-01-01'));
                });
              }
            }
          }
          // Mutate var 1 on doc side (doc is now "newer" per Date Modified)
          var ucbCDoc  = DocumentApp.openById(testDocId);
          var ucbCBody = ucbCDoc.getBody();
          var ucbCN    = ucbCBody.getNumChildren();
          for (var ucbCI = 0; ucbCI < ucbCN; ucbCI++) {
            var ucbCChild = ucbCBody.getChild(ucbCI);
            if (ucbCChild.getType() !== DocumentApp.ElementType.LIST_ITEM) continue;
            var ucbCItem = ucbCChild.asListItem();
            if (ucbCItem.getNumChildren() === 0) continue;
            if (ucbCItem.getChild(0).getType() !== DocumentApp.ElementType.PERSON) continue;
            if ((ucbCItem.getChild(0).asPerson().getEmail() || '') !== ucbEmail) continue;
            for (var ucbCJ = 1; ucbCJ < ucbCItem.getNumChildren(); ucbCJ++) {
              if (ucbCItem.getChild(ucbCJ).getType() !== DocumentApp.ElementType.TEXT) continue;
              var ucbCTxtEl = ucbCItem.getChild(ucbCJ).asText();
              var ucbCTxt   = ucbCTxtEl.getText();
              if (ucbCTxt.indexOf(ucbPrefix + 'Review the budget report') !== -1) {
                ucbCTxtEl.setText(ucbCTxt.replace('(Open)', '(In Progress)'));
                break;
              }
              break;
            }
          }
          ucbCDoc.saveAndClose();
          // Mutate var 4 on sheet side — set Dirty so sheet wins conflict resolution.
          if (ucbCSheet && ucbCLastR > 1) {
            var ucbCData2 = ucbCSheet.getRange(2, 1, ucbCLastR - 1, SHEET_HEADERS.length).getValues();
            for (var ucbCRi2 = 0; ucbCRi2 < ucbCData2.length; ucbCRi2++) {
              if (ucbCDocFmls[ucbCRi2][0].indexOf(testDocId) === -1) continue;
              if (ucbCData2[ucbCRi2][_SF.assignee_email - 1] === 'jane.smith@example.com' &&
                  ucbCData2[ucbCRi2][_SF.action_text - 1].indexOf(ucbPrefix + 'Schedule the follow-up') !== -1) {
                var ucbCRowB = ucbCRi2 + 2;
                WriteGuard.wrap(function () {
                  ucbCSheet.getRange(ucbCRowB, 7).setValue('Closed');
                  ucbCSheet.getRange(ucbCRowB, 10).setValue(new Date());
                  ucbCSheet.getRange(ucbCRowB, 11).setValue('Dirty');
                });
                break;
              }
            }
          }
          GasLogger.log('fixture.uc_b_conflict', { conflictSetupDone: true });
        }
        break;
      }

      // -----------------------------------------------------------------------
      // UC-C scenarios: insert / refresh the in-doc tracker table (gts-mol-bgq)
      //
      // All three scenarios accumulate on the shared clone doc without resetting.
      // Scenario prefixes: UCC-FIRST: / UCC-REFRESH: / UCC-VIEWONLY:
      //
      // RED PHASE: insertTrackerTable() is defined by the UC-C implementation
      // (gts-mol-vzk). Until that lands these scenarios will log an error
      // tag and the Python tests will fail as expected.
      // -----------------------------------------------------------------------

      case 'uc_c_first_insert': {
        // Insert two chip-led floating actions, sync to anchor them, then call
        // insertTrackerTable for the first time. Logs fixture.uc_c_first_insert.
        var ucCFIToken = ScriptApp.getOAuthToken();
        var ucCFIEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCFIToken, testDocId, ucCFIEmail,
                                    'UCC-FIRST: Schedule the kickoff meeting (Open)');
        _tfAppendPersonChipListItem(ucCFIToken, testDocId, ucCFIEmail,
                                    'UCC-FIRST: Review the project charter (In Review)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_first_insert', { rowsInserted: 2 });
        break;
      }

      case 'uc_c_refresh': {
        // Insert two chip-led FAs, sync+insert tracker, then simulate close+add:
        //   close: set first UCC-REFRESH: row Status=Closed in sheet
        //   add: append a new chip-led FA
        // Final sync+refresh should reflect both changes.
        var ucCRefToken = ScriptApp.getOAuthToken();
        var ucCRefEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                       || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCRefToken, testDocId, ucCRefEmail,
                                    'UCC-REFRESH: Approve the proposal (Open)');
        _tfAppendPersonChipListItem(ucCRefToken, testDocId, ucCRefEmail,
                                    'UCC-REFRESH: Update the risk register (Done)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        // Close the first UCC-REFRESH: row in the sheet.
        var ucCRefActSheet = ss.getSheetByName('Actions');
        var ucCRefLastR    = ucCRefActSheet ? ucCRefActSheet.getLastRow() : 1;
        if (ucCRefActSheet && ucCRefLastR > 1) {
          var ucCRefData = ucCRefActSheet.getRange(2, 1, ucCRefLastR - 1, _SF.action_text).getValues();
          var ucCRefFmls = ucCRefActSheet.getRange(2, _SF.document_formula, ucCRefLastR - 1, 1).getFormulas();
          for (var ucCRefI = 0; ucCRefI < ucCRefData.length; ucCRefI++) {
            if (ucCRefFmls[ucCRefI][0].indexOf(testDocId) !== -1 &&
                (ucCRefData[ucCRefI][_SF.action_text - 1] || '').indexOf('UCC-REFRESH: Approve') !== -1) {
              var ucCRefRowNum = ucCRefI + 2;
              WriteGuard.wrap(function () {
                ucCRefActSheet.getRange(ucCRefRowNum, 7).setValue('Closed');
                ucCRefActSheet.getRange(ucCRefRowNum, 10).setValue(new Date());
              });
              break;
            }
          }
        }

        // Add a new chip-led FA.
        _tfAppendPersonChipListItem(ucCRefToken, testDocId, ucCRefEmail,
                                    'UCC-REFRESH: Draft the status report');

        // Sync to propagate the Closed status to the doc and anchor the new FA.
        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_refresh', { refreshDone: true });
        break;
      }

      case 'uc_c_view_only': {
        // Insert two chip-led FAs, sync+insert tracker, then directly edit a tracker
        // table cell (simulating a forbidden user edit). A second insertTrackerTable
        // call should discard the edit and render the correct values.
        var ucCVOToken = ScriptApp.getOAuthToken();
        var ucCVOEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCVOToken, testDocId, ucCVOEmail,
                                    'UCC-VIEWONLY: Prepare the budget summary (Open)');
        _tfAppendPersonChipListItem(ucCVOToken, testDocId, ucCVOEmail,
                                    'UCC-VIEWONLY: Finalize the agenda (Open)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        // Directly edit the first data cell of the tracker table to dirty it.
        var ucCVODoc  = DocumentApp.openById(testDocId);
        var ucCVOBody = ucCVODoc.getBody();
        var ucCVOHdg  = false;
        var ucCVOTbl  = null;
        var ucCVON    = ucCVOBody.getNumChildren();
        for (var ucCVOI = 0; ucCVOI < ucCVON; ucCVOI++) {
          var ucCVOChild = ucCVOBody.getChild(ucCVOI);
          if (!ucCVOHdg) {
            if ((ucCVOChild.getType() === DocumentApp.ElementType.PARAGRAPH ||
                 ucCVOChild.getType() === DocumentApp.ElementType.LIST_ITEM) &&
                (ucCVOChild.getText().trim() === 'Action Item Summary' ||
                 ucCVOChild.getText().trim() === '=== Tracked Actions ===')) {
              ucCVOHdg = true;
            }
          } else if (ucCVOChild.getType() === DocumentApp.ElementType.TABLE) {
            ucCVOTbl = ucCVOChild.asTable();
            break;
          }
        }
        if (ucCVOTbl && ucCVOTbl.getNumRows() > 1) {
          ucCVOTbl.getRow(1).getCell(0).setText(
            ucCVOTbl.getRow(1).getCell(0).getText() + '-EDITED'
          );
        }
        ucCVODoc.saveAndClose();

        // Refresh — should overwrite the direct edit with the correct values.
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_view_only', { viewOnlyTestDone: true });
        break;
      }

      case 'uc_c_idempotent_refresh': {
        // Insert two chip-led FAs, sync+insert tracker, then call insertTrackerTable
        // again with NO intervening changes. The second call must be a no-op
        // (tracker.skip — gts-yo9q): same {id, action, status} rows as
        // the first call.
        var ucCIRToken = ScriptApp.getOAuthToken();
        var ucCIREmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ucCIRToken, testDocId, ucCIREmail,
                                    'UCC-IDEMPOTENT: Confirm the venue booking (Open)');
        _tfAppendPersonChipListItem(ucCIRToken, testDocId, ucCIREmail,
                                    'UCC-IDEMPOTENT: Send the agenda (In Review)');

        syncDocument(testDocId);
        insertTrackerTable(testDocId);

        // No changes since the first call — must skip the rewrite.
        insertTrackerTable(testDocId);

        GasLogger.log('fixture.uc_c_idempotent_refresh', { idempotentRefreshDone: true });
        break;
      }

      // -----------------------------------------------------------------------
      // Sync Status column scenarios (gts-ly5 AC1–AC7)
      //
      // Each scenario accumulates on the shared clone doc without resetting.
      // Scenario prefixes: SS-DEL: / SS-NF: / SS-REC: / SS-EDIT: / SS-ARCH:
      // -----------------------------------------------------------------------

      case 'sync_status_migration': {
        // Simulate a legacy sheet missing the Sync Status column by deleting col 10
        // (if present), then call ensureSheetStructure() to trigger migration.
        var ssMigSheet = ss.getSheetByName('Actions');
        if (ssMigSheet && ssMigSheet.getMaxColumns() >= 10) {
          WriteGuard.wrap(function () {
            ssMigSheet.deleteColumn(10);
          });
        }
        ensureSheetStructure();
        GasLogger.log('fixture.sync_status_migration', { migrationTriggered: true });
        break;
      }

      case 'sync_status_deleted': {
        // Insert a chip-led floating action (SS-DEL: prefix), run an intermediate
        // sync to anchor it, then DELETE THE ENTIRE PARAGRAPH from the doc so the
        // final sync writes 'Deleted' to Sync Status.
        //
        // Deleting only the named range (not the paragraph) causes re-anchoring on
        // the next sync, which the duplicate detector treats as a stale duplicate
        // and removes — never writing 'Deleted'.  Removing the paragraph entirely
        // means no floating action survives to match, so the orphan path fires cleanly.
        var ssDelToken = ScriptApp.getOAuthToken();
        var ssDelEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssDelToken, testDocId, ssDelEmail,
                                    'SS-DEL: Review the access log');

        syncDocument(testDocId);

        // After the first sync, read the NR ID for the SS-DEL row from the sheet.
        // GAS does NOT auto-remove named ranges when their paragraph is deleted, so
        // the NR would appear in allDocGlobalIds during the second syncDocument,
        // causing the orphan-detection loop to skip the row (activeNrIdSet check).
        // We must explicitly remove the NR from the doc after paragraph deletion.
        var ssDelSheet   = ss.getSheetByName('Actions');
        var ssDelLastRow = ssDelSheet ? ssDelSheet.getLastRow() : 1;
        var ssDelNRId    = null;
        if (ssDelSheet && ssDelLastRow > 1) {
          var ssDelSheetData = ssDelSheet.getRange(2, 1, ssDelLastRow - 1, _SF.action_text).getValues();
          var ssDelSheetFmls = ssDelSheet.getRange(2, _SF.document_formula, ssDelLastRow - 1, 1).getFormulas();
          for (var sdi = 0; sdi < ssDelSheetData.length; sdi++) {
            if (ssDelSheetFmls[sdi][0].indexOf(testDocId) !== -1 &&
                (ssDelSheetData[sdi][_SF.action_text - 1] || '').indexOf('SS-DEL:') !== -1) {
              ssDelNRId = ssDelSheetData[sdi][0]; // col 1 = globalId
              break;
            }
          }
        }

        // Remove the SS-DEL: list-item paragraph from the doc body.
        // Append a blank paragraph first — GAS throws if you try to remove
        // the last element in a document section.
        var ssDelDoc  = DocumentApp.openById(testDocId);
        var ssDelBody = ssDelDoc.getBody();
        ssDelBody.appendParagraph(''); // guard against last-element removal error
        var ssDelN    = ssDelBody.getNumChildren();
        for (var ssDelCI = ssDelN - 1; ssDelCI >= 0; ssDelCI--) {
          var ssDelChild = ssDelBody.getChild(ssDelCI);
          if (ssDelChild.getType() !== DocumentApp.ElementType.LIST_ITEM) continue;
          if (ssDelChild.asListItem().getText().indexOf('SS-DEL:') === -1) continue;
          ssDelBody.removeChild(ssDelChild);
          break;
        }

        // Explicitly remove the named range — GAS doesn't auto-delete it on paragraph removal.
        if (ssDelNRId) {
          var ssDelDocNRs = ssDelDoc.getNamedRanges();
          for (var ssDelNRI = 0; ssDelNRI < ssDelDocNRs.length; ssDelNRI++) {
            if (ssDelDocNRs[ssDelNRI].getId() === ssDelNRId) {
              ssDelDocNRs[ssDelNRI].remove();
              break;
            }
          }
        }

        ssDelDoc.saveAndClose();

        syncDocument(testDocId);

        GasLogger.log('fixture.sync_status_deleted', { scenario: 'paragraph-deleted' });
        break;
      }

      case 'sync_status_doc_not_found': {
        // Append a row referencing a non-existent doc ID, then call syncDocument
        // with that fake ID — SyncManager should catch openById failure and write
        // 'Doc Not Found' to every row in the sheet referencing this fake doc.
        var ssNFDocId   = '1_FAKEID_SYNCSTATUS_DOCNOTFOUND_FIXTURE_001';
        var ssNFFormula = '=HYPERLINK("https://docs.google.com/document/d/' +
                          ssNFDocId + '/edit","SS-NF: Fake Doc")';
        WriteGuard.wrap(function () {
          var ssNFSheet = ss.getSheetByName('Actions');
          if (ssNFSheet) {
            ssNFSheet.appendRow([
              'SS-NF-ANCHOR-FAKE-001',
              'SS-NF-ANCHOR-FAKE-001',  // fileId == globalId prefix (fake, no /AI-)
              999,
              'test@example.com',
              '',
              'SS-NF: Review the compliance doc',
              'Open',
              ssNFFormula,
              new Date('2026-01-01'),
              new Date('2026-01-01'),
              ''
            ]);
          }
        });

        try {
          syncDocument(ssNFDocId);
        } catch (ssNFErr) {
          GasLogger.log('fixture.sync_status_doc_not_found.warn', { msg: ssNFErr.message });
        }

        GasLogger.log('fixture.sync_status_doc_not_found', { fakeDocId: ssNFDocId });
        break;
      }

      case 'sync_status_recovery': {
        // Insert a chip-led floating action (SS-REC: prefix), anchor it via sync,
        // then manually set Sync Status = 'Deleted' to simulate a previously-flagged
        // state.  A final sync finds the named range still present and clears the flag.
        var ssRecToken = ScriptApp.getOAuthToken();
        var ssRecEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                      || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssRecToken, testDocId, ssRecEmail,
                                    'SS-REC: Update the access policy');

        syncDocument(testDocId);

        var ssRecSheet = ss.getSheetByName('Actions');
        var ssRecLastR = ssRecSheet ? ssRecSheet.getLastRow() : 1;
        if (ssRecSheet && ssRecLastR > 1) {
          var ssRecData = ssRecSheet.getRange(2, 1, ssRecLastR - 1, _SF.action_text).getValues();
          var ssRecFmls = ssRecSheet.getRange(2, _SF.document_formula, ssRecLastR - 1, 1).getFormulas();
          for (var ssRecI = 0; ssRecI < ssRecData.length; ssRecI++) {
            if (ssRecFmls[ssRecI][0].indexOf(testDocId) !== -1 &&
                (ssRecData[ssRecI][_SF.action_text - 1] || '').indexOf('SS-REC:') !== -1) {
              var ssRecRowNum = ssRecI + 2;
              WriteGuard.wrap(function () {
                ssRecSheet.getRange(ssRecRowNum, 11).setValue('Deleted');
              });
              break;
            }
          }
        }

        syncDocument(testDocId);

        GasLogger.log('fixture.sync_status_recovery', { setupDone: true });
        break;
      }

      case 'sync_status_on_edit': {
        // Insert a chip-led floating action (SS-EDIT: prefix), sync to stamp a
        // real Date Modified, then call onEdit() with a synthetic col-11 event to
        // verify that editing Sync Status does NOT update Date Modified.
        // Logs sentinelDateModified so the Python test can assert no change.
        var ssEditToken = ScriptApp.getOAuthToken();
        var ssEditEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                       || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssEditToken, testDocId, ssEditEmail,
                                    'SS-EDIT: Approve the request');

        syncDocument(testDocId);

        var ssEditSheet    = ss.getSheetByName('Actions');
        var ssEditLastR    = ssEditSheet ? ssEditSheet.getLastRow() : 1;
        var ssEditSentinel = null;
        var ssEditRowNum   = -1;
        if (ssEditSheet && ssEditLastR > 1) {
          var ssEditData = ssEditSheet.getRange(2, 1, ssEditLastR - 1, 11).getValues();
          var ssEditFmls = ssEditSheet.getRange(2, 8, ssEditLastR - 1, 1).getFormulas();
          for (var ssEditI = 0; ssEditI < ssEditData.length; ssEditI++) {
            if (ssEditFmls[ssEditI][0].indexOf(testDocId) !== -1 &&
                (ssEditData[ssEditI][5] || '').indexOf('SS-EDIT:') !== -1) {
              ssEditSentinel = ssEditData[ssEditI][9]; // col 10 (0-indexed: 9) = Date Modified
              ssEditRowNum   = ssEditI + 2;
              break;
            }
          }
        }

        if (ssEditRowNum > 0 && ssEditSheet) {
          var ssEditFakeEvent = { range: ssEditSheet.getRange(ssEditRowNum, 11) };
          onActionSheetEdit(ssEditFakeEvent);
        }

        _TF_RESULT = {
          tag:  'fixture.sync_status_on_edit',
          data: { sentinelDateModified: ssEditSentinel }
        };
        GasLogger.log('fixture.sync_status_on_edit', { sentinelDateModified: ssEditSentinel });
        break;
      }

      case 'sync_status_archive': {
        // Insert a chip-led floating action (SS-ARCH: prefix), anchor it via sync,
        // then mark it Closed with a 35-day-old Date Modified and Sync Status='Deleted'
        // so the archive sweep moves it from Actions to Archive sheet.
        var ssArchToken = ScriptApp.getOAuthToken();
        var ssArchEmail = props.getProperty('TEST_ASSIGNEE_EMAIL')
                       || Session.getActiveUser().getEmail();

        doc.saveAndClose();
        docAlreadyClosed = true;

        _tfInsertPersonChipListItem(ssArchToken, testDocId, ssArchEmail,
                                    'SS-ARCH: Archive the policy doc');

        syncDocument(testDocId);
        SpreadsheetApp.flush(); // ensure syncDocument's appended row is visible to ss

        var ssArchSheet   = ss.getSheetByName('Actions');
        var ssArchLastR   = ssArchSheet ? ssArchSheet.getLastRow() : 1;
        var ssArchOldDate = new Date(Date.now() - 35 * 24 * 60 * 60 * 1000);
        if (ssArchSheet && ssArchLastR > 1) {
          var ssArchData = ssArchSheet.getRange(2, 1, ssArchLastR - 1, _SF.action_text).getValues();
          var ssArchFmls = ssArchSheet.getRange(2, _SF.document_formula, ssArchLastR - 1, 1).getFormulas();
          for (var ssArchI = 0; ssArchI < ssArchData.length; ssArchI++) {
            if (ssArchFmls[ssArchI][0].indexOf(testDocId) !== -1 &&
                (ssArchData[ssArchI][_SF.action_text - 1] || '').indexOf('SS-ARCH:') !== -1) {
              var ssArchRowNum = ssArchI + 2;
              WriteGuard.wrap(function () {
                ssArchSheet.getRange(ssArchRowNum, 7).setValue('Closed');
                ssArchSheet.getRange(ssArchRowNum, 10).setValue(ssArchOldDate);
                ssArchSheet.getRange(ssArchRowNum, 11).setValue('Deleted');
              });
              break;
            }
          }
        }

        ArchiveManager.archive(ss);

        GasLogger.log('fixture.sync_status_archive', { archiveTriggered: true });
        break;
      }

      case 'sync_document': {
        // Sync the clone doc. Called between fixture steps in the HTTP test runner.
        // testDocId arrives as a real parameter (data.docId) from _handleRunFixture.
        //
        // scn.session.ScenarioSession.sync()'s own docstring promises "durable
        // convergence" for a preceding async act (e.g. the sidebar's Sync Now
        // button, whose click fires a separate syncDocument() execution).
        // syncDocument() intentionally no-ops (sync.locked.skip) rather than
        // proceed against a stale pre-lock read when it loses that race for
        // the per-doc lock -- honor the convergence promise here by retrying
        // (bounded) instead of reporting synced:true on what was actually a
        // no-op (gts-kkm7 sidebar_bootstrap_sync race, reproduced 2026-08-14:
        // sidebar_sync's async trigger held the lock, this call skipped, and
        // the immediately-following find_sheet_actions() read count=0).
        // Bound: 12 attempts * 3s = <=36s of extra wait -- comfortably above
        // the ~14s single-doc syncDocument() hold observed live (gts-kkm7
        // reproduction above), same order of magnitude as sidebar_sync's own
        // 60s cold-sync budget (scn/ui.py).
        var sdMaxAttempts = 12;
        var sdAttempts = 0;
        var sdResult;
        do {
          sdResult = syncDocument(testDocId);
          sdAttempts++;
          if (sdResult === 'locked-skip' && sdAttempts < sdMaxAttempts) {
            Utilities.sleep(3000);
          }
        } while (sdResult === 'locked-skip' && sdAttempts < sdMaxAttempts);
        if (sdResult === 'locked-skip') {
          GasLogger.log('fixture.sync_document.still_locked', { docId: testDocId, attempts: sdAttempts });
        }
        _TF_RESULT = { tag: 'fixture.sync_document', data: { synced: sdResult !== 'locked-skip', docId: testDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_lock_race': {
        // gts-li3g: deterministically proves syncDocument()'s per-docId lock
        // serializes two overlapping executions for the SAME docId, per the
        // AC's "or proves the lock serializes two overlapping syncDocument
        // calls for the same docId" alternative — genuine cross-execution
        // OS-level concurrency cannot be reliably timed from a Python test
        // harness (network jitter dwarfs GAS's own scheduling).
        //
        // Simulates a first, still in-flight execution (e.g. the 30-min
        // trigger) holding the per-doc lock, then drives the REAL
        // syncDocument() entry point a second time (e.g. sidebar Sync Now,
        // or another trigger firing mid-sync) while that lock is held. The
        // second call must skip outright — not read/reconcile/flush
        // anything — so a sheet row already marked Dirty by a concurrent
        // write is left completely untouched rather than being read against
        // a stale pre-lock snapshot and reverted.
        var raceLockAcquired = _acquireDocSyncLock(testDocId);
        try {
          syncDocument(testDocId); // the "second" overlapping execution
        } finally {
          if (raceLockAcquired) _releaseDocSyncLock(testDocId);
        }
        _TF_RESULT = {
          tag: 'fixture.sync_lock_race',
          data: { lockHeldByFirst: raceLockAcquired, docId: testDocId }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'begin_journey_session': {
        // Empty-create a fresh journey doc (§16.11 #1 — never a template clone).
        // Does NOT touch TestControl!B1 — safe to run
        // alongside an active begin_test_session clone in the same pytest session.
        var bjsNow    = new Date();
        var bjsDate   = Utilities.formatDate(bjsNow, Session.getScriptTimeZone(), 'yyyyMMdd');
        var bjsHex    = ('000' + Math.floor(Math.random() * 0xFFFF).toString(16)).slice(-4);
        var bjsName   = 'GActionSheet-Test-journey-' + bjsDate + '-' + bjsHex;
        var bjsSheetId = PropertiesService.getScriptProperties().getProperty('TEST_SHEET_ID');
        var bjsFolderIter = DriveApp.getFileById(bjsSheetId).getParents();
        var bjsParent = bjsFolderIter.hasNext() ? bjsFolderIter.next() : DriveApp.getRootFolder();
        var bjsDoc    = DocumentApp.create(bjsName);
        DriveApp.getFileById(bjsDoc.getId()).moveTo(bjsParent);
        _TF_RESULT = {
          tag:  'fixture.begin_journey_session',
          data: { ok: true, docId: bjsDoc.getId(), docName: bjsName, docUrl: bjsDoc.getUrl() }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'end_journey_session': {
        // Trash the journey clone identified by testDocId.
        DriveApp.getFileById(testDocId).setTrashed(true);
        _TF_RESULT = { tag: 'fixture.end_journey_session', data: { trashed: testDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'scenario_journey_seed': {
        // Insert the four §14 AI-token seed items into the journey doc.
        doc.saveAndClose();
        docAlreadyClosed = true;
        var sjsToken = ScriptApp.getOAuthToken();
        _tfAppendTextListItem(sjsToken, testDocId,
          'AI: This tag and text confirms creation of an unassigned action item');
        _tfAppendTextListItem(sjsToken, testDocId,
          'AI: aitest@example.com This tag and email address along with this text confirms the creation of an action item with an assignee.');
        _tfAppendTextListItem(sjsToken, testDocId,
          'AI-5: This tag and text confirms creation of an action item with id AI-5 pre-assigning the specific ID.');
        _tfAppendAINPersonChipListItem(sjsToken, testDocId,
          'AI-9:', 'minister@northlakeuu.org',
          'This tag, email and text should result in the creation of the assignee as a person chip,' +
          ' working within our Northlake domain this has a username of \'Northlake Minister\'' +
          ' which should appear in the chip.');
        _TF_RESULT = { tag: 'fixture.scenario_journey_seed', data: { itemsSeeded: 4 } };
        break;
      }

      case 'insert_tracker_table': {
        // Standalone tracker table insert — no seeding bundled in.
        doc.saveAndClose();
        docAlreadyClosed = true;
        insertTrackerTable(testDocId);
        _TF_RESULT = { tag: 'fixture.insert_tracker_table', data: { inserted: true } };
        break;
      }

      case 'append_doc_table': {
        // Builds a table from data.rows = [[{text, listItem?}, ...], ...] —
        // one paragraph (or list item) per cell. The only doc-seeding fixture
        // able to place AI: tokens inside table cells; append_doc_paragraph
        // (WebApp.js) only supports body-level plain paragraphs
        // (gts-dq6t AC-3/AC-4/AC-5).
        var adtRows    = data.rows || [];
        var adtNumRows = adtRows.length;
        var adtNumCols = adtNumRows > 0 ? adtRows[0].length : 0;
        if (adtNumRows === 0 || adtNumCols === 0) {
          _TF_RESULT = { tag: 'fixture.append_doc_table', data: { error: 'rows required' } };
          break;
        }
        var adtBlankGrid = [];
        for (var adtR = 0; adtR < adtNumRows; adtR++) {
          var adtBlankRow = [];
          for (var adtC = 0; adtC < adtNumCols; adtC++) adtBlankRow.push('');
          adtBlankGrid.push(adtBlankRow);
        }
        var adtTable = body.appendTable(adtBlankGrid);
        for (var adtR2 = 0; adtR2 < adtNumRows; adtR2++) {
          var adtRow = adtTable.getRow(adtR2);
          for (var adtC2 = 0; adtC2 < adtNumCols; adtC2++) {
            var adtSpec = adtRows[adtR2][adtC2] || {};
            var adtCell = adtRow.getCell(adtC2);
            if (adtSpec.listItem) {
              adtCell.appendListItem(adtSpec.text || '');
              adtCell.getChild(0).asParagraph().removeFromParent(); // drop appendTable's default empty paragraph
            } else {
              adtCell.setText(adtSpec.text || '');
            }
          }
        }
        _TF_RESULT = { tag: 'fixture.append_doc_table', data: { ok: true } };
        break;
      }

      case 'append_doc_list_item': {
        // Body-level bulleted list item containing an AI: token
        // (gts-dq6t AC-1/AC-2) — append_doc_paragraph only appends a
        // plain (non-list) paragraph.
        body.appendListItem(data.text || '');
        _TF_RESULT = { tag: 'fixture.append_doc_list_item', data: { ok: true } };
        break;
      }

      case 'append_doc_soft_paragraph': {
        // Appends a body-level paragraph whose text contains embedded line
        // breaks (soft returns / Shift+Enter in DocumentApp).  Used to seed
        // the soft-return multi-AI-token patterns (gts-d7z8/mrd8).
        // Note: DocumentApp represents soft returns as \r (not \n) in getText();
        // the scanner normalizes line endings before processing.
        body.appendParagraph(data.text || '');
        _TF_RESULT = { tag: 'fixture.append_doc_soft_paragraph', data: { ok: true } };
        break;
      }

      case 'append_doc_paragraph_with_chip':
      case 'append_doc_soft_paragraph_with_chip': {
        // gts-ogev/gts-mt39: seeds a PERSON-chip action header via the Docs
        // REST API (_tfAppendChipHeaderParagraph). 'append_doc_paragraph_with_chip'
        // (data.before omitted/'') puts the token at paragraph position 0 —
        // the single-token fast path's shape. 'append_doc_soft_paragraph_with_chip'
        // (data.before non-empty) puts context text before the token, joined
        // by a genuine soft return — the soft-return path's shape. The same
        // helper builds both so a test can seed one chip email through each
        // path and compare the resolved assignee.
        doc.saveAndClose();
        var chipParaToken = ScriptApp.getOAuthToken();
        _tfAppendChipHeaderParagraph(
          chipParaToken, testDocId,
          data.before || '',
          data.token || 'AI:',
          data.email,
          data.after || ''
        );
        docAlreadyClosed = true;
        _TF_RESULT = { tag: 'fixture.' + resolvedScenario, data: { ok: true } };
        break;
      }

      case 'append_tracker_cell_text': {
        // Appends an AI: token into the LAST data row's first cell of the
        // existing Action Item Tracker table (must already exist via
        // 'insert_tracker_table') to verify the scanner's tracker-table
        // exclusion (gts-dq6t AC-6). Locates the table the same way
        // _scanFloatingActions does: the first TABLE body-child after the
        // 'Action Item Summary' heading paragraph.
        var atctN           = body.getNumChildren();
        var atctHeadingSeen  = false;
        var atctTable        = null;
        for (var atctI = 0; atctI < atctN; atctI++) {
          var atctChild = body.getChild(atctI);
          if (!atctHeadingSeen) {
            if (atctChild.getType() === DocumentApp.ElementType.PARAGRAPH &&
                atctChild.asParagraph().getText().trim() === _TRACKER_HEADING) {
              atctHeadingSeen = true;
            }
            continue;
          }
          if (atctChild.getType() === DocumentApp.ElementType.TABLE) {
            atctTable = atctChild.asTable();
            break;
          }
        }
        if (!atctTable) {
          _TF_RESULT = { tag: 'fixture.append_tracker_cell_text', data: { error: 'tracker table not found' } };
          break;
        }
        var atctLastRow = atctTable.getRow(atctTable.getNumRows() - 1);
        atctLastRow.getCell(0).appendParagraph(data.text || '');
        _TF_RESULT = { tag: 'fixture.append_tracker_cell_text', data: { ok: true } };
        break;
      }

      case 'scenario_delete_unassigned': {
        // Find the §14 unassigned action by its exact seeded text and delete it.
        var sduTarget  = 'This tag and text confirms creation of an unassigned action item';
        var sduActions = _scanFloatingActions(doc);
        var sduId      = '';
        for (var sdui = 0; sdui < sduActions.length; sdui++) {
          if (sduActions[sdui].actionText === sduTarget) {
            sduId = sduActions[sdui].globalId || '';
            break;
          }
        }
        if (!sduId) {
          GasLogger.log('fixture.scenario_delete_unassigned', { msg: 'target action not found', target: sduTarget });
          _TF_RESULT = { tag: 'fixture.scenario_delete_unassigned', data: { error: 'not found' } };
          break;
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        sidebarDeleteAction(sduId, testDocId);
        _TF_RESULT = { tag: 'fixture.scenario_delete_unassigned', data: { globalId: sduId } };
        break;
      }

      case 'ensure_sheet_structure': {
        // Ensure the ActionSheet has the correct tab layout and headers.
        // Used by test_infrastructure.py before header-layout assertions.
        ensureSheetStructure();
        _TF_RESULT = { tag: 'fixture.ensure_sheet_structure', data: { ensured: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'assert_team_access': {
        // Calls the assertTeamAccess(teamId, ss) security gate (gts-me6w.5)
        // and reports the outcome instead of letting the thrown error propagate,
        // so the test harness can assert on TeamNotFound / TeamAccessDenied.
        var atfTeamId = data.teamId || '';
        try {
          assertTeamAccess(atfTeamId, ss);
          _TF_RESULT = { tag: 'fixture.assert_team_access', data: { ok: true, teamId: atfTeamId } };
        } catch (atfErr) {
          _TF_RESULT = { tag: 'fixture.assert_team_access', data: { ok: false, error: atfErr.message } };
        }
        docAlreadyClosed = true;
        break;
      }

      case 'sidebar_set_status': {
        // Mutation: change an action from "Open" to "Done" using sidebarSetStatus.
        // Resolves globalId by scanning floating actions for the target text.
        // data.targetText / data.newStatus override the journey defaults so a
        // scenario can drive the sidebar flush path against its own seeded
        // action (gts-dr8j) rather than the canonical journey's.
        var sssTargetText = data.targetText || 'AC1: Review the project budget';
        var sssNewStatus  = data.newStatus  || 'Done';
        var sssFloating   = _scanFloatingActions(doc);
        var sssNrId       = '';
        for (var ssi = 0; ssi < sssFloating.length; ssi++) {
          if (sssFloating[ssi].actionText === sssTargetText) {
            sssNrId = sssFloating[ssi].globalId || '';
            break;
          }
        }
        if (!sssNrId) {
          GasLogger.log('fixture.sidebar_set_status', { msg: 'action not found', target: sssTargetText });
          _TF_RESULT = { tag: 'fixture.sidebar_set_status', data: { error: 'action not found' } };
          docAlreadyClosed = false;
          break;
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        sidebarSetStatus(sssNrId, sssNewStatus, testDocId);
        _TF_RESULT = { tag: 'fixture.sidebar_set_status', data: { globalId: sssNrId, newStatus: sssNewStatus } };
        break;
      }

      case 'sidebar_delete_action': {
        // Mutation: delete an action using sidebarDeleteAction.
        // Resolves globalId by scanning floating actions for the target text + email.
        var sdaTargetText  = 'AC1: Approve the project proposal';
        var sdaTargetEmail = 'jane.smith@example.com';
        var sdaFloating    = _scanFloatingActions(doc);
        var sdaNrId        = '';
        for (var sdai = 0; sdai < sdaFloating.length; sdai++) {
          var sdaFa = sdaFloating[sdai];
          if (sdaFa.actionText === sdaTargetText && sdaFa.assigneeEmail === sdaTargetEmail) {
            sdaNrId = sdaFa.globalId || '';
            break;
          }
        }
        if (!sdaNrId) {
          GasLogger.log('fixture.sidebar_delete_action', { msg: 'action not found', target: sdaTargetText });
          _TF_RESULT = { tag: 'fixture.sidebar_delete_action', data: { error: 'action not found' } };
          docAlreadyClosed = false;
          break;
        }
        doc.saveAndClose();
        docAlreadyClosed = true;
        sidebarDeleteAction(sdaNrId, testDocId);
        _TF_RESULT = { tag: 'fixture.sidebar_delete_action', data: { globalId: sdaNrId } };
        break;
      }

      case 'ai_n_token_scan': {
        // Append a bare AI: paragraph, then call syncDocument so the scanner upgrades it
        // to AI-N: and writes a sheet row.  Returns the assigned globalId and action text
        // so the Python test can assert format and cross-check the sheet row.
        var antText = 'ANT: verify AI-N token format and globalId assignment';
        body.appendParagraph('AI: ' + antText);
        doc.saveAndClose();
        docAlreadyClosed = true;
        syncDocument(testDocId);
        SpreadsheetApp.flush();
        var antSheet = ss.getSheetByName('Actions');
        var antData  = antSheet.getDataRange().getValues();
        var antHdr   = antData[0];
        var antColId = antHdr.indexOf('globalId');
        var antColAc = antHdr.indexOf('Action');
        var antColDo = antHdr.indexOf('Document');
        var antRow   = null;
        for (var anti = 1; anti < antData.length; anti++) {
          if ((antData[anti][antColAc] || '').indexOf(antText) !== -1 &&
              (antData[anti][antColId] || '').indexOf(testDocId) !== -1) {
            antRow = antData[anti];
            break;
          }
        }
        var antGlobalId = antRow ? (antRow[antColId] || '') : '';
        _TF_RESULT = {
          tag:  'fixture.ai_n_token_scan',
          data: { globalId: antGlobalId, actionText: antText, docId: testDocId }
        };
        break;
      }

      case 'begin_test_session': {
        // masterDocId arrives as a real parameter (data.docId, from the HTTP
        // payload's testDocId). beginTestSession creates a named clone and
        // returns its ID directly — no script-property round-trip.
        var btsCloneId = beginTestSession(testDocId);
        _TF_RESULT = {
          tag:  'fixture.begin_test_session',
          data: { cloneId: btsCloneId }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'end_test_session': {
        // Trash the clone. Both the clone ID (testDocId, i.e. data.docId) and
        // the master ID to restore (data.masterDocId) are real parameters —
        // the caller already knows the master ID (Python: settings['testDocId'])
        // so there's no need to round-trip it through a script property.
        endTestSession(testDocId, data.masterDocId);
        _TF_RESULT = { tag: 'fixture.end_test_session', data: {} };
        docAlreadyClosed = true;
        break;
      }

      case 'verify_consistency': {
        _TF_RESULT = {
          tag: 'fixture.verify_consistency',
          data: verifyConsistencyForTest(testDocId, data.expected || null)
        };
        docAlreadyClosed = true;
        break;
      }

      case 'get_team_scope': {
        // Returns the document's Drive appProperty 'teamScope' (gts-me6w.6).
        var gtsDocId = data.docId || testDocId;
        var gtsToken = ScriptApp.getOAuthToken();
        _TF_RESULT = {
          tag: 'fixture.get_team_scope',
          data: { teamScope: _getDocAppProperty(gtsDocId, 'teamScope', gtsToken) || '' }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'edit_cell_via_trigger': {
        // Writes a cell on the Actions tab and then invokes onActionSheetEdit
        // with a real Range, driving the SAME entry point a user's spreadsheet
        // edit fires. Distinct from the edit_action_row route, which only
        // stamps Dirty and never runs the trigger (doPost writes cannot fire an
        // installable trigger), so it cannot exercise _syncSheetRowToDoc.
        // data: { globalId, field: 'action_text'|'status'|'assignee_email'|'assignee_name', value }
        var ecGid    = data.globalId || '';
        var ecField  = data.field    || 'action_text';
        var ecValue  = data.value    || '';
        var ecSheet  = ss.getSheetByName('Actions');
        var ecCol    = CONTRACT_SCHEMA.sheetAction.columnsByField[ecField];
        var ecRow    = -1;
        if (ecSheet && ecCol) {
          var ecLast = ecSheet.getLastRow();
          if (ecLast >= 2) {
            var ecIds = ecSheet.getRange(2, CONTRACT_SCHEMA.sheetAction.columnsByField.global_id, ecLast - 1, 1).getValues();
            for (var eci = 0; eci < ecIds.length; eci++) {
              if (String(ecIds[eci][0] || '') === ecGid) { ecRow = eci + 2; break; }
            }
          }
        }
        if (ecRow > 0) {
          var ecRange = ecSheet.getRange(ecRow, ecCol);
          ecRange.setValue(ecValue);
          SpreadsheetApp.flush();
          onActionSheetEdit({ range: ecRange });
        }
        _TF_RESULT = {
          tag:  'fixture.edit_cell_via_trigger',
          data: { globalId: ecGid, field: ecField, row: ecRow, applied: ecRow > 0 }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'get_docdata_row': {
        // Returns the DocData row for fileId (default testDocId), or null (gts-me6w.6).
        var gddFileId = data.fileId || testDocId;
        _TF_RESULT = {
          tag: 'fixture.get_docdata_row',
          data: { row: _readDocDataRow(ss, gddFileId) }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'get_team_data_rows': {
        // Returns all TeamData rows ({teamId, folderId, contact}) (gts-zc21).
        // Used to verify TeamData fixture setup never mutates pre-existing rows.
        _TF_RESULT = {
          tag: 'fixture.get_team_data_rows',
          data: { rows: _readTeamDataRows(ss) }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'seed_garbage_teamdata_row': {
        // gts-moy1.2 regression coverage: appends one TeamData row with a
        // deliberately implausible Folder Id (default '-NA-', the actual
        // live-sheet placeholder that triggered the bug) under a
        // distinctive, easily-cleaned-up teamId. Used to prove
        // _fetchDriveDocMetadata's scoped-listing query survives one
        // malformed folder id instead of Drive rejecting the whole combined
        // 'in parents' OR clause with a 404 that took down BOTH the scoped
        // listing and its own fallback safety net account-wide.
        var sgtrTeamSheet = _getOrCreateSheet(ss, 'TeamData');
        if (sgtrTeamSheet.getLastRow() < 1) {
          sgtrTeamSheet.getRange(1, 1, 1, 4).setValues(
            [CONTRACT_SCHEMA.sheetTeamData.headers]).setFontWeight('bold');
        }
        var sgtrTeamId   = data.teamId   || '_TEST_GTMOY12_GARBAGE';
        var sgtrFolderId = (data.folderId !== undefined) ? data.folderId : '-NA-';
        var sgtrLastRow  = sgtrTeamSheet.getLastRow();
        sgtrTeamSheet.getRange(sgtrLastRow + 1, 1, 1, 4)
          .setValues([[sgtrTeamId, sgtrFolderId, '', '']]);
        _TF_RESULT = {
          tag: 'fixture.seed_garbage_teamdata_row',
          data: { teamId: sgtrTeamId, folderId: sgtrFolderId, row: sgtrLastRow + 1 }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'remove_teamdata_row_by_team_id': {
        // Cleanup counterpart to seed_garbage_teamdata_row -- removes every
        // TeamData row whose Team Id exactly matches data.teamId. Safe no-op
        // if no such row exists.
        var rtrTeamId   = data.teamId || '_TEST_GTMOY12_GARBAGE';
        var rtrSheet    = ss.getSheetByName('TeamData');
        var rtrRemoved  = 0;
        if (rtrSheet && rtrSheet.getLastRow() >= 2) {
          var rtrCols = CONTRACT_SCHEMA.sheetTeamData.columnsByField;
          for (var rtrR = rtrSheet.getLastRow(); rtrR >= 2; rtrR--) {
            var rtrVal = rtrSheet.getRange(rtrR, rtrCols.team_id).getValue();
            if (rtrVal === rtrTeamId) {
              rtrSheet.deleteRow(rtrR);
              rtrRemoved++;
            }
          }
        }
        _TF_RESULT = {
          tag: 'fixture.remove_teamdata_row_by_team_id',
          data: { teamId: rtrTeamId, removed: rtrRemoved }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'seed_styled_action': {
        // gts-1pk step 1: seeds this invocation's doc (testDocId — the
        // caller's own isolated reference doc, set via the run_fixture
        // testDocId override) with a first floating action, AI-1:, whose
        // token and action-text ranges carry two deliberately DIFFERENT
        // fixed styles (_TF_STYLED_AI_TOKEN / _TF_STYLED_ACTION_TEXT above),
        // so configFormat/_configFormatForDoc sampling the wrong offset (or
        // not sampling at all) is visible as a mismatch, not a coincidence.
        var ssaText   = 'AI-1: Sample styled reference action';
        var ssaPara   = body.appendParagraph(ssaText);
        var ssaText2  = ssaPara.editAsText();
        var ssaTokEnd = 4; // "AI-1:" occupies offsets 0-4 inclusive
        var ssaActEnd = ssaText.length - 1;
        var ssaActStart = 6; // offset 5 is the single space after "AI-1:"
        ssaText2.setFontFamily(0, ssaTokEnd, _TF_STYLED_AI_TOKEN.fontFamily);
        ssaText2.setFontSize(0, ssaTokEnd, _TF_STYLED_AI_TOKEN.fontSize);
        ssaText2.setForegroundColor(0, ssaTokEnd, _TF_STYLED_AI_TOKEN.color);
        ssaText2.setBold(0, ssaTokEnd, _TF_STYLED_AI_TOKEN.bold);
        ssaText2.setItalic(0, ssaTokEnd, _TF_STYLED_AI_TOKEN.italic);
        ssaText2.setUnderline(0, ssaTokEnd, _TF_STYLED_AI_TOKEN.underline);
        ssaText2.setFontFamily(ssaActStart, ssaActEnd, _TF_STYLED_ACTION_TEXT.fontFamily);
        ssaText2.setFontSize(ssaActStart, ssaActEnd, _TF_STYLED_ACTION_TEXT.fontSize);
        ssaText2.setForegroundColor(ssaActStart, ssaActEnd, _TF_STYLED_ACTION_TEXT.color);
        ssaText2.setBold(ssaActStart, ssaActEnd, _TF_STYLED_ACTION_TEXT.bold);
        ssaText2.setItalic(ssaActStart, ssaActEnd, _TF_STYLED_ACTION_TEXT.italic);
        ssaText2.setUnderline(ssaActStart, ssaActEnd, _TF_STYLED_ACTION_TEXT.underline);
        _TF_RESULT = { tag: 'fixture.seed_styled_action', data: { ok: true } };
        break;
      }

      case 'seed_formatted_action': {
        // gts-zocq: seeds this invocation's doc (testDocId, or data.docId
        // when provided) with a floating action whose actionText carries a
        // bold span over one word and a separate italic span over another —
        // deliberately non-adjacent and non-overlapping so a scan bug that
        // reads the wrong offset range, merges the two runs, or drops one
        // entirely is visible as a mismatch rather than a coincidental pass.
        // No status token (so the sync's "materialize missing explicit
        // status" flush path exercises the new per-run bold/italic requests
        // in _buildFlushRequests on the very first sync).
        var sfaN        = (data && data.n) || 1;
        var sfaText     = 'AI-' + sfaN + ': Please bold this and italic that today';
        var sfaPara     = body.appendParagraph(sfaText);
        var sfaTextEl   = sfaPara.editAsText();
        var sfaBoldWord   = 'bold this';
        var sfaItalicWord = 'italic that';
        var sfaBoldStart   = sfaText.indexOf(sfaBoldWord);
        var sfaBoldEnd     = sfaBoldStart + sfaBoldWord.length - 1;
        var sfaItalicStart = sfaText.indexOf(sfaItalicWord);
        var sfaItalicEnd   = sfaItalicStart + sfaItalicWord.length - 1;
        sfaTextEl.setBold(sfaBoldStart, sfaBoldEnd, true);
        sfaTextEl.setItalic(sfaItalicStart, sfaItalicEnd, true);
        _TF_RESULT = { tag: 'fixture.seed_formatted_action', data: {
          ok: true, n: sfaN, text: sfaText,
          boldWord: sfaBoldWord, italicWord: sfaItalicWord
        } };
        break;
      }

      case 'seed_link_action': {
        // gts-tz5x: seeds this invocation's doc (testDocId, or data.docId
        // when provided) with a floating action whose actionText carries a
        // hyperlink over one phrase, deliberately isolated from any
        // bold/italic span (ADR-0027 rule 12's hasFormatting gate must fire
        // on link alone -- a link-only action must not be misread as
        // unformatted and dropped). No status token, so the first sync's
        // "materialize missing explicit status" flush path exercises the
        // link's updateTextStyle request immediately, same as
        // seed_formatted_action does for bold/italic.
        //
        // Accepts {n, url}; url defaults to one with encodable characters
        // (query string) so the same fixture covers gts-tz5x case 3 without
        // a second seed helper -- pass a plain https://host/path url to
        // isolate the encodable-URL behavior from the base round-trip case.
        var slaN     = (data && data.n) || 1;
        var slaUrl   = (data && data.url) || 'https://example.com/docs?x=1&y=2';
        var slaText  = 'AI-' + slaN + ': Please see the Q3 deck for context today';
        var slaPara  = body.appendParagraph(slaText);
        var slaTextEl = slaPara.editAsText();
        var slaLinkWord  = 'Q3 deck';
        var slaLinkStart = slaText.indexOf(slaLinkWord);
        var slaLinkEnd   = slaLinkStart + slaLinkWord.length - 1;
        slaTextEl.setLinkUrl(slaLinkStart, slaLinkEnd, slaUrl);
        _TF_RESULT = { tag: 'fixture.seed_link_action', data: {
          ok: true, n: slaN, text: slaText, url: slaUrl,
          linkWord: slaLinkWord
        } };
        break;
      }

      case 'replace_action_plain_text': {
        // gts-a8yh.2 state probe: rewrites an existing floating action's
        // paragraph (previously seeded by e.g. seed_formatted_action) with
        // NEW plain text carrying no bold/italic anywhere, so a re-sync
        // exercises WebApp.js's doc-authoritative "update existing row"
        // branch (actionText differs -> write executes) with
        // runs === [] -- the exact code path _buildRichTextValueForActionText
        // returns null for. Accepts {n, text}; `text` defaults to a plain
        // sentence distinct from seed_formatted_action's text so the content
        // comparison in that branch is guaranteed to trigger a write.
        var raptN    = (data && data.n) || 1;
        var raptText = (data && data.text) || ('AI-' + raptN + ': now nothing but plain text');
        var raptParas = body.getParagraphs();
        var raptFound = false;
        for (var rapti = 0; rapti < raptParas.length; rapti++) {
          if (raptParas[rapti].getText().indexOf('AI-' + raptN + ':') === 0) {
            var raptTextEl = raptParas[rapti].editAsText();
            var raptOldLen = raptTextEl.getText().length;
            raptTextEl.setText(raptText);
            // setText() does not reliably reset per-character style runs on
            // its own (this fixture must not itself mask the very bug it is
            // probing) -- explicitly clear bold/italic over the full new
            // range.
            raptTextEl.setBold(0, raptText.length - 1, false);
            raptTextEl.setItalic(0, raptText.length - 1, false);
            raptFound = true;
            break;
          }
        }
        _TF_RESULT = { tag: 'fixture.replace_action_plain_text', data: {
          ok: raptFound, n: raptN, text: raptText
        } };
        break;
      }

      case 'create_canonical_reference_doc': {
        // gts-colw AC#3: creates a NEW, permanent Doc (not the throwaway
        // testDocId this dispatcher always opens/closes) and decodes
        // data.apt into it — the one-time step that produces the canonical
        // reference doc's fixed Drive location. Requires testDocId only to
        // satisfy this function's own entry guard; that doc is untouched.
        var ccrdApt = data && data.apt;
        if (!ccrdApt) {
          _TF_RESULT = { tag: 'fixture.create_canonical_reference_doc', data: { ok: false, error: 'data.apt is required' } };
          break;
        }
        var ccrdName = (data && data.name) || 'GActionSheet — ADR-0027 Canonical Reference (gts-colw)';
        var ccrdDoc = DocumentApp.create(ccrdName);
        var ccrdDocId = ccrdDoc.getId();
        decodeAptIntoDoc(ccrdDoc, ccrdApt); // saves and closes ccrdDoc internally
        _TF_RESULT = { tag: 'fixture.create_canonical_reference_doc', data: {
          ok: true, docId: ccrdDocId, docUrl: 'https://docs.google.com/document/d/' + ccrdDocId + '/edit'
        } };
        break;
      }

      case 'encode_reference_document': {
        // gts-colw: encodes this invocation's doc (testDocId, or data.docId
        // when provided) to Action Portable Text (docs/interfaces/action-
        // portable-text.md). Used both for the round-trip check
        // (encode(decode(x)) == x) and to regenerate the checked-in APT
        // file from the human-maintained canonical reference doc.
        var erdDocId = (data && data.docId) || testDocId;
        var erdDoc = erdDocId === testDocId ? doc : DocumentApp.openById(erdDocId);
        var erdApt = encodeDocToApt(erdDoc);
        if (erdDoc === doc) { doc.saveAndClose(); docAlreadyClosed = true; }
        _TF_RESULT = { tag: 'fixture.encode_reference_document', data: { ok: true, apt: erdApt } };
        break;
      }

      case 'decode_reference_document': {
        // gts-colw: decodes Action Portable Text (data.apt, required) into
        // this invocation's doc (testDocId, or data.docId when provided).
        // decodeAptIntoDoc is append-only (targets an EMPTY body), so this
        // case clears the target doc's body first — makes the call a true
        // "regenerate whole" regardless of whatever the doc held before
        // (a fresh scn.new_doc() test seed, or the canonical Doc after a
        // human hand-edited or a live sync flushed it). Without this,
        // re-pushing a correction to an already-populated doc APPENDS a
        // second copy instead of replacing the first (caught live 2026-08-27
        // pushing a correction back to the canonical Doc).
        var drdApt = data && data.apt;
        if (!drdApt) {
          _TF_RESULT = { tag: 'fixture.decode_reference_document', data: { ok: false, error: 'data.apt is required' } };
          break;
        }
        var drdDocId = (data && data.docId) || testDocId;
        var drdDoc = drdDocId === testDocId ? doc : DocumentApp.openById(drdDocId);
        drdDoc.getBody().clear();
        decodeAptIntoDoc(drdDoc, drdApt); // saves and closes drdDoc internally
        if (drdDoc === doc) docAlreadyClosed = true;
        _TF_RESULT = { tag: 'fixture.decode_reference_document', data: { ok: true, docId: drdDocId } };
        break;
      }

      case 'debug_action_runs': {
        // gts-zocq round-trip verification fixture. Accepts {docId, n}
        // (docId defaults to testDocId). Returns three independently-sourced
        // views of the SAME action's inline formatting so a test can compare
        // them without trusting any one source:
        //   scanRuns  — _scanFloatingActions' own runs[] for AI-n, read via a
        //               FRESH DocumentApp.openById (not the dispatcher's own
        //               already-open `doc`, so this also proves the doc on
        //               disk — not an in-memory handle — carries the format).
        //   sheetRuns — the Actions sheet's action_text cell RichTextValue
        //               for that globalId, read via the same
        //               _richTextRunsForCell helper the product uses.
        var darDocId = (data && data.docId) || testDocId;
        var darN     = (data && data.n) || 1;
        if (darDocId === testDocId) { doc.saveAndClose(); docAlreadyClosed = true; }
        else { docAlreadyClosed = true; }

        var darDoc = DocumentApp.openById(darDocId);
        var darActions = _scanFloatingActions(darDoc);
        darDoc.saveAndClose();
        var darScan = null;
        for (var dai = 0; dai < darActions.length; dai++) {
          if (darActions[dai].N === darN) { darScan = darActions[dai]; break; }
        }

        var darGlobalId = darScan ? darScan.globalId : darDocId + '/' + _actionTokenId(darN);
        var darSheet = ss.getSheetByName('Actions');
        var darSheetRuns = [];
        var darSheetText = null;
        if (darSheet) {
          var darLastRow = darSheet.getLastRow();
          if (darLastRow >= 2) {
            var darGidCol = darSheet.getRange(2, _ACOL.global_id, darLastRow - 1, 1).getValues();
            for (var dri = 0; dri < darGidCol.length; dri++) {
              if (darGidCol[dri][0] === darGlobalId) {
                var darRow = dri + 2;
                darSheetText = darSheet.getRange(darRow, _ACOL.action_text).getValue();
                darSheetRuns = _richTextRunsForCell(darSheet.getRange(darRow, _ACOL.action_text));
                break;
              }
            }
          }
        }

        _TF_RESULT = { tag: 'fixture.debug_action_runs', data: {
          ok: true,
          globalId: darGlobalId,
          scanActionText: darScan ? darScan.actionText : null,
          scanRuns:       darScan ? darScan.runs : null,
          // gts-po8t: additive — ADR-0027 rule 5a custom fields as scanned
          // FRESH off the doc, {FieldName:{text,runs}}, so a test can assert
          // the write-side render (_renderCustomFieldLines) reparses as the
          // same field(s)/value(s)/formatting on the next scan, independent
          // of sheet custom_fields persistence (not yet shipped, gts-t6xs).
          scanCustomFields: darScan ? darScan.customFields : null,
          sheetActionText: darSheetText,
          sheetRuns:       darSheetRuns
        } };
        break;
      }

      case 'config_format': {
        // gts-d99c/gts-1pk: headless entry point for _configFormatForDoc(docId)
        // (SyncManager.js), extracted from the interactive configFormat()
        // menu shell. Accepts {docId}; falls back to this invocation's own
        // testDocId (the run_fixture testDocId override) when omitted, same
        // convention as the other fileId/docId-parameterized fixtures above.
        var cfgDocId = data.docId || testDocId;
        var cfgResult = _configFormatForDoc(cfgDocId);
        _TF_RESULT = { tag: 'fixture.config_format', data: cfgResult };
        docAlreadyClosed = true;
        break;
      }

      case 'get_config_rows': {
        // gts-1pk step 3/6: reads the Config sheet's raw rows back (durable-
        // state assertion target — exactly one 'ai_token' + one 'action_text'
        // row after sampling; zero rows after 'clear_config_rows').
        var gcrSheet = ss.getSheetByName('Config');
        var gcrRows  = [];
        if (gcrSheet) {
          var gcrLastRow = gcrSheet.getLastRow();
          if (gcrLastRow >= 2) {
            var gcrCols   = CONTRACT_SCHEMA.sheetConfig.columnsByField;
            var gcrValues = gcrSheet.getRange(2, 1, gcrLastRow - 1, CONTRACT_SCHEMA.sheetConfig.headers.length).getValues();
            for (var gcrI = 0; gcrI < gcrValues.length; gcrI++) {
              var gcrKey = gcrValues[gcrI][gcrCols.key - 1];
              if (!gcrKey) continue;
              var gcrParsed = null;
              try { gcrParsed = JSON.parse(gcrValues[gcrI][gcrCols.value - 1] || '{}'); } catch (gcrErr) { gcrParsed = null; }
              gcrRows.push({ key: gcrKey, value: gcrParsed });
            }
          }
        }
        _TF_RESULT = { tag: 'fixture.get_config_rows', data: { rows: gcrRows } };
        docAlreadyClosed = true;
        break;
      }

      case 'clear_config_rows': {
        // gts-1pk step 5: clears the Config sheet's data rows (keeps the
        // header) — an explicit reset, not an undo/revert-to-prior-style
        // (_configFormatForDoc has no stack semantics). The next
        // _getActionFormatConfig() read (any execution, including the same
        // one via the cache-invalidate below) falls back to
        // _DEFAULT_AI_TOKEN_STYLE / actionText:null.
        var ccrSheet = ss.getSheetByName('Config');
        if (ccrSheet) {
          var ccrLastRow = ccrSheet.getLastRow();
          if (ccrLastRow > 1) {
            WriteGuard.wrap(function () {
              ccrSheet.getRange(2, 1, ccrLastRow - 1, CONTRACT_SCHEMA.sheetConfig.headers.length).clearContent();
            });
          }
        }
        _actionFormatConfigCache = null;
        _TF_RESULT = { tag: 'fixture.clear_config_rows', data: { cleared: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'debug_action_text_style': {
        // gts-1pk steps 4/6: verifies an already-flushed AI-N chip's applied
        // style via the SAME Docs REST GET mechanism the real flush uses
        // (docs.googleapis.com/v1/documents/{docId}, textStyle fields) —
        // not a DocumentApp visual read, per the AC's "not just visually"
        // requirement. Accepts {docId, n}; docId defaults to testDocId.
        var datsDocId = data.docId || testDocId;
        var datsN     = data.n || data.N || 1;
        if (datsDocId === testDocId) {
          doc.saveAndClose(); // release this dispatcher's own handle first
          docAlreadyClosed = true;
        } else {
          docAlreadyClosed = true;
        }
        var datsToken  = ScriptApp.getOAuthToken();
        var datsFields = 'body.content(paragraph/elements(textRun(content,textStyle(weightedFontFamily,fontSize,foregroundColor,bold,italic,underline))))';
        var datsResp = UrlFetchApp.fetch(
          'https://docs.googleapis.com/v1/documents/' + datsDocId + '?fields=' + encodeURIComponent(datsFields),
          { headers: { Authorization: 'Bearer ' + datsToken }, muteHttpExceptions: true }
        );
        var datsResult;
        if (datsResp.getResponseCode() === 200) {
          var datsBody    = JSON.parse(datsResp.getContentText());
          var datsContent = (datsBody.body || {}).content || [];
          datsResult = _tfExtractActionTextStyle(datsContent, datsN);
        } else {
          datsResult = { ok: false, error: 'GET failed: HTTP ' + datsResp.getResponseCode() };
        }
        _TF_RESULT = { tag: 'fixture.debug_action_text_style', data: datsResult };
        break;
      }

      case 'debug_bulk_drive_metadata': {
        // Diagnostic (gts-sl64 investigation): returns what syncAll's own
        // bulk _fetchDriveDocMetadata() call currently reports for fileId,
        // to compare against the live per-doc debug_drive_ancestors walk.
        var dbdmFileId = data.fileId || testDocId;
        var dbdmMap = _fetchDriveDocMetadata();
        _TF_RESULT = {
          tag: 'fixture.debug_bulk_drive_metadata',
          data: { fileId: dbdmFileId, entry: dbdmMap[dbdmFileId] || null }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'debug_drive_ancestors': {
        // Diagnostic: returns the chain of ancestor folders ({id, name}) from
        // fileId's immediate parent up to My Drive root (gts-u2np).
        // Useful for explaining unexpected teamScope folder-walk matches.
        var ddaFileId = data.fileId || testSheetId;
        var ddaChain  = [];
        var ddaIter   = DriveApp.getFileById(ddaFileId).getParents();
        while (ddaIter.hasNext()) {
          var ddaFolder = ddaIter.next();
          ddaChain.push({ id: ddaFolder.getId(), name: ddaFolder.getName() });
          ddaIter = ddaFolder.getParents();
        }
        _TF_RESULT = {
          tag: 'fixture.debug_drive_ancestors',
          data: { fileId: ddaFileId, ancestors: ddaChain }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'set_docdata_row': {
        // Upserts a DocData row, overriding only the fields supplied
        // (gts-me6w.6: teamId/syncStatus, for the UpdateDoc-override
        // scenarios S3/S7; gts-cduk: actionCount/resolvedCount/docName,
        // to corrupt a row so the syncAll() integrity pass has something to
        // reconcile). Acts on a row already created by a prior sync.
        var sdrFileId = data.fileId || testDocId;
        var sdrExisting = _readDocDataRow(ss, sdrFileId) || {
          docName: '', lastSyncTime: new Date(), syncStatus: '', teamId: '',
          actionCount: 0, resolvedCount: 0
        };
        var sdrTeamId       = data.hasOwnProperty('teamId')       ? data.teamId       : sdrExisting.teamId;
        var sdrSyncStatus   = data.hasOwnProperty('syncStatus')   ? data.syncStatus   : sdrExisting.syncStatus;
        var sdrDocName      = data.hasOwnProperty('docName')      ? data.docName      : sdrExisting.docName;
        var sdrActionCount  = data.hasOwnProperty('actionCount')  ? data.actionCount  : sdrExisting.actionCount;
        var sdrResolvedCount = data.hasOwnProperty('resolvedCount') ? data.resolvedCount : sdrExisting.resolvedCount;
        var sdrUpdated = _getOrUpsertDocDataRow(
          ss, sdrFileId,
          sdrDocName, sdrExisting.lastSyncTime,
          sdrTeamId, sdrSyncStatus,
          sdrActionCount, sdrResolvedCount
        );
        _TF_RESULT = { tag: 'fixture.set_docdata_row', data: { row: sdrUpdated } };
        docAlreadyClosed = true;
        break;
      }

      case 'move_doc_to_folder': {
        // Moves a doc into the given folder (gts-me6w.6) — used by the
        // sticky-after-move scenario (S8) and the folder-hierarchy fixture.
        var mdtfDocId    = data.docId || testDocId;
        var mdtfFolderId = data.folderId;
        if (!mdtfFolderId) throw new Error('move_doc_to_folder: folderId required');
        DriveApp.getFileById(mdtfDocId).moveTo(DriveApp.getFolderById(mdtfFolderId));
        _TF_RESULT = {
          tag: 'fixture.move_doc_to_folder',
          data: { docId: mdtfDocId, folderId: mdtfFolderId }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'setup_team_scope_fixture': {
        // Idempotent (check-exists-or-create, no cleanup) folder hierarchy +
        // TeamData rows for the S1a/S1b/S1c/S8 folder-walk scenarios
        // (gts-me6w.6). Folder IDs are persisted in script properties so
        // repeat runs reuse the same Drive folders.
        //
        //   testTeamA (parent, registered TestTeamScopeA)
        //   |- testTeamAChild (child, registered TestTeamScopeAChild)
        //   `- testTeamAMid (unregistered)
        //      `- testTeamADeep (unregistered, no TeamData row)
        //
        //   testTeamNoTeam (sibling of testTeamA, unregistered, no TeamData
        //   row) — used by S2/S6 for the folder-walk no-match path
        //   (gts-u2np).
        //
        // NOTE (gts-vc3m): this fixture's own teamId literals are
        // 'TestTeamScopeA'/'TestTeamScopeAChild' -- distinct from the
        // separately-provisioned live multi-folder ACL fixture (gts-79dw.4.16,
        // docs/verified-team-portal-plan.md §6a), which independently uses
        // teamId 'TestTeamA' for its own two folder rows. The script-property
        // keys below (TEAMSCOPE_FOLDER_SCOPE_*) are deliberately distinct from
        // the legacy TEAMSCOPE_FOLDER_* keys this fixture used to write, which
        // had come to point at the exact same Drive folder the .4.16 ACL
        // fixture reuses (folder 1) -- reusing that folder here would leave
        // two TeamData rows with different teamIds pointing at the same
        // Folder Id, making _walkFolderForTeam's folder-walk match
        // order-dependent. Using fresh property keys forces this fixture onto
        // its own, non-shared Drive folders.
        //
        // Also memoized cross-session, like DISCOVERY_* above: TEAMSCOPE_FOLDER_*
        // sits outside the '_TEST_' prefix so 'reset_test_state' leaves these
        // Drive folder IDs alone rather than forcing re-creation every run.
        var stsfProps = PropertiesService.getScriptProperties();

        var stsfRootIter = DriveApp.getFileById(testSheetId).getParents();
        var stsfRoot = stsfRootIter.hasNext() ? stsfRootIter.next() : DriveApp.getRootFolder();

        var stsfParentId = stsfProps.getProperty('TEAMSCOPE_FOLDER_SCOPE_A');
        var stsfParent = stsfParentId ? DriveApp.getFolderById(stsfParentId)
                                       : stsfRoot.createFolder('GActionSheet Test - TeamScope A');
        stsfParentId = stsfParent.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_SCOPE_A', stsfParentId);

        var stsfChildId = stsfProps.getProperty('TEAMSCOPE_FOLDER_SCOPE_A_CHILD');
        var stsfChild = stsfChildId ? DriveApp.getFolderById(stsfChildId)
                                     : stsfParent.createFolder('GActionSheet Test - TeamScope A Child');
        stsfChildId = stsfChild.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_SCOPE_A_CHILD', stsfChildId);

        var stsfMidId = stsfProps.getProperty('TEAMSCOPE_FOLDER_SCOPE_A_MID');
        var stsfMid = stsfMidId ? DriveApp.getFolderById(stsfMidId)
                                 : stsfParent.createFolder('GActionSheet Test - TeamScope A Mid');
        stsfMidId = stsfMid.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_SCOPE_A_MID', stsfMidId);

        var stsfDeepId = stsfProps.getProperty('TEAMSCOPE_FOLDER_SCOPE_A_DEEP');
        var stsfDeep = stsfDeepId ? DriveApp.getFolderById(stsfDeepId)
                                   : stsfMid.createFolder('GActionSheet Test - TeamScope A Deep');
        stsfDeepId = stsfDeep.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_SCOPE_A_DEEP', stsfDeepId);

        // No-team folder (gts-u2np): the live TeamData row
        // 'TestGActionSheet' registers stsfRoot itself (testSheetId's parent
        // "GActionSheet" folder) — so any descendant of stsfRoot walks up to
        // a match. Create the no-team folder at My Drive root instead, which
        // has no TeamData row, so the walk reaches no-match.
        var stsfNoTeamId = stsfProps.getProperty('TEAMSCOPE_FOLDER_NOTEAM_ROOT');
        var stsfNoTeam = stsfNoTeamId ? DriveApp.getFolderById(stsfNoTeamId)
                                       : DriveApp.getRootFolder().createFolder('GActionSheet Test - TeamScope No-Team');
        stsfNoTeamId = stsfNoTeam.getId();
        stsfProps.setProperty('TEAMSCOPE_FOLDER_NOTEAM_ROOT', stsfNoTeamId);

        // Idempotent TeamData rows: TestTeamScopeA -> A, TestTeamScopeAChild -> Child
        var stsfTeamSheet = _getOrCreateSheet(ss, 'TeamData');
        if (stsfTeamSheet.getLastRow() < 1) {
          stsfTeamSheet.getRange(1, 1, 1, 3).setValues([['Team Id', 'Folder Id', 'Contact']]).setFontWeight('bold');
        }
        var stsfRows = _readTeamDataRows(ss);
        var stsfHasA = false, stsfHasChild = false;
        for (var stsfI = 0; stsfI < stsfRows.length; stsfI++) {
          if (stsfRows[stsfI].teamId === 'TestTeamScopeA') stsfHasA = true;
          if (stsfRows[stsfI].teamId === 'TestTeamScopeAChild') stsfHasChild = true;
        }
        var stsfNewRows = [];
        if (!stsfHasA) stsfNewRows.push(['TestTeamScopeA', stsfParentId, '']);
        if (!stsfHasChild) stsfNewRows.push(['TestTeamScopeAChild', stsfChildId, '']);
        if (stsfNewRows.length > 0) {
          var stsfLastRow = stsfTeamSheet.getLastRow();
          stsfTeamSheet.getRange(stsfLastRow + 1, 1, stsfNewRows.length, 3).setValues(stsfNewRows);
        }

        _TF_RESULT = {
          tag: 'fixture.setup_team_scope_fixture',
          data: {
            testTeamA:      stsfParentId,
            testTeamAChild: stsfChildId,
            testTeamAMid:   stsfMidId,
            testTeamADeep:  stsfDeepId,
            testTeamNoTeam: stsfNoTeamId
          }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_all': {
        syncAll();
        SpreadsheetApp.flush();
        _TF_RESULT = { tag: 'fixture.sync_all', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_all_force_listing_miss': {
        // gts-m33k: simulates the Shared-Drive-listing-omission symptom
        // (gts-rskf) for a specific, otherwise perfectly live and reachable
        // doc, without requiring a real Shared Drive to be provisioned in
        // this test environment — no test Shared Drive folder id exists in
        // local.settings.json (see plan-context.md). Monkey-patches the
        // global _fetchDriveDocMetadata for the duration of exactly one
        // syncAll() call so the target doc is absent from the bulk listing
        // map exactly as a Shared-Drive-hosted doc would have been pre-fix,
        // while still being fully reachable via the per-doc
        // _fetchSingleDocMetadata fallback syncAll now calls before marking
        // anything Doc Not Found. Restored in a finally block so the patch
        // never leaks past this single request.
        var flmDocId   = data.docId || testDocId;
        var flmRealFetch = _fetchDriveDocMetadata;
        _fetchDriveDocMetadata = function () {
          var map = flmRealFetch();
          delete map[flmDocId];
          return map;
        };
        try {
          syncAll();
          SpreadsheetApp.flush();
        } finally {
          _fetchDriveDocMetadata = flmRealFetch;
        }
        _TF_RESULT = { tag: 'fixture.sync_all_force_listing_miss', data: { docId: flmDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_all_force_listing_miss_multi': {
        // gts-uuse point 3: same Shared-Drive-listing-omission simulation as
        // 'sync_all_force_listing_miss' above, but removes MULTIPLE target
        // docs from the bulk map in the same syncAll() call so the sweep's
        // per-doc fallback has more than one doc to resolve at once. That is
        // exactly the condition _fetchDriveDocMetadataBatch (gts-uuse) exists
        // for: syncAll only calls it when missingDocIds.length > 1, so a
        // single-doc miss (the existing fixture) never exercises the actual
        // batch/drive/v3 HTTP path. Restored in a finally block so the patch
        // never leaks past this single request.
        var flmmDocIds     = data.docIds || [];
        var flmmRealFetch  = _fetchDriveDocMetadata;
        _fetchDriveDocMetadata = function () {
          var map = flmmRealFetch();
          for (var flmmI = 0; flmmI < flmmDocIds.length; flmmI++) {
            delete map[flmmDocIds[flmmI]];
          }
          return map;
        };
        try {
          syncAll();
          SpreadsheetApp.flush();
        } finally {
          _fetchDriveDocMetadata = flmmRealFetch;
        }
        _TF_RESULT = { tag: 'fixture.sync_all_force_listing_miss_multi', data: { docIds: flmmDocIds } };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_all_force_team_walk_error': {
        // gts-sl64 AC4: simulates a transient Drive folder-parent lookup
        // failure for one specific doc during syncAll's team-reconciliation
        // pass, without depending on a real, timing-sensitive Drive outage.
        // Monkey-patches the global _walkFolderForTeam so it returns the
        // walk's own "could not complete" sentinel (false) for the target
        // doc only, for the duration of exactly one syncAll() call, proving
        // the pass leaves that doc's existing DocData.teamId untouched
        // rather than clobbering it with a blank. Restored in a finally
        // block so the patch never leaks past this single request.
        var fweDocId    = data.docId || testDocId;
        var fweRealWalk = _walkFolderForTeam;
        _walkFolderForTeam = function (docId, teamDataRows, folderTeamCache) {
          if (docId === fweDocId) return false;
          return fweRealWalk(docId, teamDataRows, folderTeamCache);
        };
        try {
          syncAll();
          SpreadsheetApp.flush();
        } finally {
          _walkFolderForTeam = fweRealWalk;
        }
        _TF_RESULT = { tag: 'fixture.sync_all_force_team_walk_error', data: { docId: fweDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'sync_all_force_drive_5xx': {
        // gts-pm72 Backstop proof: simulates N consecutive transient Drive
        // files.list 5xx responses (the sync.driveMetadata.error symptom)
        // without depending on a real Google-side outage lining up with a
        // test run. Sets _TEST_FORCE_DRIVE_5XX_COUNT, which
        // SyncManager.js's _fetchDriveWithRetry consults on every Drive REST
        // attempt via _driveFetchTestOverrideCode -- each consulted attempt
        // decrements the counter and reports a synthetic HTTP 500 (real
        // Drive is still called underneath; only the code the retry loop
        // sees is overridden, so this never touches production Drive
        // behaviour). The counter is a '_TEST_' property, so a crashed test
        // is swept by 'reset_test_state' rather than leaking into later runs.
        //
        // data.fails (default 1) is the number of attempts to force-fail:
        //   - fails < 3 (the bounded retry's max attempts): a later attempt
        //     within the same _fetchDriveWithRetry call recovers, so
        //     sync.driveMetadata.error is never logged and syncAll finishes
        //     clean -- proves the retry recovers.
        //   - fails >= 3: every attempt in the bounded window is forced,
        //     the loop exhausts and _fetchDriveDocMetadata still throws (its
        //     existing per-doc fallback then keeps the sweep correct) --
        //     proves the retry is bounded, not infinite/skipped.
        var d5xxFails = (data && data.fails != null) ? data.fails : 1;
        PropertiesService.getScriptProperties().setProperty('_TEST_FORCE_DRIVE_5XX_COUNT', String(d5xxFails));
        try {
          syncAll();
          SpreadsheetApp.flush();
        } finally {
          PropertiesService.getScriptProperties().deleteProperty('_TEST_FORCE_DRIVE_5XX_COUNT');
        }
        _TF_RESULT = { tag: 'fixture.sync_all_force_drive_5xx', data: { requestedFails: d5xxFails } };
        docAlreadyClosed = true;
        break;
      }

      case 'insert_tracker_force_gas_retry': {
        // gts-bops Backstop proof: forces N consecutive synthetic
        // 'Service Documents failed while accessing document with id ...'
        // exceptions out of TrackerTable.js's DocumentApp.openById call --
        // the exact failure that triggered gts-bops (F10, S5 merge-gate run
        // 2026-08-07) -- via withGasRetry's own test-only fault-injection
        // hook (RetryUtil.js::_gasRetryTestShouldForceFailure), keyed on
        // that call site's label. Real DocumentApp is never touched; only
        // the code path withGasRetry sees is overridden, mirroring
        // sync_all_force_drive_5xx's fault-injection shape one level up
        // (exception-based instead of response-code-based).
        //
        // data.fails (default 1) is the number of attempts to force-fail:
        //   - fails < 3 (the bounded retry's max attempts): insertTrackerTable
        //     still succeeds, having consumed >1 attempt -- proves the retry
        //     recovers (gasRetry.attempt + gasRetry.recovered logged, no
        //     gasRetry.exhausted, no tracker.error).
        //   - fails >= 3: every attempt in the bounded window is forced, the
        //     loop exhausts and insertTrackerTable throws (caught and logged
        //     as tracker.error by its own existing catch, same as before this
        //     bead) -- proves the retry is bounded, not infinite/skipped.
        var itfLabel = 'TrackerTable.insertTrackerTable:DocumentApp.openById';
        var itfFails = (data && data.fails != null) ? data.fails : 1;
        _tfInsertFloatingAction(body, 'AI-1: gts-bops forced-retry tracker action');
        doc.saveAndClose();
        docAlreadyClosed = true;
        syncDocument(testDocId);
        SpreadsheetApp.flush();
        PropertiesService.getScriptProperties().setProperty(
          '_TEST_FORCE_GAS_RETRY_FAIL_COUNT:' + itfLabel, String(itfFails));
        var itfOk = true;
        var itfErr = null;
        try {
          insertTrackerTable(testDocId);
        } catch (e) {
          itfOk = false;
          itfErr = e.message;
        } finally {
          PropertiesService.getScriptProperties().deleteProperty(
            '_TEST_FORCE_GAS_RETRY_FAIL_COUNT:' + itfLabel);
        }
        _TF_RESULT = {
          tag: 'fixture.insert_tracker_force_gas_retry',
          data: { requestedFails: itfFails, ok: itfOk, err: itfErr }
        };
        docAlreadyClosed = true;
        break;
      }

      case 'gas_retry_classifier_selftest': {
        // gts-bops AC5 proof: RetryUtil.js::_isRetryableGasError classifies
        // real (non-transient) error messages as NOT retryable, so a genuine
        // not-found/permission-denied error still surfaces on attempt 1
        // rather than burning 2 extra attempts + ~2s of backoff on an answer
        // that will never change. Pure-function check -- no live Doc/Drive
        // call, no doc mutation, near-instant.
        doc.saveAndClose();
        docAlreadyClosed = true;
        var gcsCases = [
          { msg: 'Service Documents failed while accessing document with id abc123.', expect: true },
          { msg: 'Service invoked too many times in a short time: getFileById.', expect: true },
          { msg: 'Internal error executing the API request.', expect: true },
          { msg: "We're sorry, a server error occurred. Please wait a bit and try again.", expect: true },
          { msg: 'Invalid argument: id', expect: false },
          { msg: 'Document is missing (perhaps it was deleted?)', expect: false },
          { msg: 'You do not have permission to access the requested document.', expect: false },
          { msg: 'File not found.', expect: false }
        ];
        var gcsResults = [];
        var gcsAllMatch = true;
        for (var gc = 0; gc < gcsCases.length; gc++) {
          var gcsGot = _isRetryableGasError({ message: gcsCases[gc].msg });
          var gcsMatch = gcsGot === gcsCases[gc].expect;
          if (!gcsMatch) gcsAllMatch = false;
          gcsResults.push({ msg: gcsCases[gc].msg, expect: gcsCases[gc].expect, got: gcsGot, match: gcsMatch });
        }
        _TF_RESULT = {
          tag: 'fixture.gas_retry_classifier_selftest',
          data: { allMatch: gcsAllMatch, results: gcsResults }
        };
        break;
      }

      // ── rz4k.4: Sheets-menu entry points driven via their own MenuHandler.js ──
      // wrappers. Each case invokes the menu function itself — the call-site the
      // entry-point-coverage invariant scopes to — NOT the core function it
      // delegates to (driving syncAll()/ensureSheetStructure()/ArchiveManager
      // directly would not cover the menu call-site). No getUi() is reachable from
      // these wrappers (only onOpen touches UI), so they are safe in run_fixture.
      case 'menu_sync': {
        // menuSync() -> syncAll(); mirrors the sync_all fixture through the wrapper.
        menuSync();
        SpreadsheetApp.flush();
        _TF_RESULT = { tag: 'fixture.menu_sync', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'menu_ensure_sheet_structure': {
        // menuEnsureSheetStructure() -> ensureSheetStructure().
        menuEnsureSheetStructure();
        _TF_RESULT = { tag: 'fixture.menu_ensure_sheet_structure', data: { ensured: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'menu_run_archive': {
        // menuRunArchive() -> ArchiveManager.archive(getActiveSpreadsheet()).
        menuRunArchive();
        SpreadsheetApp.flush();
        _TF_RESULT = { tag: 'fixture.menu_run_archive', data: { archiveTriggered: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'menu_sync_active_doc': {
        // menuSyncActiveDoc() -> syncDocument(docId) — Docs-menu wrapper
        // call-site (gts-ez2e), distinct from the already-covered
        // syncDocument() core. doc.saveAndClose() first so syncDocument's own
        // open of testDocId doesn't lock against this dispatcher's handle.
        //
        // menuSyncActiveDoc() is a real zero-argument menu callback (production
        // API shape) so it cannot take docId as a parameter here either — it
        // resolves via DocumentApp.getActiveDocument(), which is null outside a
        // real Docs UI session. _TEST_ACTIVE_DOC_ID is the narrow, case-scoped
        // bridge for that one gap: set immediately before the call, cleared
        // immediately after in a finally, so its lifetime never spans more than
        // this single case (unlike the old dispatcher-wide TEST_DOC_ID shim).
        doc.saveAndClose();
        docAlreadyClosed = true;
        props.setProperty('_TEST_ACTIVE_DOC_ID', testDocId);
        try {
          menuSyncActiveDoc();
        } finally {
          props.deleteProperty('_TEST_ACTIVE_DOC_ID');
        }
        SpreadsheetApp.flush();
        _TF_RESULT = { tag: 'fixture.menu_sync_active_doc', data: { docId: testDocId } };
        break;
      }

      case 'menu_force_refresh_active_doc': {
        // menuForceRefreshActiveDoc() -> syncDocument(docId, {force:true}) —
        // Docs-menu "Force Refresh Style" wrapper call-site (gts-t78c),
        // distinct from the plain menuSyncActiveDoc() case above. See
        // 'menu_sync_active_doc' above for why _TEST_ACTIVE_DOC_ID exists.
        doc.saveAndClose();
        docAlreadyClosed = true;
        props.setProperty('_TEST_ACTIVE_DOC_ID', testDocId);
        try {
          menuForceRefreshActiveDoc();
        } finally {
          props.deleteProperty('_TEST_ACTIVE_DOC_ID');
        }
        SpreadsheetApp.flush();
        _TF_RESULT = { tag: 'fixture.menu_force_refresh_active_doc', data: { docId: testDocId } };
        break;
      }

      case 'menu_insert_tracker_active_doc': {
        // menuInsertTrackerActiveDoc() -> insertTrackerTable(docId) — Docs-menu
        // wrapper call-site (gts-ez2e), distinct from the already-covered
        // insertTrackerTable() core (see the 'insert_tracker_table' case above).
        // See 'menu_sync_active_doc' above for why _TEST_ACTIVE_DOC_ID exists.
        doc.saveAndClose();
        docAlreadyClosed = true;
        props.setProperty('_TEST_ACTIVE_DOC_ID', testDocId);
        try {
          menuInsertTrackerActiveDoc();
        } finally {
          props.deleteProperty('_TEST_ACTIVE_DOC_ID');
        }
        _TF_RESULT = { tag: 'fixture.menu_insert_tracker_active_doc', data: { docId: testDocId } };
        break;
      }

      case 'trash_doc': {
        var trashDocId = data.docId || testDocId;
        DriveApp.getFileById(trashDocId).setTrashed(true);
        _TF_RESULT = { tag: 'fixture.trash_doc', data: { trashed: trashDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'untrash_doc': {
        // gts-m33k: 24h aging-window guard — makes a previously-trashed doc
        // reachable again so a subsequent sync_all fixture call can prove it
        // gets revived (sync.docNotFound.revived) rather than archived.
        var untrashDocId = data.docId || testDocId;
        DriveApp.getFileById(untrashDocId).setTrashed(false);
        _TF_RESULT = { tag: 'fixture.untrash_doc', data: { untrashed: untrashDocId } };
        docAlreadyClosed = true;
        break;
      }

      case 'archive_journey': {
        ArchiveManager.archive(ss);
        _TF_RESULT = { tag: 'fixture.archive_journey', data: { archiveTriggered: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'purge_stale_test_docs': {
        // gts-4m7l durable fix: TEST corpus growth races sync_all's client
        // timeout. ArchiveManager's 24h 'Doc Not Found' grace window exists
        // for production safety (a transient Drive blip shouldn't evict a
        // doc's rows immediately) -- but on the shared TEST deployment it
        // means every trashed test doc from THIS session's pytest runs
        // lingers in Actions/DocData for a full day, so docCount (and
        // syncAll()'s real execution time) climbs steadily across a day of
        // repeated runs (observed 106 -> 171 in one session, see gts-4m7l).
        //
        // Rather than shortening the production threshold, this backdates
        // every currently-'Doc Not Found' Actions row's Date Modified past
        // the 24h window (same technique as 'backdate_action_row' above for
        // the 30-day Closed case), then runs the SAME unmodified production
        // ArchiveManager.archive() sweep. Invoked once per pytest session
        // (tests/conftest.py _purge_stale_test_docs, alongside
        // reset_test_state) so the shared corpus stays bounded per-suite
        // instead of growing unboundedly across a day of sessions.
        var pscActionsSheet = ss.getSheetByName('Actions');
        var pscBackdated = 0;
        if (pscActionsSheet) {
          var pscLastRow = pscActionsSheet.getLastRow();
          if (pscLastRow > 1) {
            var pscNumRows   = pscLastRow - 1;
            var pscStatusCol = pscActionsSheet.getRange(2, _ACOL.sync_status, pscNumRows, 1).getValues();
            var pscModCol    = pscActionsSheet.getRange(2, _ACOL.modified_date, pscNumRows, 1).getValues();
            var pscOldDate   = new Date(Date.now() - 25 * 60 * 60 * 1000); // > 24h threshold
            for (var pscI = 0; pscI < pscStatusCol.length; pscI++) {
              if (pscStatusCol[pscI][0] === 'Doc Not Found') {
                pscModCol[pscI][0] = pscOldDate;
                pscBackdated++;
              }
            }
            if (pscBackdated > 0) {
              pscActionsSheet.getRange(2, _ACOL.modified_date, pscNumRows, 1).setValues(pscModCol);
            }
          }
        }
        var pscArchivedCount = ArchiveManager.archive(ss);
        GasLogger.log('fixture.purge_stale_test_docs', { backdated: pscBackdated, archived: pscArchivedCount });
        _TF_RESULT = { tag: 'fixture.purge_stale_test_docs', data: { backdated: pscBackdated, archived: pscArchivedCount } };
        docAlreadyClosed = true;
        break;
      }

      case 'backdate_action_row': {
        var backdateGlobalId = data.globalId || '';
        var daysAgo = data.daysAgo != null ? Number(data.daysAgo) : 35;
        if (!backdateGlobalId) throw new Error('backdate_action_row: globalId required');
        var actionsSheet = ss.getSheetByName('Actions');
        if (!actionsSheet) throw new Error('backdate_action_row: Actions sheet not found');
        var existingMap = _loadExistingRowsByGlobalId(actionsSheet);
        var backdateEntry = existingMap[backdateGlobalId];
        if (!backdateEntry) throw new Error('backdate_action_row: row not found for globalId=' + backdateGlobalId);
        var backdateDate = new Date();
        backdateDate.setDate(backdateDate.getDate() - daysAgo);
        actionsSheet.getRange(backdateEntry.rowIndex, _ACOL.modified_date).setValue(backdateDate);
        // Optional gts-a8yh.2 state-probe extension: also stamp Status so the
        // row becomes ArchiveManager-eligible (_isExpired requires
        // status === 'Closed') without a second round-trip fixture call.
        if (data.status) {
          actionsSheet.getRange(backdateEntry.rowIndex, _ACOL.status).setValue(data.status);
        }
        _TF_RESULT = { tag: 'fixture.backdate_action_row', data: { globalId: backdateGlobalId, daysAgo: daysAgo } };
        docAlreadyClosed = true;
        break;
      }

      case 'archive_sweep': {
        // gts-a8yh.2 state probe: runs ArchiveManager.archive(ss) directly,
        // same call menuRunArchive() makes, without the doc-scoped ceremony
        // most other fixtures carry (archive operates sheet-wide).
        var archivedCount = ArchiveManager.archive(ss);
        docAlreadyClosed = true;
        _TF_RESULT = { tag: 'fixture.archive_sweep', data: { ok: true, archived: archivedCount } };
        break;
      }

      case 'seed_row': {
        _tfAppendSheetRow(ss, _tfSheetRow({
          globalId:      data.globalId        || '',
          id:            data.actionId        || 1,
          assigneeEmail: data.assigneeEmail   || '',
          assigneeName:  data.assigneeName    || '',
          action:        data.actionText      || 'Seeded action',
          status:        data.status          || 'Open',
          docFormula:    data.documentFormula || '',
          dateCreated:   new Date(),
          dateModified:  data.dateModified ? new Date(data.dateModified) : new Date()
        }));
        _TF_RESULT = { tag: 'fixture.seed_row', data: { appended: true } };
        break;
      }

      case 'set_status_from_preview': {
        var sspE = { parameters: { url: data.url || '', newStatus: data.newStatus || 'Open' } };
        _setStatusFromPreview(sspE, doc);
        _TF_RESULT = { tag: 'fixture.set_status_from_preview', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'process_pending_sheet_updates': {
        var ppsuE = { triggerUid: null };
        _processPendingSheetUpdates(ppsuE);
        _TF_RESULT = { tag: 'fixture.process_pending_sheet_updates', data: { ok: true } };
        docAlreadyClosed = true;
        break;
      }

      case 'mint_test_assertion': {
        // gts-79dw.4.18 test harness: mints an HS256 signed identity
        // assertion using the SAME Script Property secret
        // _verifySignedAssertion (src/AccessControl.js) reads at verify time,
        // so tests/test_*.py can construct real positive AND deliberately
        // broken negative assertions without a live NUUC-Dispatch round
        // trip. Gated the same way as every other fixture (run_fixture's
        // TEST_TOKEN check, _handleRunFixture in TestWebApp.js) -- no new
        // gating mechanism. Never returns the secret itself, only the
        // finished signed token; a missing Script Property is reported back
        // as {ok:false, error:'missing_secret'} rather than fabricated.
        var mtaResult = _tfMintAssertion({
          sub:             data.sub,
          email:           data.email,
          emailVerified:   data.emailVerified,
          aud:             data.aud,
          iss:             data.iss,
          kid:             data.kid,
          alg:             data.alg,
          exp:             data.exp,
          tamperSignature: data.tamperSignature
        });
        _TF_RESULT = { tag: 'fixture.mint_test_assertion', data: mtaResult };
        docAlreadyClosed = true;
        break;
      }

      case 'team_data_slice': {
        // Slice-BUILD for EPIC-A (gts-5r4l.2, ADR-0013).
        // Creates a sample DocData tab and performs the two durable-invariant
        // smoke checks in-process, returning results for Python assertion:
        //   (a) round-trip: rows written then read back are identical (non-date cols)
        //   (b) resolved authority: Resolved Count computed exclusively via isResolved()

        // --- DocData rows (action-status sets drive Resolved Count via isResolved()) ---
        // Row 1: matched-team doc — 2 actions (Done + Open) → 1 resolved
        // Row 2: no-team doc     — 1 action  (Open)         → 0 resolved
        // Row 3: UpdateDoc row   — 1 action  (Closed)       → 1 resolved
        var tdsActionSets = [
          ['Done', 'Open'],
          ['Open'],
          ['Closed']
        ];
        function _tdsCountResolved(statuses) {
          var n = 0;
          for (var i = 0; i < statuses.length; i++) { if (isResolved(statuses[i])) n++; }
          return n;
        }
        var tdsNow = new Date();
        var tdsDocDataRows = [
          ['doc-id-slice-001', 'Board Meeting Notes', tdsNow, tdsNow, '',          'board-folder-001', 2, _tdsCountResolved(tdsActionSets[0])],
          ['doc-id-slice-002', 'Membership Report',   tdsNow, tdsNow, '',          '',                 1, _tdsCountResolved(tdsActionSets[1])],
          ['doc-id-slice-003', 'Finance Review',      tdsNow, tdsNow, 'UpdateDoc', 'board-folder-001', 1, _tdsCountResolved(tdsActionSets[2])]
        ];
        var tdsDocHeaders = [['FileId', 'Doc Name', 'Last Sync Time', 'Doc Updated', 'SyncStatus', 'Team Id', 'Action Count', 'Resolved Count']];

        var tdsDocSheet = _getOrCreateSheet(ss, 'DocData');
        tdsDocSheet.clearContents();
        tdsDocSheet.getRange(1, 1, 1, 8).setValues(tdsDocHeaders).setFontWeight('bold');
        tdsDocSheet.getRange(2, 1, tdsDocDataRows.length, 8).setValues(tdsDocDataRows);

        // --- Round-trip smoke (a): read back non-date columns ---------------
        var tdsReadBack = tdsDocSheet.getRange(2, 1, tdsDocDataRows.length, 8).getValues();
        var tdsRTDiff = [];
        // Date cols (index 2 and 3) are skipped — GAS serialises dates; values survive.
        var tdsSkipCols = { 2: true, 3: true };
        for (var tdsR = 0; tdsR < tdsDocDataRows.length; tdsR++) {
          for (var tdsC = 0; tdsC < tdsDocDataRows[tdsR].length; tdsC++) {
            if (tdsSkipCols[tdsC]) continue;
            var tdsW = String(tdsDocDataRows[tdsR][tdsC]);
            var tdsV = String(tdsReadBack[tdsR][tdsC]);
            if (tdsW !== tdsV) {
              tdsRTDiff.push({ row: tdsR + 1, col: tdsC + 1, written: tdsW, readBack: tdsV });
            }
          }
        }

        _TF_RESULT = {
          tag: 'fixture.team_data_slice',
          data: {
            docDataRows:  tdsDocDataRows.length,
            resolvedCounts: [
              _tdsCountResolved(tdsActionSets[0]),
              _tdsCountResolved(tdsActionSets[1]),
              _tdsCountResolved(tdsActionSets[2])
            ],
            roundTripDiff: tdsRTDiff
          }
        };
        docAlreadyClosed = true;
        break;
      }

      default:
        // Unknown scenario — fall through to default (uc1_new_floating) behaviour.
        GasLogger.log('fixture.warn', {
          msg: 'Unknown scenario, falling back to default behaviour',
          scenario: resolvedScenario
        });
        _tfInsertFloatingAction(
          body,
          'AI- @test@example.com | Fix the bug | Open | 2026-01-01 | 2026-01-01'
        );
        break;
    }

    if (!docAlreadyClosed) {
      doc.saveAndClose();
    }

    // Scenario folded into the tag itself (not just the data payload) so the
    // name alone identifies which fixture ran, matching the per-scenario tags
    // already used above (fixture.uc_b_conflict, fixture.sync_status_archive, etc.)
    // instead of standing in for all of them under one generic name.
    GasLogger.log('fixture.' + resolvedScenario + '.setup', { scenario: resolvedScenario });
    // Return structured result for HTTP callers (_handleRunFixture in TestWebApp.js).
    // Playwright callers ignore the return value and use GasLogger.flush() instead.
    return _TF_RESULT || { tag: 'fixture.' + resolvedScenario, data: {} };
  } catch (outerErr) {
    // Catch errors that escape the per-scenario try blocks so the test always
    // receives a log entry instead of timing out on an empty flush.
    GasLogger.log('fixture.error', { msg: outerErr.message, scenario: resolvedScenario });
    GasLogger.log('fixture.' + resolvedScenario, { err: outerErr.message });
    return { tag: 'fixture.' + resolvedScenario, error: outerErr.message };
  } finally {
    GasLogger.flush(); // still fires after return — needed for Playwright log-polling compat
  }
}

/**
 * Combined fixture setup and sync in one invocation.
 *
 * @param {string} [scenario] - Name of the fixture scenario to set up.
 * @param {string} docId - Doc to operate on; always a real parameter.
 */
function setupAndSync(scenario, docId) {
  try {
    if (!docId) {
      GasLogger.log('sync.error', { msg: 'docId parameter not set' });
      return;
    }
    setupTestFixtures(scenario, { docId: docId });
    syncDocument(docId);
    GasLogger.log('sync.complete', { scenario: scenario });
  } finally {
    GasLogger.flush();
  }
}

// syncDocument() is defined in SyncManager.js.

// ---------------------------------------------------------------------------
// Post-sync consistency verification (test helper)
// ---------------------------------------------------------------------------

/**
 * Full-field consistency check between floating actions, ActionSheet rows, and
 * (when present) tracker-table rows.  Reads the test doc and test sheet directly
 * so all nine ActionSheet columns (including dates and Document formula) are
 * available without going through the WebApp.
 *
 * Checked invariants (floating action ↔ ActionSheet row, keyed by globalId):
 *   assigneeEmail, assigneeName — exact match
 *   action                      — exact text match
 *   status                      — exact match (default 'Open' on both sides)
 *   dateCreated, dateModified   — present and non-empty on ActionSheet row
 *   Document column display text — must equal the current document title
 *
 * When a tracker table is present, each tracker row is also verified against
 * the ActionSheet row for action and status.
 *
 * Logs verify.consistency.complete with the result object so Playwright tests
 * can poll gasLogDir and assert result.ok === true.
 *
 * @param {string} docId  Doc to verify; always a real parameter (no
 *   script-property fallback).
 * @param {?{teamId: string}} [expected]  Optional Team Scope expectation
 *   (gts-me6w.6). When expected.teamId is set, additionally asserts:
 *     - the document's Drive appProperty 'teamScope' === expected.teamId
 *     - DocData[fileId].team_id === expected.teamId
 *     - DocData[fileId] exists with doc_name, last_sync_time, action_count,
 *       resolved_count populated and consistent with the current scan
 */
function verifyConsistencyForTest(docId, expected) {
  var props        = PropertiesService.getScriptProperties();
  var resolvedDocId = docId;
  var testSheetId   = props.getProperty('TEST_SHEET_ID');

  if (!resolvedDocId || !testSheetId) {
    GasLogger.log('verify.consistency.complete', {
      ok: false,
      issues: ['docId parameter and/or TEST_SHEET_ID script property not set'],
      counts: { floating: 0, sheet: 0, tracker: 0, matched: 0, unparseable: 0 },
      docTitle: ''
    });
    GasLogger.flush();
    return {
      ok: false,
      issues: ['docId parameter and/or TEST_SHEET_ID script property not set'],
      counts: { floating: 0, sheet: 0, tracker: 0, matched: 0, unparseable: 0 },
      docTitle: ''
    };
  }

  var result = {
    ok: true,
    issues: [],
    counts: { floating: 0, sheet: 0, tracker: 0, matched: 0, unparseable: 0 },
    docTitle: ''
  };

  try {
    var doc = DocumentApp.openById(resolvedDocId);
    result.docTitle = doc.getName();

    // Collect floating actions with globalIds (reuses VerifySync.js helpers).
    var unparseableParagraphs = [];
    var floatingActions = _collectFloatingActionState(doc, unparseableParagraphs);
    result.counts.floating = floatingActions.length;

    // ADR-0027 rule 6 / gts-xvlu: a paragraph that starts a token but never
    // completes the grammar (e.g. the gts-tis pipe-delimited spelling) is
    // reported, not silently dropped from the scan.
    result.counts.unparseable = unparseableParagraphs.length;
    for (var vcfUpI = 0; vcfUpI < unparseableParagraphs.length; vcfUpI++) {
      var vcfUp = unparseableParagraphs[vcfUpI];
      result.issues.push(
        'Paragraph looks like an action but does not parse (body index ' + vcfUp.bodyChildIndex + '): ' + vcfUp.leadingText
      );
    }

    var tracker = _readTrackerTableState(doc);
    result.counts.tracker = tracker.rows.length;
    result.tracker = tracker;

    // Read ActionSheet rows directly (all 9 columns) to get dates and Document formula.
    var ss = SpreadsheetApp.openById(testSheetId);
    var actionsSheet = ss.getSheetByName('Actions');
    var sheetRows = [];
    if (actionsSheet && actionsSheet.getLastRow() > 1) {
      var numRows = actionsSheet.getLastRow() - 1;
      var data     = actionsSheet.getRange(2, 1, numRows, SHEET_HEADERS.length).getValues();
      var _VF = CONTRACT_SCHEMA.sheetAction.columnsByField;
      var formulas = actionsSheet.getRange(2, _VF.document_formula, numRows, 1).getFormulas();
      for (var i = 0; i < data.length; i++) {
        var formula = formulas[i][0] || '';
        // Extract display name from =HYPERLINK("url","title")
        var titleMatch = formula.match(/HYPERLINK\s*\(\s*"[^"]*"\s*,\s*"([^"]*)"\s*\)/i);
        sheetRows.push({
          globalId:      data[i][_VF.global_id       - 1] ? String(data[i][_VF.global_id - 1]) : '',
          id:            data[i][_VF.action_id       - 1] || '',
          assigneeEmail: data[i][_VF.assignee_email  - 1] || '',
          assigneeName:  data[i][_VF.assignee_name   - 1] || '',
          action:        data[i][_VF.action_text     - 1] || '',
          status:        data[i][_VF.status          - 1] || 'Open',
          docTitle:      titleMatch ? titleMatch[1] : '',
          dateCreated:   data[i][_VF.created_date    - 1],
          dateModified:  data[i][_VF.modified_date   - 1]
        });
      }
    }
    // Scope to the tested doc only — the ActionSheet accumulates rows from all
    // test runs, and globalId encodes the docId as the leading segment.
    sheetRows = sheetRows.filter(function(r) {
      return r.globalId.indexOf(resolvedDocId + '/') === 0;
    });
    result.counts.sheet = sheetRows.length;

    // Build set of IDs that were archived for this doc so orphan tracker rows
    // for archived actions are not reported as consistency failures.
    var archivedIds = {};
    var archiveSheet = ss.getSheetByName('Archive');
    if (archiveSheet && archiveSheet.getLastRow() > 1) {
      var archNumRows = archiveSheet.getLastRow() - 1;
      var archData    = archiveSheet.getRange(2, 1, archNumRows, 1).getValues();
      for (var ai = 0; ai < archData.length; ai++) {
        var archGid = archData[ai][0] || '';
        if (archGid.indexOf(resolvedDocId + '/') === 0) {
          archivedIds[archGid.substring(archGid.indexOf('/') + 1)] = true;
        }
      }
    }

    _runConsistencyChecks(result, floatingActions, tracker, sheetRows, result.docTitle, archivedIds);

    // DocData consistency (gts-zc21) — runs whenever a DocData row exists
    // for this doc, independent of `expected`. Verifies DocData.team_id matches
    // the document's actual teamScope appProperty, and that DocData.action_count
    // / resolved_count match BOTH the document's floating actions AND the
    // ActionSheet rows.
    var vcfDocDataRow = _readDocDataRow(ss, resolvedDocId);
    var vcfToken      = ScriptApp.getOAuthToken();
    var vcfTeamScope  = _getDocAppProperty(resolvedDocId, 'teamScope', vcfToken) || '';
    if (vcfDocDataRow) {
      if (vcfDocDataRow.teamId !== vcfTeamScope) {
        result.issues.push(
          'DocData.team_id mismatch vs teamScope appProperty: docData=' + vcfDocDataRow.teamId + ' appProperty=' + vcfTeamScope
        );
      }
      if (vcfDocDataRow.actionCount !== floatingActions.length) {
        result.issues.push(
          'DocData.action_count mismatch vs document: docData=' + vcfDocDataRow.actionCount + ' document=' + floatingActions.length
        );
      }
      if (vcfDocDataRow.actionCount !== sheetRows.length) {
        result.issues.push(
          'DocData.action_count mismatch vs sheet: docData=' + vcfDocDataRow.actionCount + ' sheet=' + sheetRows.length
        );
      }
      var vcfFloatingResolvedCount = 0;
      for (var vcfFI = 0; vcfFI < floatingActions.length; vcfFI++) {
        if (isResolved(floatingActions[vcfFI].status)) vcfFloatingResolvedCount++;
      }
      var vcfSheetResolvedCount = 0;
      for (var vcfSI = 0; vcfSI < sheetRows.length; vcfSI++) {
        if (isResolved(sheetRows[vcfSI].status)) vcfSheetResolvedCount++;
      }
      if (vcfDocDataRow.resolvedCount !== vcfFloatingResolvedCount) {
        result.issues.push(
          'DocData.resolved_count mismatch vs document: docData=' + vcfDocDataRow.resolvedCount + ' document=' + vcfFloatingResolvedCount
        );
      }
      if (vcfDocDataRow.resolvedCount !== vcfSheetResolvedCount) {
        result.issues.push(
          'DocData.resolved_count mismatch vs sheet: docData=' + vcfDocDataRow.resolvedCount + ' sheet=' + vcfSheetResolvedCount
        );
      }
    }

    // Team Scope consistency (gts-me6w.6) — only when requested.
    if (expected && expected.teamId !== undefined && expected.teamId !== null) {
      if (vcfTeamScope !== expected.teamId) {
        result.issues.push(
          'teamScope appProperty mismatch: expected=' + expected.teamId + ' actual=' + vcfTeamScope
        );
      }
      if (!vcfDocDataRow) {
        result.issues.push('DocData row missing for fileId=' + resolvedDocId);
      } else {
        if (vcfDocDataRow.teamId !== expected.teamId) {
          result.issues.push(
            'DocData.team_id mismatch: expected=' + expected.teamId + ' actual=' + vcfDocDataRow.teamId
          );
        }
        if (!vcfDocDataRow.docName) {
          result.issues.push('DocData.doc_name is empty for fileId=' + resolvedDocId);
        }
        if (!vcfDocDataRow.lastSyncTime) {
          result.issues.push('DocData.last_sync_time is empty for fileId=' + resolvedDocId);
        }
      }
    }

    result.ok = result.issues.length === 0;

    GasLogger.log('verify.consistency.complete', result);
  } catch (e) {
    result.ok = false;
    result.issues.push('Error during consistency check: ' + e.message);
    GasLogger.log('verify.consistency.complete', result);
  }

  GasLogger.flush();
  return result;
}

/**
 * Compares floating actions, tracker rows, and sheet rows for full-field agreement.
 * Appends mismatch descriptions to result.issues.
 *
 * @param {object}   result
 * @param {Array}    floatingActions  From _collectFloatingActionState.
 * @param {object}   tracker         {found, rows} from _readTrackerTableState.
 * @param {Array}    sheetRows       Direct ActionSheet read (all 9 fields + docTitle).
 * @param {string}   docTitle        Current document title from doc.getName().
 */
function _isEmailDerivedName(email, name) {
  if (!email || !name) return false;
  var derived = email.split('@')[0]
    .replace(/[._\-]+/g, ' ')
    .replace(/\b\w/g, function(c) { return c.toUpperCase(); });
  return derived === name;
}

function _runConsistencyChecks(result, floatingActions, tracker, sheetRows, docTitle, archivedIds) {
  archivedIds = archivedIds || {};
  var floatingByNrId = {};
  var sheetByNrId    = {};
  var sheetById      = {};
  var trackerById    = {};
  var i;

  for (i = 0; i < floatingActions.length; i++) {
    var f = floatingActions[i];
    if (!f.globalId) {
      result.issues.push('Floating action without globalId: ' + (f.action || '(blank)'));
      continue;
    }
    floatingByNrId[f.globalId] = f;
  }

  for (i = 0; i < sheetRows.length; i++) {
    var s = sheetRows[i];
    if (!s.globalId) continue;
    if (sheetByNrId[s.globalId]) {
      result.issues.push('Duplicate globalId in ActionSheet: ' + s.globalId);
      continue;
    }
    sheetByNrId[s.globalId] = s;
    if (s.id) sheetById[String(s.id)] = s;
  }

  if (tracker.found) {
    for (i = 0; i < tracker.rows.length; i++) {
      var t = tracker.rows[i];
      if (!t.id) {
        result.issues.push('Tracker row missing ID for action: ' + (t.action || '(blank)'));
        continue;
      }
      trackerById[String(t.id)] = t;
    }
  }

  // Check each floating action against its ActionSheet pair.
  for (var nrId in floatingByNrId) {
    if (!Object.prototype.hasOwnProperty.call(floatingByNrId, nrId)) continue;
    var floating = floatingByNrId[nrId];
    var sheet    = sheetByNrId[nrId];
    if (!sheet) {
      result.issues.push('Floating action has no ActionSheet row: ' + (floating.action || '(blank)'));
      continue;
    }

    if (floating.assigneeEmail !== sheet.assigneeEmail) {
      result.issues.push('assigneeEmail mismatch (ID ' + sheet.id + '): doc="' +
        floating.assigneeEmail + '" sheet="' + sheet.assigneeEmail + '"');
    }
    if (floating.assigneeName !== sheet.assigneeName) {
      // When sync converts a plain-text email to a PERSON chip, getName() returns ""
      // for emails not in the directory.  The sheet keeps the derived username name,
      // which is correct — skip the mismatch for this case.
      var docNameEmpty   = floating.assigneeName === '';
      var sheetDerived   = _isEmailDerivedName(floating.assigneeEmail, sheet.assigneeName);
      // gts-mpe1: a directory-resolved chip name (e.g. "Northlake
      // Minister") is propagated to the sheet on the next syncAll sweep, not
      // immediately (see SyncManager.js sync.sheet-to-doc.done note) — skip
      // this case too.
      var docResolved = !docNameEmpty && !_isEmailDerivedName(floating.assigneeEmail, floating.assigneeName);
      if (!((docNameEmpty || docResolved) && sheetDerived)) {
        result.issues.push('assigneeName mismatch (ID ' + sheet.id + '): doc="' +
          floating.assigneeName + '" sheet="' + sheet.assigneeName + '"');
      }
    }
    if (floating.action !== sheet.action) {
      result.issues.push('action mismatch (ID ' + sheet.id + '): doc="' +
        floating.action + '" sheet="' + sheet.action + '"');
    }
    var fStatus = floating.status || 'Open';
    var sStatus = sheet.status   || 'Open';
    if (fStatus !== sStatus) {
      result.issues.push('status mismatch (ID ' + sheet.id + '): doc="' +
        fStatus + '" sheet="' + sStatus + '"');
    }
    if (!sheet.dateCreated) {
      result.issues.push('dateCreated empty for ID ' + sheet.id);
    }
    if (!sheet.dateModified) {
      result.issues.push('dateModified empty for ID ' + sheet.id);
    }
    if (docTitle && sheet.docTitle && sheet.docTitle !== docTitle) {
      result.issues.push('Document title mismatch (ID ' + sheet.id + '): expected="' +
        docTitle + '" sheet="' + sheet.docTitle + '"');
    }

    if (tracker.found) {
      var trackerRow = trackerById[String(sheet.id || '')];
      if (!trackerRow) {
        result.issues.push('Tracker table missing row for ID ' + sheet.id);
      } else {
        if (trackerRow.action !== sheet.action) {
          result.issues.push('Tracker action mismatch (ID ' + sheet.id + '): tracker="' +
            trackerRow.action + '" sheet="' + sheet.action + '"');
        }
        var tStatus = trackerRow.status || 'Open';
        if (tStatus !== sStatus) {
          result.issues.push('Tracker status mismatch (ID ' + sheet.id + '): tracker="' +
            tStatus + '" sheet="' + sStatus + '"');
        }
      }
    }

    result.counts.matched++;
  }

  // ActionSheet rows with no corresponding floating action.
  for (var snrId in sheetByNrId) {
    if (!Object.prototype.hasOwnProperty.call(sheetByNrId, snrId)) continue;
    if (!floatingByNrId[snrId]) {
      var extra = sheetByNrId[snrId];
      result.issues.push('ActionSheet row ID ' + extra.id + ' has no floating action in doc');
    }
  }

  // Tracker rows with no ActionSheet row.
  // Only flag when the floating action still exists — if neither sheet nor doc has it,
  // the action was fully deleted and the stale tracker row is expected.
  if (tracker.found) {
    var floatingByAIN = {};
    for (var fgid in floatingByNrId) {
      if (!Object.prototype.hasOwnProperty.call(floatingByNrId, fgid)) continue;
      var ainMatch = fgid.match(new RegExp('\\/?((?:' + _ACTION_TOKEN_READ_PREFIXES.join('|') + ')-\\d+)$'));
      if (ainMatch) floatingByAIN[ainMatch[1]] = true;
    }
    for (var tid in trackerById) {
      if (!Object.prototype.hasOwnProperty.call(trackerById, tid)) continue;
      if (!sheetById[tid] && !archivedIds[tid] && floatingByAIN[tid]) {
        result.issues.push('Tracker row ID ' + tid + ' has no ActionSheet row');
      }
    }
  }
}

/**
 * Diagnostic: logs the body element types of the test doc to GasLogger.
 * Run via "Test: Debug Doc Body" menu item to verify fixture state.
 *
 * @param {string} testDocId  Doc to inspect; always a real parameter.
 */
function debugDocBody(testDocId) {
  var props   = PropertiesService.getScriptProperties();
  GasLogger.log('debug.props', {
    webAppUrl:    getWebAppUrl(),
    hasSecret:    !!props.getProperty('WEBAPP_SECRET'),
    testSheetId:  props.getProperty('TEST_SHEET_ID'),
    testDocId:    testDocId
  });
  var doc  = DocumentApp.openById(testDocId);
  var body = doc.getBody();
  var n    = body.getNumChildren();
  var items = [];
  for (var i = 0; i < n; i++) {
    var child = body.getChild(i);
    var type  = child.getType().toString();
    var item  = { index: i, type: type };
    var isPara = child.getType() === DocumentApp.ElementType.PARAGRAPH;
    var isList = child.getType() === DocumentApp.ElementType.LIST_ITEM;
    if (isPara || isList) {
      var para = isPara ? child.asParagraph() : child.asListItem();
      item.numChildren = para.getNumChildren();
      if (para.getNumChildren() > 0) {
        item.firstChildType = para.getChild(0).getType().toString();
        if (para.getChild(0).getType() === DocumentApp.ElementType.PERSON) {
          item.personEmail = para.getChild(0).asPerson().getEmail();
        }
      }
      item.text = para.getText().substring(0, 40);
    }
    items.push(item);
  }
  GasLogger.log('debug.docBody', { docId: testDocId, numChildren: n, items: items });
  GasLogger.flush();
}

/**
 * One-time bootstrap: sets all script properties needed for testing.
 * Run once from the Apps Script editor function picker after each fresh deploy.
 *
 * Properties set:
 *   TEST_SHEET_ID        — the bound spreadsheet used for testing
 *   GAS_LOGGER_FOLDER_ID — the Drive folder GasLogger writes .log files to
 *   TEST_ASSIGNEE_EMAIL  — email used for the chip-led list item in UC-A fixtures
 *   TEST_ASSIGNEE_NAME   — display name for the chip (optional; email used as fallback)
 *
 * Deliberately does NOT set a master-template-doc property: GAS holds no
 * script property for any doc ID (ADR-0006 §4). The master template ID lives
 * in local.settings.json (settings.testDocId) and is always passed to GAS as
 * a real parameter — including the very first beginTestSession call.
 */
function bootstrap() {
  var props = PropertiesService.getScriptProperties();
  props.setProperties({
    'TEST_SHEET_ID':        '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    'GAS_LOGGER_FOLDER_ID': '1lg2CWtOmDGglMVasSjEk3jTaW9SXcO6s',
    'TEST_ASSIGNEE_EMAIL':  'stuart.donaldson@gmail.com',
    'TEST_ASSIGNEE_NAME':   'Stuart Donaldson'
  });
  GasLogger.log('bootstrap.complete', {
    testSheetId:     '10UCsEHPL2RjA1IduUSFDSaA2lpkoCuZY79sIjratH_s',
    logFolderId:     '1lg2CWtOmDGglMVasSjEk3jTaW9SXcO6s',
    assigneeEmail:   'stuart.donaldson@gmail.com'
  });
  GasLogger.flush();
}

// ---------------------------------------------------------------------------
// Session lifecycle — named-clone fixture isolation (ATDD lifecycle §Principle 7)
// ---------------------------------------------------------------------------

/**
 * Creates a named clone of the master template doc in the same Drive folder as
 * the test sheet, and returns the clone's ID directly to the caller. GAS holds
 * no script property for any doc ID (ADR-0006 §4) — masterDocId arrives as a
 * real parameter (the webapp path: Python's settings.testDocId; the menu path:
 * whatever the human typed into TestControl!A1) and cloneId is returned
 * directly rather than staged anywhere for the caller to read back. Also
 * mirrors the clone ID to TestControl!B1 purely as a human-visible pointer for
 * manual continuation — not read back by any test path.
 *
 * @param {string} masterDocId  ID of the master template doc (read-only).
 * @return {string} The new clone's Drive file ID.
 */
function beginTestSession(masterDocId) {
  var cloneId = '';
  try {
    var props       = PropertiesService.getScriptProperties();
    var testSheetId = props.getProperty('TEST_SHEET_ID');

    var sheetFile = DriveApp.getFileById(testSheetId);
    var folderIter = sheetFile.getParents();
    var folder = folderIter.hasNext() ? folderIter.next() : null;

    if (!folder || (folder.isTrashed && folder.isTrashed())) {
      folder = DriveApp.getRootFolder();
    }

    var now      = new Date();
    var dateStr  = Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyyMMdd');
    var hexSuffix = ('000' + Math.floor(Math.random() * 0xFFFF).toString(16)).slice(-4);
    var cloneName = 'GActionSheet-Test-session-' + dateStr + '-' + hexSuffix;

    var cloneFile = DriveApp.getFileById(masterDocId).makeCopy(cloneName, folder);
    if (cloneFile.setTrashed) {
      cloneFile.setTrashed(false);
    }
    cloneId = cloneFile.getId();

    var ss   = SpreadsheetApp.openById(testSheetId);
    var ctrl = ss.getSheetByName('TestControl');
    if (ctrl) {
      ctrl.getRange('B1').setValue(cloneId);
    }

    GasLogger.log('session.begin', {
      cloneId: cloneId,
      cloneName: cloneName,
      masterDocId: masterDocId,
      folderId: folder.getId(),
      folderName: folder.getName()
    });
  } catch (err) {
    GasLogger.log('session.begin.error', { msg: err.message, masterDocId: masterDocId });
  }
  GasLogger.flush();
  return cloneId;
}

/**
 * Trashes the clone identified by cloneId and, when masterDocId is supplied,
 * restores TestControl!B1 to it (a human-visible convenience only — no test
 * path reads B1 back).
 *
 * @param {string} cloneId  Clone ID to end; always a real parameter.
 * @param {string} [masterDocId]  Master template ID to restore. The webapp
 *   path always passes this explicitly (Python already knows it from
 *   settings — no round trip needed). GAS holds no script property for it
 *   (ADR-0006 §4); the bare menuEndTestSession() call simply omits the
 *   B1 restore rather than reach for one.
 */
function endTestSession(cloneId, masterDocId) {
  try {
    var props      = PropertiesService.getScriptProperties();
    var masterId   = masterDocId || '';

    if (cloneId && cloneId !== masterId) {
      DriveApp.getFileById(cloneId).setTrashed(true);
    }
    if (masterId) {
      var testSheetId = props.getProperty('TEST_SHEET_ID');
      var ss   = testSheetId ? SpreadsheetApp.openById(testSheetId) : null;
      var ctrl = ss ? ss.getSheetByName('TestControl') : null;
      if (ctrl) {
        ctrl.getRange('B1').setValue(masterId);
      }
    }

    GasLogger.log('session.end', { cloneId: cloneId, masterDocId: masterId });
  } catch (err) {
    GasLogger.log('session.end.error', { msg: err.message });
  }
  GasLogger.flush();
}
