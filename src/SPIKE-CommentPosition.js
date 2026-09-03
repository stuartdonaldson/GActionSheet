/**
 * SPIKE-CommentPosition.js — Spike gts-6ls9: is comment-to-document-position
 * resolution feasible beyond quoted text?
 *
 * Prompted by a real export (/mnt/c/tmp/2025-09-26_Stuart-Test-governance.json)
 * where 100% of comments (57/57) have `quoted_text: null` from the Drive
 * Comments API v3, including comments that plainly refer to specific text.
 * docs/procedure-exporter.md §10.1 treats the Drive `anchor` field as an
 * undecodable opaque ID and relies entirely on Drive-supplied quoted text.
 * This spike checks whether any other supported signal exists before
 * anything gets built. Findings recorded in docs/procedure-exporter.md
 * §10.1 (new subsection), not in this file.
 *
 * Set SPIKE_COMMENT_POSITION_ENABLED = false to keep the route inert in real
 * deployments (same pattern as SPIKE_ENABLED in SPIKE.js). Every op here is
 * read-only against the target doc except 'create_test_comment', which
 * inserts one throwaway comment (op 'delete_test_comment' removes it).
 *
 * doPost action 'spike_comment_position' — body { op, docId, commentId?,
 * quoteText?, insertBeforeIndex?, insertText? }.
 */

var SPIKE_COMMENT_POSITION_ENABLED = false;

/**
 * @param {Object} payload
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function _handleSpikeCommentPosition(payload) {
  var op    = payload.op    || 'inspect';
  var docId = payload.docId || '';

  if (!docId) {
    return _jsonResponse({ error: 'docId required', op: op });
  }

  var result;
  try {
    switch (op) {
      case 'inspect':               result = _spikeCpInspect(docId); break;
      case 'docs_api_probe':        result = _spikeCpDocsApiProbe(docId); break;
      case 'anchor_structure':      result = _spikeCpAnchorStructure(docId); break;
      case 'gemini_recheck':        result = _spikeCpGeminiRecheck(docId); break;
      case 'toc_probe':             result = _spikeCpTocProbe(docId); break;
      case 'docx_export_probe':     result = _spikeCpDocxExportProbe(docId); break;
      case 'revision_history_probe': result = _spikeCpRevisionHistoryProbe(docId); break;
      case 'create_test_comment':   result = _spikeCpCreateTestComment(docId, payload); break;
      case 'refetch_comment':       result = _spikeCpRefetchComment(docId, payload.commentId); break;
      case 'delete_test_comment':   result = _spikeCpDeleteTestComment(docId, payload.commentId); break;
      default:
        return _jsonResponse({ error: 'unknown op: ' + op, op: op });
    }
  } catch (e) {
    GasLogger.log('webapp.spike.commentposition.error', { op: op, docId: docId, message: String(e) });
    return _jsonResponse({ error: String(e), op: op, docId: docId });
  }

  GasLogger.log('webapp.spike.commentposition', { op: op, docId: docId });
  GasLogger.flush();
  result.op = op;
  result.docId = docId;
  return _jsonResponse(result);
}

/**
 * Candidate 4: does re-requesting with different Comments.list parameters
 * or a different API version change the null-quotedFileContent result?
 * Compares Drive v3 Comments.list against Drive v2 Comments.list (the
 * legacy Comments resource, which used a `context` field instead of
 * `quotedFileContent`) for the same file, side by side.
 */
function _spikeCpInspect(docId) {
  var v3 = DriveV3.Comments.list(docId, {
    fields: 'nextPageToken,comments(id,content,createdTime,anchor,quotedFileContent(mimeType,value))',
    includeDeleted: false,
    pageSize: 100
  });

  var v3Comments = (v3.comments || []).map(function(c) {
    return {
      id: c.id,
      anchor: c.anchor || null,
      quotedFileContent: c.quotedFileContent || null
    };
  });

  var v2Comments = null;
  var v2Error = null;
  try {
    var v2 = Drive.Comments.list(docId, { maxResults: 100 });
    v2Comments = (v2.items || []).map(function(c) {
      return {
        commentId: c.commentId,
        anchor: c.anchor || null,
        context: c.context || null,
        status: c.status || null
      };
    });
  } catch (e) {
    v2Error = String(e);
  }

  return {
    v3_total: v3Comments.length,
    v3_null_quoted: v3Comments.filter(function(c) { return !c.quotedFileContent; }).length,
    v3_sample: v3Comments.slice(0, 5),
    v2_error: v2Error,
    v2_total: v2Comments ? v2Comments.length : null,
    v2_null_context: v2Comments ? v2Comments.filter(function(c) { return !c.context; }).length : null,
    v2_sample: v2Comments ? v2Comments.slice(0, 5) : null
  };
}

/**
 * Candidate 1: does the Docs API (documents.get) expose anything
 * comment-related at all — a comment id, a range, an anchor cross-reference?
 * Docs API v1's public surface is documented as having no comment
 * representation (comments are Drive-only); this walks the actual response
 * for any key containing "comment" or "anchor" rather than trusting that
 * documentation claim blind.
 */
function _spikeCpDocsApiProbe(docId) {
  var doc = Docs.Documents.get(docId, {
    suggestionsViewMode: 'SUGGESTIONS_INLINE',
    includeTabsContent: true
  });

  var hits = [];
  function walk(node, path) {
    if (node === null || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (var i = 0; i < node.length && i < 500; i++) walk(node[i], path + '[' + i + ']');
      return;
    }
    for (var key in node) {
      if (/comment|anchor/i.test(key)) {
        hits.push({ path: path + '.' + key, keyOnly: key });
      }
      walk(node[key], path + '.' + key);
    }
  }
  walk(doc, 'document');

  return {
    revisionId: doc.revisionId || null,
    topLevelKeys: Object.keys(doc),
    commentOrAnchorKeyHits: hits.slice(0, 25),
    commentOrAnchorKeyHitCount: hits.length
  };
}

/**
 * Candidate 3: does the opaque anchor string ("kix.<id>") have any
 * decodable structure? Pulls every anchor in the doc and checks for
 * (a) a shared prefix scheme, (b) any correlation between anchor value and
 * comment creation order / quoted-text presence, without assuming either
 * way.
 */
function _spikeCpAnchorStructure(docId) {
  var v3 = DriveV3.Comments.list(docId, {
    fields: 'comments(id,createdTime,anchor,quotedFileContent(value))',
    includeDeleted: false,
    pageSize: 100
  });
  var comments = (v3.comments || []).map(function(c) {
    return {
      id: c.id,
      createdTime: c.createdTime,
      anchor: c.anchor || null,
      hasQuotedText: !!(c.quotedFileContent && c.quotedFileContent.value)
    };
  }).sort(function(a, b) { return (a.createdTime || '').localeCompare(b.createdTime || ''); });

  var anchors = comments.map(function(c) { return c.anchor; }).filter(Boolean);
  var forms = {};
  anchors.forEach(function(a) {
    // classify: legacy revision-anchor JSON (starts with '{') vs kix.<token>
    var form = a.indexOf('{') === 0 ? 'json_revision_anchor' : (a.indexOf('kix.') === 0 ? 'kix_token' : 'other');
    forms[form] = (forms[form] || 0) + 1;
  });

  return {
    total_comments: comments.length,
    total_with_anchor: anchors.length,
    anchor_forms: forms,
    ordered_by_created_time: comments
  };
}

/**
 * Candidate 3 continued (stability probe): insert a throwaway comment
 * anchored to a specific, known quote via Comments.insert, capturing its
 * anchor immediately post-creation. A follow-up 'refetch_comment' call
 * after an independent doc edit (made via the Docs API, elsewhere) checks
 * whether the anchor value is stable across edits (a real position/range
 * encoding would need to shift; an opaque object-reference ID would not).
 */
function _spikeCpCreateTestComment(docId, payload) {
  var quoteText = payload.quoteText || '';
  if (!quoteText) throw new Error('quoteText required for create_test_comment');

  var inserted = DriveV3.Comments.create(
    {
      content: '[SPIKE gts-6ls9] throwaway test comment — safe to delete',
      quotedFileContent: { value: quoteText }
    },
    docId,
    { fields: 'id,anchor,quotedFileContent' }
  );

  return {
    commentId: inserted.id,
    anchor_at_creation: inserted.anchor || null,
    quotedFileContent: inserted.quotedFileContent || null
  };
}

function _spikeCpRefetchComment(docId, commentId) {
  if (!commentId) throw new Error('commentId required for refetch_comment');
  var c = DriveV3.Comments.get(docId, commentId, { fields: 'id,anchor,quotedFileContent' });
  return {
    commentId: c.id,
    anchor_now: c.anchor || null,
    quotedFileContent: c.quotedFileContent || null
  };
}

/**
 * Re-check (gts-6ls9 reopened) against two specific candidate mechanisms
 * an external review (Gemini) proposed that the original spike's candidates
 * 3/4 tested at a coarser grain than these exact claims:
 *
 *  A. `includeDeleted: true` on Comments.list changing quotedFileContent
 *     null-ness. The original _spikeCpInspect/_spikeCpAnchorStructure both
 *     hardcoded includeDeleted: false — this was never literally varied.
 *  B. The `anchor` field, when it takes the "legacy JSON" form (starts with
 *     '{', already classified as `json_revision_anchor` by
 *     _spikeCpAnchorStructure), decodes via JSON.parse into an object with
 *     an `m` key that is itself a JSON string containing a `q` key holding
 *     the raw quoted text. Runs the exact parse Gemini described and
 *     reports what's actually in there for every anchor of that form found
 *     on the live document — not assumed either way.
 */
function _spikeCpGeminiRecheck(docId) {
  var withoutDeleted = DriveV3.Comments.list(docId, {
    fields: 'comments(id,anchor,quotedFileContent(value),resolved,deleted)',
    includeDeleted: false,
    pageSize: 100
  });
  var withDeleted = DriveV3.Comments.list(docId, {
    fields: 'comments(id,anchor,quotedFileContent(value),resolved,deleted)',
    includeDeleted: true,
    pageSize: 100
  });

  var countNullQuoted = function(resp) {
    return (resp.comments || []).filter(function(c) {
      return !(c.quotedFileContent && c.quotedFileContent.value);
    }).length;
  };

  var anchorDecodeAttempts = (withDeleted.comments || []).map(function(c) {
    var attempt = { commentId: c.id, anchorRaw: c.anchor || null, form: null, mParsed: false, qFound: null, parseError: null };
    if (!c.anchor) { attempt.form = 'no_anchor'; return attempt; }
    if (c.anchor.indexOf('{') !== 0) { attempt.form = 'kix_token_or_other'; return attempt; }
    attempt.form = 'json_revision_anchor';
    try {
      var anchorObj = JSON.parse(c.anchor);
      attempt.topLevelKeys = Object.keys(anchorObj);
      if (typeof anchorObj.m === 'string') {
        attempt.mParsed = true;
        var parsedModel = JSON.parse(anchorObj.m);
        attempt.modelKeys = Object.keys(parsedModel);
        if (typeof parsedModel.q === 'string') {
          attempt.qFound = parsedModel.q;
        }
      }
    } catch (e) {
      attempt.parseError = String(e);
    }
    return attempt;
  });

  return {
    includeDeleted_false: {
      total: (withoutDeleted.comments || []).length,
      null_quoted: countNullQuoted(withoutDeleted)
    },
    includeDeleted_true: {
      total: (withDeleted.comments || []).length,
      null_quoted: countNullQuoted(withDeleted),
      deleted_count: (withDeleted.comments || []).filter(function(c) { return c.deleted === true; }).length
    },
    includeDeleted_changed_result: countNullQuoted(withoutDeleted) !== countNullQuoted(withDeleted),
    anchor_json_revision_form_count: anchorDecodeAttempts.filter(function(a) { return a.form === 'json_revision_anchor'; }).length,
    anchor_m_parsed_count: anchorDecodeAttempts.filter(function(a) { return a.mParsed; }).length,
    anchor_q_found_count: anchorDecodeAttempts.filter(function(a) { return a.qFound !== null; }).length,
    anchor_decode_attempts: anchorDecodeAttempts
  };
}

/**
 * gts-6cq2 follow-up: what does a live tableOfContents structural element's
 * paragraph content actually contain — specifically, does a TOC entry's
 * page-number run carry an internal link (headingId/bookmarkId) back to the
 * target heading, or just plain autoText? Read-only probe, one document,
 * before designing the toc_entry contract.
 */
function _spikeCpTocProbe(docId) {
  var apiDoc = Docs.Documents.get(docId, { includeTabsContent: true });
  var tabs = (apiDoc.tabs || []).length ? apiDoc.tabs : [{ documentTab: { body: apiDoc.body } }];
  var found = [];

  tabs.forEach(function(tab) {
    var body = (tab.documentTab && tab.documentTab.body && tab.documentTab.body.content) || [];
    body.forEach(function(se) {
      if (!se.tableOfContents) return;
      (se.tableOfContents.content || []).slice(0, 6).forEach(function(item) {
        if (!item.paragraph) return;
        found.push({
          startIndex: item.startIndex,
          endIndex: item.endIndex,
          namedStyle: item.paragraph.paragraphStyle && item.paragraph.paragraphStyle.namedStyleType,
          elements: (item.paragraph.elements || []).map(function(pe) {
            return {
              textRun: pe.textRun ? {
                content: pe.textRun.content,
                link: (pe.textRun.textStyle && pe.textRun.textStyle.link) || null
              } : undefined,
              autoText: pe.autoText || undefined
            };
          })
        });
      });
    });
  });

  return { tocEntriesFound: found.length, sample: found };
}

/**
 * gts-283i follow-up candidate: does exporting the doc to .docx (OOXML)
 * expose comment anchors as real position-encoded ranges
 * (w:commentRangeStart/End tied to actual runs in word/document.xml),
 * unlike the Drive Comments API's opaque kix.<token> anchor (candidate 3
 * above, confirmed no positional structure)? Read-only: a Drive export,
 * no mutation of the source doc.
 */
function _spikeCpDocxExportProbe(docId) {
  var url = 'https://www.googleapis.com/drive/v3/files/' + docId +
    '/export?mimeType=' + encodeURIComponent(
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
  var resp = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    return { error: 'export failed: ' + resp.getResponseCode(), body: resp.getContentText().slice(0, 500) };
  }

  var blob  = resp.getBlob().setName('export.docx').setContentType('application/zip');
  var parts = Utilities.unzip(blob);
  var files = {};
  parts.forEach(function(p) { files[p.getName()] = p; });

  var result = {
    docxBytes: blob.getBytes().length,
    zipEntryCount: parts.length,
    hasDocumentXml: !!files['word/document.xml'],
    hasCommentsXml: !!files['word/comments.xml']
  };

  if (files['word/document.xml']) {
    var docXml = files['word/document.xml'].getDataAsString('UTF-8');
    result.commentRangeStartCount = (docXml.match(/<w:commentRangeStart/g) || []).length;
    result.commentRangeEndCount   = (docXml.match(/<w:commentRangeEnd/g) || []).length;
    result.commentReferenceCount  = (docXml.match(/<w:commentReference/g) || []).length;
    // Sample the first range pair to eyeball whether it actually wraps real
    // text runs, rather than trusting the tag-count alone.
    var m = docXml.match(/<w:commentRangeStart w:id="(\d+)"\s*\/>([\s\S]{0,400}?)<w:commentRangeEnd w:id="\1"\s*\/>/);
    result.firstRangeSample = m ? { id: m[1], wrappedXmlSnippet: m[2].slice(0, 400) } : null;
  }

  if (files['word/comments.xml']) {
    var commentsXml = files['word/comments.xml'].getDataAsString('UTF-8');
    result.commentsXmlEntryCount = (commentsXml.match(/<w:comment /g) || []).length;
    var firstComment = commentsXml.match(/<w:comment [^>]*>([\s\S]{0,600}?)<\/w:comment>/);
    result.firstCommentSample = firstComment ? firstComment[0].slice(0, 600) : null;
  }

  return result;
}

/**
 * gts-283i follow-up candidate: is Drive's own version history (the
 * Revisions resource — distinct from Docs suggestions/track-changes, which
 * documents.get already returns inline via suggestionsViewMode) available
 * for this doc, and does it carry fetchable per-revision content?
 */
function _spikeCpRevisionHistoryProbe(docId) {
  var listUrl = 'https://www.googleapis.com/drive/v3/files/' + docId +
    '/revisions?fields=' + encodeURIComponent(
      'revisions(id,modifiedTime,lastModifyingUser(displayName),keepForever,exportLinks)');
  var resp = UrlFetchApp.fetch(listUrl, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    return { error: 'revisions.list failed: ' + resp.getResponseCode(), body: resp.getContentText().slice(0, 500) };
  }
  var revisions = (JSON.parse(resp.getContentText()).revisions || []);
  return {
    revisionCount: revisions.length,
    withExportLinks: revisions.filter(function(r) { return !!r.exportLinks; }).length,
    withKeepForever: revisions.filter(function(r) { return !!r.keepForever; }).length,
    sample: revisions.slice(0, 5).map(function(r) {
      return {
        id: r.id,
        modifiedTime: r.modifiedTime,
        lastModifyingUser: r.lastModifyingUser ? r.lastModifyingUser.displayName : null,
        keepForever: !!r.keepForever,
        hasExportLinks: !!r.exportLinks
      };
    })
  };
}

function _spikeCpDeleteTestComment(docId, commentId) {
  if (!commentId) throw new Error('commentId required for delete_test_comment');
  DriveV3.Comments.delete(docId, commentId);
  return { deleted: commentId };
}
