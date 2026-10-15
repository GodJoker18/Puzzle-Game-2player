"""Game state, levels, timer, input handling and drawing.

Game holds the state and rules flow (no drawing). The draw_* functions at the
bottom only read the Game and paint it. Puzzle validation lives in puzzles.py.
"""

import math
import random

import pygame

from puzzles import (COLOR_ORDER, SYMBOL_MATCH, FIXED_LEVEL_1_COLORS,
                     HINT_AFTER_FAILURES, make_color_puzzle, make_symbol_puzzle)

WIDTH, HEIGHT = 1280, 720
HALF = WIDTH // 2
HEADER_H = 70

FEEDBACK_SECONDS = 1.2
FLASH_SECONDS = 0.25

STATE_START = "start"
STATE_PLAYING = "playing"
STATE_LEVEL_COMPLETE = "level_complete"
STATE_VICTORY = "victory"

# Levels cycle through both puzzle types. time_limit is a SOFT limit.
LEVELS = [
    {"type": COLOR_ORDER,  "length": 4, "time_limit": 60, "fixed": True},
    {"type": SYMBOL_MATCH, "length": 3, "time_limit": 60},
    {"type": COLOR_ORDER,  "length": 4, "time_limit": 60},
    {"type": SYMBOL_MATCH, "length": 4, "time_limit": 60},
    {"type": COLOR_ORDER,  "length": 4, "time_limit": 45},
    {"type": SYMBOL_MATCH, "length": 4, "time_limit": 45},
]

SELECT_KEYS = {
    pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
    pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2, pygame.K_KP4: 3,
}

# ---- colors ---------------------------------------------------------------
BG = (22, 24, 32)
HEADER_BG = (14, 15, 22)
PANEL_LEFT = (28, 36, 56)
PANEL_RIGHT = (46, 32, 52)
CARD = (56, 60, 80)
WHITE = (240, 240, 245)
GRAY = (150, 155, 170)
GREEN = (60, 190, 100)
RED = (215, 65, 65)
ORANGE = (240, 150, 40)
YELLOW_HINT = (250, 215, 70)
COLOR_RGB = {
    "red": (220, 60, 60), "blue": (60, 110, 230),
    "green": (60, 190, 90), "yellow": (240, 210, 50),
}

PUZZLE_TITLES = {COLOR_ORDER: "Color Order", SYMBOL_MATCH: "Symbol Matching"}
OPERATOR_HELP = {
    COLOR_ORDER: "Ask Player 2 which colors to press and in what order. "
                 "Use keys 1-4. A wrong press resets your sequence.",
    SYMBOL_MATCH: "Player 2 will describe symbols to you. Find each matching "
                  "symbol and press its number key, in the order they say.",
}
READER_HELP = {
    COLOR_ORDER: "Tell Player 1 which colors to press, in this order. "
                 "Player 1 cannot see this side of the screen.",
    SYMBOL_MATCH: "Describe each clue, in order, to Player 1. They can see "
                  "the symbols but not these clues.",
}


class Game:
    def __init__(self, logger, rng=None):
        self.logger = logger
        self.rng = rng or random.Random()
        self.state = STATE_START
        self.level_index = 0
        self.puzzle = None
        self.elapsed = 0.0          # seconds since the current puzzle began
        self.timed_out = False
        self.feedback_text = ""
        self.feedback_color = GREEN
        self.feedback_time = 0.0
        self.flash_index = None
        self.flash_time = 0.0
        self.total_failures = 0
        self.total_time = 0.0
        self._log("session_start")

    # ---- small helpers ------------------------------------------------------
    @property
    def level_number(self):
        return self.level_index + 1

    @property
    def time_limit(self):
        return LEVELS[self.level_index]["time_limit"]

    def _log(self, action, outcome="", detail="", attempt=None):
        puzzle = self.puzzle
        if attempt is None:
            attempt = puzzle.attempt if puzzle else ""
        self.logger.log(
            self.level_number if puzzle else 0,
            puzzle.puzzle_type if puzzle else "",
            action, attempt, self.elapsed, outcome, detail)

    def _show_feedback(self, text, color):
        self.feedback_text = text
        self.feedback_color = color
        self.feedback_time = FEEDBACK_SECONDS

    # ---- flow ---------------------------------------------------------------
    def start_game(self):
        self.level_index = 0
        self.total_failures = 0
        self.total_time = 0.0
        self.start_level()

    def start_level(self):
        cfg = LEVELS[self.level_index]
        if cfg["type"] == COLOR_ORDER:
            fixed = FIXED_LEVEL_1_COLORS if cfg.get("fixed") else None
            self.puzzle = make_color_puzzle(cfg["length"], self.rng, fixed)
        else:
            self.puzzle = make_symbol_puzzle(cfg["length"], self.rng)
        self.elapsed = 0.0
        self.timed_out = False
        self.feedback_time = 0.0
        self.flash_index = None
        self.state = STATE_PLAYING
        self._log("level_start", "",
                  f"time_limit_s={cfg['time_limit']};"
                  f"solution={'>'.join(self.puzzle.solution)}")

    def next_level(self):
        self.level_index += 1
        self.start_level()

    def restart(self):
        self.elapsed = 0.0
        self._log("restart", "", "from=victory")
        self.start_game()

    def shutdown(self):
        self._log("session_end", self.state)
        self.logger.close()

    # ---- input --------------------------------------------------------------
    def handle_key(self, key):
        """Unknown keys, or keys in the wrong state, are safely ignored."""
        if self.state == STATE_PLAYING:
            index = SELECT_KEYS.get(key)
            if index is not None:
                self.select(index)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.state == STATE_START:
                self.start_game()
            elif self.state == STATE_LEVEL_COMPLETE:
                self.next_level()
        elif key == pygame.K_SPACE and self.state == STATE_VICTORY:
            self.restart()

    def select(self, index):
        result = self.puzzle.select(index)
        if result.outcome == "ignored":
            return
        self._log("button_press", result.outcome,
                  f"selected={result.selected};expected={result.expected}",
                  result.attempt)
        self.flash_index = index
        self.flash_time = FLASH_SECONDS

        if result.outcome == "correct_step":
            self._show_feedback("Correct!", GREEN)
        elif result.outcome == "incorrect":
            self._log("incorrect_attempt", f"failures={self.puzzle.failures}",
                      "", result.attempt)
            self._show_feedback("Incorrect - start the sequence again", RED)
            if result.hint_triggered:
                self._log("hint_shown",
                          f"after_failures={self.puzzle.failures}")
        elif result.outcome == "complete":
            self._finish_puzzle(result.attempt)

    def _finish_puzzle(self, attempt):
        self.total_failures += self.puzzle.failures
        self.total_time += self.elapsed
        self._log("puzzle_complete", "success",
                  f"mistakes={self.puzzle.failures};"
                  f"timed_out={self.timed_out}", attempt)
        if self.level_index == len(LEVELS) - 1:
            self.state = STATE_VICTORY
            self._log("game_complete", "victory",
                      f"total_mistakes={self.total_failures};"
                      f"total_time_s={self.total_time:.1f}", attempt)
        else:
            self.state = STATE_LEVEL_COMPLETE
        self._show_feedback("Puzzle solved!", GREEN)

    # ---- per-frame update ---------------------------------------------------
    def update(self, dt):
        self.feedback_time = max(0.0, self.feedback_time - dt)
        self.flash_time = max(0.0, self.flash_time - dt)
        if self.state != STATE_PLAYING:
            return
        self.elapsed += dt
        if not self.timed_out and self.elapsed >= self.time_limit:
            self.timed_out = True      # soft timer: play continues
            self._log("timeout", "soft_timeout",
                      f"limit_s={self.time_limit}")
            self._show_feedback("Time's up! Keep going - no penalty", ORANGE)

    def draw(self, screen, fonts):
        if self.state == STATE_START:
            draw_start_screen(screen, fonts)
            return
        draw_play_screen(screen, fonts, self)
        if self.state in (STATE_LEVEL_COMPLETE, STATE_VICTORY):
            draw_overlay(screen, fonts, self)


# ---------------------------------------------------------------------------
# Drawing helpers (read-only: they never change game state)
# ---------------------------------------------------------------------------
def fmt_time(seconds):
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def draw_text(screen, font, text, color, center=None, topleft=None):
    surf = font.render(text, True, color)
    rect = surf.get_rect(center=center) if center else surf.get_rect(topleft=topleft)
    screen.blit(surf, rect)


def wrap_text(font, text, max_width):
    lines, current = [], ""
    for word in text.split():
        trial = word if not current else current + " " + word
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(screen, font, text, color, x, y, max_width, centered=True):
    """Draw wrapped text. If centered, x is the center; else x is the left edge."""
    line_h = font.get_linesize()
    for line in wrap_text(font, text, max_width):
        if centered:
            draw_text(screen, font, line, color, center=(x, y + line_h // 2))
        else:
            draw_text(screen, font, line, color, topleft=(x, y))
        y += line_h
    return y


def star_points(cx, cy, outer):
    pts = []
    for i in range(10):
        r = outer if i % 2 == 0 else outer * 0.4
        angle = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts


def draw_symbol(screen, name, center, size, color):
    cx, cy = center
    s = size // 2
    if name == "circle":
        pygame.draw.circle(screen, color, (cx, cy), s)
    elif name == "square":
        pygame.draw.rect(screen, color, (cx - s, cy - s, size, size))
    elif name == "triangle":
        pygame.draw.polygon(screen, color, [
            (cx, cy - s), (cx - s, cy + int(s * 0.8)), (cx + s, cy + int(s * 0.8))])
    elif name == "star":
        pygame.draw.polygon(screen, color, star_points(cx, cy, s))


def draw_start_screen(screen, fonts):
    screen.fill(BG)
    draw_text(screen, fonts["title"], "Co-op Puzzle Game", WHITE, center=(WIDTH // 2, 110))
    draw_text(screen, fonts["medium"], "Two players. One screen. Talk to each other!",
              GRAY, center=(WIDTH // 2, 175))
    lines = [
        "Player 1 (LEFT) is the Puzzle Operator: press keys 1-4 to choose buttons.",
        "Player 2 (RIGHT) is the Clue Reader: you can see the answer. Player 1 cannot.",
        "Work out the answer by talking. Please do not peek at the other half!",
        "A wrong press resets the sequence. After "
        f"{HINT_AFTER_FAILURES} mistakes, a hint appears for Player 2.",
        "The timer is soft: when it runs out you may keep playing (it is logged).",
        f"Solve all {len(LEVELS)} puzzles to win.  ENTER = next level,  SPACE = play again.",
    ]
    y = 240
    for line in lines:
        y = draw_wrapped(screen, fonts["small"], line, WHITE, 220, y, 840,
                         centered=False) + 14
    draw_text(screen, fonts["large"], "Press ENTER to start", GREEN,
              center=(WIDTH // 2, 620))
    draw_text(screen, fonts["small"], "ESC quits", GRAY, center=(WIDTH // 2, 670))


def draw_play_screen(screen, fonts, game):
    screen.fill(BG)
    pygame.draw.rect(screen, PANEL_LEFT, (0, HEADER_H, HALF, HEIGHT - HEADER_H))
    pygame.draw.rect(screen, PANEL_RIGHT, (HALF, HEADER_H, HALF, HEIGHT - HEADER_H))
    pygame.draw.line(screen, WHITE, (HALF, HEADER_H), (HALF, HEIGHT), 3)
    draw_header(screen, fonts, game)
    draw_operator_panel(screen, fonts, game)
    draw_reader_panel(screen, fonts, game)
    if game.feedback_time > 0:
        pygame.draw.rect(screen, game.feedback_color,
                         ((WIDTH - 640) // 2, 640, 640, 56), border_radius=12)
        draw_text(screen, fonts["medium"], game.feedback_text, WHITE,
                  center=(WIDTH // 2, 668))


def draw_header(screen, fonts, game):
    pygame.draw.rect(screen, HEADER_BG, (0, 0, WIDTH, HEADER_H))
    title = PUZZLE_TITLES[game.puzzle.puzzle_type]
    draw_text(screen, fonts["medium"],
              f"Level {game.level_number} of {len(LEVELS)}  -  {title}",
              WHITE, topleft=(20, 22))
    remaining = game.time_limit - game.elapsed
    if remaining >= 0:
        color = YELLOW_HINT if remaining < 10 else WHITE
        text = f"Time left  {fmt_time(math.ceil(remaining))}"
    else:
        color = ORANGE
        text = f"Overtime +{fmt_time(-remaining)}  (keep going!)"
    draw_text(screen, fonts["medium"], text, color, center=(WIDTH - 260, 35))


def draw_operator_panel(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF // 2
    draw_text(screen, fonts["medium"], "PLAYER 1 - PUZZLE OPERATOR", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], OPERATOR_HELP[puzzle.puzzle_type],
                 GRAY, cx, 135, 560)

    size, gap = 120, 20
    x0 = (HALF - (4 * size + 3 * gap)) // 2
    y = 250
    for i, name in enumerate(puzzle.options):
        x = x0 + i * (size + gap)
        if puzzle.puzzle_type == COLOR_ORDER:
            pygame.draw.rect(screen, COLOR_RGB[name], (x, y, size, size),
                             border_radius=14)
        else:
            pygame.draw.rect(screen, CARD, (x, y, size, size), border_radius=14)
            draw_symbol(screen, name, (x + size // 2, y + size // 2), 70, WHITE)
        flashing = (game.flash_index == i and game.flash_time > 0)
        pygame.draw.rect(screen, WHITE if flashing else BG, (x, y, size, size),
                         5 if flashing else 2, border_radius=14)
        draw_text(screen, fonts["large"], str(i + 1), WHITE,
                  center=(x + size // 2, y + size + 28))
        if puzzle.puzzle_type == COLOR_ORDER:
            draw_text(screen, fonts["small"], name.title(), GRAY,
                      center=(x + size // 2, y + size + 62))

    # Progress dots
    n = len(puzzle.solution)
    draw_text(screen, fonts["small"], "Your progress", GRAY, center=(cx, 455))
    for i in range(n):
        dot = (cx - (n - 1) * 22 + i * 44, 490)
        if i < puzzle.progress:
            pygame.draw.circle(screen, GREEN, dot, 14)
        else:
            pygame.draw.circle(screen, GRAY, dot, 14, 2)
    draw_text(screen, fonts["small"],
              f"Attempt {puzzle.attempt}      Mistakes: {puzzle.failures}",
              WHITE, center=(cx, 545))


def draw_reader_panel(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF + HALF // 2
    n = len(puzzle.solution)
    draw_text(screen, fonts["medium"], "PLAYER 2 - CLUE READER", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], READER_HELP[puzzle.puzzle_type],
                 GRAY, cx, 135, 560)

    card_w, card_h, gap = 130, 170, 14
    x0 = cx - (n * card_w + (n - 1) * gap) // 2
    y = 250
    for i, name in enumerate(puzzle.solution):
        x = x0 + i * (card_w + gap)
        done = i < puzzle.progress
        pygame.draw.rect(screen, CARD, (x, y, card_w, card_h), border_radius=12)
        draw_text(screen, fonts["small"], f"Step {i + 1}", GRAY,
                  center=(x + card_w // 2, y + 20))
        if puzzle.puzzle_type == COLOR_ORDER:
            pygame.draw.rect(screen, COLOR_RGB[name],
                             (x + 15, y + 40, card_w - 30, 60), border_radius=8)
            draw_text(screen, fonts["medium"], puzzle.clue_text(name), WHITE,
                      center=(x + card_w // 2, y + 125))
        else:
            draw_wrapped(screen, fonts["small"], puzzle.clue_text(name), WHITE,
                         x + card_w // 2, y + 50, card_w - 16)
        if done:
            pygame.draw.rect(screen, GREEN, (x, y, card_w, card_h), 4,
                             border_radius=12)
            draw_text(screen, fonts["small"], "done", GREEN,
                      center=(x + card_w // 2, y + card_h - 16))

    draw_text(screen, fonts["small"],
              f"Player 1 has entered {puzzle.progress} of {n} steps",
              WHITE, center=(cx, 450))
    if puzzle.hint_ready:
        pygame.draw.rect(screen, (80, 68, 20), (HALF + 40, 490, HALF - 80, 110),
                         border_radius=12)
        pygame.draw.rect(screen, YELLOW_HINT, (HALF + 40, 490, HALF - 80, 110),
                         3, border_radius=12)
        draw_wrapped(screen, fonts["small"], "HINT: " + puzzle.hint_text(),
                     YELLOW_HINT, cx, 505, HALF - 120)
    else:
        draw_text(screen, fonts["small"],
                  f"A hint appears after {puzzle.hint_after} mistakes.",
                  GRAY, center=(cx, 530))


def draw_overlay(screen, fonts, game):
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    screen.blit(shade, (0, 0))
    w, h = 720, 340
    x, y = (WIDTH - w) // 2, (HEIGHT - h) // 2
    pygame.draw.rect(screen, (34, 38, 54), (x, y, w, h), border_radius=18)
    pygame.draw.rect(screen, GREEN, (x, y, w, h), 3, border_radius=18)
    cx = WIDTH // 2
    puzzle = game.puzzle
    if game.state == STATE_VICTORY:
        draw_text(screen, fonts["title"], "Victory!", GREEN, center=(cx, y + 70))
        draw_text(screen, fonts["medium"],
                  f"All {len(LEVELS)} puzzles solved together.", WHITE,
                  center=(cx, y + 140))
        draw_text(screen, fonts["small"],
                  f"Total mistakes: {game.total_failures}      "
                  f"Total time: {fmt_time(game.total_time)}",
                  GRAY, center=(cx, y + 185))
        draw_text(screen, fonts["large"], "Press SPACE to play again", WHITE,
                  center=(cx, y + 265))
    else:
        draw_text(screen, fonts["large"], f"Level {game.level_number} complete!",
                  GREEN, center=(cx, y + 70))
        extra = "  (went past the soft timer)" if game.timed_out else ""
        draw_text(screen, fonts["small"],
                  f"Time: {fmt_time(game.elapsed)}      "
                  f"Mistakes: {puzzle.failures}{extra}",
                  WHITE, center=(cx, y + 140))
        draw_text(screen, fonts["large"], "Press ENTER for the next level", WHITE,
                  center=(cx, y + 250))
