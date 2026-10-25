"""相机后端适配层。

主游戏只依赖 start/read/close 三个动作，不直接关心相机类型。
这里提供普通 OpenCV 摄像头和 Orbbec Gemini2 彩色流两个后端。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class CameraFrame:
    """统一的相机帧数据。

    bgr 使用 OpenCV 默认格式；source 用于在游戏角落显示当前输入来源。
    """

    bgr: np.ndarray
    source: str
    depth: Optional[np.ndarray] = None


class WebcamCamera:
    """普通摄像头后端，适合 UVC 摄像头或 Gemini2 映射出的彩色摄像头。"""

    def __init__(self, index: int = 0) -> None:
        """index 是 OpenCV 摄像头编号，通常 0 是默认摄像头。"""

        self.index = index
        self.cap: Optional[cv2.VideoCapture] = None

    def start(self) -> None:
        """打开摄像头，并尽量设置为 1280x720。"""

        self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 index={self.index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> Optional[CameraFrame]:
        """读取一帧图像；读取失败时返回 None。"""

        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        return CameraFrame(frame, f"webcam:{self.index}")

    def close(self) -> None:
        """释放摄像头资源。"""

        if self.cap is not None:
            self.cap.release()
            self.cap = None


class OBSensorCamera:
    """OpenCV OBSENSOR 后端。

    部分 OpenCV 构建可以通过 cv2.CAP_OBSENSOR 直接读取 Orbbec/Gemini2。
    这种方式通常比 SDK 包装层更短，适合追求低延迟的实时游戏。
    """

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.cap: Optional[cv2.VideoCapture] = None

    def start(self) -> None:
        if not hasattr(cv2, "CAP_OBSENSOR"):
            raise RuntimeError("当前 OpenCV 不支持 CAP_OBSENSOR")
        self.cap = cv2.VideoCapture(self.index, cv2.CAP_OBSENSOR)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法以 OBSENSOR 模式打开 Gemini2 index={self.index}")
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> Optional[CameraFrame]:
        if self.cap is None:
            return None
        depth = None
        if hasattr(cv2, "CAP_OBSENSOR_BGR_IMAGE"):
            if not self.cap.grab():
                return None
            ok, frame = self.cap.retrieve(None, cv2.CAP_OBSENSOR_BGR_IMAGE)
            if ok and hasattr(cv2, "CAP_OBSENSOR_DEPTH_MAP"):
                depth_ok, depth_frame = self.cap.retrieve(None, cv2.CAP_OBSENSOR_DEPTH_MAP)
                if depth_ok and depth_frame is not None:
                    depth = depth_frame
        else:
            ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        return CameraFrame(frame, "obsensor:gemini2", depth)

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class OrbbecColorCamera:
    """Gemini2 / Orbbec 彩色流后端。

    当前游戏只需要彩色图做手部识别。未来如果要用深度做前景过滤，
    可以在这个类里扩展 depth frame，而不用大改主游戏循环。
    """

    def __init__(self) -> None:
        self.pipeline = None

    def start(self) -> None:
        """初始化 pyorbbecsdk Pipeline，并开启默认彩色流。"""

        try:
            from pyorbbecsdk import Config, OBSensorType, Pipeline
        except Exception as exc:
            raise RuntimeError("未安装 pyorbbecsdk，无法使用 Orbbec 后端") from exc

        config = Config()
        self.pipeline = Pipeline()
        profiles = self.pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        profile = profiles.get_default_video_stream_profile()
        config.enable_stream(profile)
        self.pipeline.start(config)

    def read(self) -> Optional[CameraFrame]:
        """读取一帧 Orbbec 彩色图。

        不同 SDK/设备配置可能输出 RGB/BGR 原始数据或 MJPG 压缩数据，
        所以下方会按常见格式依次尝试解析。
        """

        if self.pipeline is None:
            return None
        frames = self.pipeline.wait_for_frames(100)
        if frames is None:
            return None
        color_frame = frames.get_color_frame()
        if color_frame is None:
            return None

        width = color_frame.get_width()
        height = color_frame.get_height()
        data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)

        # 常见情况：RGB888/BGR888 原始三通道数据。
        if data.size == width * height * 3:
            rgb = data.reshape((height, width, 3))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            return CameraFrame(bgr, "orbbec:color")

        # 另一种常见情况：MJPG/JPEG 等压缩数据，需要 imdecode 解码。
        decoded = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if decoded is not None:
            return CameraFrame(decoded, "orbbec:color")
        return None

    def close(self) -> None:
        """停止 Orbbec pipeline。"""

        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline = None


from orbbec_rgbd import OrbbecRgbdCamera  # noqa: E402,F401
