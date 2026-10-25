"""
UI for the block puzzle game.
"""

import pygame


class UIManager:
    """Manages start menu, level menu, progress, and overlays."""

    def __init__(self, config, game_logic):
        self.config = config
        self.game_logic = game_logic
        pygame.font.init()
        self.font_title = self._load_font(56)
        self.font_large = self._load_font(38)
        self.font_medium = self._load_font(24)
        self.font_small = self._load_font(18)
        self.window_width = config.get('window_width', 1280)
        self.window_height = config.get('window_height', 720)
        self.mode = 'main_menu'
        self.menu_buttons = {}
        self.back_button = None
        self.level_buttons = []
        self._hint_timer = 0
        self._hint_interval = 240.0
        self._current_hint = 0
        self._hints = [
            "握拳抓住积木，张开手释放。",
            "把积木放进发光轮廓，稍微偏一点也可以。",
            "先搭下面的积木，再搭上面的积木更稳。",
        ]

    @property
    def show_tutorial(self):
        return self.mode in ('main_menu', 'level_select')

    def _load_font(self, size):
        try:
            import os
            for path in (
                'C:/Windows/Fonts/msyh.ttc',
                'C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/simsun.ttc',
            ):
                if os.path.exists(path):
                    return pygame.font.Font(path, size)
        except Exception:
            pass
        return pygame.font.Font(None, size + 8)

    def update(self, dt):
        self._hint_timer += dt
        if self._hint_timer > self._hint_interval:
            self._hint_timer = 0
            self._current_hint = (self._current_hint + 1) % len(self._hints)

    def dismiss_tutorial(self):
        self.mode = 'playing'

    def show_main_menu(self):
        self.mode = 'main_menu'

    def show_level_select(self):
        self.mode = 'level_select'

    def handle_click(self, pos):
        if self.mode == 'main_menu':
            for action, rect in self.menu_buttons.items():
                if rect.collidepoint(pos):
                    return action
            return None

        if self.mode == 'level_select':
            if self.back_button and self.back_button.collidepoint(pos):
                return 'back'
            for index, rect in self.level_buttons:
                if rect.collidepoint(pos):
                    return index
        return None

    def draw(self, surface, hand_data=None):
        if self.mode == 'main_menu':
            self._draw_main_menu(surface)
            return
        if self.mode == 'level_select':
            self._draw_level_select(surface)
            return

        self._draw_top_bar(surface)
        self._draw_hint(surface)
        self._draw_hand_indicator(surface, hand_data)
        if self.game_logic.level_completed:
            self._draw_completed(surface)

    def _draw_menu_background(self, surface):
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        overlay.fill((15, 18, 28, 235))
        surface.blit(overlay, (0, 0))

    def _draw_button(self, surface, rect, text, primary=False):
        fill = (82, 104, 142) if primary else (48, 58, 78)
        border = (255, 220, 100) if primary else (115, 128, 156)
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, border, rect, 3, border_radius=8)
        label = self.font_medium.render(text, True, (255, 255, 255))
        surface.blit(label, label.get_rect(center=rect.center))

    def _draw_main_menu(self, surface):
        self._draw_menu_background(surface)
        title = self.font_title.render("积木拼搭", True, (255, 236, 150))
        surface.blit(title, title.get_rect(center=(self.window_width // 2, 132)))

        sub = self.font_medium.render("握拳抓取，张手释放，完成每关的图形目标", True, (220, 225, 235))
        surface.blit(sub, sub.get_rect(center=(self.window_width // 2, 196)))

        self.menu_buttons = {
            'start': pygame.Rect(0, 0, 260, 64),
            'levels': pygame.Rect(0, 0, 260, 64),
        }
        self.menu_buttons['start'].center = (self.window_width // 2, 310)
        self.menu_buttons['levels'].center = (self.window_width // 2, 392)
        self._draw_button(surface, self.menu_buttons['start'], "开始游戏", primary=True)
        self._draw_button(surface, self.menu_buttons['levels'], "关卡", primary=False)

        tips = [
            "空格 / Enter：开始游戏",
            "点击“关卡”进入关卡选择",
            "ESC：退出",
        ]
        y = 500
        for line in tips:
            surf = self.font_small.render(line, True, (190, 198, 210))
            surface.blit(surf, surf.get_rect(center=(self.window_width // 2, y)))
            y += 30

    def _draw_level_select(self, surface):
        self._draw_menu_background(surface)
        self.back_button = pygame.Rect(34, 34, 116, 48)
        self._draw_button(surface, self.back_button, "返回", primary=False)

        title = self.font_large.render("关卡选择", True, (255, 236, 150))
        surface.blit(title, title.get_rect(center=(self.window_width // 2, 86)))
        sub = self.font_medium.render("完成上一关后解锁下一关", True, (220, 225, 235))
        surface.blit(sub, sub.get_rect(center=(self.window_width // 2, 132)))

        self.level_buttons = []
        card_w = 190
        card_h = 118
        gap = 22
        total_w = card_w * 5 + gap * 4
        start_x = (self.window_width - total_w) // 2
        y = 220
        for index, level in enumerate(self.game_logic.levels):
            rect = pygame.Rect(start_x + index * (card_w + gap), y, card_w, card_h)
            unlocked = index < self.game_logic.unlocked_level_count
            current = index == self.game_logic.current_level_index
            fill = (58, 72, 96) if unlocked else (42, 45, 56)
            border = (255, 220, 100) if current else ((120, 210, 160) if unlocked else (85, 88, 98))
            pygame.draw.rect(surface, fill, rect, border_radius=8)
            pygame.draw.rect(surface, border, rect, 3, border_radius=8)

            num = self.font_large.render(str(index + 1), True, (255, 255, 255) if unlocked else (130, 130, 140))
            surface.blit(num, (rect.x + 18, rect.y + 14))
            name = self.font_medium.render(level['name'], True, (255, 255, 255) if unlocked else (145, 145, 155))
            surface.blit(name, (rect.x + 58, rect.y + 22))
            state = "可挑战" if unlocked else "未解锁"
            state_color = (150, 255, 180) if unlocked else (150, 150, 160)
            state_surf = self.font_small.render(state, True, state_color)
            surface.blit(state_surf, (rect.x + 58, rect.y + 62))
            if unlocked:
                self.level_buttons.append((index, rect))

        tips = [
            "键盘 1-5 也可以选择已解锁关卡。",
            "按 B 返回开始界面，游戏中按 L 返回关卡选择。",
        ]
        ty = 410
        for line in tips:
            surf = self.font_small.render(line, True, (190, 198, 210))
            surface.blit(surf, surf.get_rect(center=(self.window_width // 2, ty)))
            ty += 30

    def _draw_top_bar(self, surface):
        level = self.game_logic.get_current_level()
        panel = pygame.Rect(24, 18, self.window_width - 48, 72)
        pygame.draw.rect(surface, (20, 24, 36), panel, border_radius=8)
        pygame.draw.rect(surface, (75, 84, 110), panel, 2, border_radius=8)

        title = f"第 {self.game_logic.current_level_index + 1} 关  {level['name']}"
        surface.blit(self.font_medium.render(title, True, (255, 236, 150)), (44, 28))
        surface.blit(self.font_small.render(level['objective'], True, (225, 230, 238)), (44, 58))

        slots = len(level.get('goal_slots', []))
        done = sum(1 for ok in self.game_logic.last_goal_matches if ok)
        progress = self.font_medium.render(f"{done}/{slots}", True, (150, 255, 180))
        surface.blit(progress, progress.get_rect(midright=(self.window_width - 48, 54)))

    def _draw_hint(self, surface):
        hint = self._hints[self._current_hint]
        text_surf = self.font_small.render(hint, True, (180, 190, 205))
        surface.blit(text_surf, text_surf.get_rect(center=(self.window_width // 2, self.window_height - 34)))

    def _draw_hand_indicator(self, surface, hand_data):
        indicator_x = self.window_width - 70
        indicator_y = 128
        radius = 24
        if hand_data is None or not hand_data.is_valid():
            color = (110, 110, 120)
            label = "等待"
        elif hand_data.gesture.value == 'grab':
            color = (220, 70, 70)
            label = "抓"
        else:
            color = (70, 210, 110)
            label = "放"
        pygame.draw.circle(surface, color, (indicator_x, indicator_y), radius, 3)
        text_surf = self.font_small.render(label, True, (255, 255, 255))
        surface.blit(text_surf, text_surf.get_rect(center=(indicator_x, indicator_y)))

    def _draw_completed(self, surface):
        box = pygame.Rect(0, 0, 520, 170)
        box.center = (self.window_width // 2, 168)
        pygame.draw.rect(surface, (24, 38, 35), box, border_radius=8)
        pygame.draw.rect(surface, (130, 255, 170), box, 3, border_radius=8)
        title = self.font_large.render("完成啦！", True, (160, 255, 180))
        surface.blit(title, title.get_rect(center=(box.centerx, box.y + 50)))
        unlocked_more = self.game_logic.current_level_index + 1 < len(self.game_logic.levels)
        text = "按 N 进入下一关，或按 L 返回选关" if unlocked_more else "五关全部完成，按 L 回到选关"
        surf = self.font_medium.render(text, True, (235, 240, 245))
        surface.blit(surf, surf.get_rect(center=(box.centerx, box.y + 112)))


class ParticleSystem:
    """Simple particle system for visual effects."""

    def __init__(self):
        self.particles = []

    def spawn(self, x, y, color, count=8, speed=3):
        import math
        import random
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            vx = math.cos(angle) * random.uniform(1, speed)
            vy = math.sin(angle) * random.uniform(1, speed)
            self.particles.append({
                'x': x, 'y': y, 'vx': vx, 'vy': vy,
                'color': color, 'life': 1.0,
                'size': random.uniform(3, 6)
            })

    def update(self, dt=1.0):
        for p in self.particles[:]:
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
            p['vy'] += 0.15 * dt
            p['life'] -= dt * 0.03
            if p['life'] <= 0:
                self.particles.remove(p)

    def draw(self, surface):
        for p in self.particles:
            size = int(p['size'] * p['life'])
            if size > 0:
                pygame.draw.circle(surface, p['color'], (int(p['x']), int(p['y'])), size)


class CameraPreview:
    """Camera preview placeholder."""

    def __init__(self, config):
        self.enabled = False
        self.current_frame = None

    def update_frame(self, frame):
        pass

    def draw(self, surface):
        pass
