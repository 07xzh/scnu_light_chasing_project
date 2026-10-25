"""MediaPipe Tasks API 兼容层（由 apply_blocks_patch.py 生成）

mediapipe 1.1.x 移除了旧的 mp.solutions 命名空间，而本项目用的是旧接口：
    self._hands.process(rgb)                  -> result.multi_hand_landmarks
    self._mp_draw.draw_landmarks(img, hand, self._mp_hands.HAND_CONNECTIONS)

本模块用 mediapipe.tasks 的 HandLandmarker 复刻这三样东西，
使老代码不用改一行就能继续工作。
"""

import os

import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

_DEFAULT_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")


def _resolve_model_path():
    """返回一个 MediaPipe 原生层能打开的模型路径。

    MediaPipe 的 C++ 层用窄字符路径打开文件，**路径里含中文等非 ASCII 字符时会失败**，
    报错形如：Unable to open file at E:\\Game\\3.项目程序源码\\...\\hand_landmarker.task
    解决方法：把模型复制到纯 ASCII 的临时目录再加载。
    """
    env_path = os.environ.get("HAND_LANDMARKER_MODEL")
    if env_path and os.path.exists(env_path):
        return env_path

    if not os.path.exists(_DEFAULT_MODEL):
        raise RuntimeError(
            "找不到模型文件 hand_landmarker.task，应放在本模块同一目录：%s" % _DEFAULT_MODEL
        )

    if _DEFAULT_MODEL.isascii():
        return _DEFAULT_MODEL

    # 路径含非 ASCII 字符：复制到 ASCII 临时目录
    import hashlib
    import shutil
    import tempfile

    tag = hashlib.md5(_DEFAULT_MODEL.encode("utf-8")).hexdigest()[:8]
    cache_dir = os.path.join(tempfile.gettempdir(), "mp_models")
    os.makedirs(cache_dir, exist_ok=True)
    dst = os.path.join(cache_dir, "hand_landmarker_%s.task" % tag)

    src_size = os.path.getsize(_DEFAULT_MODEL)
    if not os.path.exists(dst) or os.path.getsize(dst) != src_size:
        shutil.copy2(_DEFAULT_MODEL, dst)

    print("[Camera] 模型路径含中文，已复制到 ASCII 路径: %s" % dst)
    return dst


class _Landmark:
    __slots__ = ("x", "y", "z")

    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _HandLandmarks:
    __slots__ = ("landmark",)

    def __init__(self, landmarks):
        self.landmark = landmarks


class _Result:
    __slots__ = ("multi_hand_landmarks",)

    def __init__(self, hands):
        self.multi_hand_landmarks = hands or None


class Hands:
    """旧接口 mp.solutions.hands.Hands 的替身。"""

    def __init__(self, static_image_mode=False, max_num_hands=2,
                 min_detection_confidence=0.5, min_tracking_confidence=0.5,
                 model_complexity=1, **_ignored):
        model_path = _resolve_model_path()
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            num_hands=int(max_num_hands),
            min_hand_detection_confidence=float(min_detection_confidence),
            min_hand_presence_confidence=float(min_detection_confidence),
            min_tracking_confidence=float(min_tracking_confidence),
            running_mode=vision.RunningMode.VIDEO,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._ts_ms = 0
        self._static = static_image_mode

    def process(self, rgb_image):
        if rgb_image is None:
            return _Result([])
        image = np.ascontiguousarray(rgb_image)
        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)

        if self._static:
            result = self._landmarker.detect(mp_image)
        else:
            self._ts_ms += 33
            result = self._landmarker.detect_for_video(mp_image, self._ts_ms)

        hands = []
        for hand in (result.hand_landmarks or []):
            hands.append(_HandLandmarks([_Landmark(p.x, p.y, p.z) for p in hand]))
        return _Result(hands)

    def close(self):
        try:
            self._landmarker.close()
        except Exception:
            pass


def draw_landmarks(image, hand_landmarks, connections=None,
                   point_color=(0, 0, 255), line_color=(0, 255, 0), radius=3):
    """旧接口 drawing_utils.draw_landmarks 的替身（直接画在 BGR 图上）。"""
    if hand_landmarks is None or image is None:
        return
    connections = connections or HAND_CONNECTIONS
    h, w = image.shape[:2]
    pts = []
    for lm in hand_landmarks.landmark:
        x = int(min(max(lm.x, 0.0), 1.0) * (w - 1))
        y = int(min(max(lm.y, 0.0), 1.0) * (h - 1))
        pts.append((x, y))

    for a, b in connections:
        if a < len(pts) and b < len(pts):
            cv2.line(image, pts[a], pts[b], line_color, 2)
    for p in pts:
        cv2.circle(image, p, radius, point_color, -1)
