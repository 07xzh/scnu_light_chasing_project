"""相机管理（Orbbec RGB-D 修正版）

用途：替换 backend/camera_manager.py。
对外接口与原版完全一致（.mode / .get_frames() / .release()），main.py 不需要任何改动。

相比原版的改动只有三处：
  1. 导入顺序：先 pyorbbecsdk（新版 pyorbbecsdk2 包的真实导入名），再退回 pyorbbecsdk2。
  2. 初始化改用真实 SDK API：get_stream_profile_list -> get_default_video_stream_profile
     -> config.enable_stream(profile)。原版传的是 OBSensorType 枚举，真实 API 不接受。
  3. 对齐模式改为 ALIGN_D2C_HW_MODE / ALIGN_D2C_SW_MODE，并容忍枚举缺失。

注意：作者在原文件里自己也标注了这段是"伪代码"，所以本文件属于按官方文档
（https://orbbec.github.io/pyorbbecsdk/）重写，未经真机验证。首次运行请留意
终端日志：成功会打印 "Orbbec RGB-D hardware camera started successfully!"，
失败会自动降级到 OpenCV 普通摄像头，不会让整个服务崩掉。
"""

import os

import cv2
import numpy as np


class CameraManager:
    """
    相机管理类

    默认使用 OpenCV 本地摄像头采集；
    如果设置环境变量 ENABLE_ORBBEC=1、安装了 pyorbbecsdk2、并连接了 Orbbec
    Femto / Gemini 系列 RGB-D 相机，则优先使用 Orbbec SDK 获取物理深度，
    供人脸活体检测使用。
    """

    def __init__(self):
        self.mode = "OPENCV"
        self.pipeline = None
        self.cap = None
        self.ob = None
        self.color_size = None
        self.depth_size = None
        self._init_camera()

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #
    def _init_camera(self):
        has_ob = False

        if os.environ.get("ENABLE_ORBBEC", "").strip() == "1":
            # pip 包名是 pyorbbecsdk2，但导入名是 pyorbbecsdk，两个都试一遍
            for modname in ("pyorbbecsdk", "pyorbbecsdk2"):
                try:
                    self.ob = __import__(modname)
                    has_ob = True
                    print(f"[CAMERA] 已加载 Orbbec SDK 模块: {modname}")
                    break
                except ImportError:
                    continue

            if not has_ob:
                print("[CAMERA] 未安装 pyorbbecsdk（pip install pyorbbecsdk2），跳过 Orbbec 初始化")

        if has_ob:
            print("[CAMERA] 检测到 Orbbec SDK 库，尝试初始化硬件深度相机...")
            try:
                ob = self.ob
                self.pipeline = ob.Pipeline()
                config = ob.Config()

                # --- 彩色流：必须传 stream profile，不能传 sensor type ---
                color_list = self.pipeline.get_stream_profile_list(ob.OBSensorType.COLOR_SENSOR)
                color_profile = color_list.get_default_video_stream_profile()
                config.enable_stream(color_profile)

                # --- 深度流 ---
                depth_list = self.pipeline.get_stream_profile_list(ob.OBSensorType.DEPTH_SENSOR)
                depth_profile = depth_list.get_default_video_stream_profile()
                config.enable_stream(depth_profile)

                # --- 深度对齐到彩色（硬件优先，退软件对齐） ---
                for name in ("ALIGN_D2C_HW_MODE", "ALIGN_D2C_SW_MODE"):
                    align_mode = getattr(ob.OBAlignMode, name, None)
                    if align_mode is None:
                        continue
                    try:
                        config.set_align_mode(align_mode)
                        print(f"[CAMERA] 深度对齐模式: {name}")
                        break
                    except Exception as exc:
                        print(f"[CAMERA] 对齐模式 {name} 不可用: {exc}")

                self.pipeline.start(config)

                self.mode = "ORBBEC"
                self.color_size = (color_profile.get_width(), color_profile.get_height())
                self.depth_size = (depth_profile.get_width(), depth_profile.get_height())
                print(
                    "[CAMERA] Orbbec RGB-D hardware camera started successfully! "
                    f"color={self.color_size} depth={self.depth_size}"
                )
                return

            except Exception as exc:
                print(
                    f"[CAMERA] Orbbec hardware init failed "
                    f"({type(exc).__name__}: {exc}), falling back to OpenCV..."
                )
                try:
                    if self.pipeline is not None:
                        self.pipeline.stop()
                except Exception:
                    pass
                self.pipeline = None
                self.mode = "OPENCV"

        # 降级到 OpenCV
        print("[CAMERA] 使用标准 OpenCV 摄像头采集模式...")
        self.mode = "OPENCV"
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # ------------------------------------------------------------------ #
    # 取帧
    # ------------------------------------------------------------------ #
    def get_frames(self):
        """
        返回 (bgr_image, depth_image)

        depth_image 为 uint16 数组，单位毫米；OpenCV 模式下恒为 None。
        """
        if self.mode == "ORBBEC" and self.pipeline is not None:
            try:
                frames = self.pipeline.wait_for_frames(1000)  # 原版 100ms 偏短，容易超时
                if frames is None:
                    return None, None

                color_frame = frames.get_color_frame()
                if color_frame is None:
                    return None, None

                w = color_frame.get_width()
                h = color_frame.get_height()
                color_data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)

                if color_data.size == w * h * 3:
                    color_image = color_data.reshape((h, w, 3))
                    bgr_image = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)
                else:
                    # 默认彩色流可能是 MJPEG，需要解码
                    bgr_image = cv2.imdecode(color_data, cv2.IMREAD_COLOR)
                    if bgr_image is None:
                        return None, None

                depth_image = None
                depth_frame = frames.get_depth_frame()
                if depth_frame is not None:
                    dw = depth_frame.get_width()
                    dh = depth_frame.get_height()
                    depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
                    if depth_data.size == dw * dh:
                        depth_image = depth_data.reshape((dh, dw))
                        # 统一换算成毫米，face_auth 的距离阈值是按毫米写的
                        try:
                            scale = float(depth_frame.get_depth_scale())
                        except Exception:
                            scale = 1.0
                        if scale != 1.0 and scale > 0:
                            depth_image = (depth_image.astype(np.float32) * scale).astype(np.uint16)

                return bgr_image, depth_image

            except Exception as exc:
                print(f"[CAMERA ERROR] Orbbec 读取失败: {exc}")
                return None, None

        # OpenCV 模式
        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.flip(frame, 1)
                return frame, None
        return None, None

    # ------------------------------------------------------------------ #
    # 释放
    # ------------------------------------------------------------------ #
    def release(self):
        if self.mode == "ORBBEC" and self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception as exc:
                print(f"[CAMERA] 停止 Orbbec pipeline 失败: {exc}")
        elif self.mode == "OPENCV" and self.cap is not None:
            self.cap.release()
