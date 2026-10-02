"""Title-only stage animation; no audio clock or gameplay state dependencies."""
from __future__ import annotations

import math
import pygame


class TitleScene:
    CYAN = (72, 226, 255)
    PINK = (255, 94, 173)
    GOLD = (255, 211, 102)

    def __init__(self, app, title, tagline):
        self.size = app.size
        self.mascot = app.selected_mascot
        self.started = pygame.time.get_ticks() / 1000
        self.pulse_at = -100.0
        width, height = self.size
        self.left = max(54, int(width * 0.065))
        self.menu_width = min(510, int(width * 0.40))
        self.logo = app._font_from_asset(94, bold=True).render(title, True, (238, 251, 255))
        if self.logo.get_width() > self.menu_width:
            scale = self.menu_width / self.logo.get_width()
            self.logo = pygame.transform.smoothscale(self.logo, (self.menu_width, round(self.logo.get_height() * scale)))
        self.tagline = app._font_from_asset(24).render(tagline, True, (180, 210, 224))
        self.logo_glow = pygame.Surface((self.logo.get_width() + 24, self.logo.get_height() + 24), pygame.SRCALPHA)
        tint = self.logo.copy()
        tint.fill((*self.CYAN, 255), special_flags=pygame.BLEND_RGBA_MULT)
        tint.set_alpha(25)
        for dx, dy in ((-8, 0), (8, 0), (0, -8), (0, 8), (-4, -4), (4, 4)):
            self.logo_glow.blit(tint, (12 + dx, 12 + dy))
        self.sprite = None
        if self.mascot:
            try:
                source = pygame.image.load(str(self.mascot.image_path)).convert_alpha()
                bounds = source.get_bounding_rect()
                if bounds.width and bounds.height:
                    source = source.subsurface(bounds)
                    scale = min(width * 0.34 / source.get_width(), height * 0.68 / source.get_height())
                    self.sprite = pygame.transform.smoothscale(source, (round(source.get_width() * scale), round(source.get_height() * scale)))
            except (OSError, pygame.error):
                pass
        self.base = pygame.Surface(self.size).convert()
        self.base.fill((6, 9, 19))
        horizon = int(height * 0.43)
        vanishing = (int(width * 0.74), horizon)
        for index in range(-9, 10):
            end = (vanishing[0] + index * 135, height)
            pygame.draw.line(self.base, (19, 49, 65), vanishing, end, 1)
        lights = pygame.Surface(self.size, pygame.SRCALPHA)
        for i, color in enumerate((self.CYAN, self.PINK, self.GOLD)):
            top = (int(width * (0.61 + i * 0.15)), 0)
            bottom = int(width * (0.72 + (i - 1) * 0.16))
            pygame.draw.polygon(lights, (*color, 12), (top, (bottom - 90, height - 90), (bottom + 90, height - 90)))
            pygame.draw.line(lights, (*color, 48), top, (bottom + 90, height - 90), 1)
        self.base.blit(lights, (0, 0))
        self.layer = pygame.Surface(self.size, pygame.SRCALPHA)

    def react(self):
        self.pulse_at = pygame.time.get_ticks() / 1000

    def draw(self, app, title):
        width, height = self.size
        now = pygame.time.get_ticks() / 1000
        elapsed = now - self.started
        surface = app.surface
        surface.blit(self.base, (0, 0))
        layer = self.layer
        layer.fill((0, 0, 0, 0))
        cx, horizon, floor = int(width * 0.74), int(height * 0.43), height - 105
        for i in range(12):
            p = ((i / 12 + now * 0.07) % 1) ** 2
            y = round(horizon + (height - horizon) * p)
            pygame.draw.line(layer, (55, 184, 214, int(15 + 65 * p)), (0, y), (width, y), 1)
        # Converging note trails evoke the playfield without sharing its renderer.
        for i in range(24):
            p = (i * 0.137 + now * (0.10 + (i % 3) * 0.012)) % 1
            lane = i % 7 - 3
            x = cx + lane * (20 + 85 * p)
            y = horizon + (height - horizon) * p * p
            color = (self.CYAN, self.PINK, self.GOLD)[i % 3]
            length = int(8 + p * 42)
            pygame.draw.line(layer, (*color, int(25 + 100 * p)), (x, y - 22 * p), (x, y), max(1, int(2 * p)))
            pygame.draw.line(layer, (*color, int(80 + 100 * p)), (x - length / 2, y), (x + length / 2, y), 2)
        for i in range(34):
            x = (i * 163.7 + math.sin(now * 0.4 + i) * 18) % width
            y = (i * 91.3 - now * (8 + i % 5)) % height
            color = (self.CYAN, self.PINK, self.GOLD)[i % 3]
            alpha = int(40 + 100 * (0.5 + 0.5 * math.sin(now * 1.4 + i)))
            pygame.draw.line(layer, (*color, alpha), (x - 2, y), (x + 2, y), 1)
            pygame.draw.line(layer, (*color, alpha), (x, y - 2), (x, y + 2), 1)
        for offset, color in ((0, self.CYAN), (12, self.PINK), (22, self.GOLD)):
            rect = pygame.Rect(cx - 205 + offset, floor - 35 + offset // 2, 410 - offset * 2, 82 - offset)
            pygame.draw.ellipse(layer, (*color, 28), rect.inflate(6, 6), 7)
            pygame.draw.ellipse(layer, (*color, 155), rect, 2)
        surface.blit(layer, (0, 0))
        if self.sprite:
            bounce = max(0, 1 - (now - self.pulse_at) / 0.65)
            y = floor + 7 + math.sin(now * 1.6) * 7 - math.sin(bounce * math.pi) * 26
            entrance = max(0, 1 - elapsed / 0.65)
            rect = self.sprite.get_rect(midbottom=(cx + round(entrance * 55), round(y)))
            surface.blit(self.sprite, rect)
            app.buttons.append((rect, self.react))
            app.text(self.mascot.name, "small", (170, 205, 222), center=(cx, floor + 66))
        # Solid left scrim keeps the moving stage away from menu text.
        scrim = pygame.Rect(self.left - 22, 70, self.menu_width + 44, height - 140)
        pygame.draw.rect(layer, (6, 9, 19, 225), scrim)
        surface.blit(layer, scrim, scrim)
        top = max(80, int(height * 0.13))
        surface.blit(self.logo_glow, (self.left - 12, top - 12))
        surface.blit(self.logo, (self.left, top))
        surface.blit(self.tagline, (self.left + 3, top + self.logo.get_height() + 10))
        rail_y = top - 22
        pygame.draw.line(surface, self.CYAN, (self.left, rail_y), (self.left + 94, rail_y), 3)
        pygame.draw.line(surface, self.PINK, (self.left + 104, rail_y), (self.left + 130, rail_y), 3)
        shimmer = self.left + int((now * 105) % self.menu_width)
        pygame.draw.line(surface, self.GOLD, (shimmer, rail_y), (min(shimmer + 16, self.left + self.menu_width), rail_y), 2)
        y = max(top + self.logo.get_height() + 82, round(height * 0.41))
        self.menu(app, "PLAY MUSIC", pygame.Rect(self.left, y, self.menu_width, 70), lambda: app.open_playlist("normal"), self.CYAN, primary=True)
        half = (self.menu_width - 14) // 2
        self.menu(app, "PRACTICE", pygame.Rect(self.left, y + 86, half, 52), lambda: app.open_playlist("practice"), self.PINK)
        self.menu(app, "TUTORIAL", pygame.Rect(self.left + half + 14, y + 86, half, 52), lambda: app.set_screen("tutorial"), self.GOLD)
        third = (self.menu_width - 24) // 3
        for i, (label, action, color) in enumerate((("GALLERY", lambda: app.set_screen("gallery"), self.CYAN), ("SHOP", app.open_shop, self.PINK), ("SETTINGS", lambda: app.set_screen("settings"), self.GOLD))):
            self.menu(app, label, pygame.Rect(self.left + i * (third + 12), y + 154, third, 50), action, color)
        app.button("終了", pygame.Rect(width - 145, height - 62, 100, 36), app.exit_app, accent=(168, 191, 204))

    def menu(self, app, label, rect, action, color, primary=False):
        hovered = rect.collidepoint(app._to_logical_point(pygame.mouse.get_pos()))
        pygame.draw.rect(app.surface, (22, 61, 77) if hovered else (11, 24, 37), rect, border_radius=5)
        pygame.draw.rect(app.surface, color if hovered or primary else tuple(c // 2 for c in color), rect, 2 if primary else 1, border_radius=5)
        pygame.draw.line(app.surface, color, (rect.left + 1, rect.top + 10), (rect.left + 1, rect.bottom - 10), 4)
        if primary:
            x, y = rect.left + 34, rect.centery
            pygame.draw.polygon(app.surface, color, ((x, y - 10), (x, y + 10), (x + 16, y)))
            app.text(label, "h1", (239, 252, 255), center=(rect.centerx + 12, rect.centery))
        else:
            app.text(label, "small" if rect.width < 175 else "body", (232, 243, 249), center=rect.center)
        if hovered:
            pygame.draw.line(app.surface, color, (rect.left + 15, rect.bottom - 5), (rect.right - 15, rect.bottom - 5), 2)
        app.buttons.append((rect, action))
