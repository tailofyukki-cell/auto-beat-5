from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
# 視覚確認用の疑似ライブラリーを実プレイのAppDataへ残さない。
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "select_rankings_capture_data")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from persistence import record_play


def result(score: int, accuracy: float, combo: int, rank: str) -> dict[str, object]:
    return {
        "score": score,
        "accuracy": accuracy,
        "max_combo": combo,
        "rank": rank,
        "judgments": {"PERFECT": 100, "GREAT": 0, "GOOD": 0, "MISS": 0},
        "chart_hash": "",
    }


def main() -> None:
    app = AutoBeatApp()
    songs = [
        ("a" * 64, "aurora_drive.mp3", 128.0, 184.5, [("beginner", 63400, 92.10, 124, "A"), ("easy", 78100, 95.22, 176, "S"), ("normal", 86500, 91.08, 212, "A")]),
        ("b" * 64, "city_lights.ogg", 142.0, 201.0, [("easy", 75200, 88.60, 144, "A"), ("normal", 89300, 93.75, 256, "A")]),
        ("c" * 64, "midnight_loop.wav", 110.0, 156.3, []),
        ("d" * 64, "summer_echo.flac", 96.0, 245.6, [("beginner", 99500, 99.12, 332, "S"), ("easy", 97200, 97.30, 287, "S"), ("normal", 81400, 86.15, 179, "A")]),
    ]
    app.profile["recent_songs"] = []
    for digest, name, bpm, duration, scores in songs:
        app.profile["recent_songs"].append({"music_hash": digest, "source_path": f"C:/music/{name}", "bpm": bpm, "duration": duration})
        for difficulty, score, accuracy, combo, rank in scores:
            record_play(app.paths, app.profile, chart_key=f"{digest}:{difficulty}", result=result(score, accuracy, combo, rank))
    app.set_screen("select")
    app.draw()
    output = ROOT / "artifacts" / "select_rankings.png"
    output.parent.mkdir(exist_ok=True)
    pygame.image.save(app.surface, output)
    pygame.quit()


if __name__ == "__main__":
    main()
