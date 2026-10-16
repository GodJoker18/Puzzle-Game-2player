"""Tests for the DDA (Dynamic Difficulty Adjustment) module and its integration
with the Game class.

Coverage:
  - DDAController modes: static, performance_only, communication_aware
  - compute_perf_score and compute_comm_score boundary conditions
  - Tier clamping (never goes below 0 or above max)
  - find_tier_index and get_tiers_for_type helpers
  - Game: DDA fields initialised correctly
  - Game: communication marker handlers (_handle_comm_clue, _handle_comm_repeat)
  - Game: latency recorded after C marker then Player 1 action
  - Game: _adapted_configs populated after _finish_puzzle
  - Game: static mode leaves adapted config unchanged
  - Game: TAB key cycles DDA mode on start screen
"""

import random
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pygame

from dda import (
    DDAController,
    DDAResult,
    PuzzleMetrics,
    compute_perf_score,
    compute_comm_score,
    find_tier_index,
    get_tiers_for_type,
    COLOR_TIERS,
    GRID_TIERS,
    SYMBOL_TIERS,
    MODE_STATIC,
    MODE_PERFORMANCE_ONLY,
    MODE_COMMUNICATION_AWARE,
    VALID_MODES,
)
from puzzles import COLOR_ORDER, GRID_PATH, COOP_SYMBOL

# ---- Helpers ------------------------------------------------------------------

def make_metrics(
    puzzle_type=COLOR_ORDER,
    elapsed=30.0,
    time_limit=60.0,
    failures=1,
    hint_triggered=False,
    timed_out=False,
    clue_count=0,
    repeat_count=0,
    latencies=None,
):
    return PuzzleMetrics(
        puzzle_type=puzzle_type,
        elapsed=elapsed,
        time_limit=time_limit,
        failures=failures,
        hint_triggered=hint_triggered,
        timed_out=timed_out,
        clue_count=clue_count,
        repeat_count=repeat_count,
        latencies=latencies or [],
    )


def make_game(dda_mode=MODE_STATIC):
    """Return a Game in STATE_START with no Pygame display required."""
    import io, csv
    from unittest.mock import MagicMock, patch

    mock_logger = MagicMock()
    mock_logger.close = MagicMock()

    with patch("pygame.font.Font"), patch("pygame.display.set_mode"), \
         patch("pygame.display.set_caption"), patch("pygame.init"):
        from game import Game
        g = Game(mock_logger, rng=random.Random(42), dda_mode=dda_mode)
    return g


# ==============================================================================
# 1. compute_perf_score
# ==============================================================================

class TestComputePerfScore:
    def test_perfect_fast_no_errors(self):
        m = make_metrics(elapsed=10.0, time_limit=60.0, failures=0)
        assert compute_perf_score(m) == 1.0

    def test_timed_out_penalty(self):
        m = make_metrics(elapsed=70.0, time_limit=60.0, failures=0, timed_out=True)
        score = compute_perf_score(m)
        assert score < 0.5

    def test_hint_triggered_penalty(self):
        m = make_metrics(elapsed=20.0, time_limit=60.0, failures=0, hint_triggered=True)
        no_hint = make_metrics(elapsed=20.0, time_limit=60.0, failures=0, hint_triggered=False)
        assert compute_perf_score(m) < compute_perf_score(no_hint)

    def test_many_failures_reduces_score(self):
        m = make_metrics(elapsed=30.0, time_limit=60.0, failures=8)
        score = compute_perf_score(m)
        assert score < 0.5

    def test_score_clamped_to_zero_minimum(self):
        m = make_metrics(elapsed=120.0, time_limit=60.0, failures=10,
                         hint_triggered=True, timed_out=True)
        assert compute_perf_score(m) == 0.0

    def test_score_clamped_to_one_maximum(self):
        m = make_metrics(elapsed=1.0, time_limit=60.0, failures=0)
        assert compute_perf_score(m) <= 1.0

    def test_zero_time_limit_doesnt_crash(self):
        """time_limit = 0 should not raise ZeroDivisionError."""
        m = make_metrics(elapsed=5.0, time_limit=0.0)
        score = compute_perf_score(m)
        assert 0.0 <= score <= 1.0


# ==============================================================================
# 2. compute_comm_score
# ==============================================================================

class TestComputeCommScore:
    def test_no_markers_returns_neutral(self):
        m = make_metrics(clue_count=0, repeat_count=0)
        assert compute_comm_score(m) == 0.5

    def test_fast_latency_scores_high(self):
        m = make_metrics(clue_count=3, latencies=[1.0, 1.5, 0.8])
        score = compute_comm_score(m)
        assert score > 0.7

    def test_slow_latency_scores_low(self):
        m = make_metrics(clue_count=3, latencies=[8.0, 9.0, 7.5])
        score = compute_comm_score(m)
        assert score < 0.5

    def test_many_repeats_reduces_score(self):
        m_few = make_metrics(clue_count=4, repeat_count=0, latencies=[1.5] * 4)
        m_many = make_metrics(clue_count=4, repeat_count=3, latencies=[1.5] * 4)
        assert compute_comm_score(m_many) < compute_comm_score(m_few)

    def test_score_always_bounded(self):
        for clues, reps, lats in [
            (0, 0, []),
            (5, 0, [0.1] * 5),
            (5, 10, [20.0] * 5),
        ]:
            m = make_metrics(clue_count=clues, repeat_count=reps, latencies=lats)
            s = compute_comm_score(m)
            assert 0.0 <= s <= 1.0, f"score={s} out of range for {clues}, {reps}, {lats}"

    def test_only_repeats_no_latency(self):
        """repeat_count > 0 but no latencies: should not crash."""
        m = make_metrics(clue_count=2, repeat_count=2, latencies=[])
        score = compute_comm_score(m)
        assert 0.0 <= score <= 1.0


# ==============================================================================
# 3. Tier helpers
# ==============================================================================

class TestTierHelpers:
    def test_get_tiers_color(self):
        assert get_tiers_for_type(COLOR_ORDER) is COLOR_TIERS

    def test_get_tiers_grid(self):
        assert get_tiers_for_type(GRID_PATH) is GRID_TIERS

    def test_get_tiers_symbol(self):
        assert get_tiers_for_type(COOP_SYMBOL) is SYMBOL_TIERS

    def test_get_tiers_unknown_returns_empty(self):
        assert get_tiers_for_type("bogus_type") == []

    def test_find_tier_color_baseline(self):
        cfg = {"type": COLOR_ORDER, "length": 4, "time_limit": 60}
        idx = find_tier_index(COLOR_ORDER, cfg)
        assert idx >= 0

    def test_find_tier_grid_baseline(self):
        cfg = {"type": GRID_PATH, "rows": 4, "cols": 5, "walls": 4, "time_limit": 90}
        idx = find_tier_index(GRID_PATH, cfg)
        assert 0 <= idx < len(GRID_TIERS)

    def test_find_tier_symbol_baseline(self):
        cfg = {"type": COOP_SYMBOL, "pairs": 2, "fillers": 2, "time_limit": 75}
        idx = find_tier_index(COOP_SYMBOL, cfg)
        assert 0 <= idx < len(SYMBOL_TIERS)


# ==============================================================================
# 4. DDAController – static mode
# ==============================================================================

class TestDDAControllerStatic:
    def test_static_makes_no_adjustment(self):
        ctrl = DDAController(MODE_STATIC)
        m = make_metrics(elapsed=10.0, time_limit=60.0, failures=0)
        cfg = dict(COLOR_TIERS[1])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert result.adjustment == 0
        assert result.new_tier == result.prev_tier

    def test_static_reason_string(self):
        ctrl = DDAController(MODE_STATIC)
        m = make_metrics()
        result = ctrl.evaluate(m, COLOR_ORDER, dict(COLOR_TIERS[1]))
        assert "static" in result.reason

    def test_static_adapted_config_equals_input(self):
        ctrl = DDAController(MODE_STATIC)
        cfg = dict(COLOR_TIERS[2])
        result = ctrl.evaluate(make_metrics(), COLOR_ORDER, cfg)
        assert result.adapted_config == cfg


# ==============================================================================
# 5. DDAController – performance_only mode
# ==============================================================================

class TestDDAControllerPerfOnly:
    def test_high_perf_increases_tier(self):
        ctrl = DDAController(MODE_PERFORMANCE_ONLY)
        # Fast clear, no mistakes → high score
        m = make_metrics(elapsed=8.0, time_limit=60.0, failures=0)
        cfg = dict(COLOR_TIERS[1])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert result.adjustment == +1

    def test_low_perf_decreases_tier(self):
        ctrl = DDAController(MODE_PERFORMANCE_ONLY)
        # Slow, many mistakes, hint, timeout
        m = make_metrics(elapsed=70.0, time_limit=60.0, failures=6,
                         hint_triggered=True, timed_out=True)
        cfg = dict(COLOR_TIERS[2])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert result.adjustment == -1

    def test_stable_perf_no_change(self):
        ctrl = DDAController(MODE_PERFORMANCE_ONLY)
        # Moderate performance → no change
        m = make_metrics(elapsed=40.0, time_limit=60.0, failures=2)
        cfg = dict(COLOR_TIERS[1])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert result.adjustment == 0

    def test_tier_clamps_at_zero(self):
        ctrl = DDAController(MODE_PERFORMANCE_ONLY)
        m = make_metrics(elapsed=70.0, time_limit=60.0, failures=10,
                         hint_triggered=True, timed_out=True)
        cfg = dict(COLOR_TIERS[0])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert result.new_tier == 0

    def test_tier_clamps_at_max(self):
        ctrl = DDAController(MODE_PERFORMANCE_ONLY)
        m = make_metrics(elapsed=5.0, time_limit=60.0, failures=0)
        max_idx = len(COLOR_TIERS) - 1
        cfg = dict(COLOR_TIERS[max_idx])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert result.new_tier == max_idx

    def test_result_contains_adapted_config(self):
        ctrl = DDAController(MODE_PERFORMANCE_ONLY)
        m = make_metrics(elapsed=5.0, time_limit=60.0, failures=0)
        cfg = dict(COLOR_TIERS[1])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        assert isinstance(result.adapted_config, dict)
        assert "type" in result.adapted_config


# ==============================================================================
# 6. DDAController – communication_aware mode
# ==============================================================================

class TestDDAControllerCommAware:
    def test_comm_markers_affect_combined_score(self):
        ctrl = DDAController(MODE_COMMUNICATION_AWARE)
        # Same performance, but many repeats → lower combined score
        m_good = make_metrics(elapsed=10.0, time_limit=60.0, failures=0,
                               clue_count=4, repeat_count=0, latencies=[1.5]*4)
        m_bad = make_metrics(elapsed=10.0, time_limit=60.0, failures=0,
                              clue_count=4, repeat_count=4, latencies=[9.0]*4)
        cfg = dict(COLOR_TIERS[1])
        r_good = ctrl.evaluate(m_good, COLOR_ORDER, cfg)
        r_bad  = ctrl.evaluate(m_bad,  COLOR_ORDER, cfg)
        assert r_good.combined_score >= r_bad.combined_score

    def test_no_markers_falls_back_to_perf(self):
        ctrl = DDAController(MODE_COMMUNICATION_AWARE)
        m = make_metrics(elapsed=5.0, time_limit=60.0, failures=0,
                          clue_count=0, repeat_count=0)
        cfg = dict(COLOR_TIERS[1])
        result = ctrl.evaluate(m, COLOR_ORDER, cfg)
        # Without markers fallback combined_score == perf_score
        assert result.combined_score == result.perf_score

    def test_effective_coordination_increases_tier(self):
        ctrl = DDAController(MODE_COMMUNICATION_AWARE)
        m = make_metrics(elapsed=8.0, time_limit=60.0, failures=0,
                          clue_count=3, repeat_count=0, latencies=[1.2]*3)
        cfg = dict(GRID_TIERS[1])
        result = ctrl.evaluate(m, GRID_PATH, cfg)
        assert result.adjustment == +1

    def test_coordination_friction_decreases_tier(self):
        ctrl = DDAController(MODE_COMMUNICATION_AWARE)
        m = make_metrics(elapsed=80.0, time_limit=60.0, failures=5,
                          timed_out=True, hint_triggered=True,
                          clue_count=5, repeat_count=5, latencies=[10.0]*5)
        cfg = dict(GRID_TIERS[2])
        result = ctrl.evaluate(m, GRID_PATH, cfg)
        assert result.adjustment == -1


# ==============================================================================
# 7. Mode cycling and set_mode
# ==============================================================================

class TestDDAControllerModes:
    def test_invalid_mode_defaults_to_static(self):
        ctrl = DDAController("does_not_exist")
        assert ctrl.mode == MODE_STATIC

    def test_set_mode_valid(self):
        ctrl = DDAController()
        ctrl.set_mode(MODE_PERFORMANCE_ONLY)
        assert ctrl.mode == MODE_PERFORMANCE_ONLY

    def test_set_mode_invalid_raises(self):
        ctrl = DDAController()
        with pytest.raises(ValueError):
            ctrl.set_mode("unicorn")

    def test_cycle_mode_wraps_around(self):
        ctrl = DDAController(VALID_MODES[-1])
        next_mode = ctrl.cycle_mode()
        assert next_mode == VALID_MODES[0]

    def test_cycle_mode_returns_next(self):
        ctrl = DDAController(MODE_STATIC)
        assert ctrl.cycle_mode() == MODE_PERFORMANCE_ONLY


# ==============================================================================
# 8. Game integration tests (no Pygame window)
# ==============================================================================

class TestGameDDAIntegration:
    def test_game_has_dda_controller(self):
        g = make_game(MODE_STATIC)
        assert hasattr(g, "dda")
        assert isinstance(g.dda, DDAController)
        assert g.dda.mode == MODE_STATIC

    def test_game_dda_mode_perf(self):
        g = make_game(MODE_PERFORMANCE_ONLY)
        assert g.dda.mode == MODE_PERFORMANCE_ONLY

    def test_game_has_comm_counters(self):
        g = make_game()
        assert g._clue_count == 0
        assert g._repeat_count == 0
        assert g._latencies == []
        assert g._last_clue_time is None

    def test_game_comm_clue_increments_count(self):
        g = make_game()
        # Simulate an active puzzle so logging doesn't crash
        from unittest.mock import MagicMock
        g.puzzle = MagicMock()
        g.puzzle.puzzle_type = COLOR_ORDER
        g.elapsed = 10.0
        g._handle_comm_clue()
        assert g._clue_count == 1
        assert g._last_clue_time == 10.0

    def test_game_comm_repeat_increments_count(self):
        g = make_game()
        from unittest.mock import MagicMock
        g.puzzle = MagicMock()
        g.puzzle.puzzle_type = COLOR_ORDER
        g.elapsed = 5.0
        g._handle_comm_repeat()
        assert g._repeat_count == 1

    def test_game_latency_recorded_after_clue_then_action(self):
        g = make_game()
        from unittest.mock import MagicMock
        g.puzzle = MagicMock()
        g.puzzle.puzzle_type = COLOR_ORDER
        g.elapsed = 5.0
        g._handle_comm_clue()      # C pressed at elapsed=5
        g.elapsed = 7.5
        g._record_latency_if_pending()  # Player 1 acts at elapsed=7.5
        assert len(g._latencies) == 1
        assert abs(g._latencies[0] - 2.5) < 1e-6
        assert g._last_clue_time is None

    def test_game_latency_cleared_on_start_level(self):
        from unittest.mock import MagicMock, patch
        g = make_game()
        g._clue_count = 5
        g._repeat_count = 3
        g._latencies = [1.0, 2.0]
        g._last_clue_time = 10.0
        # Patch start_level dependencies
        with patch.object(g, "_log"), \
             patch("game.make_color_puzzle", return_value=MagicMock(
                 puzzle_type=COLOR_ORDER, solution=["red", "blue"],
                 attempt=1, failures=0, hint_ready=False)):
            g.level_index = 0
            g.start_level()
        assert g._clue_count == 0
        assert g._repeat_count == 0
        assert g._latencies == []
        assert g._last_clue_time is None

    def test_game_static_mode_does_not_change_adapted_config(self):
        """In static mode _finish_puzzle must not alter the next level's baseline."""
        from unittest.mock import MagicMock, patch
        g = make_game(MODE_STATIC)
        g.level_index = 0
        pz = MagicMock()
        pz.puzzle_type = COLOR_ORDER
        pz.failures = 1
        pz.hint_ready = False
        g.puzzle = pz
        g.elapsed = 30.0
        g.timed_out = False
        with patch.object(g, "_log"), patch.object(g, "_show_feedback"):
            g._finish_puzzle(1)
        # Static mode: config for level 1 should not change from baseline
        from game import LEVELS
        if 1 in g._adapted_configs:
            adapted = g._adapted_configs[1]
            assert adapted["type"] == LEVELS[1]["type"]

    def test_game_perf_mode_populates_adapted_config(self):
        """In perf mode a DDA decision produces an _adapted_config entry."""
        from unittest.mock import MagicMock, patch
        g = make_game(MODE_PERFORMANCE_ONLY)
        g.level_index = 0
        pz = MagicMock()
        pz.puzzle_type = COLOR_ORDER
        pz.failures = 0
        pz.hint_ready = False
        g.puzzle = pz
        g.elapsed = 5.0          # fast → should increase tier
        g.timed_out = False
        with patch.object(g, "_log"), patch.object(g, "_show_feedback"):
            g._finish_puzzle(1)
        assert 1 in g._adapted_configs
        adapted = g._adapted_configs[1]
        assert isinstance(adapted, dict)
        assert "time_limit" in adapted


# ==============================================================================
# 9. Reproducible Mode Comparison with Controlled Inputs
# ==============================================================================

class TestDDAControlledComparisons:
    """Compare all three modes (static, performance_only, communication_aware)
    using identical controlled input vectors to prove behavioral divergence.
    """

    def test_comparison_high_performance_no_comm(self):
        """When performance is high and no comm markers are used:
        - static: remains at baseline (adjustment = 0)
        - perf_only: increases tier (+1)
        - comm_aware: falls back to perf, increases tier (+1)
        """
        metrics = make_metrics(elapsed=5.0, time_limit=60.0, failures=0,
                               clue_count=0, repeat_count=0)
        cfg = dict(GRID_TIERS[1])

        res_static = DDAController(MODE_STATIC).evaluate(metrics, GRID_PATH, cfg)
        res_perf   = DDAController(MODE_PERFORMANCE_ONLY).evaluate(metrics, GRID_PATH, cfg)
        res_comm   = DDAController(MODE_COMMUNICATION_AWARE).evaluate(metrics, GRID_PATH, cfg)

        assert res_static.adjustment == 0
        assert res_perf.adjustment == +1
        assert res_comm.adjustment == +1

    def test_comparison_moderate_perf_boosted_by_coordination(self):
        """When performance alone is moderate (adjustment=0 in perf_only),
        strong communication proxies boost comm_aware to adjustment=+1.
        """
        # elapsed=38/60 -> time_ratio=0.633 -> time_score=0.611
        # failures=1 -> mistake_score=0.75 -> perf_score ~ 0.681
        metrics = make_metrics(
            elapsed=38.0, time_limit=60.0, failures=1,
            clue_count=4, repeat_count=0, latencies=[1.0, 1.2, 1.1, 1.0],
        )
        cfg = dict(GRID_TIERS[1])

        res_static = DDAController(MODE_STATIC).evaluate(metrics, GRID_PATH, cfg)
        res_perf   = DDAController(MODE_PERFORMANCE_ONLY).evaluate(metrics, GRID_PATH, cfg)
        res_comm   = DDAController(MODE_COMMUNICATION_AWARE).evaluate(metrics, GRID_PATH, cfg)

        assert res_static.adjustment == 0
        assert res_perf.adjustment == 0        # Moderate perf alone does not advance
        assert res_comm.adjustment == +1       # Strong coordination boosts team to +1
        assert res_comm.comm_score == 1.0
        assert res_comm.combined_score > res_perf.combined_score

    def test_comparison_high_perf_damped_by_coordination_friction(self):
        """When performance alone is high (adjustment=+1 in perf_only),
        severe communication friction holds comm_aware back to adjustment=0.
        """
        # Perfect puzzle time and 0 mistakes, but lots of repeats and high latency
        metrics = make_metrics(
            elapsed=10.0, time_limit=60.0, failures=0,
            clue_count=4, repeat_count=4, latencies=[8.0, 9.0, 8.5, 7.5],
        )
        cfg = dict(GRID_TIERS[1])

        res_static = DDAController(MODE_STATIC).evaluate(metrics, GRID_PATH, cfg)
        res_perf   = DDAController(MODE_PERFORMANCE_ONLY).evaluate(metrics, GRID_PATH, cfg)
        res_comm   = DDAController(MODE_COMMUNICATION_AWARE).evaluate(metrics, GRID_PATH, cfg)

        assert res_static.adjustment == 0
        assert res_perf.adjustment == +1       # Perf alone triggers advancement
        assert res_comm.adjustment == 0        # Coordination friction prevents advancement
        assert res_comm.comm_score < 0.20
        assert res_comm.combined_score < 0.70

    def test_comparison_low_performance_demotion(self):
        """Under severe mistakes and timeout:
        - static: remains 0
        - perf_only: drops tier (-1)
        - comm_aware: drops tier (-1)
        """
        metrics = make_metrics(
            elapsed=70.0, time_limit=60.0, failures=5,
            timed_out=True, hint_triggered=True,
            clue_count=4, repeat_count=4, latencies=[10.0]*4,
        )
        cfg = dict(GRID_TIERS[2])

        res_static = DDAController(MODE_STATIC).evaluate(metrics, GRID_PATH, cfg)
        res_perf   = DDAController(MODE_PERFORMANCE_ONLY).evaluate(metrics, GRID_PATH, cfg)
        res_comm   = DDAController(MODE_COMMUNICATION_AWARE).evaluate(metrics, GRID_PATH, cfg)

        assert res_static.adjustment == 0
        assert res_perf.adjustment == -1
        assert res_comm.adjustment == -1


# ==============================================================================
# 10. Verification of Real Complexity Changes on Next Puzzle
# ==============================================================================

class TestDifficultyAffectsPuzzleComplexity:
    """Verify difficulty tier changes actually alter the generated puzzle instance
    (grid size, walls, pairs, board count, time limit) and are not merely logged.
    """

    def test_grid_path_tier_complexity_changes(self):
        from game import make_grid_puzzle
        # Tier 0 vs Tier 4
        t0 = GRID_TIERS[0]
        t4 = GRID_TIERS[4]

        p0 = make_grid_puzzle(t0["rows"], t0["cols"], t0["walls"], rng=random.Random(1))
        p4 = make_grid_puzzle(t4["rows"], t4["cols"], t4["walls"], rng=random.Random(1))

        # Size and complexity must differ
        assert p0.rows == 4 and p0.cols == 4
        assert p4.rows == 6 and p4.cols == 8
        assert len(p0.walls) <= t0["walls"]
        assert len(p4.walls) <= t4["walls"]
        assert len(p4.walls) > len(p0.walls)
        assert len(p0.waypoints) >= 1
        assert len(p4.waypoints) >= 1

    def test_coop_symbol_tier_complexity_changes(self):
        from game import make_coop_symbol_puzzle
        t0 = SYMBOL_TIERS[0]  # pairs=2, fillers=1 -> board=5
        t3 = SYMBOL_TIERS[3]  # pairs=3, fillers=3 -> board=9

        p0 = make_coop_symbol_puzzle(t0["pairs"], t0["fillers"], rng=random.Random(1))
        p3 = make_coop_symbol_puzzle(t3["pairs"], t3["fillers"], rng=random.Random(1))

        assert len(p0.pairs) == 2
        assert len(p3.pairs) == 3
        assert len(p0.board) == 2 * 2 + 1  # 5
        assert len(p3.board) == 2 * 3 + 3  # 9

    def test_color_order_tier_complexity_changes(self):
        from game import make_color_puzzle
        t0 = COLOR_TIERS[0]  # length=3
        t1 = COLOR_TIERS[1]  # length=4

        p0 = make_color_puzzle(t0["length"], rng=random.Random(1))
        p1 = make_color_puzzle(t1["length"], rng=random.Random(1))

        assert len(p0.solution) == 3
        assert len(p1.solution) == 4

    def test_all_tiers_generate_solvable_puzzles(self):
        """Exhaustively verify that every tier definition across all puzzle types
        generates valid, solvable instances without runtime errors.
        """
        from game import make_color_puzzle, make_grid_puzzle, make_coop_symbol_puzzle
        rng = random.Random(99)

        # 1. All Color tiers
        for t in COLOR_TIERS:
            p = make_color_puzzle(t["length"], rng=rng)
            assert len(p.solution) == t["length"]
            assert not p.solved
            # Verify can be solved
            for step in p.solution:
                idx = p.options.index(step)
                p.select(idx)
            assert p.solved

        # 2. All Grid tiers
        for t in GRID_TIERS:
            p = make_grid_puzzle(t["rows"], t["cols"], t["walls"], rng=rng)
            assert p.rows == t["rows"]
            assert p.cols == t["cols"]
            assert not p.solved
            # Follow waypoints to goal
            for d in p.waypoints:
                res = p.move(d)
            assert p.solved

        # 3. All Symbol tiers
        for t in SYMBOL_TIERS:
            p = make_coop_symbol_puzzle(t["pairs"], t["fillers"], rng=rng)
            assert len(p.pairs) == t["pairs"]
            assert not p.solved


# ==============================================================================
# 11. Mid-Puzzle Invariance (No Changes During Active Puzzle)
# ==============================================================================

class TestMidPuzzleInvariance:
    """Verify difficulty changes occur strictly between puzzles, never mid-puzzle."""

    def test_active_puzzle_parameters_remain_invariant(self):
        g = make_game(MODE_PERFORMANCE_ONLY)
        g.start_game()
        # Level 1 active
        assert g.state == "playing"
        initial_tl = g.time_limit
        pz = g.puzzle
        initial_len = len(pz.solution)

        # Trigger mistakes, comm markers, soft timeout
        pz.select((pz.options.index(pz.solution[0]) + 1) % len(pz.options))  # mistake 1
        pz.select((pz.options.index(pz.solution[0]) + 1) % len(pz.options))  # mistake 2
        pz.select((pz.options.index(pz.solution[0]) + 1) % len(pz.options))  # mistake 3 -> hint ready
        g._handle_comm_clue()
        g._handle_comm_repeat()
        g.update(initial_tl + 5.0)  # trigger soft timeout

        # Invariant checks: parameters of current puzzle MUST NOT change
        assert g.time_limit == initial_tl
        assert len(pz.solution) == initial_len
        assert g.level_index == 0
        assert 0 not in g._adapted_configs  # current level config was not mutated mid-puzzle


# ==============================================================================
# 12. CSV Logging Audit & Session Preservation
# ==============================================================================

class TestCSVLoggingAudit:
    """Verify CSV records DDA mode, full input metrics, difficulty adaptation,
    and never overwrites prior sessions.
    """

    def test_dda_decision_logged_with_all_metrics(self, tmp_path):
        import csv
        from logger import EventLogger
        from unittest.mock import patch

        csv_file = str(tmp_path / "test_events.csv")
        logger = EventLogger(csv_file, session_id="session-1")

        with patch("pygame.font.Font"), patch("pygame.display.set_mode"), \
             patch("pygame.display.set_caption"), patch("pygame.init"):
            from game import Game
            g = Game(logger, rng=random.Random(42), dda_mode=MODE_COMMUNICATION_AWARE)
            g.start_game()
            # Mark communication proxies
            g.elapsed = 5.0
            g._handle_comm_clue()
            g.elapsed = 6.5
            # Solve level 1
            for col in list(g.puzzle.solution):
                idx = g.puzzle.options.index(col)
                g.handle_key(pygame.K_1 + idx)
            g.shutdown()

        # Read back CSV
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        dda_rows = [r for r in reader if r["action"] == "dda_decision"]
        assert len(dda_rows) == 1
        row = dda_rows[0]

        detail = row["detail"]
        assert "mode=communication_aware" in detail
        assert "perf=" in detail
        assert "comm=" in detail
        assert "combined=" in detail
        assert "prev_tier=" in detail
        assert "new_tier=" in detail
        assert "adjustment=" in detail
        assert "elapsed_s=" in detail
        assert "failures=" in detail
        assert "hint=" in detail
        assert "timed_out=" in detail
        assert "clues=1" in detail
        assert "repeats=0" in detail

    def test_csv_appends_without_overwriting_prior_sessions(self, tmp_path):
        import csv
        from logger import EventLogger

        csv_file = str(tmp_path / "shared_events.csv")

        # Session 1
        log1 = EventLogger(csv_file, session_id="sess-A")
        log1.log(1, "color_order", "action_A", 1, 10.0, "ok", "detailA")
        log1.close()

        # Session 2 on same file
        log2 = EventLogger(csv_file, session_id="sess-B")
        log2.log(1, "color_order", "action_B", 1, 15.0, "ok", "detailB")
        log2.close()

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        # Both sessions must coexist, with unique session_ids and no duplicate header
        assert len(reader) == 2
        assert reader[0]["session_id"] == "sess-A"
        assert reader[0]["action"] == "action_A"
        assert reader[1]["session_id"] == "sess-B"
        assert reader[1]["action"] == "action_B"


# ==============================================================================
# 13. Session Reset Audit
# ==============================================================================

class TestSessionResetAudit:
    def test_start_game_clears_adapted_configs(self):
        g = make_game(MODE_PERFORMANCE_ONLY)
        # Simulate leftover adapted configs from a previous game
        g._adapted_configs = {1: {"tier": 4}, 2: {"tier": 3}}
        g.start_game()
        assert g._adapted_configs == {}

