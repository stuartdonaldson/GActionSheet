#!/usr/bin/env python3
"""
session-cost-report.py — Day-by-day Claude Code session cost report.

Reads session transcript JSONL files from a Claude Code project directory
and outputs a table of token usage and estimated cost per day, broken down
by model.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Pricing per million tokens (USD). Matched by substring of model ID.
# Keys are checked in order; first match wins.
MODEL_RATES = [
    ("opus",   {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50}),
    ("sonnet", {"input":  3.00, "output": 15.00, "cache_write":  3.75, "cache_read": 0.30}),
    ("haiku",  {"input":  0.80, "output":  4.00, "cache_write":  1.00, "cache_read": 0.08}),
]
DEFAULT_RATES = {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30}


def rates_for(model: str) -> dict:
    m = (model or "").lower()
    for key, r in MODEL_RATES:
        if key in m:
            return r
    return DEFAULT_RATES


def short_model(model: str) -> str:
    """Strip 'claude-' prefix and date suffixes for compact column headers."""
    s = model.removeprefix("claude-")
    # drop trailing -YYYYMMDD or -YYYYMMDDHHMMSS
    parts = s.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) >= 8:
        s = parts[0]
    return s


def project_slug(cwd: str) -> str:
    return cwd.replace("/", "-")


def resolve_transcript_dir(args) -> Path:
    if args.project_dir:
        return Path(args.project_dir).expanduser()
    cwd = args.cwd or os.getcwd()
    slug = project_slug(cwd)
    return Path.home() / ".claude" / "projects" / slug


def first_timestamp(path: Path) -> datetime | None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    ts = o.get("timestamp")
                    if ts:
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return None


def parse_session(path: Path, cutoff: date, day_data: dict, all_models: set):
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue

        if o.get("type") != "assistant":
            continue

        ts_str = o.get("timestamp")
        if not ts_str:
            continue
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        day = ts.astimezone(timezone.utc).date()
        if day < cutoff:
            continue

        msg = o.get("message", {})
        model = msg.get("model") or "unknown"
        usage = msg.get("usage")

        if usage:
            all_models.add(model)
            b = day_data[day]
            b["turns"] += 1
            b["model_turns"][model] += 1
            b["input"] += usage.get("input_tokens", 0)
            b["output"] += usage.get("output_tokens", 0)
            b["cache_write"] += usage.get("cache_creation_input_tokens", 0)
            b["cache_read"] += usage.get("cache_read_input_tokens", 0)
            # Cost computed per-turn with the correct model's rates
            r = rates_for(model)
            b["cost"] += (
                usage.get("input_tokens", 0) * r["input"]
                + usage.get("output_tokens", 0) * r["output"]
                + usage.get("cache_creation_input_tokens", 0) * r["cache_write"]
                + usage.get("cache_read_input_tokens", 0) * r["cache_read"]
            ) / 1_000_000

        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") in ("Write", "Edit"):
                fp = block.get("input", {}).get("file_path")
                if fp:
                    day_data[day]["files"].add(fp)


def new_day_bucket():
    return {
        "turns": 0, "input": 0, "output": 0,
        "cache_write": 0, "cache_read": 0,
        "cost": 0.0, "files": set(),
        "model_turns": defaultdict(int),
    }


def fmt(n: int) -> str:
    return f"{n:,}"


# ── Markdown output ────────────────────────────────────────────────────────────

def build_markdown(day_data: dict, days: int, models: list[str]) -> str:
    today = date.today()
    date_range = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    model_labels = [short_model(m) for m in models]

    mcols = " | ".join(f"{lbl}" for lbl in model_labels)
    msep  = " | ".join("------:" for _ in models)
    header = f"| Date | Turns | {mcols} | Input | Output | Cache Writes | Cache Reads | Files | Est. Cost |"
    sep    = f"|------|------:| {msep} |------:|-------:|-------------:|------------:|------:|----------:|"
    rows = [header, sep]

    tot_turns = tot_input = tot_output = tot_cw = tot_cr = 0
    tot_cost = 0.0
    tot_files: set = set()
    tot_model: dict = defaultdict(int)

    for d in date_range:
        b = day_data.get(d)
        if b is None:
            dash_mcols = " | ".join("—" for _ in models)
            rows.append(f"| {d} | — | {dash_mcols} | — | — | — | — | — | — |")
            continue
        mt = " | ".join(str(b["model_turns"].get(m, 0)) for m in models)
        rows.append(
            f"| {d} | {b['turns']} | {mt} | {fmt(b['input'])} | {fmt(b['output'])} "
            f"| {fmt(b['cache_write'])} | {fmt(b['cache_read'])} "
            f"| {len(b['files'])} | ${b['cost']:.2f} |"
        )
        tot_turns += b["turns"]
        tot_input += b["input"]
        tot_output += b["output"]
        tot_cw += b["cache_write"]
        tot_cr += b["cache_read"]
        tot_cost += b["cost"]
        tot_files |= b["files"]
        for m in models:
            tot_model[m] += b["model_turns"].get(m, 0)

    tot_mt = " | ".join(f"**{tot_model[m]}**" for m in models)
    rows.append(
        f"| **Total** | **{tot_turns}** | {tot_mt} | **{fmt(tot_input)}** | **{fmt(tot_output)}** "
        f"| **{fmt(tot_cw)}** | **{fmt(tot_cr)}** "
        f"| **{len(tot_files)}** | **${tot_cost:.2f}** |"
    )

    rate_notes = "; ".join(
        f"{short_model(m)}: ${rates_for(m)['input']}/${rates_for(m)['output']} in/out"
        for m in models
    )
    legend = f"\n_Rates ($/MTok input/output): {rate_notes}. Actual billing depends on your plan._"
    return "\n".join(rows) + "\n" + legend


# ── Terminal (plain text) output ───────────────────────────────────────────────

def build_text(day_data: dict, days: int, models: list[str]) -> str:
    today = date.today()
    date_range = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    model_labels = [short_model(m) for m in models]

    # Collect all cell values first so we can size columns
    COL_DATE = "Date"
    COL_TURNS = "Turns"
    COL_INPUT = "Input"
    COL_OUTPUT = "Output"
    COL_CW = "Cache W"
    COL_CR = "Cache R"
    COL_FILES = "Files"
    COL_COST = "Cost"

    fixed_headers = [COL_DATE, COL_TURNS] + model_labels + [COL_INPUT, COL_OUTPUT, COL_CW, COL_CR, COL_FILES, COL_COST]

    tot_turns = tot_input = tot_output = tot_cw = tot_cr = 0
    tot_cost = 0.0
    tot_files: set = set()
    tot_model: dict = defaultdict(int)

    data_rows = []
    for d in date_range:
        b = day_data.get(d)
        if b is None:
            row = [str(d), "—"] + ["—"] * len(models) + ["—", "—", "—", "—", "—", "—"]
        else:
            mt = [str(b["model_turns"].get(m, 0)) for m in models]
            row = (
                [str(d), str(b["turns"])]
                + mt
                + [fmt(b["input"]), fmt(b["output"]), fmt(b["cache_write"]),
                   fmt(b["cache_read"]), str(len(b["files"])), f"${b['cost']:.2f}"]
            )
            tot_turns += b["turns"]
            tot_input += b["input"]
            tot_output += b["output"]
            tot_cw += b["cache_write"]
            tot_cr += b["cache_read"]
            tot_cost += b["cost"]
            tot_files |= b["files"]
            for m in models:
                tot_model[m] += b["model_turns"].get(m, 0)
        data_rows.append(row)

    tot_mt = [str(tot_model[m]) for m in models]
    total_row = (
        ["TOTAL", str(tot_turns)]
        + tot_mt
        + [fmt(tot_input), fmt(tot_output), fmt(tot_cw),
           fmt(tot_cr), str(len(tot_files)), f"${tot_cost:.2f}"]
    )

    # Compute column widths
    all_rows = [fixed_headers] + data_rows + [total_row]
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(fixed_headers))]

    def render_row(row, bold=False):
        cells = []
        for i, cell in enumerate(row):
            # right-align numbers/cost, left-align date
            if i == 0:
                cells.append(cell.ljust(widths[i]))
            else:
                cells.append(cell.rjust(widths[i]))
        line = "  ".join(cells)
        return line

    def sep_line():
        return "  ".join("─" * w for w in widths)

    lines = []
    lines.append(render_row(fixed_headers))
    lines.append(sep_line())
    for row in data_rows:
        lines.append(render_row(row))
    lines.append(sep_line())
    lines.append(render_row(total_row))

    rate_notes = "  ".join(
        f"{short_model(m)}: ${rates_for(m)['input']}/${rates_for(m)['output']}/MTok"
        for m in models
    )
    lines.append(f"\nRates (input/output): {rate_notes}")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Day-by-day Claude session cost report")
    parser.add_argument("--days", type=int, default=7, help="Number of past days to include (default: 7)")
    parser.add_argument("--project-dir", help="Path to Claude project transcript directory")
    parser.add_argument("--cwd", help="Project cwd for slug derivation (default: current directory)")
    parser.add_argument("--format", choices=["markdown", "text"], default="markdown",
                        help="Output format: markdown (default) or text (terminal-friendly)")
    args = parser.parse_args()

    transcript_dir = resolve_transcript_dir(args)
    if not transcript_dir.exists():
        print(f"Error: transcript directory not found: {transcript_dir}", file=sys.stderr)
        sys.exit(1)

    today = date.today()
    cutoff = today - timedelta(days=args.days - 1)

    day_data: dict = defaultdict(new_day_bucket)
    all_models: set = set()

    session_files = sorted(transcript_dir.glob("*.jsonl"))
    processed = 0
    for path in session_files:
        first_ts = first_timestamp(path)
        if first_ts is not None and first_ts.date() < cutoff:
            mtime = date.fromtimestamp(path.stat().st_mtime)
            if mtime < cutoff:
                continue
        parse_session(path, cutoff, day_data, all_models)
        processed += 1

    # Stable model order: opus first, then sonnet, then haiku, then others
    def model_sort_key(m):
        m_lower = m.lower()
        for i, (key, _) in enumerate(MODEL_RATES):
            if key in m_lower:
                return i
        return len(MODEL_RATES)

    models = sorted(all_models, key=model_sort_key)

    prefix = f"Scanned {processed} session files in {transcript_dir}\n"
    if args.format == "text":
        print(prefix)
        print(build_text(day_data, args.days, models))
    else:
        print(f"_{prefix.strip()}_\n")
        print(build_markdown(day_data, args.days, models))


if __name__ == "__main__":
    main()
