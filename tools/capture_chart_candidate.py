from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "artifacts" / "candidate_capture_data"
shutil.rmtree(DATA_DIR, ignore_errors=True)
os.environ["AUTOBEAT_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Difficulty


def fixture_analysis() -> AnalysisResult:
    return AnalysisResult(
        music_hash="p" * 64,
        source_path="fixture.wav",
        duration=12.0,
        sample_rate=22050,
        bpm=128.0,
        beats=[index * 0.46875 for index in range(28)],
        onsets=[1.3, 1.8, 2.3, 2.8, 3.3, 3.8, 4.3, 4.8],
        onset_strengths=[0.9, 0.75, 0.88, 0.71, 0.94, 0.8, 0.85, 0.73],
        band_energy=[[0.7, 0.2, 0.1, 0.55, 0.42]] * 8,
        percussive_strengths=[0.35, 0.45, 0.38, 0.42, 0.37, 0.48, 0.41, 0.44],
        sustained_segments=[(3.3, 4.5, 1)],
    )


def main() -> None:
    app = AutoBeatApp()
    app.analysis = fixture_analysis()
    app.song_path = Path(app.analysis.source_path)
    app.select_chart(Difficulty.NORMAL)
    app.regenerate_chart()
    app.draw()
    pygame.image.save(app.surface, ROOT / "artifacts" / "chart_candidate_summary.png")

    app.session = GameSession(app.chart, JudgmentWindows.from_ms(app.settings["judgment_windows_ms"]))
    app.finish_game()
    app.draw()
    pygame.image.save(app.surface, ROOT / "artifacts" / "chart_candidate_result.png")
    pygame.quit()


if __name__ == "__main__":
    main()
