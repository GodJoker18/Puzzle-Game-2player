"""analyze.py  --  DDA Evaluation Workflow Script

Reads the gameplay event CSV and produces per-mode, per-puzzle-type summary
statistics useful for comparing the three DDA modes in a research context.

Usage
-----
    python analyze.py                      # reads default logs/events.csv
    python analyze.py --log path/to/file   # read a specific file
    python analyze.py --session SESSION_ID # filter to one session

Output columns (printed to stdout, one table per section):
    - mode             : static | performance_only | communication_aware
    - puzzle_type      : color_order | grid_path | coop_symbol
    - n_started        : number of level_start events
    - n_completed      : number of puzzle_complete events
    - completion_rate  : n_completed / n_started
    - mean_time_s      : mean elapsed seconds at puzzle_complete
    - mean_mistakes    : mean failure count recorded in dda_decision detail
    - hint_rate        : hint_shown events / n_completed
    - timeout_rate     : fraction of completed puzzles where timed_out=True
    - n_dda_decisions  : number of dda_decision events
    - mean_tier_start  : mean prev_tier from dda_decision rows
    - mean_tier_end    : mean new_tier from dda_decision rows
    - tier_increase_rate : fraction of dda_decisions where adjustment > 0
    - tier_decrease_rate : fraction of dda_decisions where adjustment < 0

Research limitations are printed at the end of each run.

Limitations
-----------
- Communication proxy columns (clue count, latency) are only populated when
  Player 2 presses the C/R keys.  Most real sessions will not have them.
- Mode detection uses the 'session_start' detail field; older sessions logged
  before the dda_mode field was added will show mode=unknown.
- This script reads real gameplay data only; it does NOT generate synthetic data.
  Synthetic data produced by test scripts is clearly identified by the test
  framework writing to a tmp_path fixture, not to logs/events.csv.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_LOG = Path(__file__).parent / "logs" / "events.csv"

KNOWN_MODES = {"static", "performance_only", "communication_aware", "unknown"}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_detail(detail: str) -> Dict[str, str]:
    """Split 'key=val;key2=val2' into a dict.  Values are always strings."""
    out: Dict[str, str] = {}
    for part in detail.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _safe_float(val: str, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SessionRecord:
    """All parsed events for one session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.mode: str = "unknown"
        self.started: List[dict] = []       # level_start rows
        self.completed: List[dict] = []     # puzzle_complete rows
        self.decisions: List[dict] = []     # dda_decision rows
        self.hints: List[dict] = []         # hint_shown rows
        self.timeouts: List[dict] = []      # timeout action rows (rare, kept for future use)


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def load_sessions(
    path: Path,
    session_filter: Optional[str] = None,
) -> Dict[str, SessionRecord]:
    """Read the CSV log and group rows by session_id.

    Only the session matching ``session_filter`` is kept when the argument is
    provided.
    """
    sessions: Dict[str, SessionRecord] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("session_id", "").strip()
            if not sid:
                continue
            if session_filter and sid != session_filter:
                continue

            if sid not in sessions:
                sessions[sid] = SessionRecord(sid)
            rec = sessions[sid]

            action = row.get("action", "").strip()
            detail = row.get("detail", "")
            level = _safe_int(row.get("level", "0"))
            ptype = row.get("puzzle_type", "").strip()
            elapsed = _safe_float(row.get("elapsed_s", "0"))

            if action == "session_start":
                d = _parse_detail(detail)
                rec.mode = d.get("dda_mode", "unknown")

            elif action == "level_start":
                d = _parse_detail(detail)
                rec.started.append({
                    "level": level,
                    "puzzle_type": ptype,
                    "time_limit_s": _safe_float(d.get("time_limit_s", "0")),
                })

            elif action == "puzzle_complete":
                d = _parse_detail(detail)
                rec.completed.append({
                    "level": level,
                    "puzzle_type": ptype,
                    "elapsed_s": elapsed,
                    "mistakes": _safe_int(d.get("mistakes", "0")),
                    "timed_out": d.get("timed_out", "False") not in ("False", "0", ""),
                })

            elif action == "dda_decision":
                d = _parse_detail(detail)
                rec.decisions.append({
                    "level": level,
                    "puzzle_type": ptype,
                    "elapsed_s": elapsed,
                    "mode": d.get("mode", rec.mode),
                    "perf": _safe_float(d.get("perf", "0")),
                    "comm": _safe_float(d.get("comm", "0.5")),
                    "combined": _safe_float(d.get("combined", "0")),
                    "prev_tier": _safe_int(d.get("prev_tier", "0")),
                    "new_tier": _safe_int(d.get("new_tier", "0")),
                    "adjustment": _safe_int(d.get("adjustment", "0")),
                    "failures": _safe_int(d.get("failures", "0")),
                    "hint": _safe_int(d.get("hint", "0")),
                    "timed_out_flag": _safe_int(d.get("timed_out", "0")),
                    "clues": _safe_int(d.get("clues", "0")),
                    "repeats": _safe_int(d.get("repeats", "0")),
                })

            elif action == "hint_shown":
                rec.hints.append({"level": level, "puzzle_type": ptype})

            elif action == "timeout":
                rec.timeouts.append({"level": level, "puzzle_type": ptype})

    return sessions


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------

def _mean(vals: List[float]) -> Optional[float]:
    """Return arithmetic mean, or None when the list is empty."""
    return sum(vals) / len(vals) if vals else None


def compute_summary(sessions: Dict[str, SessionRecord]) -> List[dict]:
    """Build one summary row per (mode, puzzle_type) across all sessions.

    Returns a list of dicts.  All numeric fields are Python floats / ints or
    None when there is no data.
    """
    completed_by: Dict[tuple, List[dict]] = defaultdict(list)
    started_by: Dict[tuple, int] = defaultdict(int)
    decisions_by: Dict[tuple, List[dict]] = defaultdict(list)
    hints_by: Dict[tuple, int] = defaultdict(int)

    for rec in sessions.values():
        mode = rec.mode
        for item in rec.started:
            key = (mode, item["puzzle_type"])
            started_by[key] += 1
        for item in rec.completed:
            key = (mode, item["puzzle_type"])
            completed_by[key].append(item)
        for item in rec.decisions:
            # Use mode from decision detail (more reliable than session_start
            # for sessions where mode was toggled)
            key = (item.get("mode", mode), item["puzzle_type"])
            decisions_by[key].append(item)
        for item in rec.hints:
            key = (mode, item["puzzle_type"])
            hints_by[key] += 1

    all_keys = sorted(set(list(completed_by.keys()) + list(started_by.keys())))
    rows = []

    for (mode, ptype) in all_keys:
        comps = completed_by[(mode, ptype)]
        decs = decisions_by[(mode, ptype)]
        n_started = started_by[(mode, ptype)]
        n_comp = len(comps)

        completion_rate = (n_comp / n_started) if n_started > 0 else None

        times = [c["elapsed_s"] for c in comps]
        mistakes_list = [float(c["mistakes"]) for c in comps]
        timed_out_flags = [float(c["timed_out"]) for c in comps]

        n_hints = hints_by[(mode, ptype)]
        hint_rate = (n_hints / n_comp) if n_comp > 0 else None
        timeout_rate = _mean(timed_out_flags)

        n_decs = len(decs)
        mean_tier_start = _mean([float(d["prev_tier"]) for d in decs])
        mean_tier_end = _mean([float(d["new_tier"]) for d in decs])
        tier_increases = (
            sum(1 for d in decs if d["adjustment"] > 0) / n_decs
            if n_decs > 0 else None
        )
        tier_decreases = (
            sum(1 for d in decs if d["adjustment"] < 0) / n_decs
            if n_decs > 0 else None
        )
        mean_clues = _mean([float(d["clues"]) for d in decs])
        mean_repeats = _mean([float(d["repeats"]) for d in decs])

        rows.append({
            "mode": mode,
            "puzzle_type": ptype,
            "n_started": n_started,
            "n_completed": n_comp,
            "completion_rate": completion_rate,
            "mean_time_s": _mean(times),
            "mean_mistakes": _mean(mistakes_list),
            "hint_rate": hint_rate,
            "timeout_rate": timeout_rate,
            "n_dda_decisions": n_decs,
            "mean_tier_start": mean_tier_start,
            "mean_tier_end": mean_tier_end,
            "tier_increase_rate": tier_increases,
            "tier_decrease_rate": tier_decreases,
            "mean_clues_per_puzzle": mean_clues,
            "mean_repeats_per_puzzle": mean_repeats,
        })

    return rows


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------

def _fmt(val: Optional[float], decimals: int = 2) -> str:
    if val is None:
        return "n/a"
    return f"{val:.{decimals}f}"


def print_session_list(sessions: Dict[str, SessionRecord]) -> None:
    hdr = f"{'SESSION':40s}  {'MODE':22s}  {'STARTED':7s}  {'COMPLETED':9s}  {'DDA':5s}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for rec in sessions.values():
        print(
            f"{rec.session_id:40s}  {rec.mode:22s}  "
            f"{len(rec.started):7d}  {len(rec.completed):9d}  {len(rec.decisions):5d}"
        )


def print_summary(rows: List[dict]) -> None:
    if not rows:
        print("  (no data)\n")
        return

    header = [
        ("mode", 22), ("puzzle_type", 16), ("start", 5), ("comp", 4),
        ("comp%", 6), ("time_s", 7), ("errs", 5), ("hint%", 6),
        ("tout%", 6), ("n_dda", 5), ("t.s", 5), ("t.e", 5),
        ("inc%", 5), ("dec%", 5),
    ]
    widths = {h[0]: h[1] for h in header}
    cols = [h[0] for h in header]

    print("  ".join(f"{c:<{widths[c]}}" for c in cols))
    print("  ".join("-" * widths[c] for c in cols))

    for row in rows:
        vals = {
            "mode": row["mode"],
            "puzzle_type": row["puzzle_type"],
            "start": str(row["n_started"]),
            "comp": str(row["n_completed"]),
            "comp%": _fmt(row["completion_rate"]),
            "time_s": _fmt(row["mean_time_s"]),
            "errs": _fmt(row["mean_mistakes"]),
            "hint%": _fmt(row["hint_rate"]),
            "tout%": _fmt(row["timeout_rate"]),
            "n_dda": str(row["n_dda_decisions"]),
            "t.s": _fmt(row["mean_tier_start"]),
            "t.e": _fmt(row["mean_tier_end"]),
            "inc%": _fmt(row["tier_increase_rate"]),
            "dec%": _fmt(row["tier_decrease_rate"]),
        }
        print("  ".join(f"{vals[c]:<{widths[c]}}" for c in cols))


def print_limitations() -> None:
    print("\n" + "=" * 72)
    print("RESEARCH LIMITATIONS")
    print("=" * 72)
    print(
        "1. Communication proxies (C/R keys) require manual marking by Player 2.\n"
        "   Columns 'mean_clues_per_puzzle' and 'mean_repeats_per_puzzle' only\n"
        "   reflect those key-presses -- they are NOT direct measures of verbal\n"
        "   communication.\n"
        "\n"
        "2. completion_rate = completed / started; restarts mid-level may skew\n"
        "   this above 1.0 in rare cases.\n"
        "\n"
        "3. A controlled comparison requires sessions with matching players,\n"
        "   identical level seeds, and equivalent starting tiers across modes.\n"
        "   Mixing modes within a single log does not constitute a valid\n"
        "   controlled experiment.\n"
        "\n"
        "4. All data here is real gameplay data. Test-generated data is written\n"
        "   to tmp directories via pytest fixtures, never to logs/events.csv."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarise DDA evaluation metrics from the gameplay CSV log."
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"CSV log file (default: {DEFAULT_LOG})",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Restrict analysis to one session_id.",
    )
    parser.add_argument(
        "--no-limits",
        action="store_true",
        help="Suppress the research-limitations footer.",
    )
    args = parser.parse_args(argv)

    if not args.log.exists():
        print(f"Error: log file not found: {args.log}", file=sys.stderr)
        return 1

    sessions = load_sessions(args.log, session_filter=args.session)
    if not sessions:
        print("No sessions found.", file=sys.stderr)
        return 1

    total_starts = sum(len(r.started) for r in sessions.values())
    print(f"\nLog : {args.log}")
    print(f"Data: {total_starts} level-starts across {len(sessions)} session(s)\n")

    print_session_list(sessions)

    print("\n" + "=" * 72)
    print("SUMMARY BY MODE + PUZZLE TYPE")
    print("=" * 72 + "\n")
    summary = compute_summary(sessions)
    print_summary(summary)

    if not args.no_limits:
        print_limitations()

    return 0


if __name__ == "__main__":
    sys.exit(main())
