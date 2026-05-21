/**
 * DocumentDiscovery.js
 *
 * Scans a Drive folder tree for Google Docs modified within the last 7 days.
 *
 * Requirements §13 (discovery), §12.5–6.
 *
 * Usage:
 *   var docs = DocumentDiscovery.findModifiedDocs();          // uses DOC_FOLDER_ID property
 *   var docs = DocumentDiscovery.findModifiedDocs(folderId);  // explicit folder
 *
 * Returns an array of:
 *   { id: string, title: string, url: string, dateModified: Date }
 */
var DocumentDiscovery = (function () {

  var SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
  var GDOC_MIME = 'application/vnd.google-apps.document';

  /**
   * Extracts a Drive folder ID from either a plain ID string or a full URL.
   *
   * Examples handled:
   *   "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
   *   "https://drive.google.com/drive/folders/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
   *
   * @param {string} folderIdOrUrl
   * @returns {string}
   */
  function _extractFolderId(folderIdOrUrl) {
    if (!folderIdOrUrl) return '';
    var m = /\/folders\/([a-zA-Z0-9_-]+)/.exec(folderIdOrUrl);
    return m ? m[1] : folderIdOrUrl;
  }

  /**
   * Recursively collects Google Docs modified within the last 7 days from
   * the given folder and all descendant folders.
   *
   * @param {Folder}  folder     Drive folder to search.
   * @param {Date}    threshold  Earliest acceptable last-modified date.
   * @param {Array}   results    Accumulator array (mutated in place).
   */
  function _collectDocs(folder, threshold, results) {
    // Files in this folder.
    var files = folder.getFiles();
    while (files.hasNext()) {
      var file = files.next();
      if (file.getMimeType() !== GDOC_MIME) continue;
      var lastUpdated = file.getLastUpdated();
      if (lastUpdated >= threshold) {
        results.push({
          id:           file.getId(),
          title:        file.getName(),
          url:          file.getUrl(),
          dateModified: lastUpdated
        });
      }
    }

    // Recurse into sub-folders.
    var subFolders = folder.getFolders();
    while (subFolders.hasNext()) {
      _collectDocs(subFolders.next(), threshold, results);
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Finds Google Docs modified in the last 7 days within the configured
     * folder tree.
     *
     * @param {string} [folderId]  Drive folder ID or URL.  Falls back to the
     *                             DOC_FOLDER_ID script property.
     * @returns {Array}  Array of { id, title, url, dateModified }.
     */
    findModifiedDocs: function (folderId) {
      var rawId = folderId
        || PropertiesService.getScriptProperties().getProperty('DOC_FOLDER_ID')
        || '';

      var resolvedId = _extractFolderId(rawId);
      if (!resolvedId) {
        throw new Error('DOC_FOLDER_ID is not set and no folderId was provided.');
      }

      var folder = DriveApp.getFolderById(resolvedId);
      var threshold = new Date(Date.now() - SEVEN_DAYS_MS);
      var results = [];

      _collectDocs(folder, threshold, results);

      GasLogger.log('discovery.complete', { count: results.length });
      return results;
    }
  };
})();
