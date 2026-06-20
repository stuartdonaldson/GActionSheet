#!/usr/bin/env bash
# deploy-brand.sh — Brand asset pipeline for GActionSheet / Northlake UU Tool Suite
#
# Run this whenever SVG sources change. Produces:
#   1. Runtime PNGs in assets/product-details/      (served via GitHub Pages)
#   2. Marketplace PNGs in assets/store-details/    (uploaded to GCP Marketplace SDK)
#   3. src/Constants.js                             (generated — do not edit by hand)
#   4. Patches src/appsscript.json logoUrl values
#
# Prerequisites: inkscape (1.x+)
# Usage: bash assets/brand-NUUTS/deploy-brand.sh [--dry-run]

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — update these if the repo or CDN base URL changes
# ---------------------------------------------------------------------------
GITHUB_PAGES_BASE="https://stuartdonaldson.github.io/GActionSheet/assets/product-details"

# Paths relative to repo root (script resolves from its own location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOURCE_DIR="$SCRIPT_DIR/source"
PRODUCT_DETAILS="$REPO_ROOT/assets/product-details"
STORE_DETAILS="$REPO_ROOT/assets/store-details"
CONSTANTS_JS="$REPO_ROOT/src/Constants.js"
APPSSCRIPT_JSON="$REPO_ROOT/src/appsscript.json"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

ink() {
  # Run inkscape silently; honour --dry-run
  local src="$1" dst="$2" w="${3:-}" h="${4:-}"
  local cmd=(inkscape "$src" --export-type=png --export-filename="$dst" --export-background-opacity=0)
  [[ -n "$w" ]] && cmd+=(--export-width="$w")
  [[ -n "$h" ]] && cmd+=(--export-height="$h")
  if $DRY_RUN; then
    echo "  [dry-run] ${cmd[*]}"
  else
    "${cmd[@]}" 2>/dev/null
    echo "  ✓ $(basename "$dst")"
  fi
}

# Status glyphs are drawn on a shared 56x56 canvas with a built-in margin
# (largest glyph, status-open, occupies x/y 6.5-49.5). Cropping every status
# icon to the same 6:6:50:50 box trims that dead canvas border uniformly so
# the glyphs fill more of the rendered PNG without changing their size
# relative to each other.
STATUS_CROP="6:6:50:50"

ink_status() {
  local src="$1" dst="$2"
  local cmd=(inkscape "$src" --export-type=png --export-filename="$dst" --export-background-opacity=0 --export-area="$STATUS_CROP")
  if $DRY_RUN; then
    echo "  [dry-run] ${cmd[*]}"
  else
    "${cmd[@]}" 2>/dev/null
    echo "  ✓ $(basename "$dst")"
  fi
}

echo "=== Brand deploy — GActionSheet ==="
$DRY_RUN && echo "    (dry run — no files written)"
echo

# ---------------------------------------------------------------------------
# 1. Runtime PNGs → assets/product-details/
# ---------------------------------------------------------------------------
echo "--- Runtime icons (product-details/) ---"
mkdir -p "$PRODUCT_DETAILS"

# Status icons, cropped to STATUS_CROP (see ink_status above) so the glyph
# fills more of the canvas; rendered by CardService + Docs API
ink_status "$SOURCE_DIR/status-open.svg"        "$PRODUCT_DETAILS/status-open.png"
ink_status "$SOURCE_DIR/status-in-progress.svg" "$PRODUCT_DETAILS/status-in-progress.png"
ink_status "$SOURCE_DIR/status-review.svg"      "$PRODUCT_DETAILS/status-review.png"
ink_status "$SOURCE_DIR/status-done.svg"        "$PRODUCT_DETAILS/status-done.png"
ink_status "$SOURCE_DIR/status-closed.svg"      "$PRODUCT_DETAILS/status-closed.png"
ink_status "$SOURCE_DIR/status-other.svg"       "$PRODUCT_DETAILS/status-other.png"
ink "$SOURCE_DIR/action-delete.svg"      "$PRODUCT_DETAILS/action-delete.png"

# Brand logos
ink "$SOURCE_DIR/northlake-uu-emblem.svg" "$PRODUCT_DETAILS/northlake-uu-emblem.png"
ink "$SOURCE_DIR/northlake-uu-lockup.svg" "$PRODUCT_DETAILS/northlake-uu-lockup.png"
ink "$SOURCE_DIR/action-item-logo.svg"    "$PRODUCT_DETAILS/action-item-logo.png"

echo

# ---------------------------------------------------------------------------
# 2. Marketplace PNGs → assets/store-details/
#    Sizes from GCP Marketplace SDK requirements
# ---------------------------------------------------------------------------
echo "--- Marketplace icons (store-details/) ---"
mkdir -p "$STORE_DETAILS"

ink "$SOURCE_DIR/action-item-logo.svg" "$STORE_DETAILS/icon-32.png"  32  32
ink "$SOURCE_DIR/action-item-logo.svg" "$STORE_DETAILS/icon-48.png"  48  48
ink "$SOURCE_DIR/action-item-logo.svg" "$STORE_DETAILS/icon-96.png"  96  96
ink "$SOURCE_DIR/action-item-logo.svg" "$STORE_DETAILS/icon-128.png" 128 128

echo

# ---------------------------------------------------------------------------
# 3. Generate src/Constants.js
# ---------------------------------------------------------------------------
echo "--- Writing src/Constants.js ---"

CONSTANTS_CONTENT="// Constants.js — GENERATED FILE. Do not edit by hand.
// Source: assets/brand-NUUTS/deploy-brand.sh
// Regenerate: bash assets/brand-NUUTS/deploy-brand.sh

/** Base URL for product assets served via GitHub Pages. */
var _PRODUCT_DETAILS_BASE = '${GITHUB_PAGES_BASE}/';

/** Ordered list of valid action statuses. Must match ActionSheet dropdown. */
var _ACTION_STATUSES = ['Open', 'In Progress', 'In Review', 'Done', 'Closed'];

/** Fallback image for non-standard/unrecognised status values (e.g. 'Backlog'). */
var _ACTION_DEFAULT_IMAGE = _PRODUCT_DETAILS_BASE + 'status-other.png';

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

/** Suite display name. Must match appsscript.json addOns.common.name. */
var _NORTHLAKE_UU_SUITE_NAME = 'Northlake UU Tool Suite';
"

if $DRY_RUN; then
  echo "  [dry-run] would write $CONSTANTS_JS"
else
  echo "$CONSTANTS_CONTENT" > "$CONSTANTS_JS"
  echo "  ✓ Constants.js"
fi

echo

# ---------------------------------------------------------------------------
# 4. Patch src/appsscript.json logoUrl values
# ---------------------------------------------------------------------------
echo "--- Patching src/appsscript.json ---"

ADDON_LOGO_URL="${GITHUB_PAGES_BASE}/action-item-logo.png"
EMBLEM_URL="${GITHUB_PAGES_BASE}/northlake-uu-emblem.png"

if $DRY_RUN; then
  echo "  [dry-run] would set common.logoUrl → $EMBLEM_URL"
  echo "  [dry-run] would set createActionTriggers[0].logoUrl → $ADDON_LOGO_URL"
  echo "  [dry-run] would set linkPreviewTriggers[0].logoUrl → $ADDON_LOGO_URL"
else
  if command -v jq &>/dev/null; then
    jq \
      --arg emblem "$EMBLEM_URL" \
      --arg logo "$ADDON_LOGO_URL" \
      '.addOns.common.logoUrl = $emblem |
       .addOns.docs.createActionTriggers[0].logoUrl = $logo |
       .addOns.docs.linkPreviewTriggers[0].logoUrl = $logo' \
      "$APPSSCRIPT_JSON" > "${APPSSCRIPT_JSON}.tmp" && mv "${APPSSCRIPT_JSON}.tmp" "$APPSSCRIPT_JSON"
    echo "  ✓ appsscript.json (via jq)"
  else
    # jq not available — sed fallback (fragile; install jq for reliability).
    # Match by filename suffix (not a fixed old base URL) so this stays
    # idempotent whether appsscript.json currently points at the legacy
    # raw.githubusercontent.com/brand-NUTS URLs or the current
    # product-details/ GitHub Pages URLs.
    sed -i \
      "s|https://[^\"]*/action-item-logo\.png|${ADDON_LOGO_URL}|g" \
      "$APPSSCRIPT_JSON"
    sed -i \
      "s|https://[^\"]*/northlake-uu-emblem\.png|${EMBLEM_URL}|g" \
      "$APPSSCRIPT_JSON"
    echo "  ✓ appsscript.json (via sed fallback)"
  fi
fi

echo
echo "=== Done. Commit assets/product-details/, assets/store-details/, src/Constants.js, src/appsscript.json ==="
echo "    Then push + deploy: npm run deploy:test"
