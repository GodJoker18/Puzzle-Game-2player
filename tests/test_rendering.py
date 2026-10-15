"""Unit tests for UI rendering routines and headless surface drawing."""

import os
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

from game import (
    Game,
    WIDTH,
    HEIGHT,
    LEVELS,
    STATE_START,
    STATE_PLAYING,
    STATE_LEVEL_COMPLETE,
    STATE_VICTORY,
    draw_symbol,
    wrap_text,
    star_points,
    diamond_points,
    cross_points,
)
from logger import EventLogger
from puzzles import SYMBOLS


class TestRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.fonts = {
            "title": pygame.font.Font(None, 84),
            "large": pygame.font.Font(None, 48),
            "medium": pygame.font.Font(None, 36),
            "small": pygame.font.Font(None, 28),
        }
        cls.screen = pygame.Surface((WIDTH, HEIGHT))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_text_wrapping(self):
        font = self.fonts["small"]
        text = "This is a simple sentence that should wrap across several lines when constrained."
        lines = wrap_text(font, text, max_width=150)
        self.assertGreater(len(lines), 1)
        # Empty string
        self.assertEqual(wrap_text(font, "", 200), [])

    def test_symbol_shapes_and_geometry(self):
        pts_star = star_points(50, 50, 20)
        self.assertEqual(len(pts_star), 10)

        pts_diamond = diamond_points(50, 50, 40)
        self.assertEqual(len(pts_diamond), 4)

        pts_cross = cross_points(50, 50, 40)
        self.assertEqual(len(pts_cross), 12)

        # Draw every symbol shape onto a test surface
        surf = pygame.Surface((100, 100))
        for sym in SYMBOLS:
            draw_symbol(surf, sym, (50, 50), 40, (255, 255, 255))

    def test_all_game_screen_states_draw_without_error(self):
        game = Game(EventLogger(path=os.devnull))

        # Start screen
        self.assertEqual(game.state, STATE_START)
        game.draw(self.screen, self.fonts)

        # Render all 6 levels
        game.start_game()
        for lvl in range(len(LEVELS)):
            game.level_index = lvl
            game.start_level()
            game.draw(self.screen, self.fonts)

            # Draw with feedback active
            game.feedback_time = 1.0
            game.feedback_text = "Test feedback banner"
            game.draw(self.screen, self.fonts)

            # Draw with hint ready (>= 3 failures)
            game.puzzle.failures = 3
            game.draw(self.screen, self.fonts)

            # Draw level complete overlay
            game.state = STATE_LEVEL_COMPLETE
            game.draw(self.screen, self.fonts)

        # Draw victory overlay
        game.state = STATE_VICTORY
        game.draw(self.screen, self.fonts)
        game.shutdown()


if __name__ == "__main__":
    unittest.main()
