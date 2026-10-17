"""Raw Pygame joystick buttons and D-pad, with per-device edge tracking."""
import pygame


class Gamepad:
    def __init__(self, settings):
        self.settings = settings
        self.devices = {}
        self.down = set()
        pygame.joystick.init()
        for index in range(pygame.joystick.get_count()):
            self.add(index)

    def add(self, index):
        try:
            device = pygame.joystick.Joystick(index)
            device.init()
            self.devices[device.get_instance_id()] = device
        except pygame.error:
            pass

    def bindings(self, count):
        defaults = [f"B{i}" for i in range(count)] + ["B9"]
        raw = self.settings.get("gamepad_bindings", {})
        raw = raw.get(str(count)) if isinstance(raw, dict) else None
        if (not isinstance(raw, list) or len(raw) != count + 1
                or not all(isinstance(v, str) for v in raw) or len(set(raw)) != len(raw)):
            return defaults
        return list(raw)

    def snapshot(self):
        down = set()
        for ident, device in self.devices.items():
            try:
                for button in range(device.get_numbuttons()):
                    if device.get_button(button):
                        down.add((ident, f"B{button}"))
                for hat in range(device.get_numhats()):
                    x, y = device.get_hat(hat)
                    for direction, active in (("L", x < 0), ("R", x > 0), ("U", y > 0), ("D", y < 0)):
                        if active:
                            down.add((ident, f"H{hat}{direction}"))
            except pygame.error:
                continue
        self.down = down

    def lanes(self, count):
        tokens = {token for _, token in self.down}
        return {lane for lane, token in enumerate(self.bindings(count)[:-1]) if token in tokens}

    def edges(self, event):
        ident = getattr(event, "instance_id", None)
        if ident not in self.devices:
            return []
        updates = []
        if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
            updates = [(f"B{event.button}", event.type == pygame.JOYBUTTONDOWN)]
        elif event.type == pygame.JOYHATMOTION:
            x, y = event.value
            updates = [(f"H{event.hat}{d}", active) for d, active in
                       (("L", x < 0), ("R", x > 0), ("U", y > 0), ("D", y < 0))]
        edges = []
        for token, pressed in updates:
            source = (ident, token)
            if pressed == (source in self.down):
                continue
            if pressed:
                self.down.add(source)
            else:
                self.down.discard(source)
            edges.append((token, pressed))
        return edges
