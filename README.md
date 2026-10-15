# Communication-Aware Co-op Puzzle Game

A local 2-player cooperative puzzle game (Python 3 + Pygame). Both players share
one keyboard and one 1280x720 window, but see **different information**, so they
must talk to solve each puzzle.

- **Player 1 - Puzzle Operator (left half):** sees the buttons and presses keys 1-4.
- **Player 2 - Clue Reader (right half):** sees the answer clues and guides Player 1.

A shared monitor cannot stop players from looking at each other's half. The game
relies on players agreeing not to peek.

## Setup and run

```
pip install -r requirements.txt     # installs pygame
python main.py
```

If `pip` points at a different Python, use `python3 -m pip install -r requirements.txt`.
Run `main.py` from any folder; the log is always saved next to the code.

## Controls

| Key | Action |
|-----|--------|
| ENTER | Start the game / go to the next level |
| 1, 2, 3, 4 (or keypad 1-4) | Player 1 presses the matching button |
| SPACE | Play again (only on the victory screen) |
| ESC | Quit |

Any other key is ignored.

## How the game works

- 6 levels alternate between **Color Order** and **Symbol Matching**.
- **Color Order:** Player 2 sees a color sequence (level 1 is Blue, Red, Yellow,
  Green; later color levels are random). Player 1 must press the colors in that order.
- **Symbol Matching:** Player 1 sees four shapes (layout shuffled each level).
  Player 2 sees only *descriptions* ("Three corners") in the required order, so
  Player 1 must match shapes to the words they hear.
- A wrong press counts as a mistake and **resets the sequence**.
- After **3 mistakes** a hint appears on Player 2's side.
- The timer is **soft**: when it hits zero the game shows "Overtime", logs a
  `timeout` once, and lets players keep going with no penalty.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Starts Pygame, runs the main loop |
| `game.py` | Game state, levels, timer, key handling, drawing |
| `puzzles.py` | Puzzle rules and validation (no Pygame) |
| `logger.py` | CSV event logging |
| `tests/` | `python -m unittest discover -s tests -v` |

Change levels, time limits, or lengths in the `LEVELS` list in `game.py`; the hint
threshold is `HINT_AFTER_FAILURES` in `puzzles.py`.

## Log file

Events are appended to `logs/events.csv` (created automatically, never overwritten).
Columns: `timestamp` (UTC), `session_id`, `level`, `puzzle_type`, `action`,
`attempt`, `elapsed_s` (seconds since the current puzzle started; 0 on session
rows), `outcome`, `detail`.

Actions: `session_start`, `level_start`, `button_press`, `incorrect_attempt`,
`hint_shown`, `timeout`, `puzzle_complete`, `game_complete`, `restart`, `session_end`.
`level_start` stores the solution in `detail` for later analysis.

**Measurement caution:** these logs record behavior (presses, mistakes, hints,
timing). They do not capture what players said. Treat any communication measure
derived from them as a behavioral proxy, not a direct measure of verbal
communication. Studying actual speech would need consented audio/transcripts or
human annotation.

## Not included yet

No dynamic difficulty adjustment (DDA), speech recognition, networking, or extra
puzzle types. Puzzle outcomes, attempts, and timing are already logged in a
consistent format, so rule-based DDA can be added later.
