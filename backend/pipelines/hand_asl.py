import os, sys
import cv2
import numpy as np
import keras

SIGN_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models")
SIGN_PATH = os.path.abspath(SIGN_PATH)

import mediapipe as mp
from mediapipe.tasks import python as mp_py
from mediapipe.tasks.python import vision

LETTERS = "ABCDEFGHIKLMNOPQRSTUVWXY"

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]


from pipelines import BasePipeline

class HandASLPipeline(BasePipeline):
    name = "hand_asl"

    def __init__(self):
        self.model = None
        self.landmarker = None

    def load(self):
        mp_path = os.path.join(SIGN_PATH, "hand_landmarker.task")
        model_path = os.path.join(SIGN_PATH, "model5.keras")

        for delegate, label in [(mp_py.BaseOptions.Delegate.GPU, "GPU"),
                                 (mp_py.BaseOptions.Delegate.CPU, "CPU")]:
            try:
                options = vision.HandLandmarkerOptions(
                    base_options=mp_py.BaseOptions(
                        model_asset_path=mp_path, delegate=delegate),
                    num_hands=1, min_hand_detection_confidence=0.75,
                    min_tracking_confidence=0.75,
                    running_mode=vision.RunningMode.IMAGE)
                self.landmarker = vision.HandLandmarker.create_from_options(options)
                print(f"[ASL] Hand landmarker loaded ({label})")
                break
            except Exception as e:
                print(f"[ASL] {label} delegate failed: {e}")

        self.model = keras.models.load_model(model_path)
        print("[ASL] Model loaded")

    def process(self, image):
        """image: BGR numpy array. Returns {'letter': str, 'conf': float, 'landmarks': np.ndarray} or None."""
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)

        if not result.hand_landmarks:
            return None

        hand = result.hand_landmarks[0]
        raw_pts = np.array([[lm.x, lm.y, lm.z] for lm in hand], dtype=np.float32)
        points = raw_pts.copy()
        min_x, max_x = points[:, 0].min(), points[:, 0].max()
        min_y, max_y = points[:, 1].min(), points[:, 1].max()
        points[:, 0] = (points[:, 0] - min_x) / (max_x - min_x + 1e-8)
        points[:, 1] = (points[:, 1] - min_y) / (max_y - min_y + 1e-8)
        points = np.expand_dims(points, axis=0)

        preds = self.model.predict(points[:, :, :2], verbose=0)
        idx = int(preds[0].argmax())
        prob = float(preds[0][idx])
        letter = LETTERS[idx]
        letter = self._fix(letter, raw_pts)

        # Send back raw landmarks for drawing on frontend
        lms = [[lm.x, lm.y, lm.z] for lm in hand]
        return {"letter": letter, "conf": prob, "landmarks": lms}

    def _fix(self, letter, pts):
        if letter in ["D", "I"]:
            letter = "I" if pts[8, 1] > pts[20, 1] else "D"
        if letter in ["F", "W"]:
            letter = "F" if pts[8, 1] > pts[20, 1] else "W"
        if letter in ["K", "V", "U", "I", "D", "X"]:
            if pts[12, 1] < pts[11, 1]:
                between = (pts[8, 0] < pts[4, 0] < pts[12, 0]) or (pts[12, 0] < pts[4, 0] < pts[8, 0])
                if between:
                    letter = "K"
        return letter
