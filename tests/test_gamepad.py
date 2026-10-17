import test_countdown as fixtures
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import pygame
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note, NoteType



class GamepadTest(unittest.TestCase):
    setUp = fixtures.CountdownTest.setUp
    tearDown = fixtures.CountdownTest.tearDown

    def prepare(self, hold=False):
        self.app.screen = "game"
        self.app.audio = SimpleNamespace(time=1.0, paused=False)
        self.app.audio.pause = lambda: setattr(self.app.audio, "paused", True)
        self.app.audio.resume = lambda: setattr(self.app.audio, "paused", False)
        self.app.session = GameSession(Chart(1, "g" * 64, Difficulty.NORMAL, 1, 5.0,
            notes=[Note(1.0, 0, NoteType.HOLD, 3.0)] if hold else [Note(1.0, 0), Note(1.1, 0)]), JudgmentWindows())
        self.device = Mock()
        self.device.get_name.return_value = "Test controller"
        self.device.get_numbuttons.return_value = 10
        self.device.get_numhats.return_value = 0
        self.device.get_button.side_effect = lambda b: (1, f"B{b}") in self.app.gamepad.down
        self.app.gamepad.devices = {1: self.device}

    def button(self, button, down=True, ident=1):
        self.app.gamepad_event(pygame.event.Event(pygame.JOYBUTTONDOWN if down else pygame.JOYBUTTONUP,
                                                instance_id=ident, button=button))

    def test_edges_and_repress(self):
        self.prepare()
        self.button(0)
        self.button(0)
        self.assertEqual(self.app.session.score, 1001)
        self.button(0, False)
        self.app.audio.time = 1.1
        self.button(0)
        self.assertEqual(self.app.session.judgment_counts['PERFECT'], 2)

    def test_pause_resume_blocks_held_tap_then_accepts_fresh_press(self):
        self.prepare()
        self.button(9)
        self.button(9, False)
        self.button(0)
        with patch('pygame.key.get_pressed', return_value=[False] * 512):
            self.button(9)
        self.assertEqual(self.app.session.score, 0)
        self.button(0, False)
        self.button(0)
        self.assertEqual(self.app.session.judgment_counts['PERFECT'], 1)

    def test_hold_survives_pause_only_while_physically_pressed(self):
        self.prepare(True)
        self.button(0)
        self.button(9)
        self.button(9, False)
        with patch('pygame.key.get_pressed', return_value=[False] * 512):
            self.button(9)
        self.assertEqual(self.app.session.held_lanes, {0})
        self.app.audio.time = 3.0
        self.button(0, False)
        self.assertEqual(self.app.session.judgment_counts['PERFECT'], 1)

    def test_keyboard_release_does_not_release_gamepad_hold(self):
        self.prepare(True)
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
        self.button(0)
        self.app.key_up_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_d))
        self.assertEqual(self.app.session.held_lanes, {0})
        self.app.audio.time = 3.0
        self.button(0, False)
        self.assertEqual(self.app.session.judgment_counts['PERFECT'], 1)

    def test_gamepad_release_does_not_release_keyboard_hold(self):
        self.prepare(True)
        self.button(0)
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
        self.button(0, False)
        self.assertEqual(self.app.session.held_lanes, {0})
        self.app.audio.time = 3.0
        self.app.key_up_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_d))
        self.assertEqual(self.app.session.judgment_counts['PERFECT'], 1)

    def test_disconnect_pauses_and_clears_state(self):
        self.prepare(True)
        self.button(0)
        self.app.gamepad_event(pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=1))
        self.assertTrue(self.app.audio.paused)
        self.assertFalse(self.app.session.held_lanes)
        self.assertFalse(self.app._lane_keys_down)
        self.assertFalse(self.app.gamepad.down)

    def test_countdown_and_background_inputs_do_not_judge(self):
        self.prepare()
        self.app.countdown_started_at = __import__('time').perf_counter()
        self.button(0)
        self.button(0, False)
        self.assertEqual(self.app.session.score, 0)
        self.app.countdown_started_at = None
        self.app._cursor_window_focused = False
        self.button(0)
        self.assertEqual(self.app.session.score, 0)

    def test_capture_hat_and_persist_per_lane_count(self):
        self.prepare()
        self.app.set_screen('gamepad')
        self.app.pad_capture = 0
        self.app.gamepad_event(pygame.event.Event(pygame.JOYHATMOTION, instance_id=1, hat=0, value=(-1, 0)))
        self.assertEqual(self.app.gamepad.bindings(5)[0], 'H0L')
        self.assertEqual(self.app.gamepad.bindings(3)[0], 'B0')
        self.assertIsNone(self.app.pad_capture)
        self.app.draw()

    def test_unknown_device_is_ignored(self):
        self.prepare()
        self.button(0, ident=999)
        self.assertEqual(self.app.session.score, 0)

    def test_released_during_pause_does_not_restore_hold(self):
        self.prepare(True)
        self.button(0)
        self.button(9)
        self.button(9, False)
        self.button(0, False)
        with patch('pygame.key.get_pressed', return_value=[False] * 512):
            self.button(9)
        self.assertFalse(self.app.session.held_lanes)
        self.assertEqual(self.app.session.judgment_counts['MISS'], 0)
        self.app.session.tick(1.1)
        self.assertEqual(self.app.session.judgment_counts['MISS'], 1)

    def test_second_controller_keeps_hold_until_both_release(self):
        self.prepare(True)
        self.app.gamepad.devices[2] = Mock()
        self.button(0)
        self.button(0, ident=2)
        self.button(0, False)
        self.assertEqual(self.app.session.held_lanes, {0})
        self.app.audio.time = 3.0
        self.button(0, False, ident=2)
        self.assertEqual(self.app.session.judgment_counts['PERFECT'], 1)

    def test_settings_saved_and_menu_confirm(self):
        import json
        self.prepare()
        self.app.set_screen('gamepad')
        self.app.pad_capture = 0
        self.button(8)
        self.assertEqual(self.app.gamepad.bindings(5)[0], 'B8')
        saved = list(__import__('pathlib').Path(self.directory.name).rglob('settings.json'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(json.loads(saved[0].read_text(encoding='utf-8'))['gamepad_bindings']['5'][0], 'B8')
        self.app.set_screen('title')
        with patch.object(self.app, 'open_playlist') as open_playlist:
            self.button(0)
        open_playlist.assert_called_once_with('normal')
