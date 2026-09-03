"""test_decode_status_icon.py — gts-3koi.

docs/interfaces/action-portable-text.md's "Status icon" section says decode
reconstructs the flush-inserted status icon "the same way `_buildFlushRequests`
does" — but `decodeAptIntoDoc` (src/PortableText.js) never called
`getStatusIconUrl`/`insertInlineImage` at all, so a decode-only doc carried
zero status icons on every established action (confirmed live against the
canonical reference Doc, see knowledge-base/staging/docdata-litter-apt-speed.md
stage `apt-batch-limits`'s external-prerequisites note).

This is a Path B retroactive gap (no live test could see it — every other
APT lane either checks doc CONTENT, which `has_status_icon` support was added
for but never asserted here, or forces a real flush afterward, which masks a
decode-side gap by re-writing the icon a second way). Oracle is specifiable
(icon present/absent is a boolean derived from parsed doc XML), so this is
test-first: this test is authored to fail red against the pre-fix decode,
then the fix in src/PortableText.js turns it green.

Deliberately uses `materialize_reference_corpus(..., sync=False)` — sync=True
would force a real flush afterward (`ScenarioSession.sync()`), which inserts
the icon via `_buildFlushRequests` and would mask a decode-side regression.
AC point 3 (no re-flush of the shared canonical `referenceDocId`) is met by
construction: `materialize_reference_corpus` always decodes into a fresh,
disposable doc distinct from the canonical one (see
tests/test_reference_corpus_fixture.py).
"""
from tests.helpers.doc_inspect import floating_actions, load_doc
from tests.helpers.download import download_docx
from tests.helpers.reference_corpus import materialize_reference_corpus


def test_decode_only_doc_shows_status_icon_on_every_established_action(settings, request):
    scn = materialize_reference_corpus(settings, request=request, sync=False)
    actions = floating_actions(load_doc(download_docx(scn.doc_id)))

    established = [a for a in actions if a.token]
    assert established, "materialized corpus produced no tokened (established) actions"

    missing = [a.token for a in established if not a.has_status_icon]
    assert not missing, (
        f"decode-only doc {scn.doc_id} is missing a status icon on "
        f"{len(missing)}/{len(established)} established action(s): {sorted(missing)} — "
        "decodeAptIntoDoc must insert the same flush-shaped insertInlineImage "
        "request _buildFlushRequests does (docs/interfaces/action-portable-text.md "
        "\"Status icon\")"
    )

    # ACT-77 (a pipe-delimited line with no ACT-N/AI-N token) is deliberately
    # NOT an established action and must not have manufactured an icon.
    untokened = [a for a in actions if not a.token]
    assert untokened, "expected the golden corpus's one deliberately-untokened line (ACT-77)"
    assert not any(a.has_status_icon for a in untokened), (
        "a paragraph with no action token must never get a status icon"
    )
