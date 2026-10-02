from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note, NoteType


def make_app(notes):
    app = AutoBeatApp.__new__(AutoBeatApp)
    app.surface = pygame.Surface((1280, 720))
    app._note_draw_index = None
    app.session = GameSession(Chart(1, "draw-index", Difficulty.NORMAL, 1, 1000, notes=notes), JudgmentWindows())
    return app


def visible(app, now):
    candidates = app._drawable_states(now, 650, 20, 646)
    return [state.note.time for state in candidates if not state.complete]


def test_draw_index_retains_hold_crossing_view_and_supports_backward_time():
    app = make_app([Note(1, 0, NoteType.HOLD, 100), Note(50, 1), Note(200, 2)])
    assert 1 in visible(app, 60)
    assert 200 not in visible(app, 60)
    assert visible(app, 300) == []
    assert 1 in visible(app, 1)


def test_draw_index_refreshes_for_new_session_and_empty_chart():
    app = make_app([Note(50, 0)])
    assert visible(app, 50) == [50]
    app.session = GameSession(Chart(1, "retry", Difficulty.NORMAL, 1, 100, notes=[Note(20, 1)]), JudgmentWindows())
    assert visible(app, 20) == [20]
    app.session = GameSession(Chart(1, "empty", Difficulty.NORMAL, 1, 100, notes=[]), JudgmentWindows())
    assert visible(app, 20) == []


def test_draw_index_preserves_pending_late_notes_and_live_judgments():
    app = make_app([Note(50, 0), Note(50, 1), Note(51, 2)])
    assert visible(app, 50.1) == [50, 50, 51]
    app.session.press(0, 50.1)
    assert visible(app, 50.1) == [50, 51]

