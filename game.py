"""Game state, levels, timer, input handling and drawing.

Game holds the state and rules flow (no drawing). The draw_* functions at the
bottom only read the Game and paint it. Puzzle validation lives in puzzles.py.
"""

import math
import random

import pygame

from puzzles import (
    COLOR_ORDER, GRID_PATH, COOP_SYMBOL, SYMBOL_MATCH,
    FIXED_LEVEL_1_COLORS, HINT_AFTER_FAILURES,
    make_color_puzzle, make_grid_puzzle, make_coop_symbol_puzzle,
    make_symbol_puzzle,
)

WIDTH, HEIGHT = 1280, 720
HALF = WIDTH // 2
HEADER_H = 70

FEEDBACK_SECONDS = 1.4
FLASH_SECONDS = 0.25

STATE_START         = "start"
STATE_PLAYING       = "playing"
STATE_LEVEL_COMPLETE = "level_complete"
STATE_VICTORY       = "victory"

# Six levels: Color Order  -  Grid Path  -  Coop Symbol ( - - 2, increasing complexity)
LEVELS = [
    {"type": COLOR_ORDER,  "length": 4, "time_limit": 60, "fixed": True},
    {"type": GRID_PATH,    "rows": 4, "cols": 5, "walls": 4,  "time_limit": 90},
    {"type": COOP_SYMBOL,  "pairs": 2, "fillers": 2,          "time_limit": 75},
    {"type": COLOR_ORDER,  "length": 4, "time_limit": 50},
    {"type": GRID_PATH,    "rows": 5, "cols": 7, "walls": 7,  "time_limit": 90},
    {"type": COOP_SYMBOL,  "pairs": 3, "fillers": 3,          "time_limit": 75},
]

# Keys for COLOR_ORDER
SELECT_KEYS = {
    pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
    pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2, pygame.K_KP4: 3,
}

# Keys for GRID_PATH
MOVE_KEYS = {
    pygame.K_UP:    "up",
    pygame.K_DOWN:  "down",
    pygame.K_LEFT:  "left",
    pygame.K_RIGHT: "right",
    pygame.K_w:     "up",
    pygame.K_s:     "down",
    pygame.K_a:     "left",
    pygame.K_d:     "right",
}

# Keys for COOP_SYMBOL highlight cycling
CYCLE_KEYS_LEFT  = (pygame.K_LEFT,  pygame.K_UP,   pygame.K_a, pygame.K_w)
CYCLE_KEYS_RIGHT = (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_d, pygame.K_s)
CONFIRM_KEYS     = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)

# ---- colors ---------------------------------------------------------------
BG           = (22, 24, 32)
HEADER_BG    = (14, 15, 22)
PANEL_LEFT   = (28, 36, 56)
PANEL_RIGHT  = (46, 32, 52)
CARD         = (56, 60, 80)
WHITE        = (240, 240, 245)
GRAY         = (150, 155, 170)
GREEN        = (60, 190, 100)
RED          = (215, 65, 65)
ORANGE       = (240, 150, 40)
YELLOW_HINT  = (250, 215, 70)
WALL_COLOR   = (80, 80, 100)
PLAYER_COLOR = (100, 180, 255)
GOAL_COLOR   = (255, 200, 60)
START_COLOR  = (100, 220, 140)
COLOR_RGB = {
    "red":    (220, 60, 60),
    "blue":   (60, 110, 230),
    "green":  (60, 190, 90),
    "yellow": (240, 210, 50),
}
SYMBOL_COLOR = {
    "circle":   (120, 180, 255),
    "square":   (180, 120, 255),
    "triangle": (255, 180, 80),
    "star":     (255, 220, 60),
    "diamond":  (80, 220, 180),
    "cross":    (255, 100, 120),
}

PUZZLE_TITLES = {
    COLOR_ORDER:  "Color Order",
    GRID_PATH:    "Grid Pathfinding",
    COOP_SYMBOL:  "Cooperative Symbol Matching",
    SYMBOL_MATCH: "Symbol Matching",
}
OPERATOR_HELP = {
    COLOR_ORDER:  "Ask Player 2 which colors to press and in what order. "
                  "Use keys 1-4. A wrong press resets your sequence.",
    GRID_PATH:    "Navigate the blue dot to the gold goal using arrow keys. "
                  "Ask Player 2 which direction to move! Walls block you.",
    COOP_SYMBOL:  "Use arrow keys or WASD to move the green highlight. "
                  "Press ENTER or SPACE to select. Select 2 to form a pair.",
    SYMBOL_MATCH: "Player 2 will describe symbols. Press 1-4 in the order given.",
}
READER_HELP = {
    COLOR_ORDER:  "Tell Player 1 which colors to press, in this order. "
                  "Player 1 cannot see this side of the screen.",
    GRID_PATH:    "Read the direction list below to Player 1 one step at a time. "
                  "Player 1 cannot see your route list.",
    COOP_SYMBOL:  "Describe each clue to Player 1 so they find matching symbols. "
                  "Give clues in order - do NOT say the symbol name!",
    SYMBOL_MATCH: "Describe each clue, in order, to Player 1.",
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
        ptype = cfg["type"]
        if ptype == COLOR_ORDER:
            fixed = FIXED_LEVEL_1_COLORS if cfg.get("fixed") else None
            self.puzzle = make_color_puzzle(cfg["length"], self.rng, fixed)
        elif ptype == GRID_PATH:
            self.puzzle = make_grid_puzzle(
                cfg["rows"], cfg["cols"], cfg["walls"], self.rng)
        elif ptype == COOP_SYMBOL:
            self.puzzle = make_coop_symbol_puzzle(
                cfg["pairs"], cfg["fillers"], self.rng)
        else:
            # Fallback: legacy symbol match (not in default LEVELS)
            self.puzzle = make_symbol_puzzle(cfg.get("length", 3), self.rng)

        self.elapsed = 0.0
        self.timed_out = False
        self.feedback_time = 0.0
        self.flash_index = None
        self.state = STATE_PLAYING

        # Build solution detail for logging
        pz = self.puzzle
        if ptype == COLOR_ORDER:
            sol_str = ">".join(pz.solution)
        elif ptype == GRID_PATH:
            sol_str = ">".join(pz.waypoints)
        else:
            sol_str = "|".join(f"{a}+{b}" for a, b in pz.pairs)
        self._log("level_start", "",
                  f"time_limit_s={cfg['time_limit']};solution={sol_str}")

    def next_level(self):
        if self.level_index < len(LEVELS) - 1:
            self.level_index += 1
            self.start_level()
        else:
            self.state = STATE_VICTORY

    def restart(self):
        self.elapsed = 0.0
        self._log("restart", "", "from=victory")
        self.start_game()

    def shutdown(self):
        self._log("session_end", self.state)
        self.logger.close()

    # ---- input --------------------------------------------------------------
    def handle_key(self, key):
        """Route key presses to the active puzzle type. Unknown keys are ignored."""
        if self.state == STATE_PLAYING:
            ptype = self.puzzle.puzzle_type

            if ptype == COLOR_ORDER:
                index = SELECT_KEYS.get(key)
                if index is not None:
                    self._handle_color_select(index)

            elif ptype == GRID_PATH:
                direction = MOVE_KEYS.get(key)
                if direction is not None:
                    self._handle_grid_move(direction)

            elif ptype == COOP_SYMBOL:
                if key in CYCLE_KEYS_LEFT:
                    self.puzzle.move_highlight("left")
                elif key in CYCLE_KEYS_RIGHT:
                    self.puzzle.move_highlight("right")
                elif key in CONFIRM_KEYS:
                    self._handle_symbol_confirm()

        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.state == STATE_START:
                self.start_game()
            elif self.state == STATE_LEVEL_COMPLETE:
                self.next_level()
            elif self.state == STATE_VICTORY:
                self.restart()
        elif key == pygame.K_SPACE and self.state == STATE_VICTORY:
            self.restart()

    # ---- puzzle-specific handlers -------------------------------------------
    def _handle_color_select(self, index):
        result = self.puzzle.select(index)
        if result.outcome == "ignored":
            return
        self._log("button_press", result.outcome,
                  f"selected={result.selected};expected={result.expected}",
                  result.attempt)
        self.flash_index = index
        self.flash_time = FLASH_SECONDS
        if result.outcome == "correct_step":
            self._show_feedback("Correct step!", GREEN)
        elif result.outcome == "incorrect":
            self._log("incorrect_attempt", f"failures={self.puzzle.failures}",
                      "", result.attempt)
            self._show_feedback("Wrong! Start the sequence over.", RED)
            if result.hint_triggered:
                self._log("hint_shown", f"after_failures={self.puzzle.failures}")
        elif result.outcome == "complete":
            self._finish_puzzle(result.attempt)

    def _handle_grid_move(self, direction):
        result = self.puzzle.move(direction)
        attempt = self.puzzle.attempt
        self._log("grid_move", result.outcome,
                  f"dir={direction};pos={result.position};steps={result.steps}",
                  attempt)
        if result.outcome == "wall":
            self._log("incorrect_attempt", f"failures={self.puzzle.failures}",
                      "", attempt)
            self._show_feedback("Blocked! Try a different direction.", RED)
            if result.hint_triggered:
                self._log("hint_shown", f"after_failures={self.puzzle.failures}")
        elif result.outcome == "moved":
            self._show_feedback(f"Moved {direction}.", GREEN)
        elif result.outcome == "goal":
            self._finish_puzzle(attempt)

    def _handle_symbol_confirm(self):
        result = self.puzzle.confirm_selection()
        attempt = self.puzzle.attempt
        if result.outcome == "ignored":
            return
        self._log("symbol_confirm", result.outcome,
                  f"selected={result.selected};expected={result.expected}",
                  attempt)
        if result.outcome == "first_pick":
            sym = result.selected[0]
            self._show_feedback(f"First symbol selected: {sym}. Pick another!", ORANGE)
        elif result.outcome == "correct_pair":
            self._show_feedback("Correct pair! Find the next one.", GREEN)
        elif result.outcome == "wrong_pair":
            self._log("incorrect_attempt", f"failures={self.puzzle.failures}",
                      "", attempt)
            self._show_feedback("Wrong pair! Try again.", RED)
            if result.hint_triggered:
                self._log("hint_shown", f"after_failures={self.puzzle.failures}")
        elif result.outcome == "complete":
            self._finish_puzzle(attempt)

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
            self._show_feedback("Time's up! Keep going - no penalty.", ORANGE)

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


def diamond_points(cx, cy, size):
    s = size // 2
    return [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]


def cross_points(cx, cy, size):
    t = max(4, size // 4)
    h = size // 2
    return [
        (cx - t, cy - h), (cx + t, cy - h),
        (cx + t, cy - t), (cx + h, cy - t),
        (cx + h, cy + t), (cx + t, cy + t),
        (cx + t, cy + h), (cx - t, cy + h),
        (cx - t, cy + t), (cx - h, cy + t),
        (cx - h, cy - t), (cx - t, cy - t),
    ]


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
    elif name == "diamond":
        pygame.draw.polygon(screen, color, diamond_points(cx, cy, size))
    elif name == "cross":
        pygame.draw.polygon(screen, color, cross_points(cx, cy, size))


def draw_start_screen(screen, fonts):
    screen.fill(BG)
    draw_text(screen, fonts["title"], "Co-op Puzzle Game", WHITE,
              center=(WIDTH // 2, 100))
    draw_text(screen, fonts["medium"], "Two players. One screen. Talk to each other!",
              GRAY, center=(WIDTH // 2, 165))
    lines = [
        "Player 1 (LEFT) is the Puzzle Operator: navigate, select, or match things.",
        "Player 2 (RIGHT) is the Clue Reader: you can see the answer. Player 1 cannot.",
        "Work out the solution by talking - please do not peek at the other half!",
        "",
        "COLOR ORDER:  Player 1 presses keys 1-4 in the order Player 2 describes.",
        "GRID PATH:    Player 1 uses arrow keys or WASD to navigate. Player 2 reads directions.",
        "SYMBOL MATCH: Player 1 uses arrows to highlight, ENTER/SPACE to pick two symbols.",
        "",
        f"A hint appears for Player 2 after {HINT_AFTER_FAILURES} mistakes.",
        "The timer is soft: overtime is logged but you keep playing.",
        f"Solve all {len(LEVELS)} puzzles to win.  ENTER = next level,  SPACE = play again.",
    ]
    y = 230
    for line in lines:
        if line == "":
            y += 12
        else:
            y = draw_wrapped(screen, fonts["small"], line, WHITE, 220, y, 840,
                             centered=False) + 10
    draw_text(screen, fonts["large"], "Press ENTER to start", GREEN,
              center=(WIDTH // 2, 620))
    draw_text(screen, fonts["small"], "ESC quits", GRAY, center=(WIDTH // 2, 665))


def draw_play_screen(screen, fonts, game):
    screen.fill(BG)
    pygame.draw.rect(screen, PANEL_LEFT,  (0,    HEADER_H, HALF, HEIGHT - HEADER_H))
    pygame.draw.rect(screen, PANEL_RIGHT, (HALF, HEADER_H, HALF, HEIGHT - HEADER_H))
    pygame.draw.line(screen, WHITE, (HALF, HEADER_H), (HALF, HEIGHT), 3)
    draw_header(screen, fonts, game)

    ptype = game.puzzle.puzzle_type
    if ptype == COLOR_ORDER:
        draw_operator_color(screen, fonts, game)
        draw_reader_color(screen, fonts, game)
    elif ptype == GRID_PATH:
        draw_operator_grid(screen, fonts, game)
        draw_reader_grid(screen, fonts, game)
    elif ptype == COOP_SYMBOL:
        draw_operator_symbol(screen, fonts, game)
        draw_reader_symbol(screen, fonts, game)
    else:
        # Legacy SYMBOL_MATCH fallback
        draw_operator_color(screen, fonts, game)
        draw_reader_color(screen, fonts, game)

    if game.feedback_time > 0:
        pygame.draw.rect(screen, game.feedback_color,
                         ((WIDTH - 680) // 2, 640, 680, 56), border_radius=12)
        draw_text(screen, fonts["medium"], game.feedback_text, WHITE,
                  center=(WIDTH // 2, 668))


def draw_header(screen, fonts, game):
    pygame.draw.rect(screen, HEADER_BG, (0, 0, WIDTH, HEADER_H))
    title = PUZZLE_TITLES.get(game.puzzle.puzzle_type, "Puzzle")
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


# ---- COLOR ORDER panels ----------------------------------------------------
def draw_operator_color(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF // 2
    draw_text(screen, fonts["medium"], "PLAYER 1 - PUZZLE OPERATOR", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], OPERATOR_HELP[COLOR_ORDER],
                 GRAY, cx, 135, 560)
    size, gap = 110, 16
    x0 = (HALF - (4 * size + 3 * gap)) // 2
    y = 248
    for i, name in enumerate(puzzle.options):
        x = x0 + i * (size + gap)
        pygame.draw.rect(screen, COLOR_RGB[name], (x, y, size, size), border_radius=12)
        flashing = (game.flash_index == i and game.flash_time > 0)
        pygame.draw.rect(screen, WHITE if flashing else BG, (x, y, size, size),
                         5 if flashing else 2, border_radius=12)
        draw_text(screen, fonts["large"], str(i + 1), WHITE,
                  center=(x + size // 2, y + size + 26))
        draw_text(screen, fonts["small"], name.title(), GRAY,
                  center=(x + size // 2, y + size + 58))
    n = len(puzzle.solution)
    draw_text(screen, fonts["small"], "Your progress", GRAY, center=(cx, 450))
    for i in range(n):
        dot = (cx - (n - 1) * 22 + i * 44, 485)
        if i < puzzle.progress:
            pygame.draw.circle(screen, GREEN, dot, 13)
        else:
            pygame.draw.circle(screen, GRAY, dot, 13, 2)
    draw_text(screen, fonts["small"],
              f"Attempt {puzzle.attempt}      Mistakes: {puzzle.failures}",
              WHITE, center=(cx, 540))


def draw_reader_color(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF + HALF // 2
    n = len(puzzle.solution)
    draw_text(screen, fonts["medium"], "PLAYER 2 - CLUE READER", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], READER_HELP[COLOR_ORDER],
                 GRAY, cx, 135, 560)
    card_w, card_h, gap = 130, 170, 12
    x0 = cx - (n * card_w + (n - 1) * gap) // 2
    y = 248
    for i, name in enumerate(puzzle.solution):
        x = x0 + i * (card_w + gap)
        done = i < puzzle.progress
        pygame.draw.rect(screen, CARD, (x, y, card_w, card_h), border_radius=12)
        draw_text(screen, fonts["small"], f"Step {i + 1}", GRAY,
                  center=(x + card_w // 2, y + 20))
        pygame.draw.rect(screen, COLOR_RGB[name],
                         (x + 14, y + 38, card_w - 28, 56), border_radius=8)
        draw_text(screen, fonts["medium"], name.title(), WHITE,
                  center=(x + card_w // 2, y + 120))
        if done:
            pygame.draw.rect(screen, GREEN, (x, y, card_w, card_h), 4,
                             border_radius=12)
            draw_text(screen, fonts["small"], "done", GREEN,
                      center=(x + card_w // 2, y + card_h - 16))
    draw_text(screen, fonts["small"],
              f"Player 1 has entered {puzzle.progress} of {n} steps",
              WHITE, center=(cx, 450))
    _draw_hint_box(screen, fonts, puzzle, cx)


# ---- GRID PATH panels ------------------------------------------------------
_GRID_PANEL_LEFT  = 20
_GRID_PANEL_TOP   = HEADER_H + 10
_GRID_PANEL_W     = HALF - 10
_GRID_PANEL_H     = HEIGHT - HEADER_H - 10


def draw_operator_grid(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF // 2
    draw_text(screen, fonts["medium"], "PLAYER 1 - PUZZLE OPERATOR", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], OPERATOR_HELP[GRID_PATH],
                 GRAY, cx, 130, 560)

    # Grid drawing parameters
    rows, cols = puzzle.rows, puzzle.cols
    cell = min((_GRID_PANEL_W - 40) // cols, (_GRID_PANEL_H - 130) // rows, 72)
    gw = cols * cell
    gh = rows * cell
    gx = (HALF - gw) // 2
    gy = 230

    for r in range(rows):
        for c in range(cols):
            rx = gx + c * cell
            ry = gy + r * cell
            if (r, c) in puzzle.walls:
                pygame.draw.rect(screen, (32, 34, 46), (rx, ry, cell, cell))
                pygame.draw.rect(screen, (70, 72, 90), (rx, ry, cell, cell), 2)
                pygame.draw.line(screen, (50, 52, 68), (rx + 6, ry + 6),
                                 (rx + cell - 6, ry + cell - 6), 2)
                pygame.draw.line(screen, (50, 52, 68), (rx + cell - 6, ry + 6),
                                 (rx + 6, ry + cell - 6), 2)
            else:
                pygame.draw.rect(screen, CARD, (rx, ry, cell, cell))
                pygame.draw.rect(screen, BG, (rx, ry, cell, cell), 1)

    # Draw start marker
    sr, sc = puzzle.start
    sx = gx + sc * cell + cell // 2
    sy = gy + sr * cell + cell // 2
    pygame.draw.circle(screen, START_COLOR, (sx, sy), cell // 5)
    draw_text(screen, fonts["small"], "S", BG, center=(sx, sy))

    # Draw goal marker
    gr2, gc2 = puzzle.goal
    goalx = gx + gc2 * cell + cell // 2
    goaly = gy + gr2 * cell + cell // 2
    half_c = cell // 2 - 4
    for dx, dy in [(-half_c, -half_c), (half_c, -half_c),
                   (half_c, half_c), (-half_c, half_c)]:
        pygame.draw.circle(screen, GOAL_COLOR,
                           (goalx + dx // 2, goaly + dy // 2), cell // 6)
    pygame.draw.circle(screen, GOAL_COLOR, (goalx, goaly), cell // 3, 3)
    draw_text(screen, fonts["small"], "G", GOAL_COLOR, center=(goalx, goaly))

    # Draw player
    pr, pc = puzzle.position
    px = gx + pc * cell + cell // 2
    py = gy + pr * cell + cell // 2
    pygame.draw.circle(screen, PLAYER_COLOR, (px, py), cell // 3)
    pygame.draw.circle(screen, WHITE, (px, py), cell // 3, 2)

    # Stats
    stat_y = gy + gh + 18
    draw_text(screen, fonts["small"],
              f"Steps: {puzzle.steps}    Wall hits: {puzzle.failures}",
              WHITE, center=(cx, stat_y))
    draw_text(screen, fonts["small"],
              "Arrow keys or WASD to move. Ask Player 2 for directions!",
              GRAY, center=(cx, stat_y + 26))


def draw_reader_grid(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF + HALF // 2
    draw_text(screen, fonts["medium"], "PLAYER 2 - CLUE READER", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], READER_HELP[GRID_PATH],
                 GRAY, cx, 130, 560)

    waypoints = puzzle.waypoints
    completed = getattr(puzzle, "route_progress", puzzle.steps)

    # Show waypoints as a scrolling list
    card_x = HALF + 30
    card_w = HALF - 60
    y = 248
    draw_text(screen, fonts["small"], "Direction sequence for Player 1:",
              GRAY, topleft=(card_x, y))
    y += 30
    visible_start = max(0, completed - 1)
    visible = waypoints[visible_start:visible_start + 6]
    for i, wp in enumerate(visible):
        abs_i = visible_start + i
        done = abs_i < completed
        current = abs_i == completed
        if done:
            col = GREEN
            prefix = f"    {abs_i + 1}. [done] {wp.upper()}"
        elif current:
            col = YELLOW_HINT
            prefix = f" -> {abs_i + 1}. {wp.upper()}  <-- NEXT"
        else:
            col = GRAY
            prefix = f"    {abs_i + 1}. {wp.upper()}"
        draw_text(screen, fonts["small"], prefix, col, topleft=(card_x, y))
        y += 28

    if completed >= len(waypoints) and not puzzle.solved:
        draw_text(screen, fonts["small"], "Almost there - keep going!", ORANGE,
                  center=(cx, y + 10))

    stat_y = 455
    draw_text(screen, fonts["small"],
              f"Player 1 at step {completed} of {len(waypoints)}",
              WHITE, center=(cx, stat_y))
    _draw_hint_box(screen, fonts, puzzle, cx)


# ---- COOP SYMBOL panels ----------------------------------------------------
def draw_operator_symbol(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF // 2
    draw_text(screen, fonts["medium"], "PLAYER 1 - PUZZLE OPERATOR", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], OPERATOR_HELP[COOP_SYMBOL],
                 GRAY, cx, 130, 560)

    board = puzzle.board
    n = len(board)
    cell_size = 78
    gap = 10
    cols_count = min(n, 5)
    rows_count = math.ceil(n / cols_count)
    grid_w = cols_count * cell_size + (cols_count - 1) * gap
    grid_h = rows_count * cell_size + (rows_count - 1) * gap
    gx = (HALF - grid_w) // 2
    gy = 240

    for idx, sym in enumerate(board):
        col_i = idx % cols_count
        row_i = idx // cols_count
        rx = gx + col_i * (cell_size + gap)
        ry = gy + row_i * (cell_size + gap)

        is_completed = idx in puzzle.completed_positions
        is_selected  = idx in puzzle.selection
        is_highlight = (idx == puzzle.highlight)

        if is_completed:
            bg_col = (30, 70, 30)
        elif is_selected:
            bg_col = (70, 65, 30)
        else:
            bg_col = CARD
        pygame.draw.rect(screen, bg_col, (rx, ry, cell_size, cell_size),
                         border_radius=10)

        if not is_completed:
            sym_col = SYMBOL_COLOR.get(sym, WHITE)
            draw_symbol(screen, sym, (rx + cell_size // 2, ry + 32),
                        40, sym_col)

        if is_completed:
            pygame.draw.rect(screen, (60, 160, 60), (rx, ry, cell_size, cell_size),
                             3, border_radius=10)
        elif is_selected and is_highlight:
            pygame.draw.rect(screen, YELLOW_HINT, (rx, ry, cell_size, cell_size),
                             4, border_radius=10)
            pygame.draw.rect(screen, GREEN, (rx - 3, ry - 3, cell_size + 6, cell_size + 6),
                             2, border_radius=12)
        elif is_selected:
            pygame.draw.rect(screen, YELLOW_HINT, (rx, ry, cell_size, cell_size),
                             4, border_radius=10)
        elif is_highlight:
            pygame.draw.rect(screen, GREEN, (rx, ry, cell_size, cell_size),
                             4, border_radius=10)
        else:
            pygame.draw.rect(screen, BG, (rx, ry, cell_size, cell_size),
                             2, border_radius=10)
        # Draw position number
        draw_text(screen, fonts["small"], str(idx + 1), GRAY,
                  center=(rx + cell_size // 2, ry + cell_size - 12))

    stat_y = gy + grid_h + 24
    picking = len(puzzle.selection)
    pair_idx = puzzle.current_pair_index
    total_pairs = len(puzzle.pairs)
    draw_text(screen, fonts["small"],
              f"Pair {pair_idx + 1} of {total_pairs}  |  "
              f"{'Pick 2nd symbol' if picking == 1 else 'Highlight then ENTER'}",
              WHITE, center=(cx, stat_y))
    draw_text(screen, fonts["small"],
              f"Mistakes: {puzzle.failures}    Completed: {len(puzzle.completed_positions) // 2} pairs",
              GRAY, center=(cx, stat_y + 28))


def draw_reader_symbol(screen, fonts, game):
    puzzle = game.puzzle
    cx = HALF + HALF // 2
    draw_text(screen, fonts["medium"], "PLAYER 2 - CLUE READER", WHITE,
              center=(cx, 105))
    draw_wrapped(screen, fonts["small"], READER_HELP[COOP_SYMBOL],
                 GRAY, cx, 130, 560)

    card_x = HALF + 30
    card_w = HALF - 60
    y = 230

    for i, (pa, pb) in enumerate(puzzle.pairs):
        done = i < puzzle.current_pair_index
        current = i == puzzle.current_pair_index
        ca, cb = puzzle.pair_clues[i]

        box_col = (30, 70, 30) if done else ((60, 55, 20) if current else CARD)
        pygame.draw.rect(screen, box_col, (card_x, y, card_w, 72), border_radius=10)
        if current:
            pygame.draw.rect(screen, YELLOW_HINT, (card_x, y, card_w, 72), 3,
                             border_radius=10)
        elif done:
            pygame.draw.rect(screen, (60, 160, 60), (card_x, y, card_w, 72), 2,
                             border_radius=10)

        status_col = GREEN if done else (YELLOW_HINT if current else GRAY)
        title_text = f"Pair {i + 1}" + ("  [done]" if done else "  (match 2 shapes)")
        draw_text(screen, fonts["small"], title_text, status_col,
                  topleft=(card_x + 16, y + 10))

        clue_text = f'"{ca}"' if pa == pb else f'"{ca}"  +  "{cb}"'
        draw_text(screen, fonts["medium"], clue_text, WHITE if (current or done) else GRAY,
                  topleft=(card_x + 16, y + 36))
        y += 82

    _draw_hint_box(screen, fonts, puzzle, cx)


# ---- Shared hint box -------------------------------------------------------
def _draw_hint_box(screen, fonts, puzzle, cx):
    stat_y = 570
    if puzzle.hint_ready:
        hint_rect = (HALF + 30 if cx > HALF else 30,
                     490, HALF - 60, 110)
        pygame.draw.rect(screen, (80, 68, 20), hint_rect, border_radius=12)
        pygame.draw.rect(screen, YELLOW_HINT, hint_rect, 3, border_radius=12)
        draw_wrapped(screen, fonts["small"], "HINT: " + puzzle.hint_text(),
                     YELLOW_HINT, cx, hint_rect[1] + 10, HALF - 120)
    else:
        draw_text(screen, fonts["small"],
                  f"A hint appears after {puzzle.hint_after} mistakes.",
                  GRAY, center=(cx, stat_y))


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

