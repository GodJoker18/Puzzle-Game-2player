"""Integration tests for Game state machine, level transitions, controls, and timer."""

import os
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

from game import (
    Game,
    LEVELS,
    STATE_START,
    STATE_PLAYING,
    STATE_LEVEL_COMPLETE,
    STATE_VICTORY,
    COLOR_ORDER,
    GRID_PATH,
    COOP_SYMBOL,
)
from logger import EventLogger


class DummyLogger:
    """In-memory event logger to track logged actions for testing."""
    def __init__(self):
        self.events = []
        self.enabled = True
        self.session_id = "test-session"

    def log(self, level, puzzle_type, action, attempt, elapsed_s, outcome="", detail=""):
        self.events.append({
            "level": level,
            "puzzle_type": puzzle_type,
            "action": action,
            "attempt": attempt,
            "elapsed_s": elapsed_s,
            "outcome": outcome,
            "detail": detail,
        })

    def close(self):
        self.enabled = False


class TestGameFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.logger = DummyLogger()
        self.game = Game(self.logger)

    def test_initial_state_and_start(self):
        self.assertEqual(self.game.state, STATE_START)
        self.assertEqual(self.game.level_index, 0)
        self.assertIsNone(self.game.puzzle)

        # Press ENTER on start screen
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.state, STATE_PLAYING)
        self.assertIsNotNone(self.game.puzzle)
        self.assertEqual(self.game.puzzle.puzzle_type, COLOR_ORDER)
        self.assertEqual(self.game.level_number, 1)

    def test_all_six_levels_progression(self):
        expected_types = [
            COLOR_ORDER,
            GRID_PATH,
            COOP_SYMBOL,
            COLOR_ORDER,
            GRID_PATH,
            COOP_SYMBOL,
        ]
        self.assertEqual(len(LEVELS), 6)
        for i, expected_type in enumerate(expected_types):
            self.assertEqual(LEVELS[i]["type"], expected_type)

        self.game.start_game()

        for lvl_idx in range(len(LEVELS)):
            self.assertEqual(self.game.level_index, lvl_idx)
            self.assertEqual(self.game.puzzle.puzzle_type, expected_types[lvl_idx])
            self.assertEqual(self.game.state, STATE_PLAYING)

            # Solve the current puzzle directly
            self.game.puzzle.solved = True
            self.game._finish_puzzle(self.game.puzzle.attempt)

            if lvl_idx == len(LEVELS) - 1:
                self.assertEqual(self.game.state, STATE_VICTORY)
            else:
                self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)
                # Press ENTER to advance to next level
                self.game.handle_key(pygame.K_RETURN)

        # Verify victory state
        self.assertEqual(self.game.state, STATE_VICTORY)

        # Test restart from victory with SPACE
        self.game.handle_key(pygame.K_SPACE)
        self.assertEqual(self.game.state, STATE_PLAYING)
        self.assertEqual(self.game.level_index, 0)
        self.assertEqual(self.game.puzzle.puzzle_type, COLOR_ORDER)

    def test_level_1_color_order_key_controls(self):
        self.game.start_game()
        self.assertEqual(self.game.puzzle.puzzle_type, COLOR_ORDER)
        solution = self.game.puzzle.solution

        # Press correct keys according to solution
        for color in solution:
            idx = self.game.puzzle.options.index(color)
            key = pygame.K_1 + idx
            self.game.handle_key(key)

        self.assertTrue(self.game.puzzle.solved)
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

    def test_level_2_grid_path_controls_and_wall_logging(self):
        self.game.start_game()
        self.game.next_level()  # Level 2 (GRID_PATH)
        self.assertEqual(self.game.puzzle.puzzle_type, GRID_PATH)

        initial_pos = self.game.puzzle.position
        # Try moving up out of bounds
        self.game.handle_key(pygame.K_UP)
        self.assertEqual(self.game.puzzle.position, initial_pos)
        self.assertEqual(self.game.puzzle.failures, 1)

        # Verify incorrect_attempt was logged for grid wall collision
        wall_events = [e for e in self.logger.events if e["action"] == "incorrect_attempt"]
        self.assertGreaterEqual(len(wall_events), 1)
        self.assertEqual(wall_events[-1]["puzzle_type"], GRID_PATH)

        # Follow solution waypoints to complete
        dir_to_key = {
            "up": pygame.K_UP,
            "down": pygame.K_DOWN,
            "left": pygame.K_LEFT,
            "right": pygame.K_RIGHT,
        }
        for d in self.game.puzzle.waypoints:
            self.game.handle_key(dir_to_key[d])

        self.assertTrue(self.game.puzzle.solved)
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

    def test_level_3_coop_symbol_controls(self):
        self.game.start_game()
        self.game.level_index = 2
        self.game.start_level()
        self.assertEqual(self.game.puzzle.puzzle_type, COOP_SYMBOL)

        # Move highlight right and confirm
        self.game.handle_key(pygame.K_RIGHT)
        self.assertEqual(self.game.puzzle.highlight, 1)

        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(len(self.game.puzzle.selection), 1)

    def test_soft_timer_and_timeout_logging(self):
        self.game.start_game()
        time_limit = self.game.time_limit

        # Advance timer almost to limit
        self.game.update(time_limit - 1.0)
        self.assertFalse(self.game.timed_out)

        # Cross the threshold
        self.game.update(2.0)
        self.assertTrue(self.game.timed_out)
        self.assertEqual(self.game.state, STATE_PLAYING)  # Soft timer: play continues

        # Verify timeout was logged
        timeout_events = [e for e in self.logger.events if e["action"] == "timeout"]
        self.assertEqual(len(timeout_events), 1)
        self.assertEqual(timeout_events[0]["outcome"], "soft_timeout")

        # Further updates must not log timeout again
        self.game.update(5.0)
        timeout_events_after = [e for e in self.logger.events if e["action"] == "timeout"]
        self.assertEqual(len(timeout_events_after), 1)

        # Can still solve puzzle after timeout
        self.game.puzzle.solved = True
        self.game._finish_puzzle(self.game.puzzle.attempt)
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

    def test_keys_for_other_puzzles_ignored(self):
        self.game.start_game()  # Color Order active
        # Arrow keys should do nothing in Color Order
        self.game.handle_key(pygame.K_UP)
        self.game.handle_key(pygame.K_DOWN)
        self.game.handle_key(pygame.K_LEFT)
        self.game.handle_key(pygame.K_RIGHT)
        self.assertEqual(self.game.puzzle.progress, 0)
        self.assertEqual(self.game.puzzle.failures, 0)

    def test_next_level_guarded_at_end(self):
        self.game.start_game()
        self.game.level_index = 5  # Last level (level 6)
        self.game.start_level()
        self.game.next_level()
        # Should guard and not raise IndexError
        self.assertEqual(self.game.state, STATE_VICTORY)

    def test_full_six_level_playthrough_and_logging(self):
        # Start game
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.state, STATE_PLAYING)

        dir_keys = {
            "up": pygame.K_UP,
            "down": pygame.K_DOWN,
            "left": pygame.K_LEFT,
            "right": pygame.K_RIGHT,
        }

        # Level 1: Color order
        self.assertEqual(self.game.level_number, 1)
        for color in self.game.puzzle.solution:
            idx = self.game.puzzle.options.index(color)
            self.game.handle_key(pygame.K_1 + idx)
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

        # Advance to Level 2: Grid path
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.level_number, 2)
        # Hit wall 3 times to trigger hint
        for _ in range(3):
            self.game.handle_key(pygame.K_UP)
        self.assertTrue(self.game.puzzle.hint_ready)
        # Solve grid
        for d in self.game.puzzle.waypoints:
            self.game.handle_key(dir_keys[d])
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

        # Advance to Level 3: Coop symbol
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.level_number, 3)
        # Fail 3 pairs via gameplay keys to trigger hint
        target_sym = self.game.puzzle.pairs[0][0]
        pos_target = [i for i, s in enumerate(self.game.puzzle.board) if s == target_sym][0]
        pos_wrong = [i for i, s in enumerate(self.game.puzzle.board) if s != target_sym][0]
        for _ in range(3):
            self.game.puzzle.highlight = pos_target
            self.game.handle_key(pygame.K_RETURN)
            self.game.puzzle.highlight = pos_wrong
            self.game.handle_key(pygame.K_RETURN)
        self.assertTrue(self.game.puzzle.hint_ready)
        # Solve coop symbol
        for pair in self.game.puzzle.pairs:
            sym_a, sym_b = pair
            pos_a = [i for i, s in enumerate(self.game.puzzle.board) if s == sym_a and i not in self.game.puzzle.completed_positions][0]
            pos_b = [i for i, s in enumerate(self.game.puzzle.board) if s == sym_b and i not in self.game.puzzle.completed_positions and i != pos_a][0]
            self.game.puzzle.highlight = pos_a
            self.game.handle_key(pygame.K_RETURN)
            self.game.puzzle.highlight = pos_b
            self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

        # Level 4: Color order
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.level_number, 4)
        for color in self.game.puzzle.solution:
            idx = self.game.puzzle.options.index(color)
            self.game.handle_key(pygame.K_1 + idx)
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

        # Level 5: Grid path
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.level_number, 5)
        for d in self.game.puzzle.waypoints:
            self.game.handle_key(dir_keys[d])
        self.assertEqual(self.game.state, STATE_LEVEL_COMPLETE)

        # Level 6: Coop symbol
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.level_number, 6)
        for pair in self.game.puzzle.pairs:
            sym_a, sym_b = pair
            pos_a = [i for i, s in enumerate(self.game.puzzle.board) if s == sym_a and i not in self.game.puzzle.completed_positions][0]
            pos_b = [i for i, s in enumerate(self.game.puzzle.board) if s == sym_b and i not in self.game.puzzle.completed_positions and i != pos_a][0]
            self.game.puzzle.highlight = pos_a
            self.game.handle_key(pygame.K_RETURN)
            self.game.puzzle.highlight = pos_b
            self.game.handle_key(pygame.K_RETURN)

        # Victory reached
        self.assertEqual(self.game.state, STATE_VICTORY)

        # Restart via SPACE
        self.game.handle_key(pygame.K_SPACE)
        self.assertEqual(self.game.state, STATE_PLAYING)
        self.assertEqual(self.game.level_number, 1)

        # Shutdown
        self.game.shutdown()

        # Verify all action categories were logged
        logged_actions = [e["action"] for e in self.logger.events]
        expected_actions = [
            "session_start", "level_start", "button_press", "grid_move",
            "symbol_confirm", "incorrect_attempt", "hint_shown",
            "puzzle_complete", "game_complete", "restart", "session_end"
        ]
        for act in expected_actions:
            self.assertIn(act, logged_actions, f"Missing logged action: {act}")


if __name__ == "__main__":
    unittest.main()
