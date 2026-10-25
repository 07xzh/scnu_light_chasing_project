"""双人水果对抗游戏主程序。

本文件负责：
1. 定义游戏规则与状态：分数、生命、倒计时、胜负判定。
2. 生成和更新水果/炸弹。
3. 绘制游戏背景、HUD、开始界面、结算界面和特效。
4. 管理 Pygame 主循环、相机输入、键盘/鼠标事件。

手部识别和刀线绘制在 pose_input.py 中；相机适配在 camera_backends.py 中。
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pygame

from camera_backends import OBSensorCamera, OrbbecColorCamera, WebcamCamera
from orbbec_rgbd import OrbbecRgbdCamera
from pose_input import KeyboardInput, PlayerInput, SplitPoseInput, all_segments, draw_player_input

# ---------------------------------------------------------------------------
# 基础游戏参数
# ---------------------------------------------------------------------------

WIDTH = 1600
HEIGHT = 900
FPS = 60

# 手刀移动速度超过该阈值才算“切割”，数值越小越灵敏。
CUT_SPEED = 28.0

# 水果抛物线重力。数值越大，下落越快。
GRAVITY = 2240.0

# 姘存灉鏈€楂樼偣锛氫粠搴曢儴寰€涓婄害 3/4 灞忓箷楂樺害锛岄伩鍏嶉寰楄繃楂樸€?
FRUIT_APEX_Y = HEIGHT * 0.25

# 单局时长：时间结束后按分数判胜。
GAME_DURATION = 60.0

MIN_ACTIVE_ITEMS = 2
MAX_ACTIVE_ITEMS = 3

Point = Tuple[float, float]
CHINESE_FONT_PATH: Optional[str] = None
_FONT_CACHE: Dict[Tuple[Optional[str], int, bool], pygame.font.Font] = {}
_BASE_BACKGROUND: Optional[pygame.Surface] = None
_CAMERA_BACKGROUND: Optional[pygame.Surface] = None
_CAMERA_TINT: Optional[pygame.Surface] = None
CAMERA_BACKGROUND_SIZE = (WIDTH // 2, HEIGHT // 2)

# ---------------------------------------------------------------------------
# 视觉主题色：参考明亮自然、低多边形海岛风格
# ---------------------------------------------------------------------------

COLOR_BG = (154, 213, 225)
COLOR_GRID = (132, 194, 206)
COLOR_PANEL = (255, 247, 224)
COLOR_PANEL_EDGE = (94, 145, 128)
COLOR_TEXT = (53, 76, 75)
COLOR_MUTED = (97, 124, 120)
COLOR_GRASS = (111, 184, 116)
COLOR_GRASS_DARK = (78, 146, 102)
COLOR_SAND = (236, 210, 151)


@dataclass
class PlayerState:
    """单个玩家的比赛状态。"""

    player_id: int
    name: str
    lives: int = 3
    score: int = 0


@dataclass
class FlyingItem:
    """飞行中的水果或炸弹。

    owner_side 用于限制物体归属：左半屏只由玩家 1 切，右半屏只由玩家 2 切。
    """

    kind: str
    owner_side: int
    pos: np.ndarray
    vel: np.ndarray
    radius: int
    color: Tuple[int, int, int]
    alive: bool = True
    cut_flash: float = 0.0

    @property
    def is_bomb(self) -> bool:
        return self.kind == "bomb"


@dataclass
class CutEffect:
    """切中后的短暂爆裂特效状态。"""

    pos: np.ndarray
    color: Tuple[int, int, int]
    is_bomb: bool
    ttl: float = 0.22
    age: float = 0.0


def find_chinese_font() -> Optional[str]:
    """查找可正常显示中文的字体。

    Pygame 的 SysFont 在部分 Windows 环境里可能会选到缺中文的字体，
    导致文字显示成方框，所以这里优先显式加载中文字体文件。
    """

    candidates = [
        "C:/Windows/Fonts/NotoSansSC-VF.ttf",
        "C:/Windows/Fonts/SIMYOU.TTF",
        "C:/Windows/Fonts/Deng.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/NotoSansCJK-Regular.ttc",
    ]
    for item in candidates:
        if Path(item).exists():
            return item
    return None


def ui_font(size: int, bold: bool = False) -> pygame.font.Font:
    """创建 UI 字体对象。"""

    cache_key = (CHINESE_FONT_PATH, size, bold)
    cached = _FONT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if CHINESE_FONT_PATH:
        font = pygame.font.Font(CHINESE_FONT_PATH, size)
        font.set_bold(bold)
    else:
        font = pygame.font.SysFont("arial", size, bold=bold)
    _FONT_CACHE[cache_key] = font
    return font


def draw_text_with_shadow(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: Tuple[int, int],
    color: Tuple[int, int, int],
    shadow: Tuple[int, int, int] = (44, 33, 36),
    offset: Tuple[int, int] = (3, 4),
) -> pygame.Rect:
    """绘制带阴影的文字，用于需要稍微突出的标题。"""

    shadow_img = font.render(text, True, shadow)
    text_img = font.render(text, True, color)
    surface.blit(shadow_img, (pos[0] + offset[0], pos[1] + offset[1]))
    return surface.blit(text_img, pos)


def draw_round_line(
    surface: pygame.Surface,
    color: Tuple[int, int, int] | Tuple[int, int, int, int],
    start: Point,
    end: Point,
    width: int,
) -> None:
    """绘制圆头线段。

    pygame.draw.line 默认线段端点偏硬，这里额外在两端画圆，让分割线、
    手刀和装饰线条更柔和。
    """

    pygame.draw.line(surface, color, start, end, width)
    radius = max(1, width // 2)
    pygame.draw.circle(surface, color, (int(start[0]), int(start[1])), radius)
    pygame.draw.circle(surface, color, (int(end[0]), int(end[1])), radius)


def dist_point_to_segment(point: Point, start: Point, end: Point) -> float:
    """计算点到线段的最短距离。

    切割判定用它判断水果中心是否足够接近手刀线段。
    """

    p = np.array(point, dtype=float)
    a = np.array(start, dtype=float)
    b = np.array(end, dtype=float)
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom <= 0.0001:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / denom, 0.0, 1.0))
    projection = a + t * ab
    return float(np.linalg.norm(p - projection))


def spawn_item() -> FlyingItem:
    """随机生成一个水果或炸弹。

    物体从屏幕底部抛出，按左右半屏随机分配给对应玩家。
    """

    side = random.choice([1, 2])
    x_min, x_max = (80, WIDTH // 2 - 80) if side == 1 else (WIDTH // 2 + 80, WIDTH - 80)
    x = random.uniform(x_min, x_max)
    y = HEIGHT + 92
    vx = random.uniform(-36, 36)
    apex_y = random.uniform(FRUIT_APEX_Y - 35, FRUIT_APEX_Y + 55)
    vy = -math.sqrt(max(0.0, 2.0 * GRAVITY * (y - apex_y)))
    kind = "bomb" if random.random() < 0.22 else random.choice(["apple", "orange", "melon", "berry"])
    colors = {
        "apple": (221, 92, 86),
        "orange": (235, 156, 72),
        "melon": (101, 178, 107),
        "berry": (124, 116, 184),
        "bomb": (62, 74, 80),
    }
    radius = 46 if kind != "bomb" else 54
    return FlyingItem(kind, side, np.array([x, y], dtype=float), np.array([vx, vy], dtype=float), radius, colors[kind])


def create_camera(input_mode: str, camera_index: int):
    """创建相机输入后端。

    auto 模式优先尝试 Orbbec SDK，失败后尝试普通 webcam；
    如果都不可用，主循环会回退到键盘模拟输入。
    """

    if input_mode == "keyboard":
        return None
    if input_mode == "obsensor":
        camera = OBSensorCamera(camera_index)
        camera.start()
        return camera
    if input_mode == "orbbec":
        camera = OrbbecRgbdCamera()
        camera.start()
        return camera
    if input_mode == "webcam":
        camera = WebcamCamera(camera_index)
        camera.start()
        return camera

    for factory in (lambda: OBSensorCamera(camera_index), OrbbecRgbdCamera, lambda: WebcamCamera(camera_index)):
        try:
            camera = factory()
            camera.start()
            return camera
        except Exception:
            continue
    return None


def camera_frame_surface(bgr_frame: np.ndarray, size: Tuple[int, int] = CAMERA_BACKGROUND_SIZE) -> pygame.Surface:
    """把 OpenCV BGR 图像转换成 Pygame Surface。

    相机画面会镜像显示，使玩家动作方向更符合“照镜子”的直觉。
    """

    frame = cv2.flip(bgr_frame, 1)
    frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))


def base_background_surface() -> pygame.Surface:
    global _BASE_BACKGROUND

    if _BASE_BACKGROUND is not None:
        return _BASE_BACKGROUND

    background = pygame.Surface((WIDTH, HEIGHT)).convert()
    for y in range(0, HEIGHT, 6):
        t = y / HEIGHT
        color = (
            int(164 - t * 18),
            int(220 - t * 35),
            int(230 - t * 38),
        )
        pygame.draw.rect(background, color, (0, y, WIDTH, 6))

    pygame.draw.circle(background, (255, 225, 128), (142, 116), 58)
    pygame.draw.circle(background, (255, 241, 174), (120, 96), 18)
    pygame.draw.polygon(background, (110, 172, 154), [(0, 460), (220, 330), (510, 462)])
    pygame.draw.polygon(background, (96, 157, 141), [(360, 462), (650, 300), (1000, 462)])
    pygame.draw.polygon(background, (122, 186, 162), [(940, 462), (1240, 330), (1600, 462)])
    pygame.draw.rect(background, (102, 178, 194), (0, 452, WIDTH, 118))
    pygame.draw.rect(background, COLOR_SAND, (0, 560, WIDTH, 74))
    pygame.draw.rect(background, COLOR_GRASS, (0, 620, WIDTH, HEIGHT - 620))
    pygame.draw.polygon(background, COLOR_GRASS_DARK, [(0, 724), (320, 664), (760, 742), (1180, 656), (1600, 710), (1600, 900), (0, 900)])
    pygame.draw.rect(background, (78, 127, 116), (WIDTH // 2 - 4, 0, 8, HEIGHT))
    pygame.draw.rect(background, (255, 247, 224), (WIDTH // 2 - 1, 0, 2, HEIGHT))

    _BASE_BACKGROUND = background
    return background


def camera_tint_surface() -> pygame.Surface:
    global _CAMERA_TINT

    if _CAMERA_TINT is None:
        _CAMERA_TINT = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        _CAMERA_TINT.fill((255, 244, 214, 38))
    return _CAMERA_TINT


def draw_camera_background(screen: pygame.Surface, bgr_frame: np.ndarray) -> None:
    global _CAMERA_BACKGROUND

    camera_surface = camera_frame_surface(bgr_frame)
    if _CAMERA_BACKGROUND is None:
        _CAMERA_BACKGROUND = pygame.Surface((WIDTH, HEIGHT)).convert()
    pygame.transform.scale(camera_surface, (WIDTH, HEIGHT), _CAMERA_BACKGROUND)
    _CAMERA_BACKGROUND.set_alpha(105)
    screen.blit(_CAMERA_BACKGROUND, (0, 0))
    screen.blit(camera_tint_surface(), (0, 0))


def draw_background(screen: pygame.Surface, source_name: str, bgr_frame: Optional[np.ndarray]) -> None:
    """绘制游戏背景。

    背景采用明亮自然的低多边形海岛风格；如果有相机画面，则以低透明度
    叠加，既能看见玩家，又不会抢走游戏元素的视觉重点。
    """

    screen.blit(base_background_surface(), (0, 0))

    if bgr_frame is not None:
        draw_camera_background(screen, bgr_frame)

    font = ui_font(18)
    label = font.render(f"input: {source_name}", True, COLOR_MUTED)
    screen.blit(label, (WIDTH - label.get_width() - 18, HEIGHT - 34))


def draw_hud(screen: pygame.Surface, players: Dict[int, PlayerState], game_winner: Optional[int], match_time: float) -> None:
    """绘制比赛 HUD：分数、生命、倒计时、操作提示和结算弹窗。"""

    font = ui_font(28, bold=True)
    small = ui_font(20)
    for pid, player in players.items():
        panel_width = 300
        panel = pygame.Rect(34 if pid == 1 else WIDTH - 34 - panel_width, 24, panel_width, 78)
        x = panel.x + 18
        accent = (63, 151, 174) if pid == 1 else (229, 154, 74)
        pygame.draw.rect(screen, (73, 111, 97), panel.move(0, 4), border_radius=12)
        pygame.draw.rect(screen, COLOR_PANEL, panel, border_radius=10)
        pygame.draw.rect(screen, COLOR_PANEL_EDGE, panel, 2, border_radius=10)
        pygame.draw.rect(screen, accent, (panel.x, panel.y, 8, panel.height), border_radius=4)
        name = font.render(f"{player.name}  {player.score}", True, COLOR_TEXT)
        screen.blit(name, (x + 8, panel.y + 10))
        for i in range(3):
            cx = panel.x + 38 + i * 38
            color = (232, 65, 85) if i < player.lives else (74, 80, 92)
            pygame.draw.circle(screen, color, (cx, panel.y + 56), 12)
            pygame.draw.circle(screen, (116, 143, 132), (cx, panel.y + 56), 12, 2)
    hint_text = "R 重开    Esc 退出"
    hint = small.render(hint_text, True, COLOR_MUTED)
    hint_rect = pygame.Rect(56, HEIGHT - 58, hint.get_width() + 30, 36)
    pygame.draw.rect(screen, (73, 111, 97), hint_rect.move(0, 3), border_radius=8)
    pygame.draw.rect(screen, COLOR_PANEL, hint_rect, border_radius=8)
    pygame.draw.rect(screen, COLOR_PANEL_EDGE, hint_rect, 1, border_radius=8)
    screen.blit(hint, (hint_rect.x + 15, hint_rect.y + 5))
    timer_text = f"{max(0, int(match_time + 0.999)):02d}s"
    timer = font.render(timer_text, True, COLOR_TEXT)
    timer_panel = pygame.Rect(0, 0, 128, 54)
    timer_panel.center = (WIDTH // 2, 58)
    pygame.draw.rect(screen, (73, 111, 97), timer_panel.move(0, 3), border_radius=12)
    pygame.draw.rect(screen, COLOR_PANEL, timer_panel, border_radius=10)
    pygame.draw.rect(screen, COLOR_PANEL_EDGE, timer_panel, 2, border_radius=10)
    screen.blit(timer, (timer_panel.centerx - timer.get_width() // 2, timer_panel.centery - timer.get_height() // 2))

    if game_winner is not None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((39, 75, 74, 150))
        screen.blit(overlay, (0, 0))
        big = ui_font(72, bold=True)
        result_text = "平局" if game_winner == 0 else f"玩家 {game_winner} 胜利"
        text = big.render(result_text, True, COLOR_TEXT)
        sub = small.render("按 R 重新开始", True, COLOR_MUTED)
        box = pygame.Rect(0, 0, 560, 230)
        box.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(screen, COLOR_PANEL, box, border_radius=14)
        pygame.draw.rect(screen, COLOR_PANEL_EDGE, box, 2, border_radius=14)
        screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 72))
        screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 18))
        restart_button = pygame.Rect(0, 0, 190, 52)
        start_button = pygame.Rect(0, 0, 190, 52)
        restart_button.center = (WIDTH // 2 - 110, HEIGHT // 2 + 82)
        start_button.center = (WIDTH // 2 + 110, HEIGHT // 2 + 82)
        pygame.draw.rect(screen, (88, 168, 112), restart_button, border_radius=8)
        pygame.draw.rect(screen, (219, 245, 207), restart_button, 2, border_radius=8)
        pygame.draw.rect(screen, (63, 151, 174), start_button, border_radius=8)
        pygame.draw.rect(screen, (219, 245, 207), start_button, 2, border_radius=8)
        restart_label = small.render("重新开始", True, (255, 255, 255))
        start_label = small.render("返回开始", True, (255, 255, 255))
        screen.blit(restart_label, (restart_button.centerx - restart_label.get_width() // 2, restart_button.centery - restart_label.get_height() // 2))
        screen.blit(start_label, (start_button.centerx - start_label.get_width() // 2, start_button.centery - start_label.get_height() // 2))


def draw_fps(screen: pygame.Surface, fps: float) -> None:
    """调试用 FPS 显示，使用 --show-fps 开启。"""

    font = ui_font(18)
    label = font.render(f"FPS {fps:4.1f}", True, COLOR_TEXT)
    rect = pygame.Rect(WIDTH - label.get_width() - 42, 20, label.get_width() + 24, 34)
    pygame.draw.rect(screen, (73, 111, 97), rect.move(0, 3), border_radius=10)
    pygame.draw.rect(screen, COLOR_PANEL, rect, border_radius=10)
    pygame.draw.rect(screen, COLOR_PANEL_EDGE, rect, 1, border_radius=10)
    screen.blit(label, (rect.x + 12, rect.y + 5))


def draw_start_screen(screen: pygame.Surface, source_name: str, bgr_frame: Optional[np.ndarray]) -> pygame.Rect:
    """绘制开始界面，并返回“开始游戏”按钮区域。"""

    draw_background(screen, source_name, None)
    wash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    wash.fill((255, 246, 218, 82))
    screen.blit(wash, (0, 0))

    panel = pygame.Rect(0, 0, 660, 390)
    panel.center = (WIDTH // 2, HEIGHT // 2)
    pygame.draw.rect(screen, (73, 111, 97), panel.move(0, 8), border_radius=18)
    pygame.draw.rect(screen, COLOR_PANEL, panel, border_radius=12)
    pygame.draw.rect(screen, COLOR_PANEL_EDGE, panel, 2, border_radius=12)
    pygame.draw.line(screen, COLOR_GRASS_DARK, (panel.x + 64, panel.y + 108), (panel.right - 64, panel.y + 108), 3)

    title_font = ui_font(58, bold=True)
    text_font = ui_font(24)
    button_font = ui_font(34, bold=True)

    title_text = "双人水果对抗"
    title = title_font.render(title_text, True, COLOR_TEXT)
    subtitle = text_font.render("手腕到小拇指指尖作为切割刀", True, COLOR_MUTED)
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, panel.y + 22))
    screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, panel.y + 132))

    info_font = ui_font(20)
    lines = ["左半屏：玩家 1", "右半屏：玩家 2", "切水果得分，碰到炸弹扣生命"]
    for index, line in enumerate(lines):
        item = info_font.render(line, True, COLOR_TEXT)
        screen.blit(item, (panel.x + 115, panel.y + 178 + index * 34))

    button_rect = pygame.Rect(0, 0, 250, 66)
    button_rect.center = (WIDTH // 2, panel.bottom - 70)
    mouse_over = button_rect.collidepoint(pygame.mouse.get_pos())
    button_color = (108, 190, 126) if mouse_over else (88, 168, 112)
    pygame.draw.rect(screen, button_color, button_rect, border_radius=8)
    pygame.draw.rect(screen, (219, 245, 207), button_rect, 2, border_radius=8)
    label = button_font.render("开始游戏", True, (255, 255, 255))
    screen.blit(label, (button_rect.centerx - label.get_width() // 2, button_rect.centery - label.get_height() // 2))

    hint = text_font.render("点击按钮或按空格开始", True, COLOR_MUTED)
    screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, panel.bottom + 28))
    return button_rect


def draw_item(screen: pygame.Surface, item: FlyingItem) -> None:
    """绘制水果或炸弹。"""

    x, y = int(item.pos[0]), int(item.pos[1])
    shadow = pygame.Surface((item.radius * 3, item.radius * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 42), (0, item.radius // 2, item.radius * 3, item.radius))
    screen.blit(shadow, (x - item.radius * 3 // 2, y + item.radius // 2))
    if item.is_bomb:
        pygame.draw.circle(screen, (42, 60, 60), (x, y + 4), item.radius + 3)
        pygame.draw.circle(screen, item.color, (x, y), item.radius)
        pygame.draw.circle(screen, (100, 118, 116), (x - 12, y - 14), item.radius // 4)
        draw_round_line(screen, (230, 190, 75), (x + 22, y - 30), (x + 44, y - 54), 6)
        pygame.draw.circle(screen, (246, 214, 105), (x + 48, y - 58), 8)
    else:
        pygame.draw.circle(screen, tuple(max(0, c - 55) for c in item.color), (x, y + 4), item.radius + 3)
        pygame.draw.circle(screen, item.color, (x, y), item.radius)
        pygame.draw.circle(screen, tuple(min(255, c + 28) for c in item.color), (x - item.radius // 5, y - item.radius // 6), item.radius - 18)
        pygame.draw.circle(screen, (238, 240, 246), (x - 14, y - 16), 7)
        draw_round_line(screen, (92, 66, 38), (x, y - item.radius + 8), (x + 11, y - item.radius - 13), 5)
        pygame.draw.ellipse(screen, (72, 190, 98), (x + 8, y - item.radius - 21, 28, 14))


def draw_cut_burst(screen: pygame.Surface, effect: CutEffect) -> None:
    """绘制切中瞬间的扩散特效。"""

    cx, cy = int(effect.pos[0]), int(effect.pos[1])
    layer_size = 140
    half = layer_size // 2
    layer = pygame.Surface((layer_size, layer_size), pygame.SRCALPHA)
    local_center = (half, half)
    progress = min(effect.age / effect.ttl, 1.0)
    alpha = int(180 * (1.0 - progress))
    burst_color = (255, 86, 62) if effect.is_bomb else effect.color
    for angle in np.linspace(0, np.pi * 2.0, 12, endpoint=False):
        length = (36 if effect.is_bomb else 26) * (0.55 + progress)
        end = (int(half + np.cos(angle) * length), int(half + np.sin(angle) * length))
        pygame.draw.line(layer, (*burst_color, alpha), local_center, end, 3)
    pygame.draw.circle(layer, (238, 240, 246, max(alpha - 50, 0)), local_center, int(12 + progress * 12))
    screen.blit(layer, (cx - half, cy - half))


def reset_game() -> Tuple[Dict[int, PlayerState], List[FlyingItem], List[CutEffect], Optional[int], float]:
    """重置一局比赛的动态状态。

    返回值中的 Optional[int] 表示胜利者：
    - None：比赛未结束
    - 0：平局
    - 1/2：对应玩家获胜
    """

    return (
        {
            1: PlayerState(1, "玩家 1"),
            2: PlayerState(2, "玩家 2"),
        },
        [],
        [],
        None,
        0.0,
    )


def handle_cuts(
    items: List[FlyingItem],
    players: Dict[int, PlayerState],
    inputs: Dict[int, PlayerInput],
    effects: List[CutEffect],
) -> Optional[int]:
    """处理所有水果/炸弹与手刀的碰撞。

    返回 loser：
    - None：无人因生命归零失败
    - 1/2：对应玩家生命归零，主循环会把胜利者设为另一个玩家
    """

    loser: Optional[int] = None
    input_segments = all_segments(inputs.values())
    for item in items:
        if not item.alive:
            continue
        for pid, segment, speed in input_segments:
            if pid != item.owner_side or speed < CUT_SPEED:
                continue
            if dist_point_to_segment(tuple(item.pos), segment[0], segment[1]) > item.radius + 42:
                continue
            item.cut_flash = 0.12
            effects.append(CutEffect(item.pos.copy(), item.color, item.is_bomb))
            item.alive = False
            if item.is_bomb:
                players[pid].lives -= 1
                if players[pid].lives <= 0:
                    loser = pid
            else:
                players[pid].score += 10
            break
    return loser


def main() -> None:
    """程序入口：初始化资源并运行 Pygame 主循环。"""

    global CHINESE_FONT_PATH

    # 命令行参数用于切换输入后端、相机编号、全屏和 FPS 调试显示。
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", choices=["auto", "obsensor", "orbbec", "webcam", "keyboard"], default="auto")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--pose-width", type=int, default=480)
    parser.add_argument("--pose-fps", type=float, default=30.0)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--show-fps", action="store_true")
    args = parser.parse_args()

    # 初始化 Pygame、中文字体、窗口和时钟。
    pygame.init()
    CHINESE_FONT_PATH = find_chinese_font()
    display_flags = pygame.FULLSCREEN if args.fullscreen else 0
    screen = pygame.display.set_mode((WIDTH, HEIGHT), display_flags)
    pygame.display.set_caption("Gemini2 双人对抗水果切除 Demo")
    clock = pygame.time.Clock()
    input_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    # 输入系统：优先用相机；如果相机不可用，自动用键盘模拟。
    source_name = "keyboard"
    camera_error: Optional[str] = None
    try:
        camera = create_camera(args.input, args.camera_index)
    except Exception as exc:
        camera = None
        camera_error = str(exc)
        source_name = f"keyboard ({camera_error})"
    keyboard = KeyboardInput(WIDTH, HEIGHT)
    pose = None
    if camera is not None:
        try:
            pose_height = max(1, int(args.pose_width * HEIGHT / WIDTH))
            pose = SplitPoseInput(WIDTH, HEIGHT, process_width=args.pose_width, process_height=pose_height, process_fps=args.pose_fps)
        except Exception as exc:
            camera_error = str(exc)
            source_name = f"keyboard ({camera_error})"
    if camera is not None:
        source_name = "camera" if pose is not None else source_name

    # 比赛状态：items 是当前飞行物，effects 是切中特效。
    players, items, effects, game_over, spawn_timer = reset_game()
    match_time = GAME_DURATION
    game_state = "start"
    prev_r_down = False
    prev_space_down = False
    r_hold_time = 0.0
    depth_print_timer = 0.0
    running = True

    def restart_match() -> None:
        """从任意状态重新开始一局。

        这里封成内部函数，是为了事件处理、按键轮询和鼠标按钮都能调用同一套逻辑，
        避免某个路径忘记重置倒计时或胜负状态。
        """

        nonlocal players, items, effects, game_over, spawn_timer, game_state, match_time, r_hold_time
        players, items, effects, game_over, spawn_timer = reset_game()
        match_time = GAME_DURATION
        r_hold_time = 0.0
        game_state = "playing"

    def return_to_start() -> None:
        """结束后返回开始界面，同时清空上一局状态。"""

        nonlocal players, items, effects, game_over, spawn_timer, game_state, match_time, r_hold_time
        players, items, effects, game_over, spawn_timer = reset_game()
        match_time = GAME_DURATION
        r_hold_time = 0.0
        game_state = "start"

    try:
        while running:
            # dt 是上一帧到当前帧的秒数，所有动画和物理都基于它更新。
            dt = clock.tick(FPS) / 1000.0

            # 事件处理：参考 hand_gesture 的 KEYDOWN 处理，同时额外做多重兜底，
            # 解决输入法/键盘布局/窗口焦点导致 R 键偶尔不响应的问题。
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    # R 键有三种判断方式：key、unicode、scancode。
                    # scancode 对键盘布局更稳定，适合做重开这种关键操作。
                    is_r_key = (
                        event.key == pygame.K_r
                        or getattr(event, "unicode", "").lower() == "r"
                        or getattr(event, "scancode", None) == pygame.KSCAN_R
                    )
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE and game_state == "start":
                        restart_match()
                    elif is_r_key:
                        restart_match()
                elif event.type == pygame.TEXTINPUT:
                    if event.text.lower() == "r":
                        restart_match()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game_state == "start":
                    # 开始页按钮点击。
                    start_rect = pygame.Rect(0, 0, 250, 66)
                    start_rect.center = (WIDTH // 2, HEIGHT // 2 + 125)
                    if start_rect.collidepoint(event.pos):
                        restart_match()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game_over is not None:
                    # 结算页“重新开始”按钮点击。
                    restart_rect = pygame.Rect(0, 0, 190, 52)
                    start_rect = pygame.Rect(0, 0, 190, 52)
                    restart_rect.center = (WIDTH // 2 - 110, HEIGHT // 2 + 82)
                    start_rect.center = (WIDTH // 2 + 110, HEIGHT // 2 + 82)
                    if restart_rect.collidepoint(event.pos):
                        restart_match()
                    elif start_rect.collidepoint(event.pos):
                        return_to_start()

            # 按键轮询兜底：即使短按事件丢失，按住 R 一小会儿也会重开。
            keys = pygame.key.get_pressed()
            r_down = keys[pygame.K_r]
            space_down = keys[pygame.K_SPACE]
            if keys[pygame.K_ESCAPE]:
                running = False
            elif r_down:
                r_hold_time += dt
                if not prev_r_down or r_hold_time > 0.18:
                    restart_match()
            elif space_down and not prev_space_down and game_state == "start":
                restart_match()
            else:
                r_hold_time = 0.0
            prev_r_down = r_down
            prev_space_down = space_down

            # 每帧读取输入。相机输入返回真实手刀；键盘输入返回模拟手刀。
            frame = camera.read() if camera is not None else None
            if pose is not None and frame is not None:
                inputs = pose.update(frame.bgr, dt, frame.depth)
                source_name = frame.source
            else:
                inputs = keyboard.update(dt)
                if camera is not None and frame is None:
                    source_name = "keyboard (camera frame lost)"

            if frame is not None and frame.depth is not None:
                depth_print_timer += dt
                if depth_print_timer >= 0.25:
                    depth_print_timer = 0.0
                    depth_parts = []
                    for pid in (1, 2):
                        depth_values = [
                            blade.depth_mm
                            for blade in inputs[pid].blades
                            if blade.depth_mm is not None
                        ]
                        if depth_values:
                            depth_parts.append(f"P{pid}: {depth_values[0]:.0f} mm")
                        else:
                            depth_parts.append(f"P{pid}: --")
                    print("[Depth] " + " | ".join(depth_parts))

            # 游戏状态更新：只有正式比赛中且尚未结束时才生成/移动物体。
            if game_state == "playing" and game_over is None:
                match_time = max(0.0, match_time - dt)
                spawn_timer -= dt
                if spawn_timer <= 0:
                    active_items = sum(1 for item in items if item.alive)
                    if active_items < MIN_ACTIVE_ITEMS:
                        target_count = random.randint(MIN_ACTIVE_ITEMS, MAX_ACTIVE_ITEMS)
                        for _ in range(target_count - active_items):
                            items.append(spawn_item())
                    spawn_timer = random.uniform(0.25, 0.45)
                for item in items:
                    item.vel[1] += GRAVITY * dt
                    item.pos += item.vel * dt
                    if item.pos[1] > HEIGHT + 90:
                        item.alive = False
                loser = handle_cuts(items, players, inputs, effects)
                if loser is not None:
                    # 生命值先耗尽：对手立即获胜。
                    game_over = 2 if loser == 1 else 1
                elif match_time <= 0:
                    # 时间到：按分数判定胜负，分数相同则平局。
                    if players[1].score > players[2].score:
                        game_over = 1
                    elif players[2].score > players[1].score:
                        game_over = 2
                    else:
                        game_over = 0
                items = [item for item in items if item.alive]

            # 特效生命周期更新。
            for effect in effects:
                effect.age += dt
            effects = [effect for effect in effects if effect.age < effect.ttl]

            # 渲染：开始界面和游戏界面分开绘制。
            if game_state == "start":
                draw_start_screen(screen, source_name, frame.bgr if frame is not None else None)
            else:
                draw_background(screen, source_name, frame.bgr if frame is not None else None)
                for item in items:
                    draw_item(screen, item)
                for effect in effects:
                    draw_cut_burst(screen, effect)
                input_layer.fill((0, 0, 0, 0))
                draw_player_input(screen, inputs[1], (58, 151, 174), input_layer)
                draw_player_input(screen, inputs[2], (229, 154, 74), input_layer)
                screen.blit(input_layer, (0, 0))
                draw_hud(screen, players, game_over, match_time)
                if args.show_fps:
                    draw_fps(screen, clock.get_fps())
            pygame.display.flip()
    finally:
        # 无论正常退出还是异常退出，都释放相机和 MediaPipe 资源。
        if pose is not None:
            pose.close()
        if camera is not None:
            camera.close()
        pygame.quit()


if __name__ == "__main__":
    main()
