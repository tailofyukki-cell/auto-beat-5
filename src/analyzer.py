"""音源を解析し、譜面生成に必要な軽量特徴量を作る。"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from models import AnalysisResult
from persistence import music_hash


class AnalysisError(RuntimeError):
    """利用者に表示できる形へ変換する前の音源解析例外。"""


@dataclass(slots=True)
class AnalysisProgress:
    ratio: float
    stage: str


class MusicAnalyzer:
    """librosaを使った決定論的な特徴抽出。生の音声や大きな行列はキャッシュしない。"""

    SAMPLE_RATE = 22050
    HOP_LENGTH = 512
    VERSION = "1.1"
    BANDS = ((20, 160), (160, 500), (500, 2000), (2000, 6000), (6000, 16000))

    def __init__(self, progress: Callable[[float, str], None] | None = None) -> None:
        self._progress = progress or (lambda _ratio, _stage: None)

    def _report(self, ratio: float, stage: str) -> None:
        self._progress(max(0.0, min(1.0, ratio)), stage)

    def analyze(self, source_path: str | Path) -> AnalysisResult:
        try:
            import librosa
        except ImportError as error:
            raise AnalysisError("音楽解析ライブラリが見つかりません。再インストールしてください。") from error

        source = Path(source_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise AnalysisError("選択された音楽ファイルが見つかりません。")
        if source.suffix.lower() not in {".mp3", ".wav", ".ogg", ".flac"}:
            raise AnalysisError("対応していない形式です。MP3 / WAV / OGG / FLACを選択してください。")

        self._report(0.05, "音源を読み込んでいます")
        try:
            signal, sample_rate = librosa.load(str(source), sr=self.SAMPLE_RATE, mono=True)
        except Exception as error:  # ライブラリ例外をそのままUIへ漏らさない
            raise AnalysisError("音源をデコードできませんでした。ファイルの破損または非対応コーデックの可能性があります。") from error
        if signal.size < self.HOP_LENGTH:
            raise AnalysisError("音源が短すぎるため解析できません。")

        duration = float(len(signal) / sample_rate)
        self._report(0.13, "打楽器と持続音を分離しています")
        try:
            harmonic_signal, percussive_signal = librosa.effects.hpss(signal)
        except Exception:
            # 分離に失敗しても、全波形で継続できるようにする。
            harmonic_signal, percussive_signal = signal, signal

        self._report(0.23, "BPMと拍を検出しています")
        onset_env = librosa.onset.onset_strength(y=percussive_signal, sr=sample_rate, hop_length=self.HOP_LENGTH)
        melodic_onset_env = librosa.onset.onset_strength(y=harmonic_signal, sr=sample_rate, hop_length=self.HOP_LENGTH)
        combined_onset_env = onset_env * 0.65 + melodic_onset_env * 0.35
        try:
            tempo, beat_frames = librosa.beat.beat_track(
                onset_envelope=combined_onset_env, sr=sample_rate, hop_length=self.HOP_LENGTH, trim=False
            )
            bpm = float(np.asarray(tempo).reshape(-1)[0])
        except Exception:
            bpm, beat_frames = 120.0, np.array([], dtype=int)
        if not 40.0 <= bpm <= 300.0:
            bpm = 120.0
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate, hop_length=self.HOP_LENGTH)
        if len(beat_times) < 2:
            beat_times = np.arange(0.0, duration, 60.0 / bpm)
        local_bpms = self._local_bpm_pairs(beat_times, bpm)
        downbeats = beat_times[::4]

        self._report(0.40, "音の立ち上がりを検出しています")
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=combined_onset_env,
            sr=sample_rate,
            hop_length=self.HOP_LENGTH,
            units="frames",
            backtrack=False,
            delta=0.06,
            wait=1,
        )
        onset_times = librosa.frames_to_time(onset_frames, sr=sample_rate, hop_length=self.HOP_LENGTH)
        strengths = combined_onset_env[onset_frames] if len(onset_frames) else np.array([], dtype=float)
        if strengths.size:
            strengths = strengths / max(float(np.percentile(strengths, 95)), 1e-9)
            strengths = np.clip(strengths, 0.0, 1.5)

        self._report(0.58, "周波数帯域を解析しています")
        stft = np.abs(librosa.stft(signal, n_fft=2048, hop_length=self.HOP_LENGTH))
        harmonic_stft = np.abs(librosa.stft(harmonic_signal, n_fft=2048, hop_length=self.HOP_LENGTH))
        percussive_stft = np.abs(librosa.stft(percussive_signal, n_fft=2048, hop_length=self.HOP_LENGTH))
        frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
        total = np.sum(harmonic_stft, axis=0) + 1e-9
        onset_energy: list[list[float]] = []
        for frame in onset_frames:
            selected = min(max(int(frame), 0), stft.shape[1] - 1)
            values: list[float] = []
            for low, high in self.BANDS:
                mask = (frequencies >= low) & (frequencies < high)
                values.append(float(np.sum(harmonic_stft[mask, selected]) / total[selected]))
            onset_energy.append(values)

        self._report(0.73, "リズム成分を解析しています")
        # HPSS後の打楽器成分に対するスペクトルフラックスをリズム優先度とする。
        flux = np.maximum(0.0, np.diff(percussive_stft, axis=1)).sum(axis=0)
        flux = np.concatenate(([0.0], flux))
        percussive = flux[onset_frames] if len(onset_frames) else np.array([], dtype=float)
        if percussive.size:
            percussive /= max(float(np.percentile(percussive, 95)), 1e-9)
            percussive = np.clip(percussive, 0.0, 1.5)

        self._report(0.87, "持続音候補を検出しています")
        rms = librosa.feature.rms(y=harmonic_signal, frame_length=2048, hop_length=self.HOP_LENGTH)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sample_rate, hop_length=self.HOP_LENGTH)
        flatness = librosa.feature.spectral_flatness(S=harmonic_stft)[0]
        sustained = self._sustained_segments(rms, rms_times, onset_times, onset_energy, flatness)

        self._report(0.96, "解析データをまとめています")
        result = AnalysisResult(
            music_hash=music_hash(source),
            source_path=str(source),
            duration=duration,
            sample_rate=int(sample_rate),
            bpm=round(bpm, 3),
            beats=[round(float(value), 5) for value in beat_times if value < duration],
            onsets=[round(float(value), 5) for value in onset_times if value < duration],
            onset_strengths=[round(float(value), 5) for value in strengths],
            band_energy=[[round(float(item), 6) for item in values] for values in onset_energy],
            percussive_strengths=[round(float(value), 5) for value in percussive],
            sustained_segments=sustained,
            local_bpms=local_bpms,
            downbeats=[round(float(value), 5) for value in downbeats if value < duration],
            analyzer_version=self.VERSION,
        )
        self._report(1.0, "解析が完了しました")
        return result

    @staticmethod
    def _local_bpm_pairs(beat_times: np.ndarray, fallback_bpm: float) -> list[tuple[float, float]]:
        """各拍区間の局所BPMを保存し、テンポ変化曲の量子化に利用する。"""
        if len(beat_times) < 2:
            return [(0.0, round(float(fallback_bpm), 3))]
        pairs: list[tuple[float, float]] = []
        for index in range(len(beat_times) - 1):
            interval = float(beat_times[index + 1] - beat_times[index])
            bpm = 60.0 / interval if interval > 1e-6 else fallback_bpm
            if not 40.0 <= bpm <= 300.0:
                bpm = fallback_bpm
            pairs.append((round(float(beat_times[index]), 5), round(float(bpm), 3)))
        return pairs

    @staticmethod
    def _sustained_segments(
        rms: np.ndarray,
        rms_times: np.ndarray,
        onset_times: np.ndarray,
        onset_energy: list[list[float]],
        flatness: np.ndarray,
    ) -> list[tuple[float, float, int]]:
        """音量が保たれ、スペクトルが比較的安定する区間を長押し候補化する。"""
        if len(rms) == 0:
            return []
        threshold = max(float(np.percentile(rms, 60)), 1e-6)
        stability_threshold = float(np.percentile(flatness, 75)) if len(flatness) else 1.0
        active = (rms >= threshold) & (flatness <= stability_threshold)
        candidates: list[tuple[float, float, int]] = []
        start: int | None = None
        for index, is_active in enumerate(active):
            if is_active and start is None:
                start = index
            elif not is_active and start is not None:
                end = index - 1
                if rms_times[end] - rms_times[start] >= 0.65:
                    segment_start = float(rms_times[start])
                    segment_end = float(rms_times[end])
                    near = np.where((onset_times >= segment_start - 0.15) & (onset_times <= segment_start + 0.25))[0]
                    if len(near) and len(onset_energy) > int(near[0]):
                        lane = int(np.argmax(onset_energy[int(near[0])]))
                    else:
                        lane = 2
                    candidates.append((round(segment_start, 4), round(segment_end, 4), lane))
                start = None
        return candidates


class AnalysisWorker(threading.Thread):
    """UIを止めずに解析するための小さなワーカー。"""

    def __init__(self, path: str | Path) -> None:
        super().__init__(daemon=True)
        self.path = str(path)
        self.events: queue.Queue[AnalysisProgress | AnalysisResult | Exception] = queue.Queue()

    def run(self) -> None:
        try:
            analyzer = MusicAnalyzer(lambda ratio, stage: self.events.put(AnalysisProgress(ratio, stage)))
            self.events.put(analyzer.analyze(self.path))
        except Exception as error:
            self.events.put(error)
