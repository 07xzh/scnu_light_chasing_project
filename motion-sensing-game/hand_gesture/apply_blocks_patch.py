# -*- coding: utf-8 -*-
"""积木拼搭（hand_gesture）· Orbbec SDK v2 相机 + MediaPipe 兼容补丁

用法（在 hand_gesture 目录里执行）：
    conda activate asl
    cd /d "E:\\Game\\3.项目程序源码\\hand_gesture"
    python apply_blocks_patch.py
    python main.py

本补丁解决四个实测问题：
  1. mediapipe 1.1.1 已移除 mp.solutions  —— 原代码 _init_mediapipe 必然失败
     → 提供 mp_hands_compat.py（用 Tasks API 复刻旧接口）并接管初始化
  2. Gemini 336L 的默认 profile 不支持硬件 D2C 对齐
     （报 "Current stream profile is not support hardware d2c process"）
     → 对齐改为 HW → SW → 不对齐 的重试链
  3. 设备为 0 时 pipeline.start() 会让原生层硬崩（进程静默退出）
     → 启动前先查设备数量
  4. 彩色按固定 640x480 切真实 1280x720 数据 → 画面错位
     → 按真实帧尺寸解码

重复执行安全：生成的模块会被覆盖重写，camera.py 的追加段只加一次。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ======================================================================
# 模块 1：MediaPipe 兼容层
# ======================================================================
COMPAT_CODE = r'''"""MediaPipe Tasks API 兼容层（由 apply_blocks_patch.py 生成）

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
'''

# ======================================================================
# 模块 2：SDK v2 相机实现
# ======================================================================
CAMERA_CODE = r'''"""Orbbec SDK v2 相机实现（由 apply_blocks_patch.py 生成）"""

import cv2
import numpy as np

import camera as _camera_pkg
from camera import BaseHandCamera


class OrbbecCameraV2(BaseHandCamera):
    """Orbbec SDK v2 的 RGB-D 相机。

    - 启动前先查设备数量（为 0 直接报错，避免原生层崩溃）
    - 深度对齐按 HW → SW → 不启用 依次重试
      （Gemini 336L 的默认 profile 不支持硬件 D2C，会抛
       "Current stream profile is not support hardware d2c process"）
    - 彩色/深度都按真实帧尺寸解码
    """

    def __init__(self, width=640, height=480):
        super().__init__(width, height)

        import pyorbbecsdk as ob

        # --- 1. 必须先在，否则 start() 会硬崩 ---
        try:
            ctx = ob.Context()
            devs = ctx.query_devices()
            n = devs.get_count() if hasattr(devs, "get_count") else len(devs)
        except Exception as exc:
            raise RuntimeError("查询 Orbbec 设备失败: %s" % exc) from exc
        if n == 0:
            raise RuntimeError(
                "未检测到 Orbbec 深度相机（设备数量 0）。请检查 USB-C 数据线、"
                "USB 3.0 接口，以及是否被其他程序占用。"
            )

        # --- 2. 对齐模式按 HW -> SW -> 无 依次重试 ---
        tries = []
        for name in ("HW_MODE", "ALIGN_D2C_HW_MODE"):
            if getattr(ob.OBAlignMode, name, None) is not None:
                tries.append(name)
                break
        for name in ("SW_MODE", "ALIGN_D2C_SW_MODE"):
            if getattr(ob.OBAlignMode, name, None) is not None:
                tries.append(name)
                break
        tries.append("none")

        last_error = None
        for name in tries:
            try:
                config = ob.Config()
                config.enable_stream(ob.OBStreamType.COLOR_STREAM)
                has_depth = True
                try:
                    config.enable_stream(ob.OBStreamType.DEPTH_STREAM)
                except Exception as exc:
                    has_depth = False
                    print("[Camera] 深度流不可用: %s" % exc)

                if name != "none":
                    config.set_align_mode(getattr(ob.OBAlignMode, name))

                pipeline = ob.Pipeline()
                pipeline.start(config)
            except Exception as exc:
                last_error = exc
                print("[Camera] 对齐模式 %s 启动失败: %s" % (name, exc))
                continue

            self._ob = ob
            self._pipeline = pipeline
            self._has_depth = has_depth
            self._align_name = name
            print("[Camera] 深度对齐模式: %s" % name)
            print("[Camera] Orbbec RGB-D 已启动（SDK v2 适配层）")
            return

        raise RuntimeError("Orbbec 启动失败: %s" % last_error)

    # ------------------------------------------------------------------
    @staticmethod
    def _decode_color(color_frame):
        width = color_frame.get_width()
        height = color_frame.get_height()
        raw = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
        if raw.size >= width * height * 3:
            rgb = raw[: width * height * 3].reshape((height, width, 3))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return cv2.imdecode(raw, cv2.IMREAD_COLOR)

    @staticmethod
    def _decode_depth(depth_frame):
        if depth_frame is None:
            return None
        width = depth_frame.get_width()
        height = depth_frame.get_height()
        raw = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
        if raw.size < width * height:
            return None
        depth = raw[: width * height].reshape((height, width)).astype(np.float32)
        get_scale = getattr(depth_frame, "get_depth_scale", None)
        if callable(get_scale):
            try:
                scale = float(get_scale())
                if scale > 0:
                    depth *= scale
            except Exception:
                pass
        return depth

    # ------------------------------------------------------------------
    def read(self):
        try:
            frames = self._pipeline.wait_for_frames(1000)
            if not frames:
                return None, None, None

            color_frame = frames.get_color_frame()
            if not color_frame:
                return None, None, None

            img = self._decode_color(color_frame)
            if img is None:
                return None, None, None
            img = cv2.flip(img, 1)

            depth = None
            if self._has_depth:
                depth = self._decode_depth(frames.get_depth_frame())
                if depth is not None:
                    depth = cv2.flip(depth, 1)

            hand_data = self._select_active_hand(img, depth)
            self._debug_depth_status(depth, hand_data)
            return img, depth, hand_data

        except Exception as exc:
            print("[Camera] Orbbec 读取失败: %s" % exc)
            return None, None, None

    def close(self):
        try:
            BaseHandCamera.close(self)
        except Exception:
            pass
        if hasattr(self, "_pipeline"):
            try:
                self._pipeline.stop()
            except Exception:
                pass


def _init_mediapipe_v2(self):
    """替换 BaseHandCamera._init_mediapipe：优先用 Tasks API 兼容层。"""
    try:
        import mp_hands_compat as compat
        self._mp_hands = compat
        self._mp_draw = compat
        self._hands = compat.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.35,
            min_tracking_confidence=0.35,
        )
        print("[Camera] MediaPipe(Tasks API) hand tracking ready")
    except Exception as exc:
        print("[Camera] MediaPipe compat init failed: %s" % exc)
        try:
            import mediapipe as mp
            self._mp_hands = mp.solutions.hands
            self._mp_draw = mp.solutions.drawing_utils
            self._hands = self._mp_hands.Hands(
                static_image_mode=False, max_num_hands=2,
                min_detection_confidence=0.35, min_tracking_confidence=0.35,
            )
            print("[Camera] MediaPipe legacy hand tracking ready")
        except Exception as exc2:
            print("[Camera] MediaPipe init failed: %s" % exc2)


def create_camera(source="orbbec", width=640, height=480, camera_index=0):
    """替换工厂：orbbec 失败时退回普通摄像头。"""
    if source == "orbbec":
        try:
            return OrbbecCameraV2(width, height)
        except Exception as exc:
            print("[Camera] Orbbec 启动失败，退回 webcam: %s" % exc)
    return _camera_pkg.WebcamCamera(width, height, camera_index)


# 立即接管 MediaPipe 初始化（必须在任何相机实例创建之前生效）
BaseHandCamera._init_mediapipe = _init_mediapipe_v2
'''

SUFFIX = '''

# ============================================================================
# Orbbec SDK v2 适配层（由 apply_blocks_patch.py 添加；删除本段即可还原）
# ============================================================================
try:
    import orbbec_rgbd_v2 as _rgbd_v2

    OrbbecCamera = _rgbd_v2.OrbbecCameraV2
    create_camera = _rgbd_v2.create_camera
    print("[Camera] 已启用 Orbbec SDK v2 适配层")
except Exception as _rgbd_exc:  # noqa: BLE001
    print("[Camera] SDK v2 适配层加载失败，继续使用原实现: %s" % _rgbd_exc)
'''

report = []
failed = []


def backup(path):
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)


def write_file(name, content):
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return path


if not os.path.exists(os.path.join(HERE, "camera.py")):
    print("[ERROR] 当前目录没有 camera.py，请先 cd 到 hand_gesture 目录")
    print("        当前目录: %s" % HERE)
    sys.exit(1)

print("=" * 62)
print("目标目录: %s" % HERE)
print("=" * 62)

try:
    write_file("mp_hands_compat.py", COMPAT_CODE)
    report.append("[OK]   已生成 mp_hands_compat.py（MediaPipe Tasks 兼容层）")
except Exception as exc:  # noqa: BLE001
    failed.append("生成 mp_hands_compat.py 失败: %s" % exc)

try:
    write_file("orbbec_rgbd_v2.py", CAMERA_CODE)
    report.append("[OK]   已生成 orbbec_rgbd_v2.py（SDK v2 相机实现）")
except Exception as exc:  # noqa: BLE001
    failed.append("生成 orbbec_rgbd_v2.py 失败: %s" % exc)

cam_path = os.path.join(HERE, "camera.py")
try:
    with open(cam_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if "Orbbec SDK v2 适配层" in text:
        report.append("[SKIP] camera.py 已追加过适配层")
    else:
        backup(cam_path)
        with open(cam_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.rstrip() + "\n" + SUFFIX)
        report.append("[OK]   camera.py 已追加适配层（覆盖 OrbbecCamera / create_camera / MediaPipe 初始化）")
except Exception as exc:  # noqa: BLE001
    failed.append("camera.py 修改失败: %s" % exc)

print()
for line in report:
    print(line)
for line in failed:
    print("[FAIL] " + line)

print()
print("=" * 62)
if failed:
    print("有 %d 项未成功" % len(failed))
else:
    print("完成。直接运行：python main.py")
    print("期待日志：")
    print("    [Camera] MediaPipe(Tasks API) hand tracking ready")
    print("    [Camera] 深度对齐模式: SW_MODE   （HW 不支持时自动降级）")
    print("    [Camera] Orbbec RGB-D 已启动（SDK v2 适配层）")
print("=" * 62)
