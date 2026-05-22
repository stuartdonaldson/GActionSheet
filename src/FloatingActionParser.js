/**
 * FloatingActionParser.js
 *
 * Parses floating action items from a Google Doc body.
 *
 * Floating action format (requirements §7):
 *   AI-<optional integer> <assignee token> | action | status | date created | date modified
 *
 * Assignee token forms:
 *   1. Bare email:      @user@example.com
 *   2. Display-name:    @Display Name <email@example.com>
 *   3. Mention chip:    a Person chip element — extract via getType() == DocumentApp.ElementType.PERSON
 *
 * Returns an IIFE exposing { parse }.
 */
var FloatingActionParser = (function () {

  /**
   * Regex: matches the AI- prefix with optional integer.
   * Group 1: the integer string (may be undefined/empty).
   * Remainder of the string after group 1 is the assignee + fields portion.
   */
  var AI_PREFIX_RE = /^AI-(\d*|#)\s+/;

  /** Matches a bare AI-<n> reference (just the ID, nothing else). Group 1: digits. */
  var BARE_REF_RE = /^AI-(\d+)\s*$/;

  /**
   * Regex for display-name form: @First Last <email@example.com>
   * Group 1: display name (trimmed)
   * Group 2: email address
   */
  var DISPLAY_NAME_RE = /^@(.+?)\s+<([^>]+)>/;

  /**
   * Regex for bare-email form: user@example.com or @user@example.com
   * Group 1: email address (local-part + @ + domain, no whitespace/pipe/angle)
   * The leading @ prefix is optional; excluded from the captured group.
   */
  var BARE_EMAIL_RE = /^@?([^\s|<>@]+@[^\s|<>]+)/;

  /**
   * Parses a date string. Returns a Date object, or null if blank/invalid.
   * @param {string} s
   * @returns {Date|null}
   */
  function _parseDate(s) {
    if (!s || s.trim() === '') return null;
    var d = new Date(s.trim());
    return isNaN(d.getTime()) ? null : d;
  }

  /**
   * Attempts to extract an assignee from a text string that starts immediately
   * after the AI- prefix and integer/space portion.
   *
   * Returns { assigneeEmail, assigneeName, rest } where rest is the remainder
   * of the line after the assignee token (starting with ' | ' or end-of-string).
   * Returns null if no valid assignee token is found.
   *
   * @param {string} text  The post-prefix portion of the paragraph text.
   * @returns {{ assigneeEmail: string, assigneeName: string, rest: string }|null}
   */
  function _parseAssigneeFromText(text) {
    var dm = DISPLAY_NAME_RE.exec(text);
    if (dm) {
      return {
        assigneeEmail: dm[2].trim(),
        assigneeName: dm[1].trim(),
        rest: text.slice(dm[0].length)
      };
    }

    var bm = BARE_EMAIL_RE.exec(text);
    if (bm) {
      return {
        assigneeEmail: bm[1].trim(),
        assigneeName: '',
        rest: text.slice(bm[0].length)
      };
    }

    return null;
  }

  /**
   * Parses one Paragraph element into an action object, or returns null if it
   * is not a valid floating action. Paragraphs with AI- prefix but no
   * recognisable assignee token are treated as non-action content and skipped.
   *
   * @param {Paragraph} para      A DocumentApp Paragraph element.
   * @param {number}    paraIndex Zero-based index of the paragraph in body.getParagraphs().
   * @param {string}    docId     Drive document ID (for skip log payload).
   * @returns {object|null}
   */
  function _parseParagraph(para, paraIndex, docId) {
    var text = para.getText();

    // Bare AI-<n> reference — just the ID, no assignee or fields (UC-5).
    var bareMatch = BARE_REF_RE.exec(text);
    if (bareMatch) {
      return { id: parseInt(bareMatch[1], 10), referenceOnly: true, paragraphIndex: paraIndex };
    }

    // Must start with AI-
    var prefixMatch = AI_PREFIX_RE.exec(text);
    if (!prefixMatch) return null;

    var idStr = prefixMatch[1];                      // '', '#', or digit string
    var id = (idStr && idStr.length > 0 && idStr !== '#') ? parseInt(idStr, 10) : null;
    var afterPrefix = text.slice(prefixMatch[0].length);

    // --- Attempt to find a mention chip before falling back to text parsing ---
    // Mention chips are Person elements embedded in the paragraph.
    // We scan the paragraph's child elements for a PERSON element that
    // appears in the assignee position (before the first ' | ').
    var assigneeEmail = '';
    var assigneeName = '';
    var restAfterAssignee = afterPrefix;
    var foundChip = false;

    var numChildren = para.getNumChildren();
    for (var ci = 0; ci < numChildren; ci++) {
      var child = para.getChild(ci);
      if (child.getType() === DocumentApp.ElementType.PERSON) {
        // Person element found — this is the mention chip assignee.
        assigneeEmail = child.getEmail ? child.getEmail() : '';
        assigneeName = child.getName ? child.getName() : '';
        // The rest of the line is everything after the chip in the text.
        // We locate the chip boundary by finding the first ' | ' in afterPrefix.
        var pipeIdx = afterPrefix.indexOf(' | ');
        restAfterAssignee = pipeIdx >= 0 ? afterPrefix.slice(pipeIdx) : '';
        foundChip = true;
        break;
      }
    }

    if (!foundChip) {
      // Pipe-prefixed format: "AI-N | [email] | action | ..."
      // The assignee field is separated by leading ' | ' rather than a space.
      if (afterPrefix.charAt(0) === '|') {
        var pipeParts = afterPrefix.slice(1).split(' | ');
        assigneeEmail = pipeParts[0].trim().replace(/^@/, '');
        assigneeName = '';
        var piFields = ['', '', '', ''];
        for (var pf = 0; pf < 4 && (pf + 1) < pipeParts.length; pf++) {
          piFields[pf] = pipeParts[pf + 1].trim();
        }
        return {
          id: id,
          assigneeEmail: assigneeEmail,
          assigneeName: assigneeName,
          action: piFields[0],
          status: piFields[1],
          dateCreated: _parseDate(piFields[2]),
          dateModified: _parseDate(piFields[3]),
          paragraphIndex: paraIndex
        };
      }

      // AI-# placeholder: old unnumbered-action marker — treat as blank assignee.
      if (/^AI-#(\s|$)/.test(afterPrefix)) {
        var hashPipe = afterPrefix.indexOf(' | ');
        assigneeEmail = '';
        assigneeName = '';
        restAfterAssignee = hashPipe >= 0 ? afterPrefix.slice(hashPipe) : '';
      } else {
        // No mention chip — parse the assignee from the text portion.
        var parsed = _parseAssigneeFromText(afterPrefix);
        if (!parsed) {
          // No valid assignee token — treat as non-action content, skip silently.
          if (typeof GasLogger !== 'undefined' && GasLogger && typeof GasLogger.log === 'function') {
            GasLogger.log('sync.skip', { reason: 'invalid-email-token', docId: docId || '', paragraph: text });
          }
          return null;
        }
        assigneeEmail = parsed.assigneeEmail;
        assigneeName = parsed.assigneeName;
        restAfterAssignee = parsed.rest;
      }
    }

    // Now split the remainder by ' | ' to extract the pipe-delimited fields.
    // restAfterAssignee may start with ' | ' or be empty.
    var fields = ['', '', '', ''];  // action, status, dateCreated, dateModified
    if (restAfterAssignee.indexOf(' | ') === 0) {
      var fieldStr = restAfterAssignee.slice(3);  // drop the leading ' | '
      var parts = fieldStr.split(' | ');
      for (var fi = 0; fi < parts.length && fi < fields.length; fi++) {
        fields[fi] = parts[fi].trim();
      }
    }

    var action      = fields[0];
    var status      = fields[1];
    var dateCreated  = _parseDate(fields[2]);
    var dateModified = _parseDate(fields[3]);

    return {
      id: id,
      assigneeEmail: assigneeEmail,
      assigneeName: assigneeName,
      action: action,
      status: status,
      dateCreated: dateCreated,
      dateModified: dateModified,
      paragraphIndex: paraIndex
    };
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Parses all floating actions from the document body.
     * AI- paragraphs with no recognisable assignee token are skipped (logged).
     *
     * @param {Document} doc  An open DocumentApp Document.
     * @returns {Array} Array of action objects:
     *   { id, assigneeEmail, assigneeName, action, status,
     *     dateCreated, dateModified, paragraphIndex }
     */
    parse: function (doc) {
      var docId = doc.getId ? doc.getId() : '';
      var body = doc.getBody();
      var paras = body.getParagraphs();
      var actions = [];

      for (var i = 0; i < paras.length; i++) {
        // Skip paragraphs inside table cells — body.getParagraphs() returns
        // all paragraphs including table cell contents, but floating actions
        // only appear in the main body flow.
        var parent = paras[i].getParent();
        if (parent && parent.getType() === DocumentApp.ElementType.TABLE_CELL) {
          continue;
        }
        var result = _parseParagraph(paras[i], i, docId);
        if (result !== null) {
          actions.push(result);
        }
      }

      return actions;
    }
  };
})();
