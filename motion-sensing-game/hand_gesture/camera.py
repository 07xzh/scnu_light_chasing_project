"""
Camera and hand tracking wrapper.

Gemini2/Orbbec color frames are used for display and MediaPipe landmarks.
Depth frames are used as a stability signal: the first valid hand becomes the
active hand, and later detections are matched by screen position plus palm depth.
"""

from enum import Enum
import time

import cv2
import numpy as np


class GestureState(Enum):
    UNKNOWN = "unknown"
    OPEN = "open"
    GRAB = "grab"


class HandData:
    def __init__(self):
        self.palm_x = 0.5
        self.palm_y = 0.5
        self.gesture = GestureState.UNKNOWN
        self.confidence = 0.0
        self.depth_mm = 0
        self.tracking_locked = False

    def is_valid(self):
        return self.confidence > 0.3


class BaseHandCamera:
    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height
        self._hands = None
        self._mp_draw = None
        self._mp_hands = None
        self._locked_palm = None
        self._locked_depth = None
        self._missing_frames = 0
        self._last_depth_debug_time = 0
        self._depth_debug_interval = 3.0
        self._init_mediapipe()

    def _init_mediapipe(self):
        try:
            import mediapipe as mp
            self._mp_hands = mp.solutions.hands
            self._mp_draw = mp.solutions.drawing_utils
            self._hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.35,
                min_tracking_confidence=0.35,
            )
            print("[Camera] MediaPipe hand tracking ready")
        except Exception as e:
            print(f"[Camera] MediaPipe init failed: {e}")

    def _prepare_detection_image(self, img, depth):
        """Enhance low-light RGB and lightly boost depth foreground contrast."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if gray.mean() >= 75:
            return img

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l_chan)
        enhanced = cv2.cvtColor(cv2.merge((enhanced_l, a_chan, b_chan)), cv2.COLOR_LAB2BGR)

        if depth is None:
            return enhanced

        valid = depth > 0
        if not np.any(valid):
            return enhanced

        near = np.percentile(depth[valid], 18)
        far = np.percentile(depth[valid], 68)
        if far <= near:
            return enhanced

        foreground = np.clip((far - depth.astype(np.float32)) / (far - near), 0, 1)
        foreground[~valid] = 0
        foreground = cv2.GaussianBlur(foreground, (9, 9), 0)
        boost = (foreground * 55).astype(np.uint8)
        return cv2.add(enhanced, cv2.merge((boost, boost, boost)))

    def _depth_at(self, depth, x_norm, y_norm):
        if depth is None:
            return 0
        h, w = depth.shape[:2]
        x = int(np.clip(x_norm, 0, 1) * (w - 1))
        y = int(np.clip(y_norm, 0, 1) * (h - 1))
        half = 3
        patch = depth[max(0, y - half):min(h, y + half + 1), max(0, x - half):min(w, x + half + 1)]
        patch = patch[patch > 0]
        if patch.size == 0:
            return 0
        return int(np.median(patch))

    def _debug_depth_status(self, depth, hand_data=None):
        now = time.time()
        if now - self._last_depth_debug_time < self._depth_debug_interval:
            return
        self._last_depth_debug_time = now

        if depth is None:
            print("[Camera] Depth status: no depth frame this interval")
            return

        valid = depth > 0
        valid_ratio = float(np.count_nonzero(valid)) / float(depth.size) if depth.size else 0.0
        if not np.any(valid):
            print("[Camera] Depth status: frame received, but no valid depth pixels")
            return

        near = int(np.percentile(depth[valid], 10))
        far = int(np.percentile(depth[valid], 90))
        palm_depth = hand_data.depth_mm if hand_data is not None else 0
        locked = self._locked_depth or 0
        print(
            f"[Camera] Depth status: valid={valid_ratio:.2f}, "
            f"range={near}-{far}, palm={palm_depth}mm, locked={locked}mm"
        )

    def _recognize_gesture(self, landmarks):
        finger_pairs = [(8, 6), (12, 10), (16, 14), (20, 18)]
        extended = sum(1 for tip, pip in finger_pairs if landmarks[tip].y < landmarks[pip].y)
        thumb_open = abs(landmarks[4].x - landmarks[0].x) > abs(landmarks[3].x - landmarks[0].x)
        extended += 1 if thumb_open else 0
        if extended <= 1:
            return GestureState.GRAB
        if extended >= 3:
            return GestureState.OPEN
        return GestureState.UNKNOWN

    def _candidate_score(self, candidate):
        palm = (candidate.palm_x, candidate.palm_y)
        if self._locked_palm is None:
            depth_bonus = 0 if candidate.depth_mm else 0.2
            return palm[1] + depth_bonus

        dx = palm[0] - self._locked_palm[0]
        dy = palm[1] - self._locked_palm[1]
        score = (dx * dx + dy * dy) ** 0.5
        if self._locked_depth and candidate.depth_mm:
            score += min(abs(candidate.depth_mm - self._locked_depth) / 1200.0, 0.6)
        return score

    def _select_active_hand(self, img, depth):
        hand_data = HandData()
        if self._hands is None:
            return hand_data

        detection_img = self._prepare_detection_image(img, depth)
        rgb_img = cv2.cvtColor(detection_img, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb_img)
        if not results.multi_hand_landmarks:
            self._missing_frames += 1
            if self._missing_frames > 45:
                self._locked_palm = None
                self._locked_depth = None
            return hand_data

        candidates = []
        for hand_landmarks in results.multi_hand_landmarks:
            landmarks = hand_landmarks.landmark
            candidate = HandData()
            candidate.palm_x = float(landmarks[9].x)
            candidate.palm_y = float(landmarks[9].y)
            candidate.gesture = self._recognize_gesture(landmarks)
            candidate.confidence = 0.9
            candidate.depth_mm = self._depth_at(depth, candidate.palm_x, candidate.palm_y)
            if depth is not None and candidate.depth_mm == 0:
                candidate.confidence = 0.35
            candidates.append((candidate, hand_landmarks))

        candidate, landmarks_to_draw = min(candidates, key=lambda item: self._candidate_score(item[0]))

        if self._locked_depth and candidate.depth_mm:
            depth_gap = abs(candidate.depth_mm - self._locked_depth)
            if depth_gap > 450 and self._locked_palm is not None:
                self._missing_frames += 1
                return hand_data
        elif self._locked_depth and depth is not None and self._locked_palm is not None:
            # If depth is available but the candidate has no palm depth, keep the
            # current lock instead of jumping to another hand.
            self._missing_frames += 1
            return hand_data

        self._locked_palm = (candidate.palm_x, candidate.palm_y)
        if candidate.depth_mm:
            self._locked_depth = candidate.depth_mm
        self._missing_frames = 0
        candidate.tracking_locked = True

        if self._mp_draw is not None and self._mp_hands is not None:
            self._mp_draw.draw_landmarks(img, landmarks_to_draw, self._mp_hands.HAND_CONNECTIONS)
        return candidate

    def close(self):
        if self._hands:
            self._hands.close()


class OrbbecCamera(BaseHandCamera):
    def __init__(self, width=640, height=480):
        super().__init__(width, height)
        from pyorbbecsdk import Config, OBStreamType, Pipeline
        self._pipeline = Pipeline()
        self._config = Config()
        self._config.enable_stream(OBStreamType.COLOR_STREAM)
        try:
            self._config.enable_stream(OBStreamType.DEPTH_STREAM)
            self._has_depth = True
        except Exception as e:
            print(f"[Camera] Depth stream unavailable: {e}")
            self._has_depth = False
        self._pipeline.start(self._config)
        print("[Camera] Orbbec pipeline started")

    def _decode_color(self, color_frame):
        raw = color_frame.get_data()
        raw_arr = np.frombuffer(raw, dtype=np.uint8)
        if raw_arr.size >= self.width * self.height * 3:
            img = raw_arr[:self.width * self.height * 3].reshape((self.height, self.width, 3))
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        return cv2.imdecode(raw_arr, cv2.IMREAD_COLOR)

    def _decode_depth(self, depth_frame):
        if depth_frame is None:
            return None
        raw = depth_frame.get_data()
        depth = np.frombuffer(raw, dtype=np.uint16)
        if depth.size == 0:
            return None
        h = getattr(depth_frame, "get_height", lambda: self.height)()
        w = getattr(depth_frame, "get_width", lambda: self.width)()
        try:
            return depth[:w * h].reshape((h, w))
        except ValueError:
            return None

    def read(self):
        try:
            frames = self._pipeline.wait_for_frames(100)
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
        except Exception as e:
            print(f"[Camera] Orbbec read error: {e}")
            return None, None, None

    def close(self):
        super().close()
        if hasattr(self, '_pipeline'):
            self._pipeline.stop()


class WebcamCamera(BaseHandCamera):
    def __init__(self, width=640, height=480, camera_index=0):
        super().__init__(width, height)
        self._cap = cv2.VideoCapture(camera_index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self._cap.isOpened():
            raise RuntimeError("Webcam could not be opened")

    def read(self):
        ok, img = self._cap.read()
        if not ok:
            return None, None, None
        img = cv2.flip(img, 1)
        hand_data = self._select_active_hand(img, None)
        return img, None, hand_data

    def close(self):
        super().close()
        if hasattr(self, '_cap'):
            self._cap.release()


def create_camera(source="webcam", width=640, height=480, camera_index=0):
    if source == "orbbec":
        try:
            return OrbbecCamera(width, height)
        except Exception as e:
            print(f"[Camera] Falling back to webcam: {e}")
    return WebcamCamera(width, height, camera_index)


# ============================================================================
# Orbbec SDK v2 适配层（由 apply_blocks_patch.py 添加；删除本段即可还原）
# 目的：用 v2 实现覆盖上面的 v1 版 OrbbecCamera，并替换 create_camera 工厂。
# ============================================================================
try:
    import orbbec_rgbd_v2 as _rgbd_v2

    OrbbecCamera = _rgbd_v2.OrbbecCameraV2
    create_camera = _rgbd_v2.create_camera
    print("[Camera] 已启用 Orbbec SDK v2 适配层")
except Exception as _rgbd_exc:  # noqa: BLE001
    print("[Camera] SDK v2 适配层加载失败，继续使用原实现: %s" % _rgbd_exc)
