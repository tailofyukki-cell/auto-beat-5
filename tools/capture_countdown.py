from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "capture_data")

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note

app = AutoBeatApp()
chart = Chart(
    version=1,
    music_hash="countdown_capture" * 4,
    difficulty=Difficulty.NORMAL,
    seed=1,
    song_duration=12.0,
    notes=[Note(1.2, 2), Note(1.8, 1), Note(2.4, 3)],
)
app.chart = chart
app.session = GameSession(chart, JudgmentWindows())
app.screen = "game"
app.countdown_started_at = time.perf_counter()
app.draw()
output = ROOT / "artifacts" / "countdown.png"
output.parent.mkdir(parents=True, exist_ok=True)
pygame.image.save(app.surface, output)
pygame.quit()
print(output)
