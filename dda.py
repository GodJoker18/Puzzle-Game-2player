"""Dynamic Difficulty Adjustment (DDA) for cooperative puzzle game.

Supports three research comparison modes:
  - STATIC: baseline fixed difficulty (no dynamic changes)
  - PERFORMANCE_ONLY: adapts using puzzle time, mistakes, attempts, and hints
  - COMMUNICATION_AWARE: adapts using performance metrics PLUS communication-related
    behavioral indicators (clue response latency, repeated clue frequency).

Research and measurement caution:
  The communication markers (C = clue communicated, R = clue repeated) and the
  resulting response latency metrics are manually marked behavioral proxies, not
  objective or direct measurements of spoken conversation. Do not claim that
  these behavioral proxies are direct measures of verbal communication.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from puzzles import COLOR_ORDER, GRID_PATH, COOP_SYMBOL

MODE_STATIC = "static"
MODE_PERFORMANCE_ONLY = "performance_only"
MODE_COMMUNICATION_AWARE = "communication_aware"

VALID_MODES = [MODE_STATIC, MODE_PERFORMANCE_ONLY, MODE_COMMUNICATION_AWARE]

# ---------------------------------------------------------------------------
# Difficulty Tiers (strictly bounded, solvable parameter sets)
# ---------------------------------------------------------------------------

COLOR_TIERS: List[Dict] = [
    {"type": COLOR_ORDER, "length": 3, "time_limit": 65},  # Tier 0 (Easier)
    {"type": COLOR_ORDER, "length": 4, "time_limit": 60},  # Tier 1 (Baseline L1)
    {"type": COLOR_ORDER, "length": 4, "time_limit": 50},  # Tier 2 (Baseline L4)
    {"type": COLOR_ORDER, "length": 4, "time_limit": 40},  # Tier 3 (Fast / Hard)
]

GRID_TIERS: List[Dict] = [
    {"type": GRID_PATH, "rows": 4, "cols": 4, "walls": 2, "time_limit": 100},  # Tier 0 (Easier)
    {"type": GRID_PATH, "rows": 4, "cols": 5, "walls": 4, "time_limit": 90},   # Tier 1 (Baseline L2)
    {"type": GRID_PATH, "rows": 5, "cols": 6, "walls": 5, "time_limit": 90},   # Tier 2 (Medium+)
    {"type": GRID_PATH, "rows": 5, "cols": 7, "walls": 7, "time_limit": 90},   # Tier 3 (Baseline L5)
    {"type": GRID_PATH, "rows": 6, "cols": 8, "walls": 9, "time_limit": 75},   # Tier 4 (Expert)
]

SYMBOL_TIERS: List[Dict] = [
    {"type": COOP_SYMBOL, "pairs": 2, "fillers": 1, "time_limit": 90},  # Tier 0 (Easier)
    {"type": COOP_SYMBOL, "pairs": 2, "fillers": 2, "time_limit": 75},  # Tier 1 (Baseline L3)
    {"type": COOP_SYMBOL, "pairs": 3, "fillers": 2, "time_limit": 75},  # Tier 2 (Medium+)
    {"type": COOP_SYMBOL, "pairs": 3, "fillers": 3, "time_limit": 75},  # Tier 3 (Baseline L6)
]


def get_tiers_for_type(puzzle_type: str) -> List[Dict]:
    """Return the ordered list of difficulty tiers for a given puzzle type."""
    if puzzle_type == COLOR_ORDER:
        return COLOR_TIERS
    elif puzzle_type == GRID_PATH:
        return GRID_TIERS
    elif puzzle_type == COOP_SYMBOL:
        return SYMBOL_TIERS
    return []


def find_tier_index(puzzle_type: str, config: Dict) -> int:
    """Match a level config dict to the closest tier index (default 0)."""
    tiers = get_tiers_for_type(puzzle_type)
    if not tiers:
        return 0

    if puzzle_type == COLOR_ORDER:
        length = config.get("length", 4)
        tl = config.get("time_limit", 60)
        for i, t in enumerate(tiers):
            if t["length"] == length and abs(t["time_limit"] - tl) <= 5:
                return i
        return 1 if length == 4 else 0

    elif puzzle_type == GRID_PATH:
        rows = config.get("rows", 4)
        cols = config.get("cols", 5)
        for i, t in enumerate(tiers):
            if t["rows"] == rows and t["cols"] == cols:
                return i
        return 1

    elif puzzle_type == COOP_SYMBOL:
        pairs = config.get("pairs", 2)
        fillers = config.get("fillers", 2)
        for i, t in enumerate(tiers):
            if t["pairs"] == pairs and t["fillers"] == fillers:
                return i
        return 1

    return 0


# ---------------------------------------------------------------------------
# Metrics and DDA Result Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PuzzleMetrics:
    """Behavioral and performance measurements recorded during one puzzle round."""
    puzzle_type: str
    elapsed: float
    time_limit: float
    failures: int
    hint_triggered: bool
    timed_out: bool
    clue_count: int = 0
    repeat_count: int = 0
    latencies: List[float] = field(default_factory=list)


@dataclass
class DDAResult:
    """Outcome of a DDA evaluation step between levels."""
    mode: str
    perf_score: float
    comm_score: float
    combined_score: float
    adjustment: int          # -1 (decrease), 0 (maintain), +1 (increase)
    reason: str
    prev_tier: int
    new_tier: int
    adapted_config: Dict


# ---------------------------------------------------------------------------
# Score Calculations (Transparent Rule-Based Functions)
# ---------------------------------------------------------------------------

def compute_perf_score(metrics: PuzzleMetrics) -> float:
    """Calculate normalized performance score in [0.0, 1.0].

    Based on:
      - Completion time relative to time limit (time efficiency)
      - Mistakes / failed moves count (error penalty)
      - Hint triggered penalty
      - Soft timeout penalty
    """
    time_limit = max(1.0, metrics.time_limit)
    time_ratio = metrics.elapsed / time_limit

    # Time score: 1.0 if finished in <= 40% of time limit, 0.0 if >= 100%
    if time_ratio <= 0.4:
        time_score = 1.0
    elif time_ratio >= 1.0:
        time_score = 0.0
    else:
        time_score = (1.0 - time_ratio) / 0.6

    # Error score: 0 failures = 1.0; 4+ failures = 0.0
    error_penalty = min(1.0, metrics.failures * 0.25)
    mistake_score = 1.0 - error_penalty

    # Deductions for hints and timeouts
    hint_deduction = 0.25 if metrics.hint_triggered else 0.0
    timeout_deduction = 0.20 if metrics.timed_out else 0.0

    raw = 0.5 * time_score + 0.5 * mistake_score - hint_deduction - timeout_deduction
    return max(0.0, min(1.0, round(raw, 3)))


def compute_comm_score(metrics: PuzzleMetrics) -> float:
    """Calculate normalized communication proxy score in [0.0, 1.0].

    Based on:
      - Mean response latency: time elapsed between Player 2 marking a clue (C)
        and Player 1's next action (button press, grid move, or pair confirm).
      - Clue repetition frequency: count of rephrased / repeated clues (R).

    Note: If no communication markers were recorded during this puzzle, returns
    0.5 (neutral fallback), allowing the controller to rely on performance.
    """
    if metrics.clue_count == 0 and metrics.repeat_count == 0:
        return 0.5  # Neutral fallback when markers were not used

    # 1. Latency score:
    # Target coordination response window is ~1.0s to 3.0s.
    # Latency <= 2.0s -> 1.0; Latency >= 6.0s -> 0.0
    if metrics.latencies:
        avg_latency = sum(metrics.latencies) / len(metrics.latencies)
        if avg_latency <= 2.0:
            lat_score = 1.0
        elif avg_latency >= 6.0:
            lat_score = 0.0
        else:
            lat_score = (6.0 - avg_latency) / 4.0
    else:
        lat_score = 0.5

    # 2. Repetition score:
    # Proportion of clues that needed repetition or clarification.
    # 0 repeats -> 1.0; repeats >= clues -> 0.0
    repeat_ratio = metrics.repeat_count / max(1, metrics.clue_count)
    if repeat_ratio == 0:
        rep_score = 1.0
    elif repeat_ratio >= 1.0:
        rep_score = 0.0
    else:
        rep_score = 1.0 - repeat_ratio

    raw = 0.6 * lat_score + 0.4 * rep_score
    return max(0.0, min(1.0, round(raw, 3)))


# ---------------------------------------------------------------------------
# DDA Controller
# ---------------------------------------------------------------------------

class DDAController:
    """Manages dynamic difficulty adjustment across puzzle transitions."""

    def __init__(self, mode: str = MODE_STATIC):
        self.mode = mode if mode in VALID_MODES else MODE_STATIC

    def set_mode(self, mode: str) -> None:
        if mode in VALID_MODES:
            self.mode = mode
        else:
            raise ValueError(f"Invalid DDA mode: {mode}. Choose from {VALID_MODES}")

    def cycle_mode(self) -> str:
        """Cycle to the next mode (useful for toggling in the start screen)."""
        idx = (VALID_MODES.index(self.mode) + 1) % len(VALID_MODES)
        self.mode = VALID_MODES[idx]
        return self.mode

    def evaluate(self, metrics: PuzzleMetrics, next_puzzle_type: str,
                 current_next_config: Dict) -> DDAResult:
        """Evaluate the completed puzzle and determine next puzzle's configuration.

        Changes are bounded to at most +/-1 tier per puzzle transition, and every
        adapted configuration is guaranteed solvable.
        """
        tiers = get_tiers_for_type(next_puzzle_type)
        prev_tier = find_tier_index(next_puzzle_type, current_next_config)
        max_tier = len(tiers) - 1 if tiers else 0

        perf_score = compute_perf_score(metrics)
        comm_score = compute_comm_score(metrics)

        # ---------------- Mode 1: STATIC (Baseline / Control) ----------------
        if self.mode == MODE_STATIC:
            adjustment = 0
            reason = "static_mode_fixed_difficulty"
            new_tier = prev_tier
            adapted_config = dict(current_next_config)
            return DDAResult(
                mode=self.mode,
                perf_score=perf_score,
                comm_score=comm_score,
                combined_score=perf_score,
                adjustment=adjustment,
                reason=reason,
                prev_tier=prev_tier,
                new_tier=new_tier,
                adapted_config=adapted_config,
            )

        # ----------- Mode 2: PERFORMANCE_ONLY (Standard DDA) -----------------
        elif self.mode == MODE_PERFORMANCE_ONLY:
            combined_score = perf_score
            if combined_score >= 0.70:
                adjustment = +1
                reason = (f"high_performance (score={combined_score:.2f}, "
                          f"time={metrics.elapsed:.1f}s, mistakes={metrics.failures})")
            elif combined_score <= 0.35:
                adjustment = -1
                reason = (f"low_performance (score={combined_score:.2f}, "
                          f"time={metrics.elapsed:.1f}s, mistakes={metrics.failures})")
            else:
                adjustment = 0
                reason = f"stable_performance (score={combined_score:.2f})"

        # ----------- Mode 3: COMMUNICATION_AWARE (Research Target) -----------
        else:  # MODE_COMMUNICATION_AWARE
            if metrics.clue_count > 0 or metrics.repeat_count > 0:
                combined_score = round(0.6 * perf_score + 0.4 * comm_score, 3)
            else:
                # Graceful fallback when no markers were logged
                combined_score = perf_score

            if combined_score >= 0.70:
                adjustment = +1
                reason = (f"effective_coordination (perf={perf_score:.2f}, "
                          f"comm={comm_score:.2f}, repeats={metrics.repeat_count})")
            elif combined_score <= 0.35:
                adjustment = -1
                reason = (f"coordination_friction (perf={perf_score:.2f}, "
                          f"comm={comm_score:.2f}, repeats={metrics.repeat_count})")
            else:
                adjustment = 0
                reason = f"stable_coordination (score={combined_score:.2f})"

        # Apply bounded step (+1, 0, or -1)
        new_tier = max(0, min(max_tier, prev_tier + adjustment))

        # Build adapted config from the tier template while preserving fixed flags
        if tiers:
            base_template = dict(tiers[new_tier])
            # Preserve special flags like 'fixed' if present in the target level
            if current_next_config.get("fixed"):
                base_template["fixed"] = True
            adapted_config = base_template
        else:
            adapted_config = dict(current_next_config)

        return DDAResult(
            mode=self.mode,
            perf_score=perf_score,
            comm_score=comm_score,
            combined_score=combined_score,
            adjustment=adjustment,
            reason=reason,
            prev_tier=prev_tier,
            new_tier=new_tier,
            adapted_config=adapted_config,
        )
