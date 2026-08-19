from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        os.environ["AUTOBEAT_DATA_DIR"] = temporary_directory
        app = AutoBeatApp()
        app.chart = Chart(
            1,
            "v" * 64,
            Difficulty.NORMAL,
            1,
            8.0,
            notes=[
                Note(0.10, 0), Note(0.30, 1), Note(0.48, 2),
                Note(0.66, 3), Note(0.82, 4), Note(0.96, 2),
            ],
        )
        app.session = GameSession(app.chart, JudgmentWindows())
        app.screen = "game"
        app.draw()
        output = PROJECT_ROOT / "artifacts" / "vertical_playfield.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(app.surface, str(output))
        app.running = False
        pygame.quit()
        print(output)


if __name__ == "__main__":
    main()
