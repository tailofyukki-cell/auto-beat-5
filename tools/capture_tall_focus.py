from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "artifacts" / "tall_focus_capture_data"
shutil.rmtree(DATA_DIR, ignore_errors=True)
os.environ["AUTOBEAT_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note, NoteType


def render(app: AutoBeatApp, mode: str, output: str) -> None:
    app.settings["playfield_mode"] = mode
    app.draw()
    pygame.image.save(app.surface, ROOT / "artifacts" / output)


def main() -> None:
    app = AutoBeatApp()
    chart = Chart(
        1,
        "tall_focus_capture" * 4,
        Difficulty.NORMAL,
        1,
        7.0,
        notes=[
            Note(2.8, 0),
            Note(3.25, 1, NoteType.HOLD, 4.45),
            Note(3.8, 2),
            Note(4.35, 3),
            Note(4.9, 4),
        ],
    )
    app.chart = chart
    app.session = GameSession(chart, JudgmentWindows())
    app.audio = SimpleNamespace(time=2.2, paused=False, finished=False)
    app.screen = "game"
    render(app, "standard", "tall_focus_standard.png")
    render(app, "tall", "tall_focus_tall.png")
    pygame.quit()


if __name__ == "__main__":
    main()
