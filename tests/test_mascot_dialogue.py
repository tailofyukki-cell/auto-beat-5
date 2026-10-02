from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mascot_dialogue import DEFAULT_RANK_LINES, MASCOT_RANK_LINES, RANKS, mascot_result_line


EXPECTED_MASCOTS = {"rhythm", "cute", "sexy2", "cool", "powerful", "sexy", "pixy", "neon", "dj"}


def test_every_bundled_mascot_has_dialogue_for_every_rank() -> None:
    assert set(MASCOT_RANK_LINES) == EXPECTED_MASCOTS
    for mascot_id in EXPECTED_MASCOTS:
        assert set(MASCOT_RANK_LINES[mascot_id]) == set(RANKS)
        assert all(mascot_result_line(mascot_id, rank).strip() for rank in RANKS)


def test_each_mascot_uses_a_distinct_line_for_each_rank() -> None:
    for mascot_id in EXPECTED_MASCOTS:
        lines = [mascot_result_line(mascot_id, rank) for rank in RANKS]
        assert len(set(lines)) == len(RANKS)


def test_unknown_dlc_mascot_uses_rank_specific_fallback() -> None:
    assert mascot_result_line("future-dlc", "A") == DEFAULT_RANK_LINES["A"]
    assert mascot_result_line("future-dlc", "S+") == DEFAULT_RANK_LINES["S+"]


def test_unknown_rank_falls_back_to_d_rank() -> None:
    assert mascot_result_line("rhythm", "unknown") == MASCOT_RANK_LINES["rhythm"]["D"]
