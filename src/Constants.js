// Constants.js — GENERATED FILE. Do not edit by hand.
// Source: assets/brand-NUUTS/deploy-brand.sh
// Regenerate: bash assets/brand-NUUTS/deploy-brand.sh

/** Base URL for product assets served via GitHub Pages. */
var _PRODUCT_DETAILS_BASE = 'https://stuartdonaldson.github.io/GActionSheet/assets/product-details/';

/** Ordered list of valid action statuses. Must match ActionSheet dropdown. */
var _ACTION_STATUSES = ['Open', 'In Progress', 'In Review', 'Done', 'Closed'];

/** Fallback image for unknown/unrecognised status values. */
var _ACTION_DEFAULT_IMAGE = _PRODUCT_DETAILS_BASE + 'status-unknown.png';

/** Status → icon URL map used by CardService buttons and Docs inline images. */
var _ACTION_STATUS_IMAGES = {
  'Open':        _PRODUCT_DETAILS_BASE + 'status-open.png',
  'In Progress': _PRODUCT_DETAILS_BASE + 'status-in-progress.png',
  'In Review':   _PRODUCT_DETAILS_BASE + 'status-review.png',
  'Done':        _PRODUCT_DETAILS_BASE + 'status-done.png',
  'Closed':      _PRODUCT_DETAILS_BASE + 'status-closed.png'
};

/** Delete button icon URL (sidebar action row). */
var _ACTION_DELETE_IMAGE = _PRODUCT_DETAILS_BASE + 'action-delete.png';

/** Add-on logo used in card headers and appsscript.json logoUrl fields. */
var _ADDON_LOGO_URL = _PRODUCT_DETAILS_BASE + 'action-item-logo.png';

/** Northlake UU emblem used as the add-on homepage logo. */
var _NORTHLAKE_UU_EMBLEM_URL = _PRODUCT_DETAILS_BASE + 'northlake-uu-emblem.png';

