"""test_apt_lane_idempotency.py — gts-5ktl, staged plan
docdata-litter-apt-speed.md stage `lane-idempotency`.

Offline backstop for the runner-level idempotency assertion added to
`tests/support/apt_lane_runner.py::run_lane`: after the lane's own golden
comparison, ONE further no-op sync is issued, the doc is captured again, and
each scenario's slice of that second capture is diffed against its slice of
the first.

Why offline (Backstop rules — "a new integrity/quality assertion must be
proven to fail before acceptance"): a live lane run against a correct build
is idempotent by construction, so a live green run proves nothing about
whether the assertion can go red. Making it go red live would need a
deliberately non-idempotent build deployed to shared TEST, which the deploy
tooling refuses (see tests/test_inline_formatting.py's own backstop note for
the same constraint). Instead the runner's live dependencies (`sync`,
`_post_fixture`, `edit_sheet`, `doc_id`) are stubbed by a fake session whose
SECOND capture drifts — the exact failure mode the assertion exists to
catch, driven through the real `run_lane`/`format_failures`/`diff_apt` path.

The live half (that the five batched lanes actually converge in one sweep) is
asserted by the lanes themselves: tests/test_apt_corpus_batch.py,
tests/test_apt_flush_lane.py, tests/test_apt_create_lane.py,
tests/test_apt_scanner_lane.py, tests/test_apt_format_lane.py.
"""
import json
import pathlib
import sys

import pytest

pytestmark = pytest.mark.no_live_session

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "support"))

import apt_lib  # noqa: E402
import apt_lane_runner  # noqa: E402


class FakeSession:
    """The narrow slice of ScenarioSession `run_lane` actually touches.

    `captures` is the list of APT texts `encode_reference_document` returns,
    in order — so a test can make the SECOND capture differ from the first
    and watch the idempotency diff go red.
    """

    def __init__(self, captures):
        self.doc_id = "FAKEDOC"
        self.captures = list(captures)
        self.sync_calls = 0
        self.encode_calls = 0
        self.decoded = None

    def sync(self):
        self.sync_calls += 1

    def edit_sheet(self, *args, **kwargs):  # pragma: no cover - unused here
        raise AssertionError("no sheetEdit scenario in these fixtures")

    def _post_fixture(self, name, payload=None):
        if name == "decode_reference_document":
            self.decoded = payload["apt"]
            return {"data": {"ok": True}}
        if name == "encode_reference_document":
            idx = min(self.encode_calls, len(self.captures) - 1)
            self.encode_calls += 1
            return {"data": {"ok": True, "apt": self.captures[idx]}}
        raise AssertionError(f"unexpected fixture call {name!r}")


def _corpus(*records):
    return "<!-- kind: golden -->\n<!-- name: x -->\n\n" + "\n\n".join(records)


def _write_scenario(fixtures_dir, name, records, **extra):
    (fixtures_dir / f"{name}.apt.txt").write_text(_corpus(*records), encoding="utf-8")
    (fixtures_dir / f"{name}-expected.apt.txt").write_text(_corpus(*records), encoding="utf-8")
    raw = {
        "name": name,
        "input": name,
        "mutation": {"kind": "sync"},
        "expected": f"{name}-expected",
        "batch": "fake-lane",
    }
    raw.update(extra)
    path = fixtures_dir / f"{name}.scenario.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return apt_lib.load_scenario(path)


@pytest.fixture
def lane(tmp_path):
    """Two one-record scenarios in one composed lane, each converged (input
    == expected), so the golden half is green and only the idempotency half
    is under test."""
    a = _write_scenario(tmp_path, "alpha", ["ACT-1: alice@example.com do alpha (Open)"])
    b = _write_scenario(tmp_path, "beta", ["ACT-2: bob@example.com do beta (Open)"])
    return tmp_path, [a, b]


CONVERGED = "<!-- kind: capture -->\n\nACT-1: alice@example.com do alpha (Open)\n\nACT-2: bob@example.com do beta (Open)"
DRIFTED = "<!-- kind: capture -->\n\nACT-1: alice@example.com do alpha (Open)\n\nACT-2: bob@example.com do  beta (Open)"
DRIFTED_STRUCTURAL = "<!-- kind: capture -->\n\nACT-1: alice@example.com do alpha (Open)\n\nACT-2: bob@example.com do beta (Open)\n\nACT-3: bob@example.com do beta again (Open)"


class TestSecondCaptureIsTaken:
    def test_stable_second_capture_is_clean(self, lane):
        fixtures_dir, scenarios = lane
        scn = FakeSession([CONVERGED, CONVERGED])
        results = apt_lane_runner.run_lane(scn, scenarios, fixtures_dir=fixtures_dir)
        assert all(r.diff.clean for r in results)
        assert all(r.idem_diff is not None and r.idem_diff.clean for r in results)
        assert all(r.clean for r in results)
        assert apt_lane_runner.format_failures(results) == ""

    def test_costs_exactly_one_extra_sync_and_capture_per_lane(self, lane):
        """AC4's shape, asserted structurally rather than by wall clock: the
        added cost is per LANE, not per scenario — two scenarios, still one
        extra sync and one extra encode."""
        fixtures_dir, scenarios = lane
        scn = FakeSession([CONVERGED, CONVERGED])
        apt_lane_runner.run_lane(scn, scenarios, fixtures_dir=fixtures_dir)
        assert scn.sync_calls == 2, "one establishing sync + exactly one no-op sync"
        assert scn.encode_calls == 2, "one capture per sync, not one per scenario"


class TestProvenToFail:
    """Backstop rules: demonstrate the assertion goes RED when the condition
    it checks is violated. A green-only run is unverified."""

    def test_drifting_second_capture_fails_and_names_the_scenario(self, lane):
        fixtures_dir, scenarios = lane
        scn = FakeSession([CONVERGED, DRIFTED])
        results = apt_lane_runner.run_lane(scn, scenarios, fixtures_dir=fixtures_dir)

        # The golden half is still clean — this failure is ONLY the second
        # capture, which is what makes it an idempotency failure and not a
        # restatement of the corpus comparison.
        assert all(r.diff.clean for r in results)

        by_name = {r.scenario.name: r for r in results}
        assert by_name["alpha"].clean, "an unaffected scenario must stay green"
        assert not by_name["beta"].clean
        assert not by_name["beta"].idem_diff.clean

        report = apt_lane_runner.format_failures(results)
        assert "beta NOT IDEMPOTENT" in report
        assert "alpha NOT IDEMPOTENT" not in report

    def test_record_added_on_second_sync_fails(self, lane):
        """The ADR-0031 failure mode with teeth: a flush that appends on every
        sweep instead of converging.

        An appended record lands PAST the last scenario's slice range, so no
        per-scenario diff can see it — the runner checks record count at the
        lane level, before slicing, and fails there."""
        fixtures_dir, scenarios = lane
        scn = FakeSession([CONVERGED, DRIFTED_STRUCTURAL])
        with pytest.raises(AssertionError, match="lane NOT IDEMPOTENT"):
            apt_lane_runner.run_lane(scn, scenarios, fixtures_dir=fixtures_dir)

    def test_record_removed_on_second_sync_fails(self, lane):
        fixtures_dir, scenarios = lane
        shrunk = "<!-- kind: capture -->\n\nACT-1: alice@example.com do alpha (Open)"
        scn = FakeSession([CONVERGED, shrunk])
        with pytest.raises(AssertionError, match="lane NOT IDEMPOTENT"):
            apt_lane_runner.run_lane(scn, scenarios, fixtures_dir=fixtures_dir)


class TestOptOut:
    def test_declared_non_idempotent_scenario_is_excluded(self, tmp_path):
        a = _write_scenario(tmp_path, "alpha", ["ACT-1: alice@example.com do alpha (Open)"])
        b = _write_scenario(
            tmp_path, "beta", ["ACT-2: bob@example.com do beta (Open)"], idempotent=False,
        )
        assert a.idempotent is True and b.idempotent is False
        scn = FakeSession([CONVERGED, DRIFTED])
        results = apt_lane_runner.run_lane(scn, [a, b], fixtures_dir=tmp_path)
        by_name = {r.scenario.name: r for r in results}
        assert by_name["beta"].idem_diff is None, "opted-out scenario is not diffed"
        assert all(r.clean for r in results)

    def test_all_opted_out_skips_the_extra_sync_entirely(self, tmp_path):
        a = _write_scenario(
            tmp_path, "alpha", ["ACT-1: alice@example.com do alpha (Open)"], idempotent=False,
        )
        scn = FakeSession([CONVERGED])
        apt_lane_runner.run_lane(scn, [a], fixtures_dir=tmp_path)
        assert scn.sync_calls == 1 and scn.encode_calls == 1

    def test_non_boolean_opt_out_is_rejected(self, tmp_path):
        path = tmp_path / "bad.scenario.json"
        path.write_text(json.dumps({
            "input": "x", "mutation": {"kind": "sync"}, "expected": "x", "idempotent": "false",
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="idempotent"):
            apt_lib.load_scenario(path)

    def test_default_is_on(self, tmp_path):
        path = tmp_path / "plain.scenario.json"
        path.write_text(json.dumps({
            "input": "x", "mutation": {"kind": "sync"}, "expected": "x",
        }), encoding="utf-8")
        assert apt_lib.load_scenario(path).idempotent is True


class TestCheckedInScenariosDeclareTheirOptOut:
    def test_every_opt_out_records_a_reason(self):
        """An opt-out is a decision on record, not a silent skip: any
        checked-in scenario.json carrying `"idempotent": false` must also
        carry a `idempotentReason` explaining why."""
        fixtures = REPO_ROOT / "tests" / "fixtures"
        files = sorted(fixtures.glob("*.scenario.json"))
        assert files, f"no *.scenario.json found under {fixtures}"
        for path in files:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("idempotent") is False:
                reason = (raw.get("idempotentReason") or "").strip()
                assert reason, (
                    f"{path.name}: opts out of the lane idempotency diff with no "
                    "'idempotentReason' (gts-5ktl — an opt-out is a decision on record)"
                )
