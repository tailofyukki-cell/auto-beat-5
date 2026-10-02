from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "manual_userdata")
sys.path.insert(0, str(ROOT / "src"))

import pygame

from app import AutoBeatApp, JudgmentFeedback, JudgmentLogEntry
from chart_summary import build_chart_summary
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Judgment, Note, NoteType

OUTPUT = ROOT / "docs" / "user_manual" / "screenshots"


def save(app: AutoBeatApp, name: str) -> None:
    app.draw()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pygame.image.save(app.surface, str(OUTPUT / f"{name}.png"))


class ManualAudio:
    def __init__(self, current: float, paused: bool = False) -> None:
        self.time = current
        self.paused = paused
        self.finished = False

    def stop(self) -> None:
        self.finished = True


with tempfile.TemporaryDirectory() as directory:
    os.environ["AUTOBEAT_DATA_DIR"] = directory
    app = AutoBeatApp()
    app.error = None
    app.message = ""

    analysis = AnalysisResult(
        music_hash="m" * 64,
        source_path=str(ROOT / "demo_songs" / "ここから始まる～夜明けの光～.wav"),
        duration=118.0,
        sample_rate=44100,
        bpm=128.0,
        beats=[index * 0.46875 for index in range(260)],
        onsets=[0.8, 1.15, 1.5, 1.85, 2.25, 2.75, 3.05, 3.45],
        onset_strengths=[0.85, 0.52, 0.95, 0.6, 0.9, 0.7, 0.88, 0.65],
        band_energy=[
            [0.25, 0.72, 0.42, 0.9, 0.35],
            [0.48, 0.35, 0.82, 0.55, 0.75],
            [0.18, 0.9, 0.52, 0.64, 0.46],
            [0.74, 0.32, 0.68, 0.41, 0.86],
        ],
        percussive_strengths=[0.8, 0.5, 0.9, 0.62, 0.86, 0.7, 0.82, 0.66],
        sustained_segments=[(1.2, 2.2), (3.1, 4.2)],
    )
    notes = [
        Note(1.05, 0),
        Note(1.45, 2),
        Note(1.75, 3),
        Note(2.10, 1, kind=NoteType.HOLD, end_time=3.35),
        Note(2.45, 4),
        Note(2.90, 0),
        Note(3.35, 3, kind=NoteType.HOLD, end_time=4.45),
        Note(3.78, 2),
        Note(4.20, 1),
        Note(4.65, 4),
    ]
    chart = Chart(1, analysis.music_hash, Difficulty.EASY, 2, analysis.duration, notes=notes)

    reward_path = app.paths.rewards / "manual_reward.png"
    reward_path.parent.mkdir(parents=True, exist_ok=True)
    reward_image = pygame.Surface((640, 360), pygame.SRCALPHA)
    reward_image.fill((16, 28, 54, 255))
    pygame.draw.circle(reward_image, (0, 210, 255, 255), (250, 180), 78)
    pygame.draw.circle(reward_image, (255, 214, 61, 255), (390, 178), 96, 10)
    pygame.draw.rect(reward_image, (236, 99, 161, 255), pygame.Rect(190, 245, 260, 26), border_radius=13)
    pygame.image.save(reward_image, str(reward_path))
    (app.paths.rewards / "reward_config.json").write_text(
        '{"manual_reward.png": {"required_score": 100000}}\n', encoding="utf-8"
    )
    app.profile["unlocked_rewards"] = ["manual_reward.png"]
    app.profile["recent_songs"] = [
        {
            "source_path": str(ROOT / "demo_songs" / "ここから始まる～夜明けの光～.wav"),
            "music_hash": analysis.music_hash,
            "bpm": analysis.bpm,
            "duration": analysis.duration,
        },
        {
            "source_path": "C:/Music/Favorite Track.wav",
            "music_hash": "f" * 64,
            "bpm": 142.0,
            "duration": 153.0,
        },
    ]

    app.screen = "title"
    save(app, "01_title")

    app.open_playlist("normal")
    save(app, "02_playlist")

    app.analysis = analysis
    app.chart = chart
    app.song_path = Path(analysis.source_path)
    app.selected_difficulty = 1
    app.chart_summary = build_chart_summary(chart, analysis)
    app.screen = "chart_summary"
    save(app, "03_chart_summary")

    app.session = GameSession(chart, JudgmentWindows())
    app.session.score = 8100
    app.session.combo = 7
    app.session.max_combo = 7
    app.session.judgment_counts[Judgment.PERFECT.value] = 6
    app.session.judgment_counts[Judgment.GREAT.value] = 2
    app.session.judgment_counts[Judgment.GOOD.value] = 1
    app.session.judgment_counts[Judgment.MISS.value] = 1
    app.judgment_log = [
        JudgmentLogEntry(Judgment.PERFECT, 0.04, 2),
        JudgmentLogEntry(Judgment.GREAT, 0.22, 3),
        JudgmentLogEntry(Judgment.GOOD, 0.40, 0),
    ]
    app.judgment_feedback = JudgmentFeedback(Judgment.PERFECT, 1.4, 3)
    app.audio = ManualAudio(2.55)
    app.countdown_started_at = None
    app.screen = "game"
    save(app, "04_gameplay")

    app.settings["lane_view"] = "perspective"
    save(app, "10_perspective")
    app.settings["lane_view"] = "classic"

    app.screen = "result"
    save(app, "11_result")
    app.screen = "game"

    app.audio = ManualAudio(2.55, paused=True)
    app.message = "PAUSED"
    save(app, "05_pause")

    app.screen = "settings"
    app.message = ""
    app.settings_selection = 13
    save(app, "06_settings")

    app.begin_calibration()
    app.message = "入力を記録しました: +12 ms"
    if app.calibration is not None:
        app.calibration.offsets_ms.extend([12.0, 8.0, 14.0, 6.0, 10.0, 9.0, 11.0])
    save(app, "07_calibration")

    app.screen = "gallery"
    save(app, "08_gallery")

    reward = app.gallery_rewards()[0]
    app.open_reward(reward)
    save(app, "09_gallery_preview")

    app.profile["wallet_score"] = 150000
    app.open_shop()
    app.message = ""
    save(app, "12_shop")

    pygame.quit()





