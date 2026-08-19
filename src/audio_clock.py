"""Pygame音源再生と単調時計を接続する同期時計。"""
from __future__ import annotations

import time
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
        self._loaded = False
        self._last_time = 0.0
        self._last_mixer_time = -1.0

    def load(self, path: str | Path, duration: float, volume: float) -> None:
        import pygame

        try:
            pygame.mixer.music.load(str(Path(path).resolve()))
            pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        except pygame.error as error:
            raise AudioClockError("音源を再生できません。対応形式または音声デバイスを確認してください。") from error
        self.path = Path(path)
        self._duration = max(0.0, duration)
        self._started_at = None
        self._paused_at = None
        self._paused_total = 0.0
        self._last_time = 0.0
        self._last_mixer_time = -1.0
        self._loaded = True

    def play(self) -> None:
        import pygame

        if not self._loaded:
            raise AudioClockError("再生する音源が読み込まれていません。")
        pygame.mixer.music.play()
        self._started_at = time.perf_counter()
        self._paused_at = None
        self._paused_total = 0.0
        self._last_time = 0.0
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
        self._started_at = None
        self._paused_at = None

    def set_volume(self, volume: float) -> None:
        import pygame

        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))

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
