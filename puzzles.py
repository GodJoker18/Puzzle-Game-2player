"""Puzzle logic and validation. No Pygame in this file, so it is easy to test.

Both puzzle types work the same way: the Operator must press the options in a
hidden order that only the Clue Reader can see. A wrong press counts as a
failed attempt and resets the sequence. The two types differ only in what the
options are and how the clue is worded.
"""

import random
from dataclasses import dataclass

COLOR_ORDER = "color_order"
SYMBOL_MATCH = "symbol_match"

COLORS = ["red", "blue", "green", "yellow"]            # keys 1-4 in this order
FIXED_LEVEL_1_COLORS = ["blue", "red", "yellow", "green"]
SYMBOLS = ["circle", "square", "triangle", "star"]

# What the Clue Reader sees for a symbol (the Operator sees the drawn shape).
SYMBOL_CLUES = {
    "circle": "Round, no corners",
    "square": "Four equal sides",
    "triangle": "Three corners",
    "star": "Five points",
}

HINT_AFTER_FAILURES = 3


@dataclass
class SelectResult:
    """What happened when the Operator pressed one option."""
    outcome: str          # "correct_step", "complete", "incorrect" or "ignored"
    selected: str         # option name pressed ("" if ignored)
    expected: str         # option name that was required ("" if none)
    attempt: int          # attempt number this press belonged to (1-based)
    hint_triggered: bool = False   # True only on the press that unlocks the hint


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
            return SYMBOL_CLUES[name]
        return name.title()

    def hint_text(self):
        """Hint for the Clue Reader: the next item still needed."""
        if self.solved:
            return ""
        name = self.solution[self.progress]
        step = self.progress + 1
        if self.puzzle_type == SYMBOL_MATCH:
            return (f"Step {step} is the {name} ({SYMBOL_CLUES[name].lower()}). "
                    "Try describing its shape in different words.")
        return (f"Step {step} is {name.upper()}. "
                "Start your sequence from the beginning each time.")


def make_color_puzzle(length=4, rng=None, fixed_sequence=None):
    rng = rng or random.Random()
    if fixed_sequence is not None:
        solution = list(fixed_sequence)
    else:
        solution = rng.sample(COLORS, min(length, len(COLORS)))
        while solution == FIXED_LEVEL_1_COLORS:       # avoid repeating level 1
            rng.shuffle(solution)
    return SequencePuzzle(COLOR_ORDER, COLORS, solution)


def make_symbol_puzzle(length=3, rng=None):
    rng = rng or random.Random()
    options = rng.sample(SYMBOLS, len(SYMBOLS))       # shuffled key layout
    solution = rng.sample(options, min(length, len(options)))
    return SequencePuzzle(SYMBOL_MATCH, options, solution)
