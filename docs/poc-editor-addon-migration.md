Updated POC Plan

Create the branch and isolate the experiment.
Branch: poc/editor-addon-action-chip
Keep the existing sync flow unchanged.
Put all experimental code behind a separate namespace.

Add a branding decision up front.
Define one canonical chip/menu icon for the POC.
Recommended default: the 32 px PNG at action-logo-t-32.png.
Reason: it matches smart-chip icon scale better than the larger PNG, and is lower risk than relying on SVG rendering in all chip surfaces.

Publish the icon at a stable HTTPS URL before wiring the manifest.
logoUrl must be a public HTTPS asset.
For the POC, either reuse the existing hosted logo location pattern or publish the selected PNG to the same public asset host already used by the add-on.
Do not point the manifest at a local repo path.

Extend the Docs @action proof of concept with branded entry points.
Add a Docs createActionTrigger with:
label text like Create action
logoUrl pointing at the published 32 px logo
a minimal creation flow for action text, optional assignee, optional status
This proves the logo appears in the @ menu as well as on the inserted chip.

Extend link preview metadata with the same logo.
Add linkPreviewTriggers for the action resource URL pattern.
Use the same logoUrl so the inserted chip and preview experience stay visually consistent.
The preview card should use the action title as the chip title and the logo as the small chip graphic.

Keep the document contract unchanged from the prior POC, but make the chip visibly branded.
Target paragraph form:
[GActionSheet chip with logo] [optional assignee token] [freeform action text] [optional trailing status]
Example:
[Action A-1042 chip] @alice@example.com Finish launch checklist (Open)

Add explicit logo-related validation to the POC.
Validate these separately from the sync logic:
the logo appears in the Docs @ menu
the inserted chip shows the logo
the hover preview card preserves the same branding
the chip remains legible at small size
fallback behavior is acceptable if the logo fails to load

Prefer PNG for the first implementation, keep SVG as a secondary test only.
For the POC, use the PNG first.
If you want to test SVG later, do it as a narrow follow-up check, not the baseline, because the POC question is chip viability, not asset-format troubleshooting.

Keep the rest of the POC narrow.
Reuse the existing Web App and ActionSheet path.
Build the experimental scanner separately.
Test edit durability and non-add-on-user readability.
Defer broader Sheets-host work until the Docs chip flow is proven.

Added Success Criteria

The @action item appears in the Docs @ menu with the GActionSheet logo.
The inserted action chip displays the GActionSheet logo.
The chip preview card uses the same branded identity.
The logo remains recognizable at chip scale and does not create visual ambiguity with a native person chip.
The branded chip still degrades acceptably for collaborators without add-on access.
../DevStandard/knowledge-base/gas-addon-guide.md has been updated to cover this editor add-on and smart-chip pattern, and the guide has been restructured as a general Google ecosystem add-on guide.
One design constraint to keep: the logo should signal “GActionSheet resource,” not “fake Google person chip.” That avoids confusing users and makes the new identity model clearer.

