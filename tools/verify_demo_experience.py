"""体験版の実デモ曲が解析なしでプレイ開始まで進めることを検証する。"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "demo_experience_test_data")
os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = str(ROOT / "demo_songs")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from models import Difficulty


def main() -> None:
    data_dir = Path(os.environ["AUTOBEAT_DATA_DIR"])
    shutil.rmtree(data_dir, ignore_errors=True)
    app = AutoBeatApp()
    try:
        demos = app.demo_song_files()
        if len(demos) != 3:
            raise RuntimeError(f"Expected 3 demo songs, found {len(demos)}")
        app.screen = "select"
        app.draw()
        for demo in demos:
            app.load_demo_song(demo)
            if app.screen != "difficulty" or app.analysis is None:
                raise RuntimeError(f"Demo analysis cache did not load: {demo.name}")
            app.select_chart(Difficulty.BEGINNER)
            if app.screen != "chart_summary" or app.chart is None or not app.chart.notes:
                raise RuntimeError(f"Demo chart did not load: {demo.name}")
            app.start_game()
            if app.screen != "game" or not app.countdown_active:
                raise RuntimeError(f"Demo did not reach countdown: {demo.name}")
            app.countdown_started_at = time.perf_counter() - 4.0
            app.update_game()
            if app.screen != "game":
                raise RuntimeError(f"Demo did not start after countdown: {demo.name}")
            app.audio.stop()
            app.return_to_song_select()
            print(f"PASS: {demo.name} | {app.analysis.bpm:.3f} BPM | {len(app.chart.notes) if app.chart else 0} notes")
    finally:
        pygame.quit()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
