# Project Context — Communication-Aware Cooperative Puzzle Game

## Goal
Build a local 2-player cooperative puzzle game in Python 3 + Pygame. The players share one game but receive different information, so they must communicate verbally to solve each puzzle. Long-term research goal: compare communication-aware Dynamic Difficulty Adjustment (DDA) with performance-only DDA.

## Current prototype
The existing single-file prototype reportedly has a split screen, one color-order puzzle, win/lose detection, timestamped CSV action logging, and SPACE restart. Inspect the actual files before assuming these features work or rewriting anything.

## Immediate MVP
- Preserve and stabilize the existing color-order puzzle.
- Add a level/round manager.
- Add a soft per-puzzle timer.
- Show a hint after a configurable number of failures.
- Add at most one simple second puzzle type initially (prefer symbol matching).
- Keep timestamped CSV logging consistent across puzzle types.
- Refactor toward `main.py`, `game.py`, `puzzles.py`, and `logger.py` only when useful; keep startup simple.

## Constraints
Python 3, Pygame, simple shapes, no networking, no external physics engine, no ML frameworks, no paid assets, beginner-friendly readable code. Avoid overengineering. Do not implement every puzzle type or DDA in one pass.

## Research and measurement caution
Later DDA should begin with transparent rule-based logic. Compare fixed difficulty, performance-only DDA, and communication-aware DDA. Gameplay logs can measure actions, attempts, errors, hint requests, and response-time proxies. They cannot directly reveal what players said. Verbal redundancy/alignment requires consented audio/transcripts or human annotation; otherwise label metrics as behavioral proxies. Do not claim that a proxy is a direct measure of verbal communication.

## Agent workflow
1. Inspect the repository and report its current structure and actual behavior.
2. Make minimal targeted changes; preserve working functionality.
3. Implement one small milestone per task; do not rewrite whole files unnecessarily.
4. Run available checks and launch the game where possible. State clearly what was and was not tested.
5. Avoid printing entire files in chat. Make edits directly and summarize changed files, tests, known issues, and the next best task.
6. Do not add DDA, speech-to-text, or extra puzzle types unless explicitly requested.
