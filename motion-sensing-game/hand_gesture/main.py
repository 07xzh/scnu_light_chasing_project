"""
Parent-child block puzzle game.

Players use a tracked hand to grab blocks and complete five shape-building
levels with tolerant target silhouettes.
"""

import time

import cv2
import pygame

from camera import GestureState, HandData, create_camera
from config import (
    BLOCK_SHAPES,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    COLOR_BACKGROUND,
    DEBUG_MODE,
    GRAVITY,
    TARGET_FPS,
    WINDOW_HEIGHT,
    WINDOW_TITLE,
    WINDOW_WIDTH,
)
from game_logic import GameLogic
from objects import ObjectManager
from ui import ParticleSystem, UIManager


class BlockBuildingGame:
    """Main game class."""

    def __init__(self):
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()

        self.config = {
            'window_width': WINDOW_WIDTH,
            'window_height': WINDOW_HEIGHT,
            'camera_width': CAMERA_WIDTH,
            'camera_height': CAMERA_HEIGHT,
            'gravity': GRAVITY,
            'grab_distance_threshold': 70,
            'platform_y': 500,
            'platform_width': 520,
            'platform_height': 20,
            'object_count': 15,
            'object_size_min': 45,
            'object_size_max': 80,
            'block_colors': [
                (255, 120, 120), (120, 255, 120), (120, 120, 255),
                (255, 255, 120), (255, 120, 255), (120, 255, 255),
                (255, 180, 120), (180, 120, 255),
            ],
            'block_shapes': BLOCK_SHAPES,
        }

        self.camera_source = "orbbec"
        try:
            self.camera = create_camera(self.camera_source, CAMERA_WIDTH, CAMERA_HEIGHT)
            print(f"[Game] Camera initialized: {self.camera_source}")
        except Exception as e:
            print(f"[Game] Camera init failed: {e}")
            self.camera = create_camera("webcam", CAMERA_WIDTH, CAMERA_HEIGHT)

        self.game_logic = GameLogic(self.config)
        self.object_manager = ObjectManager(self.config)
        self.object_manager.setup_level(self.game_logic.get_current_level())
        self.ui_manager = UIManager(self.config, self.game_logic)
        self.particle_system = ParticleSystem()

        self.running = True
        self.paused = False
        self.last_time = time.time()
        self._last_shortcut_time = 0
        self._shortcut_delay = 0.22
        self.hand_data = HandData()
        self.camera_surface = None

        self.background = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.background.fill(COLOR_BACKGROUND)
        for x in range(0, WINDOW_WIDTH, 50):
            pygame.draw.line(self.background, (30, 30, 45), (x, 0), (x, WINDOW_HEIGHT))
        for y in range(0, WINDOW_HEIGHT, 50):
            pygame.draw.line(self.background, (30, 30, 45), (0, y), (WINDOW_WIDTH, y))

        self.font_medium = self._load_font(24)

    def _load_font(self, size):
        try:
            import os
            for fp in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf'):
                if os.path.exists(fp):
                    return pygame.font.Font(fp, size)
        except Exception:
            pass
        return pygame.font.Font(None, size + 8)

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and self.ui_manager.show_tutorial:
                action = self.ui_manager.handle_click(event.pos)
                self._handle_menu_action(action)

    def _handle_menu_action(self, action):
        if action == 'start':
            self.object_manager.setup_level(self.game_logic.get_current_level())
            self.ui_manager.dismiss_tutorial()
        elif action == 'levels':
            self.ui_manager.show_level_select()
        elif action == 'back':
            self.ui_manager.show_main_menu()
        elif isinstance(action, int) and self.game_logic.select_level(action):
            self.object_manager.setup_level(self.game_logic.get_current_level())
            self.ui_manager.dismiss_tutorial()

    def _handle_command_key(self, key):
        """Handle letter shortcuts by key code so IME unicode cannot swallow them."""
        if key == pygame.K_l:
            self.ui_manager.show_level_select()
            self.paused = False
            return True

        if key == pygame.K_b:
            self.ui_manager.show_main_menu()
            self.paused = False
            return True

        if key == pygame.K_r:
            if self.ui_manager.mode == 'main_menu':
                return False
            self.ui_manager.dismiss_tutorial()
            self.paused = False
            self._reset_game()
            return True

        if key == pygame.K_n:
            if self.game_logic.level_completed and self.game_logic.next_level():
                self.object_manager.setup_level(self.game_logic.get_current_level())
                self.paused = False
            elif self.game_logic.level_completed:
                self.ui_manager.show_level_select()
            return True

        return False

    def _handle_key(self, event):
        key = event.key

        if key == pygame.K_ESCAPE:
            self.running = False
            return

        if self._handle_command_key(key):
            return

        if self.ui_manager.show_tutorial:
            if self.ui_manager.mode == 'main_menu' and key in (pygame.K_RETURN, pygame.K_SPACE):
                self._handle_menu_action('start')
            elif self.ui_manager.mode == 'main_menu' and key == pygame.K_g:
                self._handle_menu_action('levels')
            elif self.ui_manager.mode == 'level_select' and pygame.K_1 <= key <= pygame.K_5:
                index = key - pygame.K_1
                if self.game_logic.select_level(index):
                    self.object_manager.setup_level(self.game_logic.get_current_level())
                    self.ui_manager.dismiss_tutorial()
            elif self.ui_manager.mode == 'level_select' and key in (pygame.K_RETURN, pygame.K_SPACE):
                self.ui_manager.dismiss_tutorial()
            return

        if key == pygame.K_SPACE:
            self.paused = not self.paused

    def _poll_keyboard_shortcuts(self):
        """Second input path for keyboards/IMEs that do not emit usable letter events."""
        now = time.time()
        if now - self._last_shortcut_time < self._shortcut_delay:
            return

        pressed = pygame.key.get_pressed()
        for key in (pygame.K_l, pygame.K_r, pygame.K_n, pygame.K_b):
            if pressed[key]:
                self._handle_command_key(key)
                self._last_shortcut_time = now
                return

    def _update_camera(self):
        try:
            frame, depth, hand_data = self.camera.read()
            if frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.camera_surface = pygame.surfarray.make_surface(frame_rgb.swapaxes(0, 1))
            if hand_data is not None:
                self.hand_data = hand_data
        except Exception as e:
            if DEBUG_MODE:
                print(f"[Game] Camera update error: {e}")

    def _update(self, dt):
        if self.paused or self.ui_manager.show_tutorial:
            return

        self._update_camera()
        self.game_logic.process_hand(self.hand_data, self.object_manager)
        self.object_manager.update(dt)
        self.game_logic.update_goal_state(self.object_manager)
        self.object_manager.set_goal_matches(self.game_logic.last_goal_matches)
        self.ui_manager.update(dt)
        self.particle_system.update(dt)

    def _render(self):
        self.screen.blit(self.background, (0, 0))

        if self.camera_surface is not None and not self.ui_manager.show_tutorial:
            cam_w, cam_h = self.camera_surface.get_size()
            scale = min(WINDOW_WIDTH / cam_w, WINDOW_HEIGHT / cam_h) * 0.6
            new_w = int(cam_w * scale)
            new_h = int(cam_h * scale)
            x = (WINDOW_WIDTH - new_w) // 2
            y = (WINDOW_HEIGHT - new_h) // 2
            scaled = pygame.transform.scale(self.camera_surface, (new_w, new_h))
            scaled.set_alpha(115)
            self.screen.blit(scaled, (x, y))
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 35))
            self.screen.blit(overlay, (0, 0))

        self.object_manager.draw(self.screen)
        self.particle_system.draw(self.screen)
        if not self.ui_manager.show_tutorial:
            self._draw_hand_indicator()
        self.ui_manager.draw(self.screen, self.hand_data)

        if self.paused:
            self._draw_pause_overlay()

        pygame.display.flip()

    def _draw_hand_indicator(self):
        if self.hand_data is None or not self.hand_data.is_valid():
            return

        game_x = int(self.hand_data.palm_x * WINDOW_WIDTH)
        game_y = int(self.hand_data.palm_y * WINDOW_HEIGHT)
        if self.hand_data.gesture == GestureState.GRAB:
            color = (200, 50, 50)
            label = "抓取"
        elif self.hand_data.gesture == GestureState.OPEN:
            color = (50, 200, 50)
            label = "张开"
        else:
            color = (100, 100, 100)
            label = "识别中"

        pygame.draw.circle(self.screen, color, (game_x, game_y), 12, 2)
        pygame.draw.circle(self.screen, (255, 255, 255), (game_x, game_y), 4, 1)
        pygame.draw.circle(self.screen, color, (game_x, game_y), 60, 1)
        text_surf = self.font_medium.render(label, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=(game_x, game_y - 35))
        pygame.draw.rect(self.screen, (30, 30, 40), text_rect.inflate(12, 6), border_radius=4)
        self.screen.blit(text_surf, text_rect)

    def _draw_pause_overlay(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        text = self.font_medium.render("游戏暂停", True, (255, 255, 255))
        self.screen.blit(text, text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 40)))
        instructions = ["空格继续", "R 重玩当前关", "L 返回选关", "ESC 退出"]
        y = WINDOW_HEIGHT // 2 + 10
        for line in instructions:
            surf = self.font_medium.render(line, True, (210, 215, 225))
            self.screen.blit(surf, surf.get_rect(center=(WINDOW_WIDTH // 2, y)))
            y += 32

    def _reset_game(self):
        self.game_logic.reset()
        self.object_manager.release_all()
        self.object_manager.setup_level(self.game_logic.get_current_level())
        self.particle_system.particles.clear()

    def run(self):
        print("[Game] Parent-child block puzzle")
        print("Controls: 1-5=level, SPACE=pause, R=retry, L=level select, N=next, ESC=quit")

        while self.running:
            current_time = time.time()
            dt = (current_time - self.last_time) * 60
            self.last_time = current_time
            self._handle_events()
            self._poll_keyboard_shortcuts()
            self._update(dt)
            self._render()
            self.clock.tick(TARGET_FPS)

        self.cleanup()

    def cleanup(self):
        print("[Game] Cleaning up...")
        try:
            self.camera.close()
        except Exception:
            pass
        pygame.quit()


def main():
    try:
        game = BlockBuildingGame()
        game.run()
    except KeyboardInterrupt:
        print("\n[Game] Exited")
    except Exception as e:
        print(f"[Game] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
