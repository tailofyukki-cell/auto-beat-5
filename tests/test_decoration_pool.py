from __future__ import annotations
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from app import AutoBeatApp

def reference_draw(self, commands: list[tuple]) -> None:
    """Rasterize translucent primitives in visible bounds, preserving draw order."""
    shapes = []
    for kind, color, *args in commands:
        closed = False
        if kind == "line":
            points, width = args[:2], args[2] if len(args) > 2 else 1
        elif kind == "lines":
            closed, points = args[:2]
            width = args[2] if len(args) > 2 else 1
        else:
            points, width = args[0], args[1] if len(args) > 1 else 0
        # Round before translating so offscreen primitives retain their original pixels.
        shapes.append((kind, color, [(int(x), int(y)) for x, y in points], width, closed))
    if not shapes:
        return
    points = [point for _, _, vertices, _, _ in shapes for point in vertices]
    padding = max(width for _, _, _, width, _ in shapes) + 2
    min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points), max(y for _, y in points)
    bounds = pygame.Rect(min_x - padding, min_y - padding,
                         max_x - min_x + padding * 2 + 1,
                         max_y - min_y + padding * 2 + 1).clip(self.surface.get_rect())
    if not bounds:
        return
    layer = pygame.Surface(bounds.size, pygame.SRCALPHA)
    for kind, color, vertices, width, closed in shapes:
        local = [(x - bounds.x, y - bounds.y) for x, y in vertices]
        if kind == "line":
            pygame.draw.line(layer, color, local[0], local[1], width)
        elif kind == "lines":
            pygame.draw.lines(layer, color, closed, local, width)
        else:
            pygame.draw.polygon(layer, color, local, width)
    self.surface.blit(layer, bounds.topleft)



class DecorationPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": self.temp.name})
        self.env.start()
        self.app = AutoBeatApp()

    def tearDown(self):
        pygame.quit()
        self.env.stop()
        self.temp.cleanup()

    def test_reused_surface_is_cleared_and_matches_original(self):
        for color in ((80, 150, 230, 140), (200, 30, 50, 25), (0, 0, 0, 0)):
            for offset in (-40, 0, 100):
                commands = [("polygon", color, [(offset, 20), (offset+200, 20), (offset+180, 600), (offset+50, 600)]),
                            ("line", (255, 255, 255, 75), (offset, 30), (offset+150, 500), 2)]
                self.app.surface.fill((14, 22, 35))
                reference_draw(self.app, commands)
                expected = pygame.image.tobytes(self.app.surface, "RGB")
                self.app.surface.fill((14, 22, 35))
                self.app._blit_local_primitives(commands)
                self.assertEqual(pygame.image.tobytes(self.app.surface, "RGB"), expected)

    def test_small_shapes_skip_pool_and_large_shapes_reuse(self):
        self.app._blit_local_primitives([("line", (255, 0, 0, 80), (10, 10), (20, 20), 1)])
        self.assertFalse(getattr(self.app, "_decoration_surface_pool", {}))
        commands = [("polygon", (80, 150, 230, 80), [(10, 10), (210, 10), (210, 600), (10, 600)])]
        self.app._blit_local_primitives(commands)
        first = next(iter(self.app._decoration_surface_pool.values()))
        self.app._blit_local_primitives(commands)
        self.assertIs(next(iter(self.app._decoration_surface_pool.values())), first)
        for width in range(100, 200):
            self.app._blit_local_primitives([("polygon", (80, 150, 230, 80), [(10, 10), (width, 10), (width, 600), (10, 600)])])
        pool = self.app._decoration_surface_pool
        self.assertLessEqual(len(pool), 32)
        self.assertLessEqual(sum(s.get_pitch()*s.get_height() for s in pool.values()), 8*1024*1024)
