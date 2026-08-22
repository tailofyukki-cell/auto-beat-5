"""Create the deterministic PCM WAV fixture used by the release preflight gate."""
from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "通常音源_日本語パス_PCM.wav"
SAMPLE_RATE = 48_000
DURATION_SECONDS = 6.0


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(SAMPLE_RATE * DURATION_SECONDS)
    timeline = np.arange(frame_count, dtype=np.float64) / SAMPLE_RATE
    # A quiet deterministic tone bed plus short percussive pulses supplies
    # enough onset information for the BEGINNER chart generation assertion.
    signal = 0.10 * np.sin(2.0 * math.pi * 220.0 * timeline)
    for beat in np.arange(0.5, DURATION_SECONDS, 0.5):
        envelope = np.exp(-np.maximum(0.0, timeline - beat) * 30.0)
        envelope[timeline < beat] = 0.0
        signal += 0.65 * envelope * np.sin(2.0 * math.pi * 880.0 * timeline)
    signal = np.clip(signal, -0.95, 0.95)
    pcm = (signal * 32767.0).astype("<i2")
    stereo = np.column_stack((pcm, pcm)).reshape(-1)
    with wave.open(str(OUTPUT), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(stereo.tobytes())
    print(OUTPUT)


if __name__ == "__main__":
    main()
