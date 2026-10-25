"""玩家输入与手刀绘制。

本文件负责把“玩家动作”统一转换成游戏可用的 PlayerInput：
1. 摄像头模式：用 MediaPipe Hands 识别手腕到小拇指指尖，作为手刀。
2. 键盘模式：用 WASD/方向键模拟两名玩家的手刀，方便无设备调试。
3. 绘制模式：绘制玩家笑脸头像、手刀线、拖尾和火花。

注意：为了性能，当前版本不再做人体彩色骨架 Pose 识别，只保留手部识别。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np
import pygame

Point = Tuple[float, float]


def draw_round_line(
    surface: pygame.Surface,
    color: Tuple[int, int, int] | Tuple[int, int, int, int],
    start: Point,
    end: Point,
    width: int,
) -> None:
    """绘制圆头线段，用于手刀和拖尾。"""

    pygame.draw.line(surface, color, start, end, width)
    radius = max(1, width // 2)
    pygame.draw.circle(surface, color, (int(start[0]), int(start[1])), radius)
    pygame.draw.circle(surface, color, (int(end[0]), int(end[1])), radius)


def draw_smiley(surface: pygame.Surface, center: Point, color: Tuple[int, int, int]) -> None:
    """绘制玩家头像。

    这个头像只是轻量的状态提示，替代原先比较耗性能的人体骨架显示。
    """

    x, y = int(center[0]), int(center[1])
    pygame.draw.circle(surface, (73, 111, 97, 145), (x, y + 4), 36)
    pygame.draw.circle(surface, (255, 247, 224, 235), (x, y), 36)
    pygame.draw.circle(surface, color, (x, y), 36, 3)
    pygame.draw.circle(surface, (53, 76, 75, 230), (x - 12, y - 5), 4)
    pygame.draw.circle(surface, (53, 76, 75, 230), (x + 12, y - 5), 4)
    pygame.draw.arc(surface, (53, 76, 75, 230), (x - 17, y - 11, 34, 28), 0.18, 2.96, 3)


@dataclass
class ArmState:
    """旧版手臂输入结构。

    现在真实相机模式主要使用 BladeState；保留 ArmState 是为了键盘模拟
    和可能的后续扩展不需要大改 PlayerInput。
    """

    shoulder: Optional[Point] = None
    elbow: Optional[Point] = None
    wrist: Optional[Point] = None
    previous_wrist: Optional[Point] = None
    speed: float = 0.0
    visible: bool = False

    @property
    def blade_segments(self) -> List[Tuple[Point, Point]]:
        if not self.visible or self.elbow is None or self.wrist is None:
            return []
        segments = [(self.elbow, self.wrist)]
        if self.shoulder is not None:
            segments.append((self.shoulder, self.elbow))
        return segments


@dataclass
class BladeState:
    """一条可用于切割判定的手刀线段。

    start/end 当前表示“手腕 -> 小拇指指尖”。
    previous_center 用于计算移动速度和绘制拖尾。
    """

    start: Optional[Point] = None
    end: Optional[Point] = None
    previous_center: Optional[Point] = None
    speed: float = 0.0
    visible: bool = False
    depth_mm: Optional[float] = None

    @property
    def center(self) -> Optional[Point]:
        if self.start is None or self.end is None:
            return None
        return ((self.start[0] + self.end[0]) / 2.0, (self.start[1] + self.end[1]) / 2.0)

    @property
    def blade_segments(self) -> List[Tuple[Point, Point]]:
        if not self.visible or self.start is None or self.end is None:
            return []
        return [(self.start, self.end)]


@dataclass
class PlayerInput:
    """某一帧中单个玩家的输入数据。

    游戏主循环只关心 blade_segments 和 max_speed，因此不需要知道输入来自
    摄像头、键盘还是其他设备。
    """

    player_id: int
    arms: List[ArmState] = field(default_factory=lambda: [ArmState(), ArmState()])
    blades: List[BladeState] = field(default_factory=list)
    skeleton_segments: List[Tuple[Point, Point]] = field(default_factory=list)
    joints: List[Point] = field(default_factory=list)

    @property
    def blade_segments(self) -> List[Tuple[Point, Point]]:
        segments: List[Tuple[Point, Point]] = []
        for blade in self.blades:
            segments.extend(blade.blade_segments)
        if not segments:
            for arm in self.arms:
                segments.extend(arm.blade_segments)
        return segments

    @property
    def max_speed(self) -> float:
        blade_speed = max((blade.speed for blade in self.blades), default=0.0)
        arm_speed = max((arm.speed for arm in self.arms), default=0.0)
        return max(blade_speed, arm_speed)


class KeyboardInput:
    """键盘模拟输入。

    玩家 1 使用 WASD，玩家 2 使用方向键。它会生成和相机模式一致的
    PlayerInput，方便测试游戏逻辑、UI 和切割判定。
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.positions = {
            1: np.array([width * 0.25, height * 0.55], dtype=float),
            2: np.array([width * 0.75, height * 0.55], dtype=float),
        }
        self.prev = {1: self.positions[1].copy(), 2: self.positions[2].copy()}

    def update(self, dt: float) -> Dict[int, PlayerInput]:
        """根据当前按键状态更新两个玩家的模拟手刀。"""

        keys = pygame.key.get_pressed()
        velocity = 620.0
        moves = {
            1: np.array(
                [
                    float(keys[pygame.K_d]) - float(keys[pygame.K_a]),
                    float(keys[pygame.K_s]) - float(keys[pygame.K_w]),
                ]
            ),
            2: np.array(
                [
                    float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT]),
                    float(keys[pygame.K_DOWN]) - float(keys[pygame.K_UP]),
                ]
            ),
        }
        result: Dict[int, PlayerInput] = {}
        bounds = {
            1: (30, self.width / 2 - 30),
            2: (self.width / 2 + 30, self.width - 30),
        }
        for pid, move in moves.items():
            if np.linalg.norm(move) > 0:
                move = move / np.linalg.norm(move)
            self.prev[pid] = self.positions[pid].copy()
            self.positions[pid] += move * velocity * dt
            min_x, max_x = bounds[pid]
            self.positions[pid][0] = np.clip(self.positions[pid][0], min_x, max_x)
            self.positions[pid][1] = np.clip(self.positions[pid][1], 80, self.height - 80)
            center = tuple(self.positions[pid])
            prev = tuple(self.prev[pid])
            speed = float(np.linalg.norm(self.positions[pid] - self.prev[pid]) / max(dt, 0.001))
            wrist = (center[0] - 28, center[1] + 20)
            pinky = (center[0] + 28, center[1] - 20)
            elbow = (center[0] - (60 if pid == 1 else -60), center[1] + 35)
            shoulder = (elbow[0] - (70 if pid == 1 else -70), elbow[1] + 35)
            blade = BladeState(wrist, pinky, prev, speed, True)
            result[pid] = PlayerInput(pid, [ArmState(shoulder, elbow, center, prev, speed, True)], [blade])
        return result


class SplitPoseInput:
    """全画面手部识别输入。

    为了降低延迟，这里只跑一次 maxHands=2 的手部检测，然后按照手刀中心点
    的 x 坐标分配给玩家 1/2。相比左右各跑一个检测器，这种方式更接近
    OpenCV demo 的实时性，也天然支持两只手同时切水果。
    """

    def __init__(
        self,
        width: int,
        height: int,
        process_width: int = 480,
        process_height: int = 270,
        process_fps: float = 30.0,
    ) -> None:
        """初始化手部识别器。

        优先使用 cvzone.HandDetector；如果没有安装 cvzone，再退回到 MediaPipe Hands。
        """

        self.width = width
        self.height = height
        self.process_width = process_width
        self.process_height = process_height
        self.min_process_interval = 1.0 / max(process_fps, 1.0)
        self.scale_x = width / process_width
        self.scale_y = height / process_height
        self.detector_backend = "mediapipe"
        self.cvzone_detector = None
        self.mp_hands = None
        self.hands = None
        try:
            from cvzone.HandTrackingModule import HandDetector

            self.cvzone_detector = HandDetector(detectionCon=0.45, maxHands=2, minTrackCon=0.45)
            self.detector_backend = "cvzone"
        except Exception:
            if not hasattr(mp, "solutions"):
                raise RuntimeError("未安装 cvzone，且当前 mediapipe 不包含 solutions.hands，无法进行手部识别")
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                model_complexity=0,
                min_detection_confidence=0.38,
                min_tracking_confidence=0.38,
            )
        self.prev_blades: Dict[Tuple[int, int], Optional[Point]] = {}
        self._elapsed_since_process = 0.0
        self._last_inputs: Optional[Dict[int, PlayerInput]] = None

    def update(
        self,
        bgr_frame: np.ndarray,
        dt: float,
        depth_frame: Optional[np.ndarray] = None,
    ) -> Dict[int, PlayerInput]:
        """处理一帧相机画面，并返回两个玩家的输入。"""

        self._elapsed_since_process += dt
        if self._last_inputs is not None and self._elapsed_since_process < self.min_process_interval:
            return self._last_inputs

        process_dt = max(self._elapsed_since_process, dt, 0.001)
        self._elapsed_since_process = 0.0
        frame = cv2.flip(bgr_frame, 1)
        if depth_frame is not None:
            depth_frame = cv2.flip(depth_frame, 1)  # 深度必须和彩色一起翻
        frame = cv2.resize(frame, (self.process_width, self.process_height), interpolation=cv2.INTER_AREA)
        blades_by_player: Dict[int, List[BladeState]] = {1: [], 2: []}

        if self.detector_backend == "cvzone":
            hands, _ = self.cvzone_detector.findHands(frame, draw=False, flipType=False)
            for hand_index, hand in enumerate(hands):
                lm_list = hand.get("lmList", [])
                if len(lm_list) > 20:
                    wrist = self._scale_point((lm_list[0][0], lm_list[0][1]))
                    pinky = self._scale_point((lm_list[20][0], lm_list[20][1]))
                    blade = self._make_blade(wrist, pinky, hand_index, process_dt, depth_frame)
                    pid = 1 if blade.center and blade.center[0] < self.width / 2 else 2
                    blades_by_player[pid].append(blade)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            result = self.hands.process(rgb)
            if result.multi_hand_landmarks:
                for hand_index, hand_lm in enumerate(result.multi_hand_landmarks):
                    wrist_lm = hand_lm.landmark[self.mp_hands.HandLandmark.WRIST]
                    pinky_lm = hand_lm.landmark[self.mp_hands.HandLandmark.PINKY_TIP]
                    wrist = self._scale_point((wrist_lm.x * self.process_width, wrist_lm.y * self.process_height))
                    pinky = self._scale_point((pinky_lm.x * self.process_width, pinky_lm.y * self.process_height))
                    blade = self._make_blade(wrist, pinky, hand_index, process_dt, depth_frame)
                    pid = 1 if blade.center and blade.center[0] < self.width / 2 else 2
                    blades_by_player[pid].append(blade)

        self._last_inputs = {
            1: PlayerInput(1, [], blades_by_player[1], [], []),
            2: PlayerInput(2, [], blades_by_player[2], [], []),
        }
        return self._last_inputs

    def _scale_point(self, point: Point) -> Point:
        """把识别分辨率下的点坐标映射回游戏显示坐标。"""

        return (point[0] * self.scale_x, point[1] * self.scale_y)

    def _make_blade(
        self,
        wrist: Point,
        pinky: Point,
        hand_index: int,
        dt: float,
        depth_frame: Optional[np.ndarray] = None,
    ) -> BladeState:
        """根据手腕和小拇指指尖生成手刀，并计算速度。"""

        center = ((wrist[0] + pinky[0]) / 2.0, (wrist[1] + pinky[1]) / 2.0)
        pid = 1 if center[0] < self.width / 2 else 2
        prev = self.prev_blades.get((pid, hand_index))
        speed = 0.0
        if prev is not None:
            speed = float(np.linalg.norm(np.array(center) - np.array(prev)) / max(dt, 0.001))
        self.prev_blades[(pid, hand_index)] = center
        depth_mm = self._sample_depth(depth_frame, center)
        return BladeState(wrist, pinky, prev, speed, True, depth_mm)

    def _sample_depth(self, depth_frame: Optional[np.ndarray], point: Point) -> Optional[float]:
        """Sample median depth around a display-space point.

        OBSENSOR depth and color frames can have different resolutions, so the
        display coordinate is scaled back into the depth map before sampling.
        A small median patch is more stable than a single pixel when the hand
        edge has holes or noisy depth values.
        """

        if depth_frame is None or depth_frame.size == 0:
            return None
        depth = depth_frame
        if depth.ndim == 3:
            depth = depth[:, :, 0]
        depth_height, depth_width = depth.shape[:2]
        if depth_width <= 0 or depth_height <= 0:
            return None

        x = int(np.clip(point[0] / self.width * depth_width, 0, depth_width - 1))
        y = int(np.clip(point[1] / self.height * depth_height, 0, depth_height - 1))
        radius = 3
        x1 = max(0, x - radius)
        x2 = min(depth_width, x + radius + 1)
        y1 = max(0, y - radius)
        y2 = min(depth_height, y + radius + 1)
        patch = np.asarray(depth[y1:y2, x1:x2], dtype=np.float32).reshape(-1)
        patch = patch[np.isfinite(patch) & (patch > 0)]
        if patch.size == 0:
            return None
        return float(np.median(patch))

    def close(self) -> None:
        """释放手部识别资源。"""

        if self.hands is not None:
            self.hands.close()


def draw_player_input(
    surface: pygame.Surface,
    player: PlayerInput,
    color: Tuple[int, int, int],
    layer: Optional[pygame.Surface] = None,
) -> None:
    """绘制单个玩家的输入反馈。

    包括：玩家头像、当前手刀、移动拖尾、手刀中心点和少量火花。
    """

    owns_layer = layer is None
    knife_layer = layer if layer is not None else pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    avatar_center = (surface.get_width() * (0.25 if player.player_id == 1 else 0.75), 160)
    if player.blades:
        center = player.blades[0].center
        if center is not None:
            # 头像跟随手部上方，保证玩家知道系统当前追踪到了哪只手。
            avatar_center = (center[0], max(90, center[1] - 150))
    draw_smiley(knife_layer, avatar_center, color)

    for blade in player.blades:
        for start, end in blade.blade_segments:
            speed_alpha = int(np.clip(blade.speed / 3.5, 100, 245))
            # 三层圆头线：暗色底、玩家色主体、米白高光。
            draw_round_line(knife_layer, (73, 111, 97, 115), start, end, 22)
            draw_round_line(knife_layer, (*color, 210), start, end, 12)
            draw_round_line(knife_layer, (255, 247, 224, speed_alpha), start, end, 4)
            center = blade.center
            if blade.previous_center is not None and center is not None and blade.speed > 45:
                # 手移动时绘制拖尾，帮助玩家感知切割轨迹。
                draw_round_line(knife_layer, (*color, 68), blade.previous_center, center, 30)
                draw_round_line(knife_layer, (255, 247, 224, 120), blade.previous_center, center, 6)
        center = blade.center
        if center is not None and blade.visible:
            point = (int(center[0]), int(center[1]))
            pygame.draw.circle(knife_layer, (73, 111, 97, 150), point, 12)
            pygame.draw.circle(knife_layer, (*color, 230), point, 8)
            pygame.draw.circle(knife_layer, (255, 247, 224, 230), point, 3)
            if blade.speed > 180:
                # 快速挥动时给一点轻量火花反馈。
                for i in range(3):
                    angle = (i / 5.0) * np.pi * 2.0
                    spark = (
                        int(center[0] + np.cos(angle) * 18),
                        int(center[1] + np.sin(angle) * 18),
                    )
                    pygame.draw.circle(knife_layer, (255, 247, 224, 120), spark, 2)
    if owns_layer:
        surface.blit(knife_layer, (0, 0))


def all_segments(players: Iterable[PlayerInput]) -> List[Tuple[int, Tuple[Point, Point], float]]:
    """收集所有玩家当前可用于切割的线段。

    返回值包含玩家编号、线段坐标和玩家最大手刀速度，供 main.py 做碰撞判定。
    """

    result: List[Tuple[int, Tuple[Point, Point], float]] = []
    for player in players:
        for segment in player.blade_segments:
            result.append((player.player_id, segment, player.max_speed))
    return result
