from __future__ import annotations

import math
import os
import queue
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pygame
from analyzer import AnalysisProgress, AnalysisWorker
from app import AutoBeatApp
from models import AnalysisResult


class WorkerStub:
    def __init__(self) -> None:
        self.events: queue.Queue[object] = queue.Queue()


class WorkerCompletionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    @staticmethod
    def result() -> AnalysisResult:
        return AnalysisResult(
            music_hash="a" * 64,
            source_path="C:/music/test.wav",
            duration=3.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0],
            onsets=[0.5, 1.0],
            onset_strengths=[1.0, 0.8],
            band_energy=[[0.2] * 5, [0.2] * 5],
            percussive_strengths=[1.0, 0.8],
            sustained_segments=[],
            local_bpms=[(0.0, 120.0)],
            downbeats=[0.0],
            analyzer_version="1.1",
        )

    def test_completion_after_progress_does_not_rereference_cleared_worker(self) -> None:
        worker = WorkerStub()
        worker.events.put(AnalysisProgress(0.5, "解析中"))
        worker.events.put(self.result())
        self.app.worker = worker
        self.app.poll_worker()
        self.assertIsNone(self.app.worker)
        self.assertEqual(self.app.screen, "difficulty")
        self.assertIsNotNone(self.app.analysis)
        self.assertIn("完了", self.app.message)

    def test_failure_after_progress_returns_to_selection_without_rereference(self) -> None:
        worker = WorkerStub()
        worker.events.put(AnalysisProgress(0.5, "解析中"))
        worker.events.put(RuntimeError("テスト用解析失敗"))
        self.app.worker = worker
        self.app.poll_worker()
        self.assertIsNone(self.app.worker)
        self.assertEqual(self.app.screen, "select")
        self.assertIn("テスト用解析失敗", self.app.error)

    def test_real_analysis_worker_reaches_difficulty_without_unhandled_state_error(self) -> None:
        sample_rate = 22050
        duration = 4.0
        timeline = np.arange(int(sample_rate * duration)) / sample_rate
        signal = 0.18 * np.sin(2 * math.pi * 110 * timeline)
        for onset in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            start = int(onset * sample_rate)
            end = min(len(signal), start + int(0.035 * sample_rate))
            signal[start:end] += 0.70 * np.linspace(1.0, 0.0, end - start) * np.sin(2 * math.pi * 90 * timeline[start:end])
        fixture = Path(self.directory.name) / "worker_fixture.wav"
        with wave.open(str(fixture), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes((np.clip(signal, -1, 1) * 32767).astype("<i2").tobytes())
        self.app.song_path = fixture
        self.app.begin_analysis()
        self.assertEqual(self.app.screen, "analyzing")
        self.assertIsNotNone(self.app.worker)
        deadline = time.monotonic() + 60.0
        while self.app.worker is not None and time.monotonic() < deadline:
            self.app.poll_worker()
            time.sleep(0.01)
        self.assertIsNone(self.app.worker, "解析ワーカーが制限時間内に完了しませんでした")
        self.assertEqual(self.app.screen, "difficulty")
        self.assertIsNotNone(self.app.analysis)
        self.assertEqual(self.app.error, "")


if __name__ == "__main__":
    unittest.main()
