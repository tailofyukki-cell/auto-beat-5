"""音源を必要としない、メトロノーム型チュートリアル用の固定譜面。"""
from __future__ import annotations

from dataclasses import dataclass

from models import Chart, Difficulty, Note, NoteType

TUTORIAL_BPM = 120.0
TUTORIAL_BEAT_SECONDS = 60.0 / TUTORIAL_BPM


@dataclass(frozen=True, slots=True)
class TutorialStep:
    """一つの操作だけに焦点を当てた、短いチュートリアル課題。"""

    key: str
    title: str
    instruction: str
    notes: tuple[Note, ...]
    duration: float


def _tap(time: float, lane: int) -> Note:
    return Note(time=time, lane=lane, kind=NoteType.TAP, source="tutorial", strength=1.0)


def _hold(time: float, lane: int, end_time: float) -> Note:
    return Note(time=time, lane=lane, kind=NoteType.HOLD, end_time=end_time, source="tutorial", strength=1.0)


TUTORIAL_STEPS: tuple[TutorialStep, ...] = (
    TutorialStep(
        key="center",
        title="STEP 1 / 4  中央レーン",
        instruction="クリック音に合わせて SPACE を4回押しましょう。",
        notes=(_tap(2.0, 2), _tap(2.5, 2), _tap(3.0, 2), _tap(3.5, 2)),
        duration=5.0,
    ),
    TutorialStep(
        key="lanes",
        title="STEP 2 / 4  5レーン",
        instruction="D・F・SPACE・J・K を順番に押しましょう。",
        notes=(
            _tap(2.0, 0),
            _tap(2.5, 1),
            _tap(3.0, 2),
            _tap(3.5, 3),
            _tap(4.0, 4),
            _tap(4.5, 3),
            _tap(5.0, 2),
            _tap(5.5, 1),
            _tap(6.0, 0),
        ),
        duration=7.5,
    ),
    TutorialStep(
        key="hold",
        title="STEP 3 / 4  長押しノーツ",
        instruction="F を押したまま、終端キャップで離しましょう。",
        notes=(_hold(2.0, 1, 4.0), _tap(5.0, 3), _tap(5.5, 2)),
        duration=7.0,
    ),
    TutorialStep(
        key="practice",
        title="STEP 4 / 4  基本の練習",
        instruction="クリック音を聞きながら、流れてくるノーツを叩きましょう。",
        notes=(
            _tap(2.0, 2),
            _tap(2.5, 1),
            _tap(3.0, 3),
            _tap(3.5, 0),
            _tap(4.0, 4),
            _tap(4.5, 2),
            _tap(5.0, 1),
            _tap(5.5, 3),
            _tap(6.0, 2),
            _tap(6.5, 0),
            _tap(7.0, 4),
        ),
        duration=8.5,
    ),
)


def build_tutorial_chart(step_index: int) -> Chart:
    """指定した課題を通常のGameSessionで扱える固定譜面へ変換する。"""
    if not 0 <= step_index < len(TUTORIAL_STEPS):
        raise IndexError(f"tutorial step out of range: {step_index}")
    step = TUTORIAL_STEPS[step_index]
    chart = Chart(
        version=1,
        music_hash=f"tutorial:{step.key}",
        difficulty=Difficulty.BEGINNER,
        seed=step_index,
        song_duration=step.duration,
        notes=[Note.from_dict(note.to_dict()) for note in step.notes],
        generator_version="tutorial-1.0",
        metadata={
            "tutorial": True,
            "tutorial_step": step_index,
            "tutorial_title": step.title,
            "tutorial_instruction": step.instruction,
            "bpm": TUTORIAL_BPM,
        },
    )
    chart.sort()
    return chart
