from __future__ import annotations

import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analyzer import MusicAnalyzer


class AnalysisTest(unittest.TestCase):
    def make_fixture(self, path: Path) -> None:
        sample_rate = 22050
        duration = 4.0
        time = np.arange(int(sample_rate * duration)) / sample_rate
        signal = 0.18 * np.sin(2 * math.pi * 110 * time) + 0.08 * np.sin(2 * math.pi * 1760 * time)
        # 一秒間隔の強いトランジェントを重ね、onsetとbeatの検出を確認する。
        for onset in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
            start = int(onset * sample_rate)
            end = min(len(signal), start + int(0.035 * sample_rate))
            envelope = np.linspace(1.0, 0.0, end - start)
            signal[start:end] += 0.70 * envelope * np.sin(2 * math.pi * 90 * time[start:end])
        data = (np.clip(signal, -1, 1) * 32767).astype("<i2")
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(data.tobytes())

    def test_wav_analysis_returns_chart_features(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.wav"
            self.make_fixture(fixture)
            result = MusicAnalyzer().analyze(fixture)
        self.assertGreater(result.duration, 3.9)
        self.assertGreater(result.bpm, 40)
        self.assertGreater(len(result.onsets), 2)
        self.assertEqual(len(result.onsets), len(result.band_energy))
        self.assertEqual(len(result.onsets), len(result.percussive_strengths))
        self.assertGreater(len(result.local_bpms), 0)
        self.assertGreater(len(result.downbeats), 0)


if __name__ == "__main__":
    unittest.main()
