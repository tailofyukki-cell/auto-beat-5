from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "capture_data")

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note, NoteType

app = AutoBeatApp()
chart = Chart(
    version=1,
    music_hash="hold_endcap_capture" * 4,
    difficulty=Difficulty.NORMAL,
    seed=1,
    song_duration=8.0,
    notes=[
        Note(1.5, 2, NoteType.HOLD, 3.2),
        Note(3.9, 1),
        Note(4.4, 3),
    ],
)
app.chart = chart
app.session = GameSession(chart, JudgmentWindows())
app.screen = "game"
# 始点は画面外、終端だけが近づいている状態を可視化する。
app.audio = SimpleNamespace(time=2.9, paused=False)
app.draw()
output = ROOT / "artifacts" / "hold_endcap.png"
output.parent.mkdir(parents=True, exist_ok=True)
pygame.image.save(app.surface, output)
pygame.quit()
print(output)
