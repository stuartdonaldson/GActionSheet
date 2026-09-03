#!/usr/bin/env python3
"""apt.py — push | pull | bless | diff over Action Portable Text (APT) corpora
(gts-4bop, designed at stage `apt-cli` of the staged plan that built this
tooling — deleted on close, per Pattern D; its numbered "decision N" design
calls cited below are reconstructed at
docs/interfaces/action-portable-text.md §Tooling design decisions).

One entry point over `apt_lib`'s differ/header code (stage `apt-differ`,
gts-snub/gts-x9un) and the `encode_reference_document`/`decode_reference_document`
test-support fixtures (`src/TestFixtures.js`, gts-colw), transported via
`call_webapp.call_action` (never hand-rolled HTTP — same rule as every other
script in this repo).

    push  <name>   file  -> Doc   (materialise; overwrites the Doc)
    pull  <name>   Doc   -> capture file + classified diff against the golden
    bless <name>   promote the last reviewed capture -> golden
    lint           scenario-triple hygiene: a state-changing mutation whose
                    input and expected corpora are identical (modulo N) is an
                    error unless reasonedly allowlisted (gts-5st5)
    diff  A B      direct file x file diff (decision 3's "free" CLI — no
                    network, no corpus resolution, just two paths)

Corpus resolution (`<name>` for push/pull/bless): `tests/fixtures/<name>.apt.txt`
is the golden; `--file` overrides the path read from disk (push's source, or
the file diffed against for pull/bless — the corpus NAME still drives capture-
store layout and Doc-id resolution). The Doc id comes from `--doc`, else the
golden's own `<!-- doc: ... -->` header line, else (only for the canonical
`action-reference` corpus) `referenceDocId` in local.settings.json.

Exit codes mirror `apt_lib.AptDiffResult.exit_code()`: 0 clean, 1 highest
class present is presentational, 2 structural, 3 preservation. `diff` prints
and exits the same way; `push`/`bless` reuse it for their own guard/prompt
decisions but always exit 0 on success (or 1 on a refused/aborted operation).
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import apt_lib  # noqa: E402
import call_webapp  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
CAPTURES_DIR = REPO_ROOT / ".apt-captures"
_SETTINGS_PATH = REPO_ROOT / "local.settings.json"

# decision 8 default retention -- not itself decision-numbered, just a sane
# bound so .apt-captures/ (gitignored, decision 1) doesn't grow unbounded.
DEFAULT_KEEP_LAST_N = 10

_CLASS_LABEL = {
    apt_lib.POSITIONAL: "positional (renumbering only -- not shown)",
    apt_lib.PRESENTATIONAL: "presentational",
    apt_lib.STRUCTURAL: "structural",
    apt_lib.PRESERVATION: "preservation",
}


class AptCliError(RuntimeError):
    """A resolvable, user-facing apt.py failure (bad corpus, no capture, etc)."""


# ---------------------------------------------------------------------------
# Corpus / Doc-id resolution
# ---------------------------------------------------------------------------

def golden_path(name: str) -> pathlib.Path:
    return FIXTURES_DIR / f"{name}.apt.txt"


def _load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        return {}
    return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))


def resolve_doc_id(name: str, golden_text: str, explicit_doc: str | None) -> str:
    """`--doc` wins; else the golden's own header `doc:` field; else (only for
    the canonical `action-reference` corpus) `referenceDocId` in
    local.settings.json. Raises AptCliError otherwise -- a scenario corpus
    with no doc (decision 7) materialises into a fresh Doc instead, which is
    `apt-scenarios`' (stage 4) job, not this CLI's."""
    if explicit_doc:
        return explicit_doc
    if golden_text:
        header_doc = apt_lib.parse_header(golden_text).get("doc")
        if header_doc:
            return header_doc
    if name == "action-reference":
        settings_doc = _load_settings().get("referenceDocId")
        if settings_doc:
            return settings_doc
    raise AptCliError(
        f"apt: cannot resolve a Doc id for corpus {name!r} -- pass --doc, or give the "
        "golden a '<!-- doc: ... -->' header line. A doc-less scenario corpus "
        "(decision 7) materialises fresh instead; that is stage apt-scenarios, "
        "not push/pull/bless."
    )


def _read_text(path: pathlib.Path) -> str:
    if not path.exists():
        raise AptCliError(f"apt: {_display_path(path)} does not exist")
    return path.read_text(encoding="utf-8")


def _display_path(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Header rewriting helpers
# ---------------------------------------------------------------------------

def _body_of(text: str) -> str:
    _, body = apt_lib.split_preamble_and_body(text)
    return body.strip("\n")


def _rewrite_header(text: str, **overrides) -> str:
    """Reparses `text`'s own header, applies `overrides` (None values dropped
    silently -- pass explicit '' to blank a field), and re-serialises with
    `apt_lib.format_header`. Body is carried through unchanged."""
    header = apt_lib.parse_header(text)
    for key, value in overrides.items():
        if value is None:
            continue
        header[key] = value
    return apt_lib.format_header(header) + "\n\n" + _body_of(text) + "\n"


def _now_iso() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _capture_filename_stamp() -> str:
    # Filesystem- and sort-safe: no colons, lexical order == chronological
    # order, which is what apt_lib.captures_to_evict assumes of its input.
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------

def _print_diff(result: apt_lib.AptDiffResult, *, label_a: str, label_b: str) -> None:
    if result.clean:
        print(f"apt: no difference ({label_a} == {label_b})")
        return
    by_class: dict[str, list[apt_lib.DiffEntry]] = {}
    for entry in result.entries:
        by_class.setdefault(entry.klass, []).append(entry)
    for klass in (apt_lib.PRESENTATIONAL, apt_lib.STRUCTURAL, apt_lib.PRESERVATION):
        entries = by_class.get(klass)
        if not entries:
            continue
        print(f"[{_CLASS_LABEL[klass]}] {len(entries)} record(s)")
        for e in entries:
            print(f"  record {e.record_index}: {e.summary}")


# ---------------------------------------------------------------------------
# pull -- Doc -> capture file + classified diff against the golden
# ---------------------------------------------------------------------------

def cmd_pull(name: str, *, doc: str | None, env: str, keep_last_n: int) -> int:
    golden_file = golden_path(name)
    golden_text = golden_file.read_text(encoding="utf-8") if golden_file.exists() else ""
    doc_id = resolve_doc_id(name, golden_text, doc)

    resp = call_webapp.call_action(
        "run_fixture", {"fixture": "encode_reference_document", "docId": doc_id}, env=env,
    )
    data = resp.get("data") or {}
    if not data.get("ok"):
        raise AptCliError(f"apt pull: encode_reference_document failed: {resp}")
    raw_apt = data["apt"]

    capture_text = _rewrite_header(raw_apt, name=name)
    corpus_dir = CAPTURES_DIR / name
    corpus_dir.mkdir(parents=True, exist_ok=True)
    capture_path = corpus_dir / f"{_capture_filename_stamp()}.apt.txt"
    capture_path.write_text(capture_text, encoding="utf-8")

    existing = sorted(p.name for p in corpus_dir.glob("*.apt.txt"))
    for evicted in apt_lib.captures_to_evict(existing, keep_last_n):
        (corpus_dir / evicted).unlink(missing_ok=True)

    print(f"apt pull: captured {name!r} from {doc_id} -> "
          f"{_display_path(capture_path)}")

    if not golden_text:
        print(f"apt pull: no golden yet for {name!r} -- bless when reviewed.")
        result = apt_lib.diff_apt("", capture_text)
        _print_diff(result, label_a="(no golden)", label_b=str(capture_path.name))
        return result.exit_code()

    result = apt_lib.diff_apt(golden_text, capture_text)
    _print_diff(result, label_a=str(_display_path(golden_file)), label_b=str(capture_path.name))
    return result.exit_code()


# ---------------------------------------------------------------------------
# push -- file -> Doc, refusing a hand-edited canonical Doc without --force
# ---------------------------------------------------------------------------

def cmd_push(name: str, *, file: pathlib.Path | None, doc: str | None, env: str, force: bool) -> int:
    golden_file = golden_path(name)
    golden_text = golden_file.read_text(encoding="utf-8") if golden_file.exists() else ""
    source_path = file or golden_file
    source_text = _read_text(source_path)
    doc_id = resolve_doc_id(name, golden_text, doc)

    if golden_text and not force:
        # Guard (spec: "push refuses a hand-edited canonical Doc without
        # --force"): capture what the Doc actually holds RIGHT NOW and diff
        # it against the golden -- the last state anyone reviewed and
        # blessed. Any difference means the live Doc has drifted (a hand
        # edit, or a sync flush) since that review; pushing would silently
        # clobber it.
        resp = call_webapp.call_action(
            "run_fixture", {"fixture": "encode_reference_document", "docId": doc_id}, env=env,
        )
        data = resp.get("data") or {}
        if not data.get("ok"):
            raise AptCliError(f"apt push: pre-push encode_reference_document failed: {resp}")
        live_text = _rewrite_header(data["apt"], name=name)
        guard = apt_lib.diff_apt(golden_text, live_text)
        if not guard.clean:
            print(f"apt push: refusing -- {doc_id} has drifted from "
                  f"{_display_path(golden_file)} since it was last blessed:")
            _print_diff(guard, label_a=str(_display_path(golden_file)), label_b=f"live Doc {doc_id}")
            print("apt push: re-run with --force to overwrite the live Doc anyway.")
            return 1

    resp = call_webapp.call_action(
        "run_fixture", {"fixture": "decode_reference_document", "docId": doc_id, "apt": source_text}, env=env,
    )
    data = resp.get("data") or {}
    if not data.get("ok"):
        raise AptCliError(f"apt push: decode_reference_document failed: {resp}")
    print(f"apt push: {_display_path(source_path)} -> {doc_id}")
    return 0


# ---------------------------------------------------------------------------
# bless -- promote the last reviewed capture -> golden (never a fresh re-capture)
# ---------------------------------------------------------------------------

def _latest_capture(name: str) -> pathlib.Path:
    corpus_dir = CAPTURES_DIR / name
    captures = sorted(corpus_dir.glob("*.apt.txt")) if corpus_dir.is_dir() else []
    if not captures:
        raise AptCliError(f"apt bless: no capture for {name!r} in .apt-captures/ -- run `apt.py pull {name}` first.")
    return captures[-1]


def cmd_bless(name: str, *, accept_presentational: bool, assume_yes: bool) -> int:
    capture_path = _latest_capture(name)
    capture_text = capture_path.read_text(encoding="utf-8")
    golden_file = golden_path(name)
    golden_text = golden_file.read_text(encoding="utf-8") if golden_file.exists() else ""

    result = apt_lib.diff_apt(golden_text, capture_text)
    if result.clean:
        print(f"apt bless: {capture_path.name} is already clean against "
              f"{_display_path(golden_file) if golden_file.exists() else '(no golden)'} -- nothing to bless.")
        return 0

    _print_diff(result, label_a=str(_display_path(golden_file)) if golden_text else "(no golden)",
                label_b=capture_path.name)

    highest = result.exit_code()  # 1/2/3, matching _STRICTNESS ordering
    only_presentational = highest == 1

    bless_notes: dict[int, str] = {}
    if only_presentational and accept_presentational:
        print("apt bless: highest class is presentational and --accept-presentational was given -- auto-accepting.")
    else:
        # Interactive by default (spec): confirm overall, and for every
        # preservation-tier entry, require a reason (decision 4: "itemized,
        # reason required and persisted") -- structural entries are itemized
        # above but need no reason, only confirmation.
        for e in result.entries:
            if e.klass != apt_lib.PRESERVATION:
                continue
            reason = input(f"apt bless: record {e.record_index} is a PRESERVATION diff "
                            f"({e.summary}) -- reason to bless anyway (blank to abort): ").strip()
            if not reason:
                print("apt bless: aborted -- a preservation diff needs a reason.")
                return 1
            bless_notes[e.record_index] = reason
        if not assume_yes:
            answer = input(f"apt bless: promote {capture_path.name} -> "
                            f"{_display_path(golden_file)}? [y/N] ").strip().lower()
            if answer != "y":
                print("apt bless: aborted.")
                return 1

    overrides = {"kind": "golden", "name": name, "generated": _now_iso()}
    if golden_text:
        # Preserve the outgoing golden's own `serves` unless the capture
        # already carries one (it never does today -- see gts-4bop's note in
        # apt_lib.py -- but a future opts-carrying encode might).
        prior_serves = apt_lib.parse_header(golden_text).get("serves")
        if prior_serves and not apt_lib.parse_header(capture_text).get("serves"):
            overrides["serves"] = prior_serves
    if bless_notes:
        overrides["bless_notes"] = "; ".join(f"{i}:{r}" for i, r in sorted(bless_notes.items()))

    new_golden = _rewrite_header(capture_text, **overrides)
    golden_file.parent.mkdir(parents=True, exist_ok=True)
    golden_file.write_text(new_golden, encoding="utf-8")
    print(f"apt bless: wrote {_display_path(golden_file)}")
    return 0


# ---------------------------------------------------------------------------
# diff -- direct file x file (decision 3's "free" CLI)
# ---------------------------------------------------------------------------

def cmd_diff(path_a: pathlib.Path, path_b: pathlib.Path) -> int:
    text_a, text_b = _read_text(path_a), _read_text(path_b)
    result = apt_lib.diff_apt(text_a, text_b)
    _print_diff(result, label_a=str(path_a), label_b=str(path_b))
    return result.exit_code()


# ---------------------------------------------------------------------------
# lint -- scenario-triple hygiene (gts-5st5), offline like `diff`
# ---------------------------------------------------------------------------

def cmd_lint(fixtures_dir: pathlib.Path) -> int:
    """Reports every scenario whose declared mutation cannot change anything
    the assertion can see (input and expected carry identical records modulo
    N), unless it is on apt_lib's reasoned degenerate allowlist. Exits 2 --
    `structural`, the class a record-level content difference would carry --
    so a CI caller can treat it exactly like a failing `diff`."""
    problems = apt_lib.lint_scenarios(fixtures_dir)
    if not problems:
        print(f"apt lint: {fixtures_dir} -- no degenerate scenarios")
        for name, reason in sorted(apt_lib.DEGENERATE_SCENARIO_ALLOWLIST.items()):
            print(f"  allowlisted: {name} -- {reason}")
        return 0
    print(f"apt lint: {len(problems)} problem(s) in {fixtures_dir}", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return apt_lib._STRICTNESS[apt_lib.STRUCTURAL]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb", required=True)

    p_pull = sub.add_parser("pull", help="Doc -> capture file + classified diff against the golden")
    p_pull.add_argument("name", help="corpus name, e.g. action-reference")
    p_pull.add_argument("--doc", default=None, help="override the Doc id")
    p_pull.add_argument("--env", choices=["test", "prod", "dev"], default="test")
    p_pull.add_argument("--keep-last", type=int, default=DEFAULT_KEEP_LAST_N,
                         help=f"capture retention per corpus (default {DEFAULT_KEEP_LAST_N})")

    p_push = sub.add_parser("push", help="file -> Doc (materialise; overwrites the Doc)")
    p_push.add_argument("name", help="corpus name, e.g. action-reference")
    p_push.add_argument("--file", type=pathlib.Path, default=None,
                         help="source file (default: the corpus's own golden)")
    p_push.add_argument("--doc", default=None, help="override the Doc id")
    p_push.add_argument("--env", choices=["test", "prod", "dev"], default="test")
    p_push.add_argument("--force", action="store_true",
                         help="overwrite even if the live Doc has drifted from the golden")

    p_bless = sub.add_parser("bless", help="promote the last reviewed capture -> golden")
    p_bless.add_argument("name", help="corpus name, e.g. action-reference")
    p_bless.add_argument("--accept-presentational", action="store_true",
                          help="auto-accept when the highest class present is presentational")
    p_bless.add_argument("-y", "--yes", dest="assume_yes", action="store_true",
                          help="skip the overall confirmation prompt (preservation reasons are still required)")

    p_diff = sub.add_parser("diff", help="direct file x file diff -- no network, no corpus resolution")
    p_diff.add_argument("a", type=pathlib.Path)
    p_diff.add_argument("b", type=pathlib.Path)

    p_lint = sub.add_parser("lint", help="scenario-triple hygiene -- no network")
    p_lint.add_argument("--fixtures-dir", type=pathlib.Path, default=FIXTURES_DIR,
                        help=f"directory of *.scenario.json (default {FIXTURES_DIR})")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.verb == "pull":
            return cmd_pull(args.name, doc=args.doc, env=args.env, keep_last_n=args.keep_last)
        if args.verb == "push":
            return cmd_push(args.name, file=args.file, doc=args.doc, env=args.env, force=args.force)
        if args.verb == "bless":
            return cmd_bless(args.name, accept_presentational=args.accept_presentational, assume_yes=args.assume_yes)
        if args.verb == "diff":
            return cmd_diff(args.a, args.b)
        if args.verb == "lint":
            return cmd_lint(args.fixtures_dir)
    except AptCliError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:  # call_webapp's own transport errors
        print(f"apt: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled verb {args.verb!r}")  # argparse `required=True` makes this unreachable


if __name__ == "__main__":
    sys.exit(main())
