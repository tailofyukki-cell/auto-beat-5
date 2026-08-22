"""Pygame音源再生と単調時計を接続する同期時計。"""
from __future__ import annotations

import tempfile
import time
import wave
from pathlib import Path


class AudioClockError(RuntimeError):
    pass


class AudioClock:
    """単調時計を基準にしつつ、mixerの再生位置を補助的に反映する。"""

    def __init__(self) -> None:
        self.path: Path | None = None
        self._started_at: float | None = None
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._duration = 0.0
        self._volume = 0.8
        self._segment_path: Path | None = None
        self._loaded = False
        self._last_time = 0.0
        self._last_mixer_time = -1.0

    def _cleanup_segment(self) -> None:
        """区間練習用の一時WAVを残さない。失敗しても次の再生を妨げない。"""
        if self._segment_path is None:
            return
        try:
            self._segment_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._segment_path = None

    def _unload_music(self) -> None:
        import pygame

        try:
            pygame.mixer.music.unload()
        except (AttributeError, pygame.error):
            pass

    def load(self, path: str | Path, duration: float, volume: float) -> None:
        import pygame

        self._unload_music()
        self._cleanup_segment()
        source = Path(path)
        try:
            pygame.mixer.music.load(str(source.resolve()))
            self._volume = max(0.0, min(1.0, volume))
            pygame.mixer.music.set_volume(self._volume)
        except pygame.error as error:
            raise AudioClockError("音源を再生できません。対応形式または音声デバイスを確認してください。") from error
        self.path = source
        self._duration = max(0.0, duration)
        self._started_at = None
        self._paused_at = None
        self._paused_total = 0.0
        self._last_time = 0.0
        self._last_mixer_time = -1.0
        self._loaded = True

    def _play_wav_segment(self, offset: float) -> None:
        """PCM WAVを標準ライブラリで切り出し、WAVでも任意位置から再生する。"""
        import pygame

        if self.path is None:
            raise AudioClockError("再生するWAVファイルが見つかりません。")
        segment: Path | None = None
        try:
            with wave.open(str(self.path.resolve()), "rb") as reader:
                total_frames = reader.getnframes()
                start_frame = min(total_frames, max(0, int(offset * reader.getframerate())))
                reader.setpos(start_frame)
                parameters = reader.getparams()
                remaining = reader.readframes(total_frames - start_frame)
            handle = tempfile.NamedTemporaryFile(prefix="autobeat5_practice_", suffix=".wav", delete=False)
            segment = Path(handle.name)
            handle.close()
            with wave.open(str(segment), "wb") as writer:
                writer.setparams(parameters)
                writer.writeframes(remaining)
            self._cleanup_segment()
            self._segment_path = segment
            pygame.mixer.music.load(str(segment))
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()
        except (OSError, wave.Error, pygame.error) as error:
            if segment is not None:
                try:
                    segment.unlink(missing_ok=True)
                except OSError:
                    pass
            self._cleanup_segment()
            raise AudioClockError("このWAVは区間開始位置の再生に対応していません。PCM WAV または MP3 / OGG をお試しください。") from error

    def play(self, start_at: float = 0.0) -> None:
        """指定した曲内時刻から再生し、判定時計も同じ絶対時刻へ合わせる。"""
        import pygame

        if not self._loaded:
            raise AudioClockError("再生する音源が読み込まれていません。")
        offset = max(0.0, min(float(start_at), self._duration))
        if offset > 0.001 and self.path is not None and self.path.suffix.lower() == ".wav":
            self._play_wav_segment(offset)
        else:
            try:
                # pygame 2系ではMP3 / OGG等に開始位置を渡せる。
                pygame.mixer.music.play(start=offset)
            except (TypeError, pygame.error) as error:
                if offset > 0.001:
                    raise AudioClockError("この音源形式は区間練習の開始位置指定に対応していません。MP3 / OGG または PCM WAV をお試しください。") from error
                pygame.mixer.music.play()
        self._started_at = time.perf_counter() - offset
        self._paused_at = None
        self._paused_total = 0.0
        self._last_time = offset
        self._last_mixer_time = -1.0

    def pause(self) -> None:
        import pygame

        if self._started_at is not None and self._paused_at is None:
            # pause前に時刻を評価して、停止位置を固定する。
            self._last_time = self.time
            pygame.mixer.music.pause()
            self._paused_at = time.perf_counter()

    def resume(self) -> None:
        import pygame

        if self._paused_at is not None:
            self._paused_total += time.perf_counter() - self._paused_at
            self._paused_at = None
            pygame.mixer.music.unpause()

    def stop(self) -> None:
        import pygame

        pygame.mixer.music.stop()
        self._unload_music()
        self._cleanup_segment()
        self._started_at = None
        self._paused_at = None

    def set_volume(self, volume: float) -> None:
        import pygame

        self._volume = max(0.0, min(1.0, volume))
        pygame.mixer.music.set_volume(self._volume)

    def _monotonic_time(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._paused_at if self._paused_at is not None else time.perf_counter()
        return max(0.0, end - self._started_at - self._paused_total)

    @property
    def time(self) -> float:
        if self._started_at is None:
            return 0.0
        if self._paused_at is not None:
            return self._last_time
        estimated = self._monotonic_time()
        try:
            import pygame

            mixer_ms = pygame.mixer.music.get_pos()
        except pygame.error:
            mixer_ms = -1
        if mixer_ms is not None and mixer_ms >= 0:
            mixer_time = mixer_ms / 1000.0
            # get_posが短時間だけ巻き戻る実装差を吸収し、極端な不連続値は単調時計へフォールバックする。
            stable = mixer_time + 0.040 >= self._last_mixer_time
            close_enough = abs(mixer_time - estimated) <= 0.75
            if stable and close_enough:
                current = mixer_time
                self._last_mixer_time = mixer_time
            else:
                current = estimated
        else:
            current = estimated
        self._last_time = min(self._duration, max(self._last_time, current))
        return self._last_time

    @property
    def finished(self) -> bool:
        return self._started_at is not None and self.time >= self._duration - 0.03

    @property
    def paused(self) -> bool:
        return self._paused_at is not None
