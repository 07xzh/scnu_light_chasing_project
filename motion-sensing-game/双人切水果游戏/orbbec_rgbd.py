"""Orbbec RGB-D 相机后端（由 apply_rgbd_patch.py 自动生成）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

try:
    from camera_backends import CameraFrame
except Exception:  # 允许单独调试

    @dataclass
    class CameraFrame:  # type: ignore
        bgr: np.ndarray
        source: str
        depth: Optional[np.ndarray] = None


class OrbbecRgbdCamera:
    """Orbbec SDK RGB-D 后端：一帧同时给出彩色图与深度图。

    彩色：优先按 RGB888 原始数据解析，失败则按 MJPG/JPEG 解码
    深度：uint16 数组，乘以 get_depth_scale() 后统一为毫米
    """

    def __init__(self, align: bool = True) -> None:
        self.pipeline = None
        self._align = align
        self._ob = None
        self._scale_logged = False

    def start(self) -> None:
        try:
            # pip 包名是 pyorbbecsdk2，导入名是 pyorbbecsdk
            import pyorbbecsdk as ob
        except ImportError as exc:
            raise RuntimeError(
                "未安装 pyorbbecsdk，请先执行：\n"
                "    python -m pip install --upgrade pyorbbecsdk2"
            ) from exc

        self._ob = ob

        # 关键：先确认有设备。设备为 0 时直接 startup 会让 SDK 原生层崩溃
        # （进程静默退出，退出码 0xC0000374，看不到任何 traceback）。
        try:
            _ctx = ob.Context()
            _devs = _ctx.query_devices()
            _n = _devs.get_count() if hasattr(_devs, "get_count") else len(_devs)
        except Exception as exc:
            raise RuntimeError("查询 Orbbec 设备失败: %s" % exc) from exc
        if _n == 0:
            raise RuntimeError(
                "未检测到 Orbbec 深度相机（设备数量 0）。请检查：\n"
                "  1) 相机是否插好，是否用原装 USB-C 数据线\n"
                "  2) 是否插在 USB 3.0 口（蓝色/SS），不要经 USB Hub\n"
                "  3) 是否被 Orbbec Viewer 或其他程序占用（同一时间只能一个程序用）\n"
                "确认命令：python -c \"from pyorbbecsdk import Context; "
                "print(Context().query_devices().get_count())\""
            )

        config = ob.Config()
        self.pipeline = ob.Pipeline()

        color_list = self.pipeline.get_stream_profile_list(ob.OBSensorType.COLOR_SENSOR)
        self.color_profile = color_list.get_default_video_stream_profile()
        config.enable_stream(self.color_profile)

        depth_list = self.pipeline.get_stream_profile_list(ob.OBSensorType.DEPTH_SENSOR)
        self.depth_profile = depth_list.get_default_video_stream_profile()
        config.enable_stream(self.depth_profile)

        if self._align:
            for name in ("ALIGN_D2C_HW_MODE", "ALIGN_D2C_SW_MODE"):
                mode = getattr(ob.OBAlignMode, name, None)
                if mode is None:
                    continue
                try:
                    config.set_align_mode(mode)
                    print("[CAMERA] 深度对齐: %s" % name)
                    break
                except Exception:
                    continue

        self.pipeline.start(config)
        print(
            "[CAMERA] Orbbec RGB-D 已启动  color=%dx%d  depth=%dx%d"
            % (
                self.color_profile.get_width(),
                self.color_profile.get_height(),
                self.depth_profile.get_width(),
                self.depth_profile.get_height(),
            )
        )

    def _decode_color(self, color_frame):
        width = color_frame.get_width()
        height = color_frame.get_height()
        data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)

        if data.size >= width * height * 3:
            rgb = data[: width * height * 3].reshape((height, width, 3))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        decoded = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return decoded if decoded is not None else None

    def _decode_depth(self, depth_frame):
        width = depth_frame.get_width()
        height = depth_frame.get_height()
        data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
        if data.size < width * height:
            return None

        depth = data[: width * height].reshape((height, width)).astype(np.float32)

        get_scale = getattr(depth_frame, "get_depth_scale", None)
        if callable(get_scale):
            try:
                scale = float(get_scale())
                if scale > 0:
                    depth *= scale
                if not self._scale_logged:
                    print("[CAMERA] depth_scale = %s" % scale)
                    self._scale_logged = True
            except Exception:
                pass
        return depth

    def read(self):
        if self.pipeline is None:
            return None

        frames = self.pipeline.wait_for_frames(1000)
        if frames is None:
            return None

        color_frame = frames.get_color_frame()
        if color_frame is None:
            return None

        bgr = self._decode_color(color_frame)
        if bgr is None:
            return None

        depth = None
        depth_frame = frames.get_depth_frame()
        if depth_frame is not None:
            depth = self._decode_depth(depth_frame)

        source = "orbbec:rgbd" if depth is not None else "orbbec:color"
        return CameraFrame(bgr, source, depth)

    def close(self) -> None:
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass
            self.pipeline = None
