"""
test_gas_log_op_correlation.py — gts-obry.1

`matches_op` (tests/helpers/gas_log.py) wraps an existing match_fn to also
require an entry's `parentOp` equal a caller-supplied opId, so a batching-
count assertion (e.g. "exactly ONE sync.driveMetadata.fetched for this
sweep") can't be inflated by an unrelated concurrent syncAll (the account's
installed 30-min trigger, or another test/session) landing in the same
tag+timestamp fence window — see gts-li3g and gts-moy1.2 for two prior
incidents of exactly that false-failure shape.

Pure unit test — no live GAS backend, no network. Proves matches_op both
excludes a same-tag/different-parentOp entry (the false-positive this exists
to prevent) and still requires the wrapped match_fn to agree (a same-parentOp
entry of the WRONG tag is still excluded).
"""
from tests.helpers.gas_log import matches_op

import pytest

# gts-aqpk: fast/local tier -- this module makes no live GAS/Google round trip
# (verified offline with sockets blocked). See docs/OPERATIONS.md "Test tiers".
pytestmark = pytest.mark.no_live_session


def _entry(tag: str, parent_op: str | None) -> dict:
    return {"tag": tag, "parentOp": parent_op, "data": {}}


def test_matches_op_accepts_entry_with_matching_parent_op_and_tag():
    op_id = "own-sweep-op-id"
    fn = matches_op(lambda e: e.get("tag") == "sync.driveMetadata.fetched", op_id)
    assert fn(_entry("sync.driveMetadata.fetched", op_id)) is True


def test_matches_op_rejects_same_tag_different_parent_op():
    """The exact false-positive this wrapper exists to close: a concurrent
    sweep (a different call, different opId) logging the identical tag inside
    the same fence window must NOT count toward this call's own assertion."""
    op_id = "own-sweep-op-id"
    fn = matches_op(lambda e: e.get("tag") == "sync.driveMetadata.fetched", op_id)
    assert fn(_entry("sync.driveMetadata.fetched", "some-other-concurrent-op-id")) is False


def test_matches_op_rejects_matching_parent_op_but_wrong_tag():
    op_id = "own-sweep-op-id"
    fn = matches_op(lambda e: e.get("tag") == "sync.driveMetadata.fetched", op_id)
    assert fn(_entry("sync.docNotFound.confirmed", op_id)) is False


def test_matches_op_rejects_entry_with_no_parent_op():
    """An entry from a call that never populated opId (parentOp is null,
    e.g. a manual call_webapp.py probe -- see gts-obry.1 bead notes on the
    known call_webapp.py instrumentation gap) must not spuriously match."""
    op_id = "own-sweep-op-id"
    fn = matches_op(lambda e: e.get("tag") == "sync.driveMetadata.fetched", op_id)
    assert fn(_entry("sync.driveMetadata.fetched", None)) is False
