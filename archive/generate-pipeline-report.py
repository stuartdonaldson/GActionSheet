#!/usr/bin/env python3
"""
generate-pipeline-report.py — Generate pipeline-report.md from test results and deployment ledger.

Sources (all relative to project root):
  test-results/pytest.xml          — pytest JUnit XML
  test-results/playwright.xml      — Playwright JUnit XML (optional)
  test-results/*/error-context.md  — Playwright failure artifacts (fallback)
  test-results/.last-run.json      — Playwright last-run summary (fallback)
  deployment-ledger/test.jsonl     — Deployment ledger (one JSON object per line)

Usage:
  python generate-pipeline-report.py [--root DIR] [--output FILE] [--stdout] [--format text|md]

  --format defaults to 'text' when --stdout, 'md' when writing to a file.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_xml(path: Path):
    if not path.exists():
        return None
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as e:
        print(f"Warning: could not parse {path}: {e}", file=sys.stderr)
        return None


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")


def fmt_local(dt: datetime, label: str = "PDT") -> str:
    local = dt.astimezone()
    return local.strftime(f"%H:%M %b %-d") + f" ({label})"


def seconds_to_hms(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


# ---------------------------------------------------------------------------
# Failure triage classification
# ---------------------------------------------------------------------------

def classify_failure(text: str) -> str:
    t = text.lower()
    if "test-token-unauthorized" in t or "test-token-expired" in t or "fixture token rejected" in t:
        return "Harness/Config"
    if "add-on" in t and ("not installed" in t or "not found" in t):
        return "Env"
    if "side panel" in t and "not" in t:
        return "Env"
    # UI assertion failures take precedence over generic timeout text
    if "tobevisible" in t or "element(s) not found" in t or "expect(locator)" in t:
        return "Product"
    if "429" in t or "too many requests" in t:
        return "Product"   # blocks correctness verification — treat as product risk
    # Only classify as perf if the *primary* error is a timeout (not a timeout param in assertion output)
    if "timed out after" in t or ("timed out" in t and "waiting for" in t):
        return "Perf/Timeout"
    return "Product"


# ---------------------------------------------------------------------------
# pytest XML parsing
# ---------------------------------------------------------------------------

def parse_pytest_xml(root) -> dict:
    found = root.find("testsuite")
    suite = found if found is not None else root
    total    = int(suite.get("tests", 0))
    errors   = int(suite.get("errors", 0))
    failures = int(suite.get("failures", 0))
    skipped  = int(suite.get("skipped", 0))
    wall     = float(suite.get("time", 0))
    ts_str   = suite.get("timestamp")
    run_time = parse_iso(ts_str) if ts_str else None

    passed = total - failures - errors - skipped

    # Per-suite breakdown: group by top-level module (first two parts of classname)
    suites = defaultdict(lambda: {"tests": 0, "pass": 0, "fail": 0, "err": 0, "skip": 0, "time": 0.0})
    failing_tests = []
    skipped_tests = []

    for tc in suite.findall("testcase"):
        classname = tc.get("classname", "")
        parts = classname.split(".")
        # e.g. tests.test_scn_ai.TestAiAsText -> test_scn_ai
        suite_key = parts[1] if len(parts) > 1 else classname
        t = float(tc.get("time", 0))
        suites[suite_key]["tests"] += 1
        suites[suite_key]["time"] += t

        fail_el  = tc.find("failure")
        err_el   = tc.find("error")
        skip_el  = tc.find("skipped")

        if fail_el is not None:
            suites[suite_key]["fail"] += 1
            msg = fail_el.get("message", "") + "\n" + (fail_el.text or "")
            failing_tests.append({
                "suite": suite_key,
                "name": tc.get("name", ""),
                "classname": classname,
                "message": fail_el.get("message", ""),
                "body": fail_el.text or "",
                "bucket": classify_failure(msg),
            })
        elif err_el is not None:
            suites[suite_key]["err"] += 1
            msg = err_el.get("message", "") + "\n" + (err_el.text or "")
            failing_tests.append({
                "suite": suite_key,
                "name": tc.get("name", ""),
                "classname": classname,
                "message": err_el.get("message", ""),
                "body": err_el.text or "",
                "bucket": classify_failure(msg),
            })
        elif skip_el is not None:
            suites[suite_key]["skip"] += 1
            skipped_tests.append({
                "suite": suite_key,
                "name": tc.get("name", ""),
                "message": skip_el.get("message", ""),
            })
        else:
            suites[suite_key]["pass"] += 1

    return {
        "total": total, "passed": passed, "failed": failures,
        "errors": errors, "skipped": skipped, "wall": wall,
        "run_time": run_time,
        "suites": dict(suites),
        "failing_tests": failing_tests,
        "skipped_tests": skipped_tests,
    }


# ---------------------------------------------------------------------------
# Playwright XML parsing
# ---------------------------------------------------------------------------

def parse_playwright_xml(root) -> dict:
    total = passed = failed = errors = skipped = 0
    wall = 0.0
    suites = defaultdict(lambda: {"tests": 0, "pass": 0, "fail": 0, "err": 0, "skip": 0, "time": 0.0})
    failing_tests = []

    for suite_el in root.iter("testsuite"):
        t = int(suite_el.get("tests", 0))
        if t == 0:
            continue
        total    += t
        errors   += int(suite_el.get("errors", 0))
        failed   += int(suite_el.get("failures", 0))
        skipped  += int(suite_el.get("skipped", 0))
        wall     += float(suite_el.get("time", 0))
        suite_name = suite_el.get("name", "unknown")
        key = Path(suite_name).stem if suite_name else "unknown"

        for tc in suite_el.findall("testcase"):
            t = float(tc.get("time", 0))
            suites[key]["tests"] += 1
            suites[key]["time"] += t
            fail_el = tc.find("failure")
            err_el  = tc.find("error")
            skip_el = tc.find("skipped")
            if fail_el is not None:
                suites[key]["fail"] += 1
                msg = fail_el.get("message", "") + "\n" + (fail_el.text or "")
                failing_tests.append({
                    "suite": key,
                    "name": tc.get("name", ""),
                    "message": fail_el.get("message", ""),
                    "location": tc.get("classname", ""),
                    "bucket": classify_failure(msg),
                })
            elif err_el is not None:
                suites[key]["err"] += 1
                msg = err_el.get("message", "") + "\n" + (err_el.text or "")
                failing_tests.append({
                    "suite": key,
                    "name": tc.get("name", ""),
                    "message": err_el.get("message", ""),
                    "location": tc.get("classname", ""),
                    "bucket": classify_failure(msg),
                })
            elif skip_el is not None:
                suites[key]["skip"] += 1
            else:
                suites[key]["pass"] += 1

    passed = total - failed - errors - skipped
    return {
        "total": total, "passed": passed, "failed": failed,
        "errors": errors, "skipped": skipped, "wall": wall,
        "suites": dict(suites),
        "failing_tests": failing_tests,
        "source": "xml",
    }


# ---------------------------------------------------------------------------
# Playwright artifact fallback (no playwright.xml)
# ---------------------------------------------------------------------------

def parse_playwright_artifacts(test_results_dir: Path) -> dict:
    """Read error-context.md files from Playwright artifact directories."""
    failing_tests = []
    suites = defaultdict(lambda: {"tests": 0, "pass": 0, "fail": 0, "err": 0, "skip": 0, "time": 0.0})

    for ec_path in sorted(test_results_dir.glob("*/error-context.md")):
        text = ec_path.read_text(errors="replace")

        name_m   = re.search(r"- Name:\s*(.+)", text)
        loc_m    = re.search(r"- Location:\s*(.+)", text)
        err_m    = re.search(r"```\n(.*?)\n```", text, re.DOTALL)

        name     = name_m.group(1).strip() if name_m else ec_path.parent.name
        location = loc_m.group(1).strip() if loc_m else ""
        error    = err_m.group(1).strip() if err_m else ""

        # Derive suite from test name prefix (e.g. "smoke.test.js >> ...")
        suite_m = re.match(r"(.+?)\s*>>", name)
        suite = Path(suite_m.group(1).strip()).stem if suite_m else "unknown"

        bucket = classify_failure(error)
        suites[suite]["tests"] += 1
        suites[suite]["fail"] += 1
        failing_tests.append({
            "suite": suite,
            "name": name,
            "message": error.split("\n")[0],
            "location": location,
            "bucket": bucket,
        })

    # Try .last-run.json for total failed count (may differ if some had no artifacts)
    last_run_path = test_results_dir / ".last-run.json"
    total_failed = len(failing_tests)
    if last_run_path.exists():
        try:
            lr = json.loads(last_run_path.read_text())
            total_failed = max(total_failed, len(lr.get("failedTests", [])))
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "total": None,
        "passed": None,
        "failed": total_failed,
        "errors": 0,
        "skipped": None,
        "wall": None,
        "suites": dict(suites),
        "failing_tests": failing_tests,
        "source": "artifacts",
    }


# ---------------------------------------------------------------------------
# Deployment ledger
# ---------------------------------------------------------------------------

def load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            e["_dt"] = parse_iso(e["timestamp"])
            entries.append(e)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return sorted(entries, key=lambda e: e["_dt"])


def match_deployment(ledger: list[dict], run_time: datetime | None) -> dict | None:
    """Return the latest deployment whose timestamp is <= run_time."""
    if not ledger:
        return None
    if run_time is None:
        return ledger[-1]
    candidates = [e for e in ledger if e["_dt"] <= run_time]
    return candidates[-1] if candidates else ledger[-1]



# ---------------------------------------------------------------------------
# Run history (from test-results/runs/)
# ---------------------------------------------------------------------------

def load_run_history(runs_dir: Path, ledger: list[dict]) -> list[dict]:
    """Return runs sorted oldest-first, each with pytest_data, pw_data, deployment."""
    if not runs_dir.exists():
        return []
    # Collect all slugs present in runs/
    slugs: dict[str, dict] = {}
    for f in runs_dir.glob("pytest-*.xml"):
        slug = f.stem[len("pytest-"):]
        slugs.setdefault(slug, {})["pytest_path"] = f
    for f in runs_dir.glob("playwright-*.xml"):
        slug = f.stem[len("playwright-"):]
        slugs.setdefault(slug, {})["playwright_path"] = f

    runs = []
    for slug in sorted(slugs):
        entry = slugs[slug]
        pdata = pwdata = None
        root = load_xml(entry.get("pytest_path"))
        if root is not None:
            pdata = parse_pytest_xml(root)
        pw_path = entry.get("playwright_path")
        root = load_xml(pw_path) if pw_path else None
        if root is not None:
            pwdata = parse_playwright_xml(root)
        else:
            pwdata = None
        run_time = pdata["run_time"] if pdata else None
        deploy = match_deployment(ledger, run_time)
        runs.append({
            "slug": slug,
            "run_time": run_time,
            "pytest": pdata,
            "playwright": pwdata,
            "deploy": deploy,
        })
    return runs

# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def bucket_icon(bucket: str) -> str:
    return {"Env": "🟠", "Harness/Config": "🟠", "Perf/Timeout": "🟡", "Product": "🔴"}.get(bucket, "🔴")


def overall_status(pytest_data: dict | None, pw_data: dict | None) -> str:
    if pytest_data is None:
        pw_fail = (pw_data["failed"] or 0) if pw_data else 0
        return "**UNKNOWN** (results pending)" if pw_fail == 0 else "**RED**"
    pytest_fail = (pytest_data["failed"] or 0) + (pytest_data["errors"] or 0)
    pw_fail = (pw_data["failed"] or 0) if pw_data else 0
    if pytest_fail > 0 or pw_fail > 0:
        return "**RED**"
    return "**GREEN**"


def build_report(pytest_data: dict | None, pw_data: dict | None, ledger: list[dict],
                 generated_at: datetime, runs: list[dict] | None = None) -> str:
    run_time = pytest_data.get("run_time") if pytest_data else None
    current_deploy = match_deployment(ledger, run_time)
    status = overall_status(pytest_data, pw_data)

    lines = []

    # Header with generation timestamp
    lines.append(f"# Pipeline Report")
    lines.append(f"")
    lines.append(f"_Generated: {fmt_utc(generated_at)}_")
    lines.append(f"")
    lines.append("---")
    lines.append("")

    # 1. Headline Join
    lines.append("## 1. Headline Join")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    if run_time:
        lines.append(f"| Run timestamp | {fmt_utc(run_time)} |")
    if current_deploy:
        ver     = current_deploy.get("version", "unknown")
        dep_id  = current_deploy.get("deploymentId", "unknown")
        desc    = current_deploy.get("description", "")
        dep_dt  = current_deploy["_dt"]
        delta_s = (run_time - dep_dt).total_seconds() if run_time else None
        delta   = f"({int(delta_s // 60)} min before run)" if delta_s is not None and delta_s >= 0 else ""
        lines.append(f"| Deployment matched | `{ver}` — {desc} |")
        lines.append(f"| DeploymentId | `{dep_id}` |")
        lines.append(f"| Deployed at | {fmt_utc(dep_dt)} {delta} |")
    lines.append(f"| Current deployment status | {status} |")
    if ledger:
        last = ledger[-1]
        lines.append(f"| Current version | `{last.get('version')}` (deployed {fmt_utc(last['_dt'])}) |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Run Summary
    lines.append("## 2. Run Summary")
    lines.append("")

    # Pytest
    lines.append("### Pytest")
    if pytest_data is None:
        lines.append("_No results — pytest.xml not found. Test run may be in progress._")
    else:
        p = pytest_data
        runnable = p["total"] - p["skipped"]
        pass_rate = f"{p['passed'] / runnable * 100:.1f}%" if runnable > 0 else "—"
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total | {p['total']} |")
        lines.append(f"| Passed | {p['passed']} |")
        lines.append(f"| Failed | {p['failed']} |")
        lines.append(f"| Errors | {p['errors']} |")
        lines.append(f"| Skipped | {p['skipped']} |")
        lines.append(f"| Pass rate (of runnable) | {p['passed']} / {runnable} = **{pass_rate}** |")
        lines.append(f"| Wall time | {p['wall']:.1f} s ({seconds_to_hms(p['wall'])}) |")
    lines.append("")

    # Playwright
    if pw_data:
        lines.append("### Playwright")
        if pw_data["source"] == "xml":
            pw_runnable = (pw_data["total"] or 0) - (pw_data["skipped"] or 0)
            pw_rate = f"{pw_data['passed'] / pw_runnable * 100:.1f}%" if pw_runnable > 0 else "—"
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Total | {pw_data['total']} |")
            lines.append(f"| Passed | {pw_data['passed']} |")
            lines.append(f"| Failed | {pw_data['failed']} |")
            lines.append(f"| Errors | {pw_data['errors']} |")
            lines.append(f"| Skipped | {pw_data['skipped']} |")
            lines.append(f"| Pass rate (of runnable) | {pw_data['passed']} / {pw_runnable} = **{pw_rate}** |")
            if pw_data["wall"]:
                lines.append(f"| Wall time | {pw_data['wall']:.1f} s ({seconds_to_hms(pw_data['wall'])}) |")
        else:
            lines.append("_No `playwright.xml` found — reporting from failure artifact directories._")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Failed (confirmed from artifacts) | {pw_data['failed']} |")
            lines.append(f"| Passed | unknown |")
        lines.append("")
    else:
        lines.append("### Playwright")
        lines.append("_No Playwright results found (no `playwright.xml` and no artifact directories)._")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 3. Per-Suite Table
    lines.append("## 3. Per-Suite Table")
    lines.append("")

    lines.append("### Pytest")
    lines.append("")
    if pytest_data is None:
        lines.append("_No results — pytest.xml not found._")
    else:
        p = pytest_data
        lines.append("| Suite | Tests | Pass | Fail | Err | Skip | Time (s) |")
        lines.append("|-------|------:|-----:|-----:|----:|-----:|---------:|")
        for suite_name in sorted(p["suites"]):
            s = p["suites"][suite_name]
            pass_col = f"**{s['pass']}**" if s["fail"] == 0 and s["err"] == 0 else str(s["pass"])
            fail_col = f"**{s['fail']}**" if s["fail"] > 0 else "0"
            err_col  = f"**{s['err']}**"  if s["err"]  > 0 else "0"
            lines.append(f"| {suite_name} | {s['tests']} | {pass_col} | {fail_col} | {err_col} | {s['skip']} | {s['time']:.1f} |")
        lines.append(f"| **Total** | **{p['total']}** | **{p['passed']}** | **{p['failed']}** | **{p['errors']}** | **{p['skipped']}** | **{p['wall']:.1f}** |")
        lines.append("")
        if p["skipped_tests"]:
            lines.append("**Skipped / xfail:**")
            for sk in p["skipped_tests"]:
                lines.append(f"- `{sk['suite']}::{sk['name']}` — {sk['message']}")
            lines.append("")

    if pw_data and pw_data.get("suites"):
        lines.append("### Playwright")
        lines.append("")
        lines.append("| Suite | Tests | Pass | Fail | Err | Skip | Time (s) |")
        lines.append("|-------|------:|-----:|-----:|----:|-----:|---------:|")
        for suite_name in sorted(pw_data["suites"]):
            s = pw_data["suites"][suite_name]
            total_s = s["tests"]
            fail_col = f"**{s['fail']}**" if s["fail"] > 0 else "0"
            time_col = f"{s['time']:.1f}" if s["time"] else "—"
            lines.append(f"| {suite_name} | {total_s} | {s['pass']} | {fail_col} | {s['err']} | {s['skip']} | {time_col} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 4. Failure Triage
    lines.append("## 4. Failure Triage by Root-Cause Bucket")
    lines.append("")

    all_failures = (pytest_data["failing_tests"] if pytest_data else []) + (pw_data["failing_tests"] if pw_data else [])

    if not all_failures:
        lines.append("_No failures._")
    else:
        by_bucket = defaultdict(list)
        for f in all_failures:
            by_bucket[f["bucket"]].append(f)

        bucket_order = ["Env", "Harness/Config", "Perf/Timeout", "Product"]
        for bucket in bucket_order:
            icon = bucket_icon(bucket)
            items = by_bucket.get(bucket, [])
            lines.append(f"### {icon} {bucket}")
            if not items:
                lines.append("_None._")
            else:
                lines.append("")
                lines.append("| Test | Location | Error |")
                lines.append("|------|----------|-------|")
                for f in items:
                    name = f.get("name", "")
                    loc  = f.get("location", f.get("classname", ""))
                    msg  = f.get("message", "").replace("\n", " ").replace("|", "\\|")
                    # Truncate long messages
                    if len(msg) > 120:
                        msg = msg[:117] + "..."
                    lines.append(f"| `{name}` | {loc} | {msg} |")
            lines.append("")

    lines.append("---")
    lines.append("")

    # 5. Deployments & Test Coverage
    lines.append("## 5. Deployments & Test Coverage")
    lines.append("")
    if not ledger:
        lines.append("_No deployment ledger found._")
    else:
        # Build a lookup: deployment index -> list of runs that ran against it
        # A run belongs to deployment D if run_time is in [D.time, next_D.time)
        deploy_runs: dict[int, list] = {i: [] for i in range(len(ledger))}
        for run in (runs or []):
            rt = run["run_time"]
            if rt is None:
                continue
            for idx, dep in enumerate(ledger):
                next_dt = ledger[idx + 1]["_dt"] if idx + 1 < len(ledger) else None
                if rt >= dep["_dt"] and (next_dt is None or rt < next_dt):
                    deploy_runs[idx].append(run)
                    break

        lines.append("| # | Version | Deployed (UTC) | Test Run (UTC) | Pytest | Playwright | Status |")
        lines.append("|---|---------|----------------|----------------|--------|------------|--------|")
        for i, dep in enumerate(reversed(ledger)):
            idx      = len(ledger) - 1 - i
            ver      = dep.get("version", "?")
            dep_ts   = fmt_utc(dep["_dt"])
            is_cur   = " ←" if dep is current_deploy else ""
            dep_runs = deploy_runs.get(idx, [])

            if not dep_runs:
                # Untested deployment
                if dep is current_deploy and pytest_data is None:
                    status_s = "⏳ pending"
                else:
                    status_s = "— untested"
                lines.append(f"| {idx+1} | `{ver}`{is_cur} | {dep_ts} | — | — | — | {status_s} |")
            else:
                for run in dep_runs:
                    rt   = fmt_utc(run["run_time"]) if run["run_time"] else "—"
                    p    = run["pytest"]
                    pw   = run["playwright"]
                    py_s = f"{p['passed']}/{p['total']} ({p['failed']+p['errors']} ✗)" if p else "—"
                    pw_s = f"{pw['passed']}/{pw['total']} ({pw['failed']+pw['errors']} ✗)" if pw else "—"
                    st   = overall_status(p, pw).replace("**", "")
                    icon = "🔴" if "RED" in st else ("🟢" if "GREEN" in st else "⏳")
                    lines.append(f"| {idx+1} | `{ver}`{is_cur} | {dep_ts} | {rt} | {py_s} | {pw_s} | {icon} {st} |")

        if len(ledger) > 1:
            first = ledger[0]["_dt"]
            last  = ledger[-1]["_dt"]
            span_h = (last - first).total_seconds() / 3600
            tested = sum(1 for dep_list in deploy_runs.values() if dep_list)
            lines.append("")
            lines.append(f"**{len(ledger)} deployment(s)** over {span_h:.1f} h — {tested} tested, {len(ledger)-tested} untested.")
            if runs and len(runs) > 1:
                reds = sum(1 for r in runs if "RED" in overall_status(r["pytest"], r["playwright"]))
                lines.append(f"**Trend:** {len(runs)} run(s) — {reds} 🔴 red, {len(runs)-reds} 🟢 green.")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 6. Health Flags
    lines.append("## 6. Health Flags & Recommended Next Action")
    lines.append("")
    lines.append("| Flag | Severity | Detail |")
    lines.append("|------|----------|--------|")

    # Derive flags from failures in the most recent run
    pw_no_xml = pw_data and pw_data.get("source") == "artifacts"
    has_product = any(f["bucket"] == "Product" for f in all_failures)
    has_perf    = any(f["bucket"] == "Perf/Timeout" for f in all_failures)
    has_env     = any(f["bucket"] in ("Env", "Harness/Config") for f in all_failures)

    if has_product:
        for f in [x for x in all_failures if x["bucket"] == "Product"]:
            name = f.get("name", "unknown test")
            lines.append(f"| `{name}` | 🔴 RED | Product failure — see triage above |")
    if has_perf:
        for f in [x for x in all_failures if x["bucket"] == "Perf/Timeout"]:
            name = f.get("name", "unknown test")
            lines.append(f"| `{name}` | 🟡 YELLOW | Perf/Timeout — environment or latency, not confirmed product failure |")
    if has_env:
        for f in [x for x in all_failures if x["bucket"] in ("Env", "Harness/Config")]:
            name = f.get("name", "unknown test")
            lines.append(f"| `{name}` | 🟠 ORANGE | Env/Config — check add-on installation or token setup |")
    if pw_no_xml:
        lines.append("| No `playwright.xml` | 🟠 INFO | Playwright JUnit reporter not producing output — total count unknown |")
    if not runs:
        lines.append("| No archived runs | 🔵 INFO | Run `archive-test-results.py` after each suite to build coverage history |")
    elif len(runs) == 1:
        lines.append("| Single run | 🔵 INFO | No trend data — flaky classification requires ≥2 runs |")
    if not all_failures and not pw_no_xml and (pytest_data is not None or pw_data is not None):
        lines.append("| All tests passing | 🟢 GREEN | No failures detected |")
    if pytest_data is None and pw_data is None:
        lines.append("| No results | ⏳ PENDING | Tests in progress or not yet run against current deployment |")

    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text renderer (converts markdown output to terminal-friendly plain text)
# ---------------------------------------------------------------------------

def _strip_inline(text: str) -> str:
    """Remove **bold**, _italic_, `code` markers; unescape \\|."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = text.replace('\\|', '|')
    return text


def _render_text_table(table_lines: list[str]) -> list[str]:
    rows = []
    for line in table_lines:
        if re.match(r'^\|[-:\s|]+\|$', line):
            continue
        cells = [_strip_inline(c.strip()) for c in line.strip('|').split('|')]
        rows.append(cells)
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    widths = [0] * ncols
    for row in rows:
        for j, cell in enumerate(row[:ncols]):
            widths[j] = max(widths[j], len(cell))
    out = []
    for k, row in enumerate(rows):
        padded = [row[j].ljust(widths[j]) if j < len(row) else ' ' * widths[j]
                  for j in range(ncols)]
        out.append('  '.join(padded).rstrip())
        if k == 0:
            out.append('  '.join('─' * w for w in widths))
    return out


def md_to_text(md: str) -> str:
    """Convert the markdown pipeline report to a plain-text terminal layout."""
    result = []
    lines = md.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('# '):
            text = _strip_inline(line[2:])
            result.append(text)
            result.append('═' * len(text))
        elif line.startswith('## '):
            text = _strip_inline(line[3:])
            result.append('')
            result.append(text)
            result.append('─' * len(text))
        elif line.startswith('### '):
            text = _strip_inline(line[4:])
            result.append('')
            result.append(text)
            result.append('·' * len(text))
        elif line == '---':
            result.append('━' * 72)
        elif line.startswith('|'):
            table_block = []
            while i < len(lines) and lines[i].startswith('|'):
                table_block.append(lines[i])
                i += 1
            result.extend(_render_text_table(table_block))
            continue  # i already advanced past table
        else:
            result.append(_strip_inline(line))
        i += 1
    return '\n'.join(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate pipeline-report.md")
    parser.add_argument("--root", default=".", help="Project root directory (default: .)")
    parser.add_argument("--output", default="pipeline-report.md",
                        help="Output file path (default: pipeline-report.md)")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing file")
    parser.add_argument("--format", choices=["text", "md"], default=None,
                        help="Output format: text (terminal) or md (markdown). "
                             "Defaults to 'text' with --stdout, 'md' when writing to file.")
    args = parser.parse_args()

    # Smart default: text for terminal, md for file
    if args.format is None:
        args.format = "text" if args.stdout else "md"

    root = Path(args.root).resolve()
    test_results = root / "test-results"
    ledger_path  = root / "deployment-ledger" / "test.jsonl"

    # Load pytest results (optional — may be absent while a run is in progress)
    pytest_root = load_xml(test_results / "pytest.xml")
    if pytest_root is None:
        pytest_data = None
    else:
        pytest_data = parse_pytest_xml(pytest_root)

    # Load Playwright results
    pw_xml_root = load_xml(test_results / "playwright.xml")
    if pw_xml_root is not None:
        pw_data = parse_playwright_xml(pw_xml_root)
        pw_data["source"] = "xml"
    else:
        artifact_dirs = [d for d in test_results.iterdir()
                         if d.is_dir() and (d / "error-context.md").exists()]
        if artifact_dirs:
            pw_data = parse_playwright_artifacts(test_results)
        else:
            pw_data = None

    # Load deployment ledger and run history
    ledger = load_ledger(ledger_path)
    runs = load_run_history(test_results / "runs", ledger)

    generated_at = datetime.now(timezone.utc)
    md_report = build_report(pytest_data, pw_data, ledger, generated_at, runs)
    report = md_to_text(md_report) if args.format == "text" else md_report

    if args.stdout:
        print(report)
    else:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = root / out_path
        out_path.write_text(report)
        print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
