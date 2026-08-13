"""[gts-bops] Backstop proof for RetryUtil.js::withGasRetry.

S5's merge-gate run (plan-0806-flake-recovery.md, F10, 2026-08-07) failed
test_journey.py::test_journey on an unretried TrackerTable.js::
insertTrackerTable -> DocumentApp.openById(docId) that threw Google's
transient "Service Documents failed while accessing document with id ..."
error. gts-pm72 already retries the equivalent failure mode for Drive REST
calls (response-code based); this bead adds the exception-based analog
(RetryUtil.js::withGasRetry) and applies it to every production call site of
the same shape (see gts-bops description).

This file proves the wrapper via the 'insert_tracker_force_gas_retry'
fixture (TestFixtures.js), which forces N synthetic throws out of exactly
the failing call site (TrackerTable.js:49) using withGasRetry's own
test-only fault-injection hook (RetryUtil.js::_gasRetryTestShouldForceFailure)
-- real DocumentApp is never touched.

Backstop case: pre-gts-bops, ANY forced failure count -- even 1 -- makes
insertTrackerTable throw immediately (no retry existed), so
test_recovers_within_retry_budget below fails against that build and passes
against the current one.
"""
from scn.session import ScenarioSession


def test_recovers_within_retry_budget(settings, gas_log_dir, request):
    """[gts-bops] A single forced transient DocumentApp.openById failure
    (within the 3-attempt retry budget) is absorbed: insertTrackerTable still
    succeeds, gasRetry.attempt + gasRetry.recovered are logged, and no
    tracker.error is logged."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs, assert_no_log, assert_log
            fence = clear_logs(gas_log_dir)
        else:
            fence = 0.0

        result = scn._post_fixture("insert_tracker_force_gas_retry", {"fails": 1})
        data = result.get("data", {})
        assert data.get("ok") is True, (
            f"[bops] insertTrackerTable did not recover from 1 forced "
            f"transient failure (within budget): {data}"
        )
        assert data.get("err") is None

        if gas_log_dir:
            assert_no_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "tracker.error",
                "[bops] tracker.error logged for a single forced transient "
                "DocumentApp.openById failure -- the bounded retry did not "
                "absorb it",
            )
            assert_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "gasRetry.attempt"
                and (e.get("data") or {}).get("label")
                    == "TrackerTable.insertTrackerTable:DocumentApp.openById",
                "[bops] expected a gasRetry.attempt entry naming the "
                "TrackerTable call-site label",
            )
            assert_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "gasRetry.recovered"
                and (e.get("data") or {}).get("label")
                    == "TrackerTable.insertTrackerTable:DocumentApp.openById",
                "[bops] expected a gasRetry.recovered entry after the forced "
                "failure was absorbed",
            )
    finally:
        # Doc-trashing deferred to new_doc(request=request)'s pytest
        # finalizer (gts-hroj).
        scn.engine.close()


def test_classifier_does_not_retry_real_errors(settings, request):
    """[gts-bops AC5] RetryUtil.js::_isRetryableGasError classifies genuine
    (non-transient) error messages -- invalid id, not-found, permission
    denied -- as NOT retryable, so those still surface on attempt 1 rather
    than burning 2 extra attempts + backoff on an answer that will never
    change. Pure-function check via a dedicated fixture; no live Doc/Drive
    call is made."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        result = scn._post_fixture("gas_retry_classifier_selftest")
        data = result.get("data", {})
        assert data.get("allMatch") is True, (
            f"[bops] retry classifier disagreed with expectation on at least "
            f"one message: {data.get('results')}"
        )
    finally:
        scn.engine.close()


def test_exhaustion_still_bounded_and_logged(settings, gas_log_dir, request):
    """[gts-bops] A persistent forced failure (beyond the 3-attempt retry
    budget) still throws -- proving the retry is bounded, not silently
    infinite or skipped -- and gasRetry.exhausted is logged with the
    call-site label and attempt count, then insertTrackerTable's own
    existing catch logs tracker.error exactly as it did before this bead
    (unchanged failure contract for a genuinely-persistent error)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        if gas_log_dir:
            from tests.helpers.gas_log import clear_logs, assert_log
            fence = clear_logs(gas_log_dir)
        else:
            fence = 0.0

        result = scn._post_fixture("insert_tracker_force_gas_retry", {"fails": 5})
        data = result.get("data", {})
        assert data.get("ok") is False, (
            f"[bops] insertTrackerTable unexpectedly succeeded despite 5 "
            f"forced failures (> the 3-attempt budget): {data}"
        )
        assert data.get("err"), "[bops] expected an error message on exhaustion"

        if gas_log_dir:
            assert_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "gasRetry.exhausted"
                and (e.get("data") or {}).get("label")
                    == "TrackerTable.insertTrackerTable:DocumentApp.openById"
                and (e.get("data") or {}).get("attempts") == 3,
                "[bops] expected a gasRetry.exhausted entry naming the "
                "TrackerTable call-site label after exactly 3 attempts",
            )
            assert_log(
                gas_log_dir, fence,
                lambda e: e.get("tag") == "tracker.error",
                "[bops] expected insertTrackerTable's own pre-existing catch "
                "to still log tracker.error once the retry is exhausted -- "
                "unchanged failure contract",
            )
    finally:
        scn.engine.close()
