# -*- coding: utf-8 -*-
"""双人切水果 · Orbbec RGB-D 一键补丁

用法（在游戏目录里执行）：
    conda activate asl
    cd /d "E:\\Game\\3.项目程序源码\\双人切水果游戏"
    python apply_rgbd_patch.py

它会做四件事：
  1. 生成 orbbec_rgbd.py（RGB + Depth 相机后端）
  2. camera_backends.py 末尾追加一行导入
  3. main.py 的 orbbec 分支改用新的 RGB-D 后端
  4. pose_input.py 修「镜像只翻彩色不翻深度」的 bug

每个改动都会先备份为 *.bak，并在最后打印一份报告。
重复执行是安全的：已经改过的会跳过，不会叠加。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

BACKEND_CODE = r'''"""Orbbec RGB-D 相机后端（由 apply_rgbd_patch.py 自动生成）"""

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
'''

report = []
failed = []


def backup(path):
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        return True
    return False


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ----------------------------------------------------------------------
# 0. 确认目录对
# ----------------------------------------------------------------------
need = ["main.py", "camera_backends.py", "pose_input.py"]
missing = [f for f in need if not os.path.exists(os.path.join(HERE, f))]
if missing:
    print("[ERROR] 当前目录不是游戏目录，缺少: %s" % ", ".join(missing))
    print("        请先把本脚本复制到 main.py 所在目录再运行。")
    print("        当前目录: %s" % HERE)
    sys.exit(1)

print("=" * 62)
print("目标目录: %s" % HERE)
print("=" * 62)

# ----------------------------------------------------------------------
# 1. 生成 orbbec_rgbd.py
# ----------------------------------------------------------------------
target = os.path.join(HERE, "orbbec_rgbd.py")
try:
    write(target, BACKEND_CODE)
    report.append("[OK]   已生成 orbbec_rgbd.py")
except Exception as exc:  # noqa: BLE001
    failed.append("生成 orbbec_rgbd.py 失败: %s" % exc)

# ----------------------------------------------------------------------
# 2. camera_backends.py 追加导入
# ----------------------------------------------------------------------
cb = os.path.join(HERE, "camera_backends.py")
try:
    text = read(cb)
    if "from orbbec_rgbd import" in text:
        report.append("[SKIP] camera_backends.py 已有导入语句")
    else:
        backup(cb)
        write(cb, text.rstrip() + "\n\n\nfrom orbbec_rgbd import OrbbecRgbdCamera  # noqa: E402,F401\n")
        report.append("[OK]   camera_backends.py 已追加 RGB-D 后端导入")
except Exception as exc:  # noqa: BLE001
    failed.append("camera_backends.py 修改失败: %s" % exc)

# ----------------------------------------------------------------------
# 3. main.py：导入 + 分支
# ----------------------------------------------------------------------
mn = os.path.join(HERE, "main.py")
try:
    text = read(mn)
    orig = text
    changed = []

    # 3a. 若之前误把 import 行里的 OrbbecColorCamera 换掉了，先恢复
    mangled = "from camera_backends import OBSensorCamera, OrbbecRgbdCamera, WebcamCamera"
    good = "from camera_backends import OBSensorCamera, OrbbecColorCamera, WebcamCamera"
    if mangled in text:
        text = text.replace(mangled, good)
        changed.append("恢复 camera_backends 的导入行")

    # 3b. 确保有 orbbec_rgbd 的独立导入
    if "from orbbec_rgbd import OrbbecRgbdCamera" not in text and good in text:
        text = text.replace(good, good + "\nfrom orbbec_rgbd import OrbbecRgbdCamera", 1)
        changed.append("追加 orbbec_rgbd 导入")

    # 3c. orbbec 分支
    if "camera = OrbbecColorCamera()" in text:
        text = text.replace("camera = OrbbecColorCamera()", "camera = OrbbecRgbdCamera()")
        changed.append("orbbec 分支改用 RGB-D")

    # 3d. auto 模式工厂（精确锚点，不碰 import 行）
    if "OrbbecColorCamera, lambda" in text:
        text = text.replace("OrbbecColorCamera, lambda", "OrbbecRgbdCamera, lambda")
        changed.append("auto 模式工厂改用 RGB-D")

    if text != orig:
        backup(mn)
        write(mn, text)
        report.append("[OK]   main.py: " + "；".join(changed))
    else:
        report.append("[SKIP] main.py 无需修改")
except Exception as exc:  # noqa: BLE001
    failed.append("main.py 修改失败: %s" % exc)

# ----------------------------------------------------------------------
# 4. pose_input.py：镜像时连深度一起翻
# ----------------------------------------------------------------------
pi = os.path.join(HERE, "pose_input.py")
try:
    text = read(pi)
    old = ("        frame = cv2.flip(bgr_frame, 1)\n"
           "        frame = cv2.resize(frame, (self.process_width, self.process_height), "
           "interpolation=cv2.INTER_AREA)")
    if "depth_frame = cv2.flip(depth_frame, 1)" in text:
        report.append("[SKIP] pose_input.py 已修过镜像深度")
    elif old in text:
        backup(pi)
        new = ("        frame = cv2.flip(bgr_frame, 1)\n"
               "        if depth_frame is not None:\n"
               "            depth_frame = cv2.flip(depth_frame, 1)  # 深度必须和彩色一起翻\n"
               "        frame = cv2.resize(frame, (self.process_width, self.process_height), "
               "interpolation=cv2.INTER_AREA)")
        write(pi, text.replace(old, new, 1))
        report.append("[OK]   pose_input.py 已修：镜像时深度一起翻转")
    else:
        failed.append("pose_input.py 找不到锚点，请手动在第 264 行附近加两行")
except Exception as exc:  # noqa: BLE001
    failed.append("pose_input.py 修改失败: %s" % exc)

# ----------------------------------------------------------------------
print()
for line in report:
    print(line)
if failed:
    print()
    for line in failed:
        print("[FAIL] " + line)

print()
print("=" * 62)
if failed:
    print("有 %d 项未成功，见上面的 [FAIL]" % len(failed))
else:
    print("全部完成。下一步：")
    print('    python main.py --input orbbec --show-fps')
    print("期待终端出现：[Depth] P1: 8xx mm | P2: 10xx mm")
print("=" * 62)
