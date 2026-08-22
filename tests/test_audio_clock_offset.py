from __future__ import annotations

import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from audio_clock import AudioClock


class AudioClockOffsetTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.mixer.init()
        self.directory = tempfile.TemporaryDirectory()
        self.source = Path(self.directory.name) / "日本語の練習曲.wav"
        with wave.open(str(self.source), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(b"\x00\x00" * 8000 * 2)

    def tearDown(self) -> None:
        pygame.mixer.quit()
        self.directory.cleanup()

    def test_pcm_wav_offset_creates_cleaned_segment_and_preserves_absolute_time(self) -> None:
        clock = AudioClock()
        clock.load(self.source, 2.0, 0.5)
        clock.play(0.75)

        self.assertIsNotNone(clock._segment_path)
        assert clock._segment_path is not None
        self.assertTrue(clock._segment_path.is_file())
        self.assertGreaterEqual(clock.time, 0.75)

        segment = clock._segment_path
        clock.stop()
        self.assertFalse(segment.exists())
        self.assertEqual(clock.time, 0.0)


if __name__ == "__main__":
    unittest.main()
