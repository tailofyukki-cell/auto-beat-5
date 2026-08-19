from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from models import Chart, Difficulty, Note
from persistence import record_play


def make_result(score: int, accuracy: float, combo: int, rank: str) -> dict[str, object]:
    return {
        "score": score,
        "accuracy": accuracy,
        "max_combo": combo,
        "rank": rank,
        "judgments": {"PERFECT": 100, "GREAT": 0, "GOOD": 0, "MISS": 0},
        "chart_hash": "r" * 64 + ":normal",
    }


def main() -> None:
    app = AutoBeatApp()
    app.chart = Chart(1, "r" * 64, Difficulty.NORMAL, 1, 120.0, notes=[Note(1.2, 0)])
    chart_key = f"{app.chart.music_hash}:{app.chart.difficulty.value}"
    for score, accuracy, combo, rank in (
        (98500, 98.72, 426, "S"),
        (94200, 96.18, 389, "S"),
        (89800, 92.40, 321, "A"),
        (82100, 88.06, 254, "A"),
        (75400, 81.32, 201, "B"),
    ):
        record_play(app.paths, app.profile, chart_key=chart_key, result=make_result(score, accuracy, combo, rank))
    app.open_ranking()
    app.draw()
    output = ROOT / "artifacts" / "ranking.png"
    output.parent.mkdir(exist_ok=True)
    pygame.image.save(app.surface, output)
    pygame.quit()


if __name__ == "__main__":
    main()
