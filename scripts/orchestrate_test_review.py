#!/mnt/c/dev/venvs/uv1/bin/python3
"""
orchestrate_test_review.py — drive the GTaskSheet-80mo "Test review feedback" epic
to completion by invoking headless Claude Code sessions, one per bead, each at the
model named by the bead's `model:*` label.

Design choice — deterministic, not LLM-coordinated.
    bd already encodes both the execution order (dependency waves) and the model
    for each bead (the model:* label set when the epic was authored). A Haiku
    "coordinator" model would only re-derive what bd already states, adding cost
    and nondeterminism. So this script reads the plan from bd and dispatches a
    CLEAN-CONTEXT `claude -p` subagent per bead at the right model. (If you ever
    want the coordinator variant, swap pick_next_bead() for a Haiku call — the
    rest of the harness is unchanged.)

What it does, in order (R1 → R2 → R3 → R7):
  * For each bead (design→impl→docs): if not closed, launch `claude -p --model <m>`
    with the bead's launch prompt and a clean context; loop until the bead closes.
  * STALL GUARD: if a bead runs and neither its status nor the git tree changes,
    that is "iterating over the same ground." After STALL_LIMIT such no-progress
    runs on the same bead (or GLOBAL_ITER_CAP total runs), the script aborts with
    a report rather than burning tokens in a loop.
  * After an R#'s *impl* bead closes, run that R#'s TEST BLOCK. On pass, append a
    work-log entry for R# and (optionally) push. On fail, append the failure to the
    impl bead's notes, reopen it, and re-dispatch (counts toward the stall guard).

Placeholders: R5/R6 (".11"/".12") are stubs needing human scoping; the script skips
any bead whose title contains "(stub)" and reports it.

Usage:
    scripts/orchestrate_test_review.py --dry-run          # print the plan, invoke nothing
    scripts/orchestrate_test_review.py --only R1           # just R1 (design+impl+docs+tests)
    scripts/orchestrate_test_review.py --yolo              # real run, skip permission prompts
    scripts/orchestrate_test_review.py --yolo --push       # also push after each R# passes

Without --yolo, sessions run with --permission-mode acceptEdits; bash-heavy beads
(deploy:test, pytest-against-live) will have their Bash calls auto-denied in headless
mode and likely fail — use --yolo for an unattended run.

Env overrides:
    CLAUDE_BIN   path to the claude CLI (default: "claude")
    PYTEST_BIN   python used for test blocks (default: the shebang interpreter)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EPIC = "GTaskSheet-80mo"
WORKLOG = REPO / "work-log.md"
RUNLOG_DIR = REPO / "test-results" / "orchestrator"

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
PYTEST_BIN = os.environ.get("PYTEST_BIN", sys.executable)

# Stall guard knobs.
STALL_LIMIT = 2          # consecutive no-progress runs on ONE bead before aborting
GLOBAL_ITER_CAP = 40     # absolute ceiling on claude invocations for the whole run
SESSION_TIMEOUT = 60 * 45  # per-session wall-clock cap (seconds)
TEST_TIMEOUT = 60 * 30


# ---------------------------------------------------------------------------
# Roadmap — the ordered units. model is the authored source of truth; the script
# cross-checks it against the live bd label and warns on drift.
# test: shell argv for the R# test block, or None for doc-only units.
# ---------------------------------------------------------------------------

SCN_UNIT_TESTS = [
    PYTEST_BIN, "-m", "pytest",
    "tests/test_scn_engine.py", "tests/test_scn_session.py", "tests/test_scn_ui.py",
    "-x", "-q",
]

@dataclass
class Bead:
    suffix: str          # e.g. ".1"
    role: str            # design | impl | docs
    model: str           # opus | sonnet | haiku

    @property
    def id(self) -> str:
        return f"{EPIC}{self.suffix}"


@dataclass
class Unit:
    rid: str
    beads: list[Bead]
    test: list[str] | None = None          # test block argv, run after the impl bead
    test_label: str = ""

    @property
    def impl(self) -> Bead | None:
        return next((b for b in self.beads if b.role == "impl"), None)


ROADMAP: list[Unit] = [
    Unit("R1",
         [Bead(".1", "design", "opus"),
          Bead(".2", "impl",   "sonnet"),
          Bead(".3", "docs",   "haiku")],
         test=SCN_UNIT_TESTS,
         test_label="scn engine/session/ui unit tests"),
    Unit("R2",
         [Bead(".4", "design", "opus"),
          Bead(".5", "impl",   "sonnet"),
          Bead(".6", "docs",   "haiku")],
         test=SCN_UNIT_TESTS,
         test_label="scn engine/session/ui unit tests"),
    Unit("R3",
         [Bead(".7", "design", "opus"),
          Bead(".8", "impl",   "sonnet"),
          Bead(".9", "docs",   "haiku")],
         test=[PYTEST_BIN, "-m", "pytest", "tests/", "-x", "-q",
               "--ignore=tests/test_journey.py"],
         test_label="full pytest suite (excl. live journey)"),
    Unit("R7",
         [Bead(".10", "docs", "haiku")],
         test=None,
         test_label="doc-only (no test block)"),
]


# ---------------------------------------------------------------------------
# bd helpers
# ---------------------------------------------------------------------------

def bd(*args: str) -> str:
    out = subprocess.run(["bd", *args], cwd=REPO, capture_output=True, text=True)
    return (out.stdout or "") + (out.stderr or "")


def bd_show(bead_id: str) -> str:
    return bd("show", bead_id)


_STATUS_RE = re.compile(r"\[●?\s*P\d+\s*·\s*([A-Z _]+)\]")
_MODEL_RE = re.compile(r"model:(opus|sonnet|haiku)")


def bead_status(bead_id: str) -> str:
    """Return OPEN | IN_PROGRESS | CLOSED | UNKNOWN (parsed from `bd show`)."""
    text = bd_show(bead_id)
    m = _STATUS_RE.search(text)
    if not m:
        return "UNKNOWN"
    return m.group(1).strip().replace(" ", "_").upper()


def bead_model(bead_id: str, fallback: str) -> str:
    """Read the model:* label from bd's LABELS line; fall back to roadmap on miss.

    Scope the match to the LABELS line — descriptions/design fields routinely
    mention things like "(model:opus)" which must NOT be read as the bead's model.
    """
    for line in bd_show(bead_id).splitlines():
        if line.strip().upper().startswith("LABELS:"):
            m = _MODEL_RE.search(line)
            if m:
                return m.group(1)
    return fallback


def bead_title(bead_id: str) -> str:
    first = bd_show(bead_id).splitlines()[0] if bd_show(bead_id) else ""
    return first


# ---------------------------------------------------------------------------
# git / progress fingerprint
# ---------------------------------------------------------------------------

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()


def repo_fingerprint() -> str:
    """HEAD rev + a hash of the working-tree status — changes on any code/commit move."""
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return f"{head}|{hash(status)}"


# ---------------------------------------------------------------------------
# claude session
# ---------------------------------------------------------------------------

LAUNCH_PROMPT = """You are working bead {bead_id} in the GActionSheet repo. Assume a CLEAN context.

1. Run `bd show {bead_id}` — read description, acceptance, the --design field, dependencies, and the model:* label; work at that altitude.
2. Run `bd show {epic}` — read the Coordination Log for cross-cutting, contract-level facts from sibling beads.
3. Read ONLY the sources the bead names. If this is a *design* bead, your deliverable is to POPULATE the paired build bead's --design field (via `bd update <impl-id> --design ...`) so a clean-context build can proceed — do not write production code. If this is a *build* bead, build strictly to your own --design field; if it still says "DESIGN PENDING", STOP and report rather than guessing. Do NOT read the paired [IMP]/[TST] sibling's code — the contract is the only shared artifact.
4. `bd update {bead_id} --claim` before you start.
5. Run the implementation-gate skill, then do the work. Honor the §16 vocabulary and §16.11 decisions verbatim. For GAS use the package.json npm scripts, never raw clasp.
6. Quality gates: run the relevant tests/lint for what you changed.
7. Record cross-cutting facts a sibling needs: durable → the planning doc / ContractSchema and say where; transient → `bd update {epic} --append-notes "..."`.
8. When acceptance is met: `bd close {bead_id} --reason "..."`, then `git add` + `git commit` your changes locally. DO NOT `git push` — the orchestrator owns pushing after each R# test block passes.
9. If you cannot complete the bead, append the blocker to the bead notes and stop — do not loop.
"""


def run_claude(bead: Bead, runlog: Path, extra: str = "") -> None:
    model = bead_model(bead.id, bead.model)
    if model != bead.model:
        print(f"  ! label/roadmap model drift on {bead.id}: bd={model} roadmap={bead.model}; using bd")
    prompt = LAUNCH_PROMPT.format(bead_id=bead.id, epic=EPIC)
    if extra:
        prompt += "\n\nADDITIONAL CONTEXT FROM ORCHESTRATOR:\n" + extra

    perm = (["--dangerously-skip-permissions"] if ARGS.yolo
            else ["--permission-mode", "acceptEdits"])
    cmd = [CLAUDE_BIN, "-p", prompt, "--model", model, *perm]

    print(f"  → claude -p --model {model}  (bead {bead.id})")
    if ARGS.dry_run:
        print(f"    [dry-run] would run: {CLAUDE_BIN} -p <prompt> --model {model} {' '.join(perm)}")
        return

    with runlog.open("a") as fh:
        fh.write(f"\n\n===== {datetime.now().isoformat()} {bead.id} model={model} =====\n")
        fh.flush()
        try:
            subprocess.run(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT,
                           timeout=SESSION_TIMEOUT, text=True)
        except subprocess.TimeoutExpired:
            fh.write(f"\n[orchestrator] SESSION TIMEOUT after {SESSION_TIMEOUT}s\n")
            print(f"    ! session timed out after {SESSION_TIMEOUT}s")


# ---------------------------------------------------------------------------
# work-log
# ---------------------------------------------------------------------------

def append_worklog(unit: Unit, test_rc: int | None, test_tail: str) -> None:
    if ARGS.dry_run:
        print(f"  ✎ [dry-run] would update work-log for {unit.rid}")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    rev = git("rev-parse", "--short", "HEAD")
    beads = " ".join(b.id for b in unit.beads)
    if test_rc is None:
        verdict = "doc-only — no test block"
    else:
        verdict = f"{unit.test_label} → {'PASS' if test_rc == 0 else 'FAIL'}"
    entry = [
        f"### [orchestrator] {unit.rid} complete — {bead_title(unit.beads[0].id)[:80]}",
        f"- Beads closed: {beads}",
        f"- Tests: {verdict}",
        f"- HEAD: {rev}",
    ]
    if test_tail.strip():
        entry.append("- Test tail:")
        entry += [f"  {ln}" for ln in test_tail.strip().splitlines()[-8:]]
    block = "\n".join(entry) + "\n"

    # Append in binary, preserving the file's existing newline style, so existing
    # lines are never rewritten (avoids CRLF↔LF churn that shows the whole file as changed).
    data = WORKLOG.read_bytes() if WORKLOG.exists() else b""
    nl = "\r\n" if b"\r\n" in data else "\n"
    chunk = ""
    if f"## {today}" not in data.decode("utf-8", errors="replace"):
        chunk += f"\n## {today}\n"
    chunk += "\n" + block
    with WORKLOG.open("ab") as fh:
        fh.write(chunk.replace("\n", nl).encode("utf-8"))
    print(f"  ✎ work-log updated for {unit.rid}")


# ---------------------------------------------------------------------------
# test block
# ---------------------------------------------------------------------------

def run_test_block(unit: Unit, runlog: Path) -> tuple[int, str]:
    if unit.test is None:
        return 0, ""
    print(f"  ⧗ test block: {unit.test_label}")
    if ARGS.dry_run:
        print(f"    [dry-run] would run: {' '.join(unit.test)}")
        return 0, "(dry-run)"
    proc = subprocess.run(unit.test, cwd=REPO, capture_output=True, text=True,
                          timeout=TEST_TIMEOUT)
    tail = (proc.stdout + proc.stderr)
    with runlog.open("a") as fh:
        fh.write(f"\n----- test block {unit.rid} rc={proc.returncode} -----\n{tail}\n")
    print(f"    {'PASS' if proc.returncode == 0 else 'FAIL'} (rc={proc.returncode})")
    return proc.returncode, tail


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

class StallError(RuntimeError):
    pass


@dataclass
class Driver:
    runlog: Path
    invocations: int = 0

    def ensure_done(self, bead: Bead, extra: str = "") -> None:
        """Dispatch sessions for `bead` until it closes or the stall guard trips."""
        title = bead_title(bead.id)
        if "(stub)" in title.lower():
            print(f"  ⤳ SKIP {bead.id} — placeholder stub, needs human scoping")
            return

        stall = 0
        while True:
            status = bead_status(bead.id)
            if status == "CLOSED":
                print(f"  ✓ {bead.id} closed")
                return
            if status == "UNKNOWN":
                raise StallError(f"cannot read status of {bead.id} — is bd healthy?")

            if self.invocations >= GLOBAL_ITER_CAP:
                raise StallError(f"global iteration cap ({GLOBAL_ITER_CAP}) hit at {bead.id}")

            before = repo_fingerprint()
            self.invocations += 1
            run_claude(bead, self.runlog, extra=extra)
            extra = ""  # only feed extra context on the first attempt

            if ARGS.dry_run:
                return  # don't loop in dry-run

            after = repo_fingerprint()
            new_status = bead_status(bead.id)
            progressed = (new_status != status) or (after != before)
            if new_status == "CLOSED":
                print(f"  ✓ {bead.id} closed")
                return
            if progressed:
                stall = 0
                print(f"  … {bead.id} progressed (status {status}→{new_status}); re-checking")
            else:
                stall += 1
                print(f"  ⚠ {bead.id} NO forward progress (stall {stall}/{STALL_LIMIT})")
                if stall >= STALL_LIMIT:
                    raise StallError(
                        f"{bead.id} made no forward progress in {STALL_LIMIT} runs — "
                        f"same ground, stopping. See {self.runlog}"
                    )

    def run_unit(self, unit: Unit) -> None:
        print(f"\n=== {unit.rid} ===")
        for bead in unit.beads:
            self.ensure_done(bead)

        impl = unit.impl
        if impl is None and unit.test is None:
            append_worklog(unit, None, "")
            return

        # Test block, with one feedback retry into the impl bead on failure.
        attempts = 0
        while True:
            rc, tail = run_test_block(unit, self.runlog)
            if rc == 0:
                append_worklog(unit, rc, tail)
                if ARGS.push and not ARGS.dry_run:
                    do_push()
                return
            attempts += 1
            if impl is None or attempts > STALL_LIMIT or ARGS.dry_run:
                append_worklog(unit, rc, tail)
                raise StallError(f"{unit.rid} test block failing and no path forward")
            print(f"  ↻ test FAIL — reopening {impl.id} with failure context (attempt {attempts})")
            bd("update", impl.id, "--status", "in_progress",
               "--append-notes", f"[orchestrator] test block FAILED:\n{tail[-3000:]}")
            self.ensure_done(impl, extra=f"The {unit.test_label} failed. Tail:\n{tail[-3000:]}")


def do_push() -> None:
    print("  ⇪ pushing …")
    subprocess.run(["git", "pull", "--rebase"], cwd=REPO)
    rc = subprocess.run(["git", "push"], cwd=REPO).returncode
    if rc == 0:
        subprocess.run(["bd", "dolt", "push"], cwd=REPO)
        print("    pushed (git + bd dolt)")
    else:
        print("    ! git push failed — resolve manually")


# ---------------------------------------------------------------------------

def main() -> int:
    global ARGS
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", metavar="R#",
                        help="restrict to these units (e.g. --only R1 --only R7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and commands; invoke nothing")
    parser.add_argument("--yolo", action="store_true",
                        help="run sessions with --dangerously-skip-permissions (needed for unattended bash)")
    parser.add_argument("--push", action="store_true",
                        help="git push + bd dolt push after each R# test block passes")
    ARGS = parser.parse_args()

    RUNLOG_DIR.mkdir(parents=True, exist_ok=True)
    runlog = RUNLOG_DIR / f"run-{datetime.now():%Y%m%d-%H%M%S}.log"
    print(f"Orchestrating {EPIC}  (runlog: {runlog})")
    if ARGS.dry_run:
        print("DRY RUN — no claude/test invocations\n")
    elif not ARGS.yolo:
        print("NOTE: no --yolo → sessions use acceptEdits; bash-heavy beads may be auto-denied.\n")

    units = ROADMAP
    if ARGS.only:
        want = {u.upper() for u in ARGS.only}
        units = [u for u in ROADMAP if u.rid in want]
        if not units:
            print(f"no units match --only {ARGS.only}")
            return 2

    driver = Driver(runlog=runlog)
    try:
        for unit in units:
            driver.run_unit(unit)
    except StallError as e:
        print(f"\n✖ STOPPED: {e}")
        print(f"  total claude invocations this run: {driver.invocations}")
        return 1

    print(f"\n✔ all requested units complete  ({driver.invocations} invocations)")
    return 0


ARGS = argparse.Namespace()  # populated in main()

if __name__ == "__main__":
    raise SystemExit(main())
