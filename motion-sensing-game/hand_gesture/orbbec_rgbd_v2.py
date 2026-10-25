"""Orbbec SDK v2 相机实现（由 apply_blocks_patch.py 生成）"""

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
