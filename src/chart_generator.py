"""音楽の特徴量を5レーン譜面へ変換する決定論的な生成器。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import inf
from typing import Iterable

import numpy as np

from models import AnalysisResult, Chart, Difficulty, Note, NoteType


@dataclass(frozen=True, slots=True)
class DifficultyRule:
    strength_percentile: float
    min_gap: float
    allow_chords: bool
    max_chord_size: int
    allow_holds: bool
    allow_dense_patterns: bool
    max_notes_per_second: float


# ノーツが画面上端から判定線へ届く時間より少し長く確保する。
# カウントダウン後に音源が始まっても、最初の入力を準備できる。
START_LEAD_IN_SECONDS = 1.20

RULES: dict[Difficulty, DifficultyRule] = {
    Difficulty.BEGINNER: DifficultyRule(80, 0.48, False, 1, False, False, 2.0),
    Difficulty.EASY: DifficultyRule(65, 0.30, False, 1, False, False, 3.5),
    Difficulty.NORMAL: DifficultyRule(50, 0.17, True, 2, True, True, 5.5),
    Difficulty.HARD: DifficultyRule(35, 0.10, True, 3, True, True, 8.0),
    Difficulty.EXPERT: DifficultyRule(20, 0.07, True, 3, True, True, 11.0),
}


class ChartGenerator:
    VERSION = "1.3"

    def generate(self, analysis: AnalysisResult, difficulty: Difficulty, *, variant: int = 0) -> Chart:
        """同じvariantでは再現可能に、variantを変えると別のレーン候補を生成する。"""
        rule = RULES[difficulty]
        variant = max(0, int(variant))
        seed = int(hashlib.sha256(f"{analysis.music_hash}:{difficulty.value}:{variant}".encode()).hexdigest()[:16], 16)
        notes: list[Note] = []
        candidates = self._select_candidates(analysis, rule)
        last_by_lane = [-inf] * 5
        previous_lane = 2

        for index in candidates:
            time = self._quantize(float(analysis.onsets[index]), analysis.beats, difficulty)
            if time < START_LEAD_IN_SECONDS or time > analysis.duration - 0.05:
                continue
            bands = self._bands_at(analysis, index)
            strength = self._at(analysis.onset_strengths, index, 0.0)
            percussion = self._at(analysis.percussive_strengths, index, 0.0)
            downbeat = self._near_downbeat(time, analysis.downbeats)
            lanes = self._assign_lanes(bands, strength, percussion, previous_lane, rule, downbeat, variant)
            lanes = [lane for lane in lanes if time - last_by_lane[lane] >= rule.min_gap]
            if not lanes:
                continue
            for lane in lanes:
                source = "downbeat" if downbeat and lane == 2 else "onset"
                notes.append(Note(time=time, lane=lane, source=source, strength=strength))
                last_by_lane[lane] = time
                previous_lane = lane

        if rule.allow_dense_patterns:
            self._shape_roll_patterns(notes, analysis, difficulty)
        if rule.allow_holds:
            self._add_holds(notes, analysis, difficulty)
        notes = self._cap_density(notes, analysis.duration, rule.max_notes_per_second)
        # sustain候補はonset候補とは別経路で加わるため、最後に先頭の助走時間を統一する。
        notes = [note for note in notes if note.time >= START_LEAD_IN_SECONDS]
        chart = Chart(
            version=1,
            music_hash=analysis.music_hash,
            difficulty=difficulty,
            seed=seed,
            song_duration=analysis.duration,
            notes=notes,
            generator_version=self.VERSION,
            metadata={
                "bpm": analysis.bpm,
                "source_path": analysis.source_path,
                "analysis_version": analysis.analyzer_version,
                "algorithm": "hpss-frequency-onset-downbeat-sustain-roll-v1",
                "start_lead_in_seconds": START_LEAD_IN_SECONDS,
                "downbeats": len(analysis.downbeats),
                "local_tempo_points": len(analysis.local_bpms),
                "generation_variant": variant,
            },
        )
        chart.sort()
        return chart

    @staticmethod
    def _at(values: list[float], index: int, default: float) -> float:
        return float(values[index]) if index < len(values) else default

    @staticmethod
    def _bands_at(analysis: AnalysisResult, index: int) -> list[float]:
        if index < len(analysis.band_energy):
            result = list(analysis.band_energy[index])
            return (result + [0.0] * 5)[:5]
        return [0.0] * 5

    def _select_candidates(self, analysis: AnalysisResult, rule: DifficultyRule) -> list[int]:
        if not analysis.onsets:
            return []
        strengths = np.asarray(analysis.onset_strengths or [0.0] * len(analysis.onsets), dtype=float)
        if len(strengths) < len(analysis.onsets):
            strengths = np.pad(strengths, (0, len(analysis.onsets) - len(strengths)))
        percussion = np.asarray(analysis.percussive_strengths or [0.0] * len(analysis.onsets), dtype=float)
        if len(percussion) < len(analysis.onsets):
            percussion = np.pad(percussion, (0, len(analysis.onsets) - len(percussion)))
        combined = strengths[: len(analysis.onsets)] * 0.70 + percussion[: len(analysis.onsets)] * 0.30
        threshold = float(np.percentile(combined, rule.strength_percentile))
        chosen = [index for index, value in enumerate(combined) if value >= threshold]
        # 初級は拍と小節頭の骨格を必ず残し、上級は音の細部を段階的に追加する。
        if rule is RULES[Difficulty.BEGINNER] and analysis.beats:
            for beat in analysis.beats[::2]:
                nearest = min(range(len(analysis.onsets)), key=lambda i: abs(analysis.onsets[i] - beat))
                if abs(analysis.onsets[nearest] - beat) < 0.13:
                    chosen.append(nearest)
        for downbeat in analysis.downbeats:
            nearest = min(range(len(analysis.onsets)), key=lambda i: abs(analysis.onsets[i] - downbeat))
            if abs(analysis.onsets[nearest] - downbeat) < 0.11:
                chosen.append(nearest)
        return sorted(set(chosen), key=lambda i: analysis.onsets[i])

    @staticmethod
    def _quantize(time: float, beats: list[float], difficulty: Difficulty) -> float:
        """onsetを尊重しつつ、近い拍の細分へだけ寄せる。可変beat間隔にも追従する。"""
        if not beats or difficulty is Difficulty.EXPERT:
            return round(time, 5)
        subdivision = 2 if difficulty in (Difficulty.BEGINNER, Difficulty.EASY) else 4
        candidates: list[float] = []
        for index, beat in enumerate(beats):
            if index + 1 < len(beats):
                interval = beats[index + 1] - beat
            elif index > 0:
                interval = beat - beats[index - 1]
            else:
                interval = 0.5
            for step in range(subdivision):
                candidates.append(beat + interval * step / subdivision)
        nearest = min(candidates, key=lambda candidate: abs(candidate - time))
        local_interval = min((abs(candidate - time) for candidate in beats), default=0.5)
        tolerance = min(0.045, max(0.020, local_interval * 0.35))
        if abs(nearest - time) <= tolerance:
            return round(float(nearest), 5)
        return round(time, 5)

    @staticmethod
    def _near_downbeat(time: float, downbeats: list[float]) -> bool:
        return any(abs(time - downbeat) <= 0.085 for downbeat in downbeats)

    def _assign_lanes(
        self,
        bands: list[float],
        strength: float,
        percussion: float,
        previous_lane: int,
        rule: DifficultyRule,
        downbeat: bool,
        variant: int = 0,
    ) -> list[int]:
        ranked = sorted(range(5), key=lambda lane: bands[lane], reverse=True)
        primary = ranked[0]
        # 強い広帯域トランジェント、小節頭のリズム、キック・スネアに近い成分は中心レーンを優先する。
        if (percussion >= 0.58 and strength >= 0.42) or (downbeat and percussion >= 0.28):
            primary = 2
        elif primary == 0:
            primary = 0 if previous_lane != 0 else 1
        elif primary == 1:
            primary = 1 if previous_lane != 1 else 0
        elif primary == 3:
            primary = 3 if previous_lane != 3 else 4
        elif primary == 4:
            primary = 4 if previous_lane != 4 else 3

        # 再生成は音価・タイミングを保ち、左右レーンの選択だけを決定論的に切り替える。
        # 中央レーンは強拍のアンカーとして固定し、譜面の読みやすさを損なわない。
        if variant % 2:
            if primary in (0, 1):
                primary = 1 - primary
            elif primary in (3, 4):
                primary = 7 - primary

        lanes = [primary]
        if rule.allow_chords:
            for candidate in ranked:
                if candidate == primary:
                    continue
                separated = abs(candidate - primary) >= 2
                strong_enough = bands[candidate] >= max(0.12, bands[primary] * 0.42)
                if separated and strong_enough:
                    lanes.append(candidate)
                if len(lanes) >= rule.max_chord_size:
                    break
        return sorted(set(lanes))

    def _shape_roll_patterns(self, notes: list[Note], analysis: AnalysisResult, difficulty: Difficulty) -> None:
        """連続onsetを、同一手の無理な反復でなく演奏感のある交互配置へ寄せる。"""
        if difficulty not in (Difficulty.NORMAL, Difficulty.HARD, Difficulty.EXPERT):
            return
        notes.sort(key=lambda note: (note.time, note.lane))
        by_time: dict[float, list[Note]] = {}
        for note in notes:
            by_time.setdefault(round(note.time, 4), []).append(note)
        isolated = [note for note in notes if note.kind is NoteType.TAP and len(by_time[round(note.time, 4)]) == 1]
        if len(isolated) < 3:
            return
        beat_interval = 60.0 / max(analysis.bpm, 1.0)
        run_gap = min(0.22, beat_interval * 0.58)
        start = 0
        while start < len(isolated):
            end = start + 1
            while end < len(isolated) and isolated[end].time - isolated[end - 1].time <= run_gap:
                end += 1
            run = isolated[start:end]
            if len(run) >= 3:
                dominant = max(set(note.lane for note in run), key=lambda lane: sum(note.lane == lane for note in run))
                if dominant in (0, 1):
                    pattern = (0, 1)
                elif dominant in (3, 4):
                    pattern = (3, 4)
                elif difficulty in (Difficulty.HARD, Difficulty.EXPERT):
                    pattern = (0, 2, 3, 2)
                else:
                    pattern = (2,)
                for index, note in enumerate(run):
                    note.lane = pattern[index % len(pattern)]
                    note.source = "roll"
            start = end

    def _add_holds(self, notes: list[Note], analysis: AnalysisResult, difficulty: Difficulty) -> None:
        occupied: dict[int, list[tuple[float, float]]] = {lane: [] for lane in range(5)}
        for note in notes:
            occupied[note.lane].append((note.time, note.time))
        min_duration = 0.85 if difficulty is Difficulty.NORMAL else 0.60
        for start, end, natural_lane in analysis.sustained_segments:
            duration = end - start
            if duration < min_duration:
                continue
            lane = int(max(0, min(4, natural_lane)))
            hold_start = self._nearest_existing_or_time(notes, start, lane)
            hold_end = min(end, analysis.duration - 0.05)
            if hold_end - hold_start < min_duration:
                continue
            if any(self._overlap((hold_start, hold_end), interval) for interval in occupied[lane]):
                continue
            # 同一手の二重ホールドは禁止。中央は親指として独立扱い。
            hand = "left" if lane < 2 else "right" if lane > 2 else "center"
            if any(
                note.kind is NoteType.HOLD
                and self._overlap((hold_start, hold_end), (note.time, note.end_time or note.time))
                and ((note.lane < 2 and hand == "left") or (note.lane > 2 and hand == "right"))
                for note in notes
            ):
                continue
            # 同じ開始時刻・同じレーンのtapはholdの始点に統合する。
            notes[:] = [
                note
                for note in notes
                if not (note.kind is NoteType.TAP and note.lane == lane and abs(note.time - hold_start) <= 0.03)
            ]
            notes.append(Note(time=round(hold_start, 5), lane=lane, kind=NoteType.HOLD, end_time=round(hold_end, 5), source="sustain", strength=0.6))
            occupied[lane].append((hold_start, hold_end))

    @staticmethod
    def _nearest_existing_or_time(notes: Iterable[Note], time: float, lane: int) -> float:
        near = [note.time for note in notes if note.lane == lane and abs(note.time - time) <= 0.18]
        return min(near, key=lambda value: abs(value - time)) if near else time

    @staticmethod
    def _overlap(left: tuple[float, float], right: tuple[float, float]) -> bool:
        return max(left[0], right[0]) < min(left[1], right[1])

    @staticmethod
    def _cap_density(notes: list[Note], duration: float, max_nps: float) -> list[Note]:
        if duration <= 0:
            return notes
        limit = max(1, int(duration * max_nps))
        if len(notes) <= limit:
            return notes
        ordered = sorted(notes, key=lambda note: (note.strength, note.kind is NoteType.HOLD), reverse=True)[:limit]
        return sorted(ordered, key=lambda note: (note.time, note.lane))
