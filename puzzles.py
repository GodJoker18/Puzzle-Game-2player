"""Puzzle logic and validation. No Pygame in this file, so it is easy to test.

Three puzzle types:
  COLOR_ORDER  - Operator presses colors in a hidden sequence (key-sequence).
  GRID_PATH    - Operator navigates a character through a grid using arrow keys;
                 Clue Reader sees route waypoints but not the grid walls.
  COOP_SYMBOL  - Operator sees a board of symbols; Clue Reader sees pair clues.
                 Operator cycles the highlight with LEFT/RIGHT arrow keys and
                 confirms with ENTER. Two confirmed symbols = one pair attempt.
"""

import random
from collections import deque
from dataclasses import dataclass

# ---- puzzle type identifiers -------------------------------------------------
COLOR_ORDER  = "color_order"
GRID_PATH    = "grid_path"
COOP_SYMBOL  = "coop_symbol"
SYMBOL_MATCH = "symbol_match"   # legacy constant, kept for compatibility

COLORS = ["red", "blue", "green", "yellow"]            # keys 1-4 in this order
FIXED_LEVEL_1_COLORS = ["blue", "red", "yellow", "green"]
SYMBOLS = ["circle", "square", "triangle", "star", "diamond", "cross"]

# What the Clue Reader sees for a symbol (the Operator sees the drawn shape).
SYMBOL_CLUES = {
    "circle":   "Round, no corners",
    "square":   "Four equal sides",
    "triangle": "Three corners",
    "star":     "Five points",
    "diamond":  "Tilted square / rhombus",
    "cross":    "Plus sign / two bars crossing",
}

HINT_AFTER_FAILURES = 3

# ===========================================================================
# Shared result dataclass for COLOR_ORDER (SequencePuzzle)
# ===========================================================================
@dataclass
class SelectResult:
    """What happened when the Operator pressed one option."""
    outcome: str          # "correct_step", "complete", "incorrect" or "ignored"
    selected: str         # option name pressed ("" if ignored)
    expected: str         # option name that was required ("" if none)
    attempt: int          # attempt number this press belonged to (1-based)
    hint_triggered: bool = False   # True only on the press that unlocks the hint


# ===========================================================================
# SequencePuzzle  (COLOR_ORDER)  — unchanged logic from original
# ===========================================================================
class SequencePuzzle:
    def __init__(self, puzzle_type, options, solution,
                 hint_after=HINT_AFTER_FAILURES):
        self.puzzle_type = puzzle_type
        self.options = list(options)      # what keys 1-4 map to, in order
        self.solution = list(solution)    # required press order
        self.hint_after = hint_after
        self.progress = 0                 # correct presses in the current attempt
        self.failures = 0                 # failed attempts so far
        self.solved = False

    @property
    def attempt(self):
        """Current attempt number (1 = first try)."""
        return self.failures + 1

    @property
    def hint_ready(self):
        return self.failures >= self.hint_after

    def select(self, index):
        """Press option number `index` (0-based). Invalid input is ignored."""
        valid = (isinstance(index, int) and not isinstance(index, bool)
                 and 0 <= index < len(self.options))
        if self.solved or not valid:
            return SelectResult("ignored", "", "", self.attempt)

        selected = self.options[index]
        expected = self.solution[self.progress]
        attempt = self.attempt

        if selected == expected:
            self.progress += 1
            if self.progress == len(self.solution):
                self.solved = True
                return SelectResult("complete", selected, expected, attempt)
            return SelectResult("correct_step", selected, expected, attempt)

        self.failures += 1
        self.progress = 0
        return SelectResult("incorrect", selected, expected, attempt,
                            hint_triggered=(self.failures == self.hint_after))

    def clue_text(self, name):
        """Words the Clue Reader sees for one solution item."""
        if self.puzzle_type == SYMBOL_MATCH:
            return SYMBOL_CLUES.get(name, name)
        return name.title()

    def hint_text(self):
        """Hint for the Clue Reader: the next item still needed."""
        if self.solved:
            return ""
        name = self.solution[self.progress]
        step = self.progress + 1
        if self.puzzle_type == SYMBOL_MATCH:
            return (f"Step {step} is the {name} ({SYMBOL_CLUES.get(name, '').lower()}). "
                    "Try describing its shape in different words.")
        return (f"Step {step} is {name.upper()}. "
                "Start your sequence from the beginning each time.")


# ===========================================================================
# GridPuzzle  (GRID_PATH)
# ===========================================================================
_DIR_DELTA = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


@dataclass
class MoveResult:
    outcome: str           # "moved", "wall", "goal", "already_done", "ignored"
    direction: str
    position: tuple        # (row, col) after the move
    steps: int             # total valid moves so far
    failures: int          # total wall-hits so far
    hint_triggered: bool = False


class GridPuzzle:
    """
    Player 1 navigates a character from start to goal on a grid using arrow keys.
    Player 2 sees the solution waypoints (sequence of direction words) but not
    the grid walls or layout.
    """

    def __init__(self, rows, cols, walls, start, goal, waypoints,
                 hint_after=HINT_AFTER_FAILURES):
        self.puzzle_type = GRID_PATH
        self.rows = rows
        self.cols = cols
        self.walls = set(walls)              # set of (row, col) wall cells
        self.start = start                   # (row, col)
        self.goal = goal                     # (row, col)
        self.waypoints = list(waypoints)     # list of direction strings (solution)
        self.hint_after = hint_after
        self.position = start
        self.steps = 0                       # valid moves taken
        self.failures = 0                    # wall-hit count
        self.solved = False

    @property
    def attempt(self):
        return self.failures + 1

    @property
    def hint_ready(self):
        return self.failures >= self.hint_after

    def move(self, direction):
        """Attempt a move. Returns MoveResult."""
        if self.solved:
            return MoveResult("already_done", direction, self.position,
                              self.steps, self.failures)
        if direction not in _DIR_DELTA:
            return MoveResult("ignored", direction, self.position,
                              self.steps, self.failures)
        dr, dc = _DIR_DELTA[direction]
        nr, nc = self.position[0] + dr, self.position[1] + dc
        # Out of bounds or wall
        if not (0 <= nr < self.rows and 0 <= nc < self.cols) or (nr, nc) in self.walls:
            self.failures += 1
            triggered = (self.failures == self.hint_after)
            return MoveResult("wall", direction, self.position,
                              self.steps, self.failures, hint_triggered=triggered)
        self.position = (nr, nc)
        self.steps += 1
        if self.position == self.goal:
            self.solved = True
            return MoveResult("goal", direction, self.position,
                              self.steps, self.failures)
        return MoveResult("moved", direction, self.position,
                          self.steps, self.failures)

    def hint_text(self):
        if self.solved:
            return ""
        idx = min(self.steps, len(self.waypoints) - 1)
        nxt = self.waypoints[idx] if self.waypoints else "forward"
        return (f"Move {nxt.upper()} next. "
                "Player 2: read the next direction from your list.")


# ===========================================================================
# CoopSymbolPuzzle  (COOP_SYMBOL)
# ===========================================================================
@dataclass
class PairResult:
    outcome: str           # "first_pick", "correct_pair", "wrong_pair",
                           # "complete", "ignored"
    selected: tuple        # (sym_a, sym_b) or (sym_a, "") on first pick
    expected: tuple        # correct pair for this step
    pair_index: int        # which pair was attempted (0-based)
    failures: int
    hint_triggered: bool = False


class CoopSymbolPuzzle:
    """
    Board has num_pairs*2 target symbols plus filler symbols.
    Player 1 cycles highlight with LEFT/RIGHT arrow keys; presses ENTER to
    confirm. Two confirmations = one pair attempt.
    Player 2 reads pair clues in order.
    """

    def __init__(self, board, pairs, pair_clues, hint_after=HINT_AFTER_FAILURES):
        """
        board      : list of symbol names shown to Player 1
        pairs      : list of (sym_a, sym_b) tuples to match, in order
        pair_clues : list of (clue_a, clue_b) string tuples for Player 2
        """
        self.puzzle_type = COOP_SYMBOL
        self.board = list(board)
        self.pairs = [tuple(p) for p in pairs]
        self.pair_clues = [tuple(c) for c in pair_clues]
        self.hint_after = hint_after

        self.current_pair_index = 0
        self.selection = []             # list of board-position indices (0 or 1 items)
        self.highlight = 0             # currently highlighted board position
        self.failures = 0
        self.solved = False
        self.completed_positions = []  # board positions already correctly paired

    @property
    def attempt(self):
        return self.failures + 1

    @property
    def hint_ready(self):
        return self.failures >= self.hint_after

    def move_highlight(self, direction):
        """Cycle highlight left or right, skipping completed positions."""
        n = len(self.board)
        step = 1 if direction == "right" else -1
        new_hl = (self.highlight + step) % n
        # Skip already-completed positions if possible
        attempts = 0
        while new_hl in self.completed_positions and attempts < n:
            new_hl = (new_hl + step) % n
            attempts += 1
        self.highlight = new_hl

    def confirm_selection(self):
        """Player 1 confirms the currently highlighted cell. Returns PairResult."""
        if self.solved:
            return PairResult("ignored", ("", ""), ("", ""),
                              self.current_pair_index, self.failures)
        pos = self.highlight
        # Ignore already-completed or already-selected positions
        if pos in self.completed_positions or pos in self.selection:
            return PairResult("ignored", ("", ""), ("", ""),
                              self.current_pair_index, self.failures)

        self.selection.append(pos)
        expected = tuple(self.pairs[self.current_pair_index])

        if len(self.selection) == 1:
            # First pick acknowledged
            return PairResult("first_pick",
                              (self.board[pos], ""), expected,
                              self.current_pair_index, self.failures)

        # Second pick: validate
        a_pos, b_pos = self.selection
        sym_a, sym_b = self.board[a_pos], self.board[b_pos]
        selected = (sym_a, sym_b)
        pair_idx = self.current_pair_index

        if set(selected) == set(expected):
            self.completed_positions.extend([a_pos, b_pos])
            self.selection = []
            self.current_pair_index += 1
            if self.current_pair_index >= len(self.pairs):
                self.solved = True
                return PairResult("complete", selected, expected,
                                  pair_idx, self.failures)
            return PairResult("correct_pair", selected, expected,
                              pair_idx, self.failures)

        # Wrong pair
        self.failures += 1
        self.selection = []
        triggered = (self.failures == self.hint_after)
        return PairResult("wrong_pair", selected, expected,
                          pair_idx, self.failures, hint_triggered=triggered)

    def hint_text(self):
        if self.solved or self.current_pair_index >= len(self.pairs):
            return ""
        i = self.current_pair_index
        ca, cb = self.pair_clues[i]
        return (f"Pair {i + 1}: find '{ca}' and '{cb}'. "
                "Player 2: describe the shapes without naming them directly.")


# ===========================================================================
# Factory functions
# ===========================================================================

def make_color_puzzle(length=4, rng=None, fixed_sequence=None):
    rng = rng or random.Random()
    if fixed_sequence is not None:
        solution = list(fixed_sequence)
    else:
        solution = rng.sample(COLORS, min(length, len(COLORS)))
        while solution == FIXED_LEVEL_1_COLORS:
            rng.shuffle(solution)
    return SequencePuzzle(COLOR_ORDER, COLORS, solution)


def _bfs_path(rows, cols, walls, start, goal):
    """BFS shortest path. Returns list of (row,col) or None if unreachable."""
    q = deque([(start, [start])])
    visited = {start}
    while q:
        pos, path = q.popleft()
        if pos == goal:
            return path
        r, c = pos
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nxt = (r + dr, c + dc)
            nr, nc = nxt
            if (0 <= nr < rows and 0 <= nc < cols
                    and nxt not in walls and nxt not in visited):
                visited.add(nxt)
                q.append((nxt, path + [nxt]))
    return None


def _path_to_waypoints(path):
    waypoints = []
    for i in range(1, len(path)):
        dr = path[i][0] - path[i - 1][0]
        dc = path[i][1] - path[i - 1][1]
        if dr == -1:   waypoints.append("up")
        elif dr == 1:  waypoints.append("down")
        elif dc == -1: waypoints.append("left")
        else:          waypoints.append("right")
    return waypoints


def make_grid_puzzle(rows=5, cols=7, wall_count=6, rng=None):
    """Generate a solvable grid puzzle with random walls via BFS validation."""
    rng = rng or random.Random()
    all_cells = [(r, c) for r in range(rows) for c in range(cols)]
    start, goal = (0, 0), (rows - 1, cols - 1)
    for _ in range(200):
        candidates = [cell for cell in all_cells
                      if cell != start and cell != goal]
        walls = set(rng.sample(candidates, min(wall_count, len(candidates))))
        path = _bfs_path(rows, cols, walls, start, goal)
        if path and len(path) >= 4:
            return GridPuzzle(rows, cols, walls, start, goal,
                              _path_to_waypoints(path))
    # Fallback: no walls
    walls = set()
    path = _bfs_path(rows, cols, walls, start, goal)
    return GridPuzzle(rows, cols, walls, start, goal, _path_to_waypoints(path))


def make_coop_symbol_puzzle(num_pairs=2, filler_count=2, rng=None):
    """
    Build a CoopSymbolPuzzle with num_pairs matching pairs and filler_count
    extra distractor symbols on the board.
    """
    rng = rng or random.Random()
    pool = list(SYMBOLS)
    rng.shuffle(pool)
    pair_syms = pool[:num_pairs]
    board = []
    pairs = []
    pair_clues = []
    for sym in pair_syms:
        board.extend([sym, sym])
        pairs.append((sym, sym))
        clue = SYMBOL_CLUES.get(sym, sym)
        pair_clues.append((clue, clue))
    fillers = [s for s in pool if s not in pair_syms][:filler_count]
    board.extend(fillers)
    rng.shuffle(board)
    return CoopSymbolPuzzle(board, pairs, pair_clues)


# Legacy factory (kept so old imports still work)
def make_symbol_puzzle(length=3, rng=None):
    rng = rng or random.Random()
    options = rng.sample(SYMBOLS[:4], 4)
    solution = rng.sample(options, min(length, 4))
    return SequencePuzzle(SYMBOL_MATCH, options, solution)
