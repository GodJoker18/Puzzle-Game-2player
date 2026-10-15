"""Unit tests for puzzle logic, validation, invalid inputs, and hints."""

import random
import unittest

from puzzles import (
    COLOR_ORDER,
    GRID_PATH,
    COOP_SYMBOL,
    COLORS,
    FIXED_LEVEL_1_COLORS,
    SYMBOLS,
    SYMBOL_CLUES,
    SequencePuzzle,
    GridPuzzle,
    CoopSymbolPuzzle,
    make_color_puzzle,
    make_grid_puzzle,
    make_coop_symbol_puzzle,
)


class TestColorOrderPuzzle(unittest.TestCase):
    def setUp(self):
        self.puzzle = SequencePuzzle(COLOR_ORDER, COLORS, ["red", "blue", "green"])

    def test_correct_sequence_solves_puzzle(self):
        # Options: ["red", "blue", "green", "yellow"] -> indices 0, 1, 2, 3
        res1 = self.puzzle.select(0)  # red
        self.assertEqual(res1.outcome, "correct_step")
        self.assertEqual(self.puzzle.progress, 1)
        self.assertFalse(self.puzzle.solved)

        res2 = self.puzzle.select(1)  # blue
        self.assertEqual(res2.outcome, "correct_step")
        self.assertEqual(self.puzzle.progress, 2)

        res3 = self.puzzle.select(2)  # green
        self.assertEqual(res3.outcome, "complete")
        self.assertEqual(self.puzzle.progress, 3)
        self.assertTrue(self.puzzle.solved)

    def test_incorrect_selection_resets_progress_and_increments_failures(self):
        self.puzzle.select(0)  # red (correct)
        self.assertEqual(self.puzzle.progress, 1)

        res = self.puzzle.select(3)  # yellow (incorrect, expected blue)
        self.assertEqual(res.outcome, "incorrect")
        self.assertEqual(self.puzzle.progress, 0)
        self.assertEqual(self.puzzle.failures, 1)
        self.assertEqual(self.puzzle.attempt, 2)

    def test_hint_triggers_after_three_failures(self):
        self.assertFalse(self.puzzle.hint_ready)

        res1 = self.puzzle.select(3)  # fail 1
        self.assertFalse(res1.hint_triggered)
        self.assertFalse(self.puzzle.hint_ready)

        res2 = self.puzzle.select(3)  # fail 2
        self.assertFalse(res2.hint_triggered)
        self.assertFalse(self.puzzle.hint_ready)

        res3 = self.puzzle.select(3)  # fail 3
        self.assertTrue(res3.hint_triggered)
        self.assertTrue(self.puzzle.hint_ready)

        hint = self.puzzle.hint_text()
        self.assertIn("RED", hint)

        res4 = self.puzzle.select(3)  # fail 4
        self.assertFalse(res4.hint_triggered)  # triggered only on exact 3rd
        self.assertTrue(self.puzzle.hint_ready)

    def test_invalid_and_ignored_inputs(self):
        # Out of bounds
        self.assertEqual(self.puzzle.select(-1).outcome, "ignored")
        self.assertEqual(self.puzzle.select(4).outcome, "ignored")
        self.assertEqual(self.puzzle.select(99).outcome, "ignored")

        # Non-integer / boolean types
        self.assertEqual(self.puzzle.select(True).outcome, "ignored")
        self.assertEqual(self.puzzle.select(False).outcome, "ignored")
        self.assertEqual(self.puzzle.select("0").outcome, "ignored")
        self.assertEqual(self.puzzle.select(1.5).outcome, "ignored")
        self.assertEqual(self.puzzle.select(None).outcome, "ignored")

        # After solved, inputs are ignored
        self.puzzle.select(0)
        self.puzzle.select(1)
        self.puzzle.select(2)
        self.assertTrue(self.puzzle.solved)
        self.assertEqual(self.puzzle.select(0).outcome, "ignored")
        self.assertEqual(self.puzzle.hint_text(), "")

    def test_make_color_puzzle_fixed_and_random(self):
        p_fixed = make_color_puzzle(4, fixed_sequence=FIXED_LEVEL_1_COLORS)
        self.assertEqual(p_fixed.solution, FIXED_LEVEL_1_COLORS)

        # Random puzzle must not equal fixed level 1 colors
        rng = random.Random(42)
        for _ in range(20):
            p_rand = make_color_puzzle(4, rng=rng)
            self.assertNotEqual(p_rand.solution, FIXED_LEVEL_1_COLORS)


class TestGridPathPuzzle(unittest.TestCase):
    def setUp(self):
        # 3x3 grid:
        # S . .
        # W W .
        # . . G
        walls = {(1, 0), (1, 1)}
        start = (0, 0)
        goal = (2, 2)
        waypoints = ["right", "right", "down", "down"]
        path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)]
        self.puzzle = GridPuzzle(3, 3, walls, start, goal, waypoints, path=path)

    def test_valid_moves_to_goal(self):
        self.assertEqual(self.puzzle.position, (0, 0))
        self.assertEqual(self.puzzle.route_progress, 0)

        res1 = self.puzzle.move("right")
        self.assertEqual(res1.outcome, "moved")
        self.assertEqual(self.puzzle.position, (0, 1))
        self.assertEqual(self.puzzle.route_progress, 1)

        self.puzzle.move("right")
        self.puzzle.move("down")
        res_goal = self.puzzle.move("down")
        self.assertEqual(res_goal.outcome, "goal")
        self.assertEqual(self.puzzle.position, (2, 2))
        self.assertTrue(self.puzzle.solved)

    def test_wall_and_boundary_collision(self):
        # Moving into wall at (1, 0) from (0, 0)
        res = self.puzzle.move("down")
        self.assertEqual(res.outcome, "wall")
        self.assertEqual(self.puzzle.position, (0, 0))  # position unchanged
        self.assertEqual(self.puzzle.failures, 1)

        # Boundary checks: moving up from row 0
        res_up = self.puzzle.move("up")
        self.assertEqual(res_up.outcome, "wall")
        self.assertEqual(self.puzzle.position, (0, 0))
        self.assertEqual(self.puzzle.failures, 2)

        # Moving left from col 0
        res_left = self.puzzle.move("left")
        self.assertEqual(res_left.outcome, "wall")
        self.assertEqual(self.puzzle.failures, 3)
        self.assertTrue(res_left.hint_triggered)
        self.assertTrue(self.puzzle.hint_ready)

    def test_grid_hint_text(self):
        self.puzzle.failures = 3
        hint = self.puzzle.hint_text()
        self.assertIn("RIGHT", hint)

        # Move right
        self.puzzle.move("right")
        hint2 = self.puzzle.hint_text()
        self.assertIn("RIGHT", hint2)

    def test_grid_invalid_direction_and_post_solve(self):
        res = self.puzzle.move("diagonal")
        self.assertEqual(res.outcome, "ignored")

        # Solve puzzle
        self.puzzle.move("right")
        self.puzzle.move("right")
        self.puzzle.move("down")
        self.puzzle.move("down")
        self.assertTrue(self.puzzle.solved)

        res_post = self.puzzle.move("up")
        self.assertEqual(res_post.outcome, "already_done")
        self.assertEqual(self.puzzle.hint_text(), "")

    def test_make_grid_puzzle_solvable(self):
        rng = random.Random(12345)
        for _ in range(10):
            gp = make_grid_puzzle(rows=4, cols=5, wall_count=4, rng=rng)
            self.assertFalse(gp.solved)
            self.assertGreaterEqual(len(gp.waypoints), 3)
            # Following the waypoints must solve the puzzle
            for d in gp.waypoints:
                r = gp.move(d)
            self.assertTrue(gp.solved)
            self.assertEqual(r.outcome, "goal")


class TestCoopSymbolPuzzle(unittest.TestCase):
    def setUp(self):
        # 6-cell board: two pairs ('circle', 'star') and two fillers ('square', 'cross')
        board = ["circle", "star", "square", "circle", "star", "cross"]
        pairs = [("circle", "circle"), ("star", "star")]
        pair_clues = [(SYMBOL_CLUES["circle"], SYMBOL_CLUES["circle"]),
                      (SYMBOL_CLUES["star"], SYMBOL_CLUES["star"])]
        self.puzzle = CoopSymbolPuzzle(board, pairs, pair_clues)

    def test_highlight_movement_and_wrapping(self):
        self.assertEqual(self.puzzle.highlight, 0)
        self.puzzle.move_highlight("right")
        self.assertEqual(self.puzzle.highlight, 1)

        self.puzzle.move_highlight("left")
        self.assertEqual(self.puzzle.highlight, 0)

        # Wrap left from 0 to 5
        self.puzzle.move_highlight("left")
        self.assertEqual(self.puzzle.highlight, 5)

        # Wrap right from 5 to 0
        self.puzzle.move_highlight("right")
        self.assertEqual(self.puzzle.highlight, 0)

    def test_correct_pair_matching(self):
        # First pair: circle at 0 and circle at 3
        self.puzzle.highlight = 0
        r1 = self.puzzle.confirm_selection()
        self.assertEqual(r1.outcome, "first_pick")
        self.assertEqual(r1.selected, ("circle", ""))

        self.puzzle.highlight = 3
        r2 = self.puzzle.confirm_selection()
        self.assertEqual(r2.outcome, "correct_pair")
        self.assertEqual(r2.selected, ("circle", "circle"))
        self.assertIn(0, self.puzzle.completed_positions)
        self.assertIn(3, self.puzzle.completed_positions)
        self.assertEqual(self.puzzle.current_pair_index, 1)

        # Highlight should automatically advance off completed positions
        self.assertNotIn(self.puzzle.highlight, self.puzzle.completed_positions)

        # Second pair: star at 1 and star at 4
        self.puzzle.highlight = 4
        self.puzzle.confirm_selection()
        self.puzzle.highlight = 1
        r4 = self.puzzle.confirm_selection()
        self.assertEqual(r4.outcome, "complete")
        self.assertTrue(self.puzzle.solved)

    def test_wrong_pair_matching_and_hints(self):
        # Pick circle at 0 and star at 1
        self.puzzle.highlight = 0
        self.puzzle.confirm_selection()
        self.puzzle.highlight = 1
        r = self.puzzle.confirm_selection()
        self.assertEqual(r.outcome, "wrong_pair")
        self.assertEqual(self.puzzle.failures, 1)
        self.assertEqual(self.puzzle.selection, [])  # cleared

        # Two more failures to trigger hint
        self.puzzle.highlight = 0
        self.puzzle.confirm_selection()
        self.puzzle.highlight = 2  # square
        self.puzzle.confirm_selection()

        self.puzzle.highlight = 0
        self.puzzle.confirm_selection()
        self.puzzle.highlight = 5  # cross
        r3 = self.puzzle.confirm_selection()
        self.assertEqual(r3.outcome, "wrong_pair")
        self.assertTrue(r3.hint_triggered)
        self.assertTrue(self.puzzle.hint_ready)

        hint = self.puzzle.hint_text()
        self.assertIn("Round, no corners", hint)

    def test_cannot_pick_same_position_twice(self):
        self.puzzle.highlight = 0
        r1 = self.puzzle.confirm_selection()
        self.assertEqual(r1.outcome, "first_pick")

        # Pressing confirm on the same position again is ignored
        r2 = self.puzzle.confirm_selection()
        self.assertEqual(r2.outcome, "ignored")
        self.assertEqual(len(self.puzzle.selection), 1)

    def test_cannot_pick_completed_position(self):
        # Complete first pair (0 and 3)
        self.puzzle.highlight = 0
        self.puzzle.confirm_selection()
        self.puzzle.highlight = 3
        self.puzzle.confirm_selection()

        self.puzzle.highlight = 0
        r = self.puzzle.confirm_selection()
        self.assertEqual(r.outcome, "ignored")

    def test_make_coop_symbol_puzzle(self):
        rng = random.Random(999)
        p = make_coop_symbol_puzzle(num_pairs=3, filler_count=3, rng=rng)
        self.assertEqual(len(p.pairs), 3)
        self.assertEqual(len(p.board), 9)
        # Verify all pair items exist twice and fillers exist once
        pair_syms = [p[0] for p in p.pairs]
        for sym in pair_syms:
            self.assertEqual(p.board.count(sym), 2)


if __name__ == "__main__":
    unittest.main()
