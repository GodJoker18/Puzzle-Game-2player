"""Tests for analyze.py -- DDA evaluation analysis script.

All tests use synthetic in-memory data (StringIO / tmp_path) and never read
from or write to logs/events.csv.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import List

import pytest

# Import the module under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyze import (
    _parse_detail,
    _safe_float,
    _safe_int,
    _mean,
    load_sessions,
    compute_summary,
    main,
    SessionRecord,
    DEFAULT_LOG,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIELDS = [
    "timestamp", "session_id", "level", "puzzle_type",
    "action", "attempt", "elapsed_s", "outcome", "detail",
]


def _make_csv(tmp_path: Path, rows: List[dict]) -> Path:
    """Write a minimal CSV to a tmp file and return its path."""
    path = tmp_path / "test_events.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            full_row = {k: row.get(k, "") for k in FIELDS}
            writer.writerow(full_row)
    return path


def _session_row(sid, action, level=0, ptype="", elapsed=0.0,
                 outcome="", detail=""):
    return {
        "timestamp": "2026-01-01T00:00:00.000+00:00",
        "session_id": sid,
        "level": str(level),
        "puzzle_type": ptype,
        "action": action,
        "attempt": "1",
        "elapsed_s": str(elapsed),
        "outcome": outcome,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Unit: parsing helpers
# ---------------------------------------------------------------------------

class TestParseDetail:
    def test_single_pair(self):
        assert _parse_detail("mode=static") == {"mode": "static"}

    def test_multiple_pairs(self):
        d = _parse_detail("mode=static;perf=0.75;tier=2")
        assert d == {"mode": "static", "perf": "0.75", "tier": "2"}

    def test_empty_string(self):
        assert _parse_detail("") == {}

    def test_missing_value(self):
        d = _parse_detail("key=")
        assert d["key"] == ""

    def test_whitespace_tolerant(self):
        d = _parse_detail(" a = 1 ; b = 2 ")
        assert d["a"] == "1"
        assert d["b"] == "2"

    def test_equals_in_value(self):
        # Partition on first '=' only
        d = _parse_detail("solution=blue>red>green")
        assert d["solution"] == "blue>red>green"


class TestSafeConversions:
    def test_float_valid(self):
        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_float_invalid_returns_default(self):
        assert _safe_float("abc") == 0.0
        assert _safe_float("") == 0.0
        assert _safe_float(None) == 0.0

    def test_int_valid(self):
        assert _safe_int("5") == 5

    def test_int_invalid_returns_default(self):
        assert _safe_int("x") == 0
        assert _safe_int("") == 0

    def test_positive_adjustment(self):
        # Adjustment stored as "+1" in logs
        assert _safe_int("+1") == 1


class TestMean:
    def test_empty_list_returns_none(self):
        assert _mean([]) is None

    def test_single_value(self):
        assert _mean([7.0]) == 7.0

    def test_multiple_values(self):
        assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)

    def test_mean_preserves_float(self):
        result = _mean([1.5, 2.5])
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Integration: load_sessions
# ---------------------------------------------------------------------------

class TestLoadSessions:
    def test_single_session_mode_detected(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=performance_only"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert sessions["S1"].mode == "performance_only"

    def test_unknown_mode_when_detail_missing(self, tmp_path):
        rows = [_session_row("S1", "session_start")]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert sessions["S1"].mode == "unknown"

    def test_level_start_counted(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=static"),
            _session_row("S1", "level_start", level=1, ptype="color_order",
                         detail="time_limit_s=60;solution=x"),
            _session_row("S1", "level_start", level=2, ptype="grid_path",
                         detail="time_limit_s=90;solution=x"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert len(sessions["S1"].started) == 2

    def test_puzzle_complete_parsed(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=static"),
            _session_row("S1", "puzzle_complete", level=1, ptype="color_order",
                         elapsed=20.5, outcome="success", detail="mistakes=2;timed_out=False"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        comp = sessions["S1"].completed
        assert len(comp) == 1
        assert comp[0]["elapsed_s"] == pytest.approx(20.5)
        assert comp[0]["mistakes"] == 2
        assert comp[0]["timed_out"] is False

    def test_timed_out_true_parsed(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=static"),
            _session_row("S1", "puzzle_complete", level=1, ptype="color_order",
                         elapsed=60.0, detail="mistakes=3;timed_out=True"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert sessions["S1"].completed[0]["timed_out"] is True

    def test_dda_decision_parsed(self, tmp_path):
        detail = (
            "mode=performance_only;perf=0.800;comm=0.500;combined=0.800;"
            "prev_tier=1;new_tier=2;adjustment=+1;failures=0;hint=0;"
            "timed_out=0;clues=0;repeats=0"
        )
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=performance_only"),
            _session_row("S1", "dda_decision", level=1, ptype="color_order",
                         elapsed=20.0, outcome="high_performance", detail=detail),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        dec = sessions["S1"].decisions[0]
        assert dec["prev_tier"] == 1
        assert dec["new_tier"] == 2
        assert dec["adjustment"] == 1
        assert dec["perf"] == pytest.approx(0.800)

    def test_hint_shown_counted(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=static"),
            _session_row("S1", "hint_shown", level=1, ptype="color_order"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert len(sessions["S1"].hints) == 1

    def test_session_filter(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=static"),
            _session_row("S2", "session_start", detail="dda_mode=performance_only"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path, session_filter="S2")
        assert list(sessions.keys()) == ["S2"]

    def test_blank_session_id_skipped(self, tmp_path):
        rows = [
            {"timestamp": "t", "session_id": "", "level": "0", "puzzle_type": "",
             "action": "session_start", "attempt": "", "elapsed_s": "0",
             "outcome": "", "detail": "dda_mode=static"},
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert len(sessions) == 0

    def test_multiple_sessions_independent(self, tmp_path):
        rows = [
            _session_row("A", "session_start", detail="dda_mode=static"),
            _session_row("A", "puzzle_complete", level=1, ptype="color_order",
                         elapsed=10.0, detail="mistakes=1;timed_out=False"),
            _session_row("B", "session_start", detail="dda_mode=performance_only"),
            _session_row("B", "puzzle_complete", level=2, ptype="grid_path",
                         elapsed=30.0, detail="mistakes=0;timed_out=False"),
        ]
        path = _make_csv(tmp_path, rows)
        sessions = load_sessions(path)
        assert sessions["A"].mode == "static"
        assert sessions["B"].mode == "performance_only"
        assert sessions["A"].completed[0]["puzzle_type"] == "color_order"
        assert sessions["B"].completed[0]["puzzle_type"] == "grid_path"


# ---------------------------------------------------------------------------
# Integration: compute_summary
# ---------------------------------------------------------------------------

class TestComputeSummary:
    def _one_session(self, tmp_path, mode: str, ptype: str,
                     n_start=1, n_comp=1, elapsed=20.0,
                     mistakes=0, timed_out=False, hint=False,
                     dda_decision=None):
        """Helper to build a minimal SessionRecord for testing."""
        rec = SessionRecord("S1")
        rec.mode = mode
        for _ in range(n_start):
            rec.started.append({"level": 1, "puzzle_type": ptype, "time_limit_s": 60.0})
        for i in range(n_comp):
            rec.completed.append({
                "level": 1,
                "puzzle_type": ptype,
                "elapsed_s": elapsed,
                "mistakes": mistakes,
                "timed_out": timed_out,
            })
        if hint:
            rec.hints.append({"level": 1, "puzzle_type": ptype})
        if dda_decision:
            rec.decisions.append(dda_decision)
        return {"S1": rec}

    def test_completion_rate_one_of_one(self, tmp_path):
        sessions = self._one_session(tmp_path, "static", "color_order",
                                     n_start=1, n_comp=1)
        rows = compute_summary(sessions)
        assert len(rows) == 1
        assert rows[0]["completion_rate"] == pytest.approx(1.0)

    def test_completion_rate_partial(self, tmp_path):
        sessions = self._one_session(tmp_path, "static", "color_order",
                                     n_start=4, n_comp=3)
        rows = compute_summary(sessions)
        assert rows[0]["completion_rate"] == pytest.approx(0.75)

    def test_mean_time_correct(self, tmp_path):
        rec = SessionRecord("S1")
        rec.mode = "static"
        for t in [10.0, 20.0, 30.0]:
            rec.started.append({"level": 1, "puzzle_type": "color_order", "time_limit_s": 60.0})
            rec.completed.append({"level": 1, "puzzle_type": "color_order",
                                  "elapsed_s": t, "mistakes": 0, "timed_out": False})
        rows = compute_summary({"S1": rec})
        assert rows[0]["mean_time_s"] == pytest.approx(20.0)

    def test_hint_rate_when_no_hints(self, tmp_path):
        sessions = self._one_session(tmp_path, "static", "color_order",
                                     n_comp=2, hint=False)
        rows = compute_summary(sessions)
        assert rows[0]["hint_rate"] == pytest.approx(0.0)

    def test_hint_rate_when_hint_present(self, tmp_path):
        # 1 completed, 1 hint -> rate = 1.0
        sessions = self._one_session(tmp_path, "static", "color_order",
                                     n_comp=1, hint=True)
        rows = compute_summary(sessions)
        assert rows[0]["hint_rate"] == pytest.approx(1.0)

    def test_timeout_rate(self, tmp_path):
        rec = SessionRecord("S1")
        rec.mode = "static"
        for timed_out in [True, False, False, False]:
            rec.started.append({"level": 1, "puzzle_type": "grid_path", "time_limit_s": 90.0})
            rec.completed.append({"level": 1, "puzzle_type": "grid_path",
                                  "elapsed_s": 50.0, "mistakes": 0, "timed_out": timed_out})
        rows = compute_summary({"S1": rec})
        assert rows[0]["timeout_rate"] == pytest.approx(0.25)

    def test_dda_tier_increase_rate(self, tmp_path):
        dec = {
            "level": 1, "puzzle_type": "color_order", "elapsed_s": 10.0,
            "mode": "performance_only", "perf": 0.9, "comm": 0.5, "combined": 0.9,
            "prev_tier": 1, "new_tier": 2, "adjustment": 1,
            "failures": 0, "hint": 0, "timed_out_flag": 0, "clues": 0, "repeats": 0,
        }
        sessions = self._one_session(tmp_path, "performance_only", "color_order",
                                     dda_decision=dec)
        rows = compute_summary(sessions)
        # Find the performance_only row
        po_rows = [r for r in rows if r["mode"] == "performance_only"]
        assert po_rows, "No performance_only row found"
        assert po_rows[0]["tier_increase_rate"] == pytest.approx(1.0)
        assert po_rows[0]["tier_decrease_rate"] == pytest.approx(0.0)

    def test_dda_static_no_movement(self, tmp_path):
        dec = {
            "level": 1, "puzzle_type": "color_order", "elapsed_s": 10.0,
            "mode": "static", "perf": 1.0, "comm": 0.5, "combined": 1.0,
            "prev_tier": 1, "new_tier": 1, "adjustment": 0,
            "failures": 0, "hint": 0, "timed_out_flag": 0, "clues": 0, "repeats": 0,
        }
        sessions = self._one_session(tmp_path, "static", "color_order",
                                     dda_decision=dec)
        rows = compute_summary(sessions)
        st_rows = [r for r in rows if r["mode"] == "static"]
        assert st_rows[0]["tier_increase_rate"] == pytest.approx(0.0)
        assert st_rows[0]["tier_decrease_rate"] == pytest.approx(0.0)

    def test_two_modes_separated(self, tmp_path):
        """Summary rows must be separate for different modes."""
        recA = SessionRecord("A")
        recA.mode = "static"
        recA.started.append({"level": 1, "puzzle_type": "color_order", "time_limit_s": 60.0})
        recA.completed.append({"level": 1, "puzzle_type": "color_order",
                                "elapsed_s": 15.0, "mistakes": 0, "timed_out": False})

        recB = SessionRecord("B")
        recB.mode = "performance_only"
        recB.started.append({"level": 1, "puzzle_type": "color_order", "time_limit_s": 60.0})
        recB.completed.append({"level": 1, "puzzle_type": "color_order",
                                "elapsed_s": 30.0, "mistakes": 2, "timed_out": False})

        rows = compute_summary({"A": recA, "B": recB})
        modes = {r["mode"] for r in rows}
        assert "static" in modes
        assert "performance_only" in modes

        static_row = next(r for r in rows if r["mode"] == "static")
        perf_row = next(r for r in rows if r["mode"] == "performance_only")
        assert static_row["mean_time_s"] == pytest.approx(15.0)
        assert perf_row["mean_time_s"] == pytest.approx(30.0)

    def test_empty_sessions_returns_empty_list(self):
        rows = compute_summary({})
        assert rows == []

    def test_n_started_zero_completion_rate_none(self):
        rec = SessionRecord("S1")
        rec.mode = "static"
        rec.completed.append({"level": 1, "puzzle_type": "color_order",
                               "elapsed_s": 10.0, "mistakes": 0, "timed_out": False})
        # No started events -> completion_rate should be None (started=0)
        rows = compute_summary({"S1": rec})
        # started_by key may not exist; completion_rate = None
        st = [r for r in rows if r["puzzle_type"] == "color_order"]
        # It's okay if n_started=0 and completion_rate is None
        assert st[0]["completion_rate"] is None

    def test_mean_mistakes_computed(self, tmp_path):
        rec = SessionRecord("S1")
        rec.mode = "static"
        for m in [0, 2, 4]:
            rec.started.append({"level": 1, "puzzle_type": "color_order", "time_limit_s": 60.0})
            rec.completed.append({"level": 1, "puzzle_type": "color_order",
                                  "elapsed_s": 10.0, "mistakes": m, "timed_out": False})
        rows = compute_summary({"S1": rec})
        assert rows[0]["mean_mistakes"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Integration: CLI main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_log_returns_exit_code_1(self, tmp_path, capsys):
        nonexistent = str(tmp_path / "nope.csv")
        code = main(["--log", nonexistent])
        assert code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_valid_log_returns_exit_code_0(self, tmp_path):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=static"),
            _session_row("S1", "level_start", level=1, ptype="color_order",
                         detail="time_limit_s=60;solution=x"),
            _session_row("S1", "puzzle_complete", level=1, ptype="color_order",
                         elapsed=15.0, detail="mistakes=0;timed_out=False"),
        ]
        path = _make_csv(tmp_path, rows)
        code = main(["--log", str(path)])
        assert code == 0

    def test_output_contains_session_id(self, tmp_path, capsys):
        rows = [_session_row("MYSESSION", "session_start", detail="dda_mode=static")]
        path = _make_csv(tmp_path, rows)
        main(["--log", str(path)])
        captured = capsys.readouterr()
        assert "MYSESSION" in captured.out

    def test_output_contains_mode(self, tmp_path, capsys):
        rows = [
            _session_row("S1", "session_start", detail="dda_mode=communication_aware"),
            _session_row("S1", "level_start", level=1, ptype="color_order",
                         detail="time_limit_s=60;solution=x"),
            _session_row("S1", "puzzle_complete", level=1, ptype="color_order",
                         elapsed=20.0, detail="mistakes=0;timed_out=False"),
        ]
        path = _make_csv(tmp_path, rows)
        main(["--log", str(path)])
        captured = capsys.readouterr()
        assert "communication_aware" in captured.out

    def test_session_filter_applied(self, tmp_path, capsys):
        rows = [
            _session_row("AAA", "session_start", detail="dda_mode=static"),
            _session_row("BBB", "session_start", detail="dda_mode=performance_only"),
        ]
        path = _make_csv(tmp_path, rows)
        main(["--log", str(path), "--session", "AAA"])
        captured = capsys.readouterr()
        assert "AAA" in captured.out
        assert "BBB" not in captured.out

    def test_no_sessions_filter_returns_exit_code_1(self, tmp_path, capsys):
        rows = [_session_row("S1", "session_start", detail="dda_mode=static")]
        path = _make_csv(tmp_path, rows)
        code = main(["--log", str(path), "--session", "NOSUCHSESSION"])
        assert code == 1

    def test_limitations_suppressed_by_no_limits_flag(self, tmp_path, capsys):
        rows = [_session_row("S1", "session_start", detail="dda_mode=static")]
        path = _make_csv(tmp_path, rows)
        main(["--log", str(path), "--no-limits"])
        captured = capsys.readouterr()
        assert "RESEARCH LIMITATIONS" not in captured.out

    def test_limitations_printed_by_default(self, tmp_path, capsys):
        rows = [_session_row("S1", "session_start", detail="dda_mode=static")]
        path = _make_csv(tmp_path, rows)
        main(["--log", str(path)])
        captured = capsys.readouterr()
        assert "RESEARCH LIMITATIONS" in captured.out

    def test_real_log_readable(self):
        """Smoke test: the real log (if present) can be read without crashing."""
        if not DEFAULT_LOG.exists():
            pytest.skip("Real log file not present")
        code = main(["--log", str(DEFAULT_LOG)])
        assert code == 0
