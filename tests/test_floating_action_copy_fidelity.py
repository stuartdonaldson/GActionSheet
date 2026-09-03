"""test_floating_action_copy_fidelity.py

Confirms a manually-synced COPY of a real, non-fixture-seeded reference Doc
(ADR-0027-grammar floating actions) reads back as the same Action Portable
Text as the ORIGINAL, pulled read-only and never synced or otherwise
mutated. `REFERENCE_DOC_ID` below is a real, human-maintained Google Doc --
not a doc this suite creates or seeds -- so every fixture call that touches
it is read-only (`encode_reference_document`'s `DocumentApp.openById()` read,
and `clone_doc_with_test_id`'s `DriveApp.makeCopy()`, neither of which ever
calls `saveAndClose()` on the source -- see src/TestFixtures.js). All
mutation -- the copy itself, and syncing it -- happens on a disposable clone
made in the source doc's own Drive folder (not the TEST_SHEET scratch
folder, since the source lives in a real, non-disposable folder), trashed
at teardown whether the test session passes or fails.

"Manually synced" means the real Sheets "Test: Sync Document" menu path
(tests/helpers/gas_invoke.sync_document -> src/MenuHandler.js's
menuSyncDocument -> SyncManager.js's syncDocument(docId)) -- the same path a
human operator uses, not the bulk/trigger sync path (`sync_all`) and not a
direct webapp route call.

Guards against docs/lessons-learned/2026-08-29-round-trip-oracle-passes-
without-the-system-doing-anything.md: comparing the copy's post-sync APT
against the original's APT is a round-trip oracle -- it would pass
vacuously if syncDocument() scanned zero actions and did no real work.
`TestFloatingActionCopyFidelity.test_sync_did_real_work` is an independent
assertion that does not share that shape: it compares the sync's own
`sync.scanned` log count against the number of genuine action-shaped
records (`_is_action_record` below) found in the ORIGINAL's own pulled
APT -- a value established before the sync ever ran, from a source the
sync's own output cannot influence. A no-op sync (count 0, or any count
other than that independently-known count) fails this assertion regardless
of whether the round-trip diff happens to pass. (A raw
`len(apt_lib.split_records(...))` was tried first and rejected: this real
doc's own worked-example structure mixes section-heading prose and orphaned
field-only paragraphs in among the real actions, so the unfiltered record
count -- confirmed live -- is a number no correct sync could ever match,
which would make the assertion fail unconditionally instead of catching a
real no-op. See `_is_action_record`'s docstring.)

Distinct from tests/test_apt_corpus_check.py (every checked-in scenario
corpus round-trips through a FRESH, disposable doc -- no live human-authored
Doc involved) and tests/test_adr0027_reference_document.py (field-by-field
grammar assertions materialized from the legacy checked-in
action-reference.apt.txt corpus) -- this lane's oracle is a real Doc's own
fidelity through a real Drive copy and a real manual sync, with no
checked-in corpus required for the doc-vs-doc comparison to run.

No golden exists yet for corpus name "floating-action-copy-fidelity".
`test_copy_matches_golden_once_blessed` is a no-op (skipped, with a message
naming the exact bless command) until a human runs
`python scripts/apt.py bless floating-action-copy-fidelity` against a
reviewed `python scripts/apt.py pull floating-action-copy-fidelity --doc
<clone-doc-id>` capture, promoting it into
tests/fixtures/floating-action-copy-fidelity.apt.txt.
"""
import pathlib
import re
import sys
import uuid
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import apt_lib  # noqa: E402

from tests.helpers import gas_invoke  # noqa: E402
from tests.helpers.gas_log import clear_logs, wait_for_log  # noqa: E402
from scn.session import ScenarioSession  # noqa: E402

CORPUS_NAME = "floating-action-copy-fidelity"
GOLDEN_PATH = FIXTURES_DIR / f"{CORPUS_NAME}.apt.txt"

# Real, existing, human-maintained Doc with ADR-0027-grammar floating
# actions. NOT a fixture-seeded doc. Never synced, never mutated by this
# test -- read via encode_reference_document only.
REFERENCE_DOC_ID = "1h4QuL7mZVybEj6T4QHAAqk8LMoyNGj0fT9XVTHVs9_E"

# Mirrors src/ActionToken.js's _ACTION_TOKEN_REGEX_ANCHORED ('^(ACT|AI)-(\d+):')
# and _ACTION_TOKEN_BARE_TRIGGER_REGEX_ANCHORED ('^(ACT|AI):') -- an
# already-numbered token or a bare (not-yet-assigned) trigger, anchored at
# line start. src/SyncManager.js's _collectTokenParagraphs scans every LINE
# of every paragraph for this (not just the paragraph's first line), which
# is why _is_action_record below checks every line of a record, not just
# its first.
_ACTION_TRIGGER_LINE_RE = re.compile(r"^(?:\[\*\*)?(?:ACT|AI)(?:-\d+)?:")


def _is_action_record(record: str) -> bool:
    """True iff `record` (one apt_lib.split_records() chunk) is a genuine
    floating-action paragraph in GAS's own sense -- carries either an
    already-numbered token (ACT-N:/AI-N:) or a not-yet-assigned bare
    trigger (ACT:/AI:) on some line.

    This exists because apt_lib.split_records() returns EVERY body record
    (every blank-line-separated chunk in the encoded doc), not just action
    paragraphs -- confirmed live 2026-08-29 pulling REFERENCE_DOC_ID: of 24
    records, 8 are non-action content this doc's own worked-example
    structure produces (a "Standard Action as a standalone paragraph"-style
    section-heading prose line before each demonstrated shape, an orphaned
    "Field-1: ..." paragraph the doc separates from its action by a blank
    line, and <EMPTY>/<BLANK> structural sentinels) -- and the remaining 16
    are the genuine ACT:-triggered action paragraphs, exactly matching that
    run's sync.scanned count. A raw len(split_records(...)) count is a
    vacuous baseline against THIS doc's real content: it would demand
    sync.scanned == 24, which no correct sync could ever produce, silently
    turning "sync-did-real-work" into "sync never matches" -- itself a
    second, inverted way to fail to catch a real no-op (any fixed wrong
    number closes off the vacuous-pass hole only by accident, not by
    measuring the right thing).
    """
    for i, line in enumerate(record.split("\n")):
        if line.endswith("<SR>"):
            line = line[: -len("<SR>")]
        if i == 0 and line.startswith("<LI> "):
            line = line[len("<LI> "):]
        if _ACTION_TRIGGER_LINE_RE.match(line):
            return True
    return False


@pytest.fixture(scope="module")
def synced_copy(settings, gas_log_dir):
    """Materializes the whole scenario once for every test in this module:
    pulls the ORIGINAL's APT read-only, clones it into its own parent
    folder with a traceable test id, manually syncs the CLONE via the real
    Sheets menu path, and pulls the clone's post-sync APT. Trashes the
    clone at teardown regardless of outcome (success or exception).

    Module-scoped rather than per-test: a live Playwright menu click that
    waits on a real GAS sync of a ~21-action doc is expensive, and every
    test below needs the SAME synced state, not an independent one (mirrors
    tests/test_adr0027_reference_document.py's `reference` fixture).
    """
    scn = ScenarioSession.new_doc(settings)
    clone_doc_id = None
    try:
        # 1. Pull the ORIGINAL's APT read-only, before the copy exists.
        orig_resp = scn._post_fixture("encode_reference_document", {"docId": REFERENCE_DOC_ID})
        orig_data = orig_resp.get("data") or {}
        assert orig_data.get("ok"), (
            f"encode_reference_document(original) failed -- check the TEST "
            f"deployment's Drive read access to {REFERENCE_DOC_ID}: {orig_resp}"
        )
        original_apt = orig_data["apt"]

        expected_scanned = sum(
            1 for r in apt_lib.split_records(original_apt) if _is_action_record(r)
        )
        assert expected_scanned > 0, (
            f"original doc {REFERENCE_DOC_ID} pulled zero floating-action "
            "records -- this test cannot establish a nonzero sync-did-real-"
            "work baseline against it"
        )

        # 2. Clone into the source doc's OWN parent folder, with a
        #    traceable test id embedded in the copy's name.
        test_id = uuid.uuid4().hex[:8]
        clone_resp = scn._post_fixture(
            "clone_doc_with_test_id",
            {"docId": REFERENCE_DOC_ID, "testId": test_id},
        )
        clone_data = clone_resp.get("data") or {}
        clone_doc_id = clone_data.get("docId")
        assert clone_doc_id, (
            f"clone_doc_with_test_id did not return a docId -- check the TEST "
            f"deployment's Drive copy access to {REFERENCE_DOC_ID}: {clone_resp}"
        )

        # 3. Manually sync the COPY -- real Sheets "Test: Sync Document"
        #    menu path, not sync_all and not a direct webapp route call.
        fence = clear_logs(gas_log_dir)
        gas_invoke.sync_document(clone_doc_id)

        scanned_entry = wait_for_log(
            gas_log_dir,
            lambda e: e.get("tag") == "sync.scanned"
            and (e.get("data") or {}).get("docId") == clone_doc_id,
            timeout_s=90,
            after=fence,
        )
        actual_scanned = (scanned_entry.get("data") or {}).get("count")

        # 4. Pull the COPY's post-sync APT.
        copy_resp = scn._post_fixture("encode_reference_document", {"docId": clone_doc_id})
        copy_data = copy_resp.get("data") or {}
        assert copy_data.get("ok"), f"encode_reference_document(copy) failed: {copy_resp}"

        # Each doc's own id shows up in every token's chip-badge preview
        # link (docs/interfaces/action-portable-text.md); normalise both
        # sides to a shared placeholder so the diff isn't purely a doc-id
        # mismatch -- same technique tests/test_apt_corpus_check.py uses
        # for its own freshly-materialised doc.
        original_norm = original_apt.replace(REFERENCE_DOC_ID, "DOC_ID")
        copy_norm = copy_data["apt"].replace(clone_doc_id, "DOC_ID")

        yield SimpleNamespace(
            original_apt=original_norm,
            copy_apt=copy_norm,
            expected_scanned=expected_scanned,
            actual_scanned=actual_scanned,
            clone_doc_id=clone_doc_id,
            test_id=test_id,
        )
    finally:
        if clone_doc_id:
            scn._post_fixture("trash_doc", {"docId": clone_doc_id})
        scn.close()


class TestFloatingActionCopyFidelity:

    def test_sync_did_real_work(self, synced_copy):
        """Independent of the round-trip diff below (LL 2026-08-29): the
        manual sync's own sync.scanned count must equal the number of
        floating-action records the ORIGINAL's own pulled APT declares. A
        no-op sync (locked-skip, doc-not-found, or a genuine zero-action
        scan) reports 0 (or some other mismatching count) here and fails,
        regardless of what the round-trip comparison would otherwise show."""
        assert synced_copy.actual_scanned == synced_copy.expected_scanned, (
            f"sync.scanned count ({synced_copy.actual_scanned}) for the copy "
            f"({synced_copy.clone_doc_id}) does not match the original's own "
            f"{synced_copy.expected_scanned} floating-action records -- the "
            "manual sync did not scan the same content the original defines, "
            "or did no real work"
        )

    def test_copy_matches_original(self, synced_copy):
        """The copy's post-sync APT diffs clean against the original's own
        pulled APT (doc ids normalised to a shared placeholder first)."""
        result = apt_lib.diff_apt(synced_copy.original_apt, synced_copy.copy_apt)
        if not result.clean:
            lines = [
                f"copy {synced_copy.clone_doc_id} (test:{synced_copy.test_id}) of "
                f"{REFERENCE_DOC_ID} did not diff clean against the original:"
            ]
            for entry in result.entries:
                lines.append(f"  [{entry.klass}] record {entry.record_index}: {entry.summary}")
            pytest.fail("\n".join(lines))

    def test_copy_matches_golden_once_blessed(self, synced_copy):
        """No-op until a human blesses tests/fixtures/floating-action-copy-
        fidelity.apt.txt. Once that golden exists, this activates
        automatically and diffs the copy's post-sync APT against it."""
        if not GOLDEN_PATH.exists():
            pytest.skip(
                f"no golden yet at {GOLDEN_PATH} -- review a capture (e.g. "
                f"`python scripts/apt.py pull {CORPUS_NAME} --doc "
                f"{synced_copy.clone_doc_id}`) and promote it with "
                f"`python scripts/apt.py bless {CORPUS_NAME}` to activate "
                "this assertion."
            )
        golden_text = GOLDEN_PATH.read_text(encoding="utf-8")
        result = apt_lib.diff_apt(golden_text, synced_copy.copy_apt)
        if not result.clean:
            lines = [
                f"copy {synced_copy.clone_doc_id} of {REFERENCE_DOC_ID} did not "
                f"diff clean against blessed golden {GOLDEN_PATH.name}:"
            ]
            for entry in result.entries:
                lines.append(f"  [{entry.klass}] record {entry.record_index}: {entry.summary}")
            pytest.fail("\n".join(lines))
