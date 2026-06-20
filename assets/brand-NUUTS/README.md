# Brand Assets — Northlake UU Tool Suite (NUUTS)

This folder contains all brand source materials for the GActionSheet add-on.
Run `deploy-brand.sh` whenever SVG sources change to regenerate all derived assets.

## Folder layout

```
brand-NUUTS/
├── deploy-brand.sh              ← brand asset pipeline (run this)
├── README.md                    ← this file
├── source/                      ← SVG source files (edit these)
│   ├── action-item-logo.svg     ← add-on logo / product icon
│   ├── northlake-uu-emblem.svg  ← Northlake UU circular emblem
│   ├── northlake-uu-lockup.svg  ← full wordmark lockup
│   ├── status-open.svg
│   ├── status-in-progress.svg
│   ├── status-review.svg
│   ├── status-done.svg
│   ├── status-closed.svg
│   ├── status-other.svg         ← fallback for non-standard/unrecognised status
│   └── action-delete.svg        ← delete button icon (sidebar)
├── Design language and logo requirements.zip
└── Northlake-UU-Tool-Suite-Marks.pptx
```

Generated outputs (not edited by hand):

| Output folder | Purpose | Served by |
|---------------|---------|-----------|
| `assets/product-details/` | Runtime icons used by the add-on UI | GitHub Pages |
| `assets/store-details/icon-*.png` | Marketplace listing icons | GCP Console upload |
| `src/Constants.js` | GAS URL constants for all icon references | GAS runtime |
| `src/appsscript.json` | Add-on manifest logoUrl values | GAS manifest |

---

## Running the brand pipeline

Prerequisites: Inkscape 1.x, jq

```bash
# From repo root
bash assets/brand-NUUTS/deploy-brand.sh

# Preview without writing files
bash assets/brand-NUUTS/deploy-brand.sh --dry-run
```

After running, commit all changed files and deploy:

```bash
git add assets/product-details/ assets/store-details/ src/Constants.js src/appsscript.json
git commit -m "chore(brand): regenerate assets"
npm run deploy:test
```

---

## GCP Marketplace SDK — upload guide

The marketplace icon slots require specific PNG sizes. After running `deploy-brand.sh`,
upload from `assets/store-details/`:

| GCP Console field | File | Size |
|-------------------|------|------|
| Small icon | `icon-32.png` | 32 × 32 px |
| Medium icon | `icon-48.png` | 48 × 48 px |
| Large icon | `icon-96.png` | 96 × 96 px |
| Extra-large icon | `icon-128.png` | 128 × 128 px |
| Promotional banner | `banner-220x140.png` | 220 × 140 px |

Navigate to: [Google Cloud Console](https://console.cloud.google.com) →
APIs & Services → OAuth consent screen → App information.

For the Workspace Marketplace listing:
Google Cloud Console → Google Workspace Marketplace SDK → Store Listing.

Store listing text, terms, and privacy URLs are documented in
`assets/store-details/store-listing-text.md`.

---

## Brand colours and design language

See `Design language and logo requirements.zip` and
`Northlake-UU-Tool-Suite-Marks.pptx` for the full brand guide.

Status icon colour palette:

| Status | Colour |
|--------|--------|
| Open | `#7CB342` (green) |
| In Progress | amber |
| In Review | blue |
| Done | teal |
| Closed | grey |
| Unknown | grey (fallback) |
