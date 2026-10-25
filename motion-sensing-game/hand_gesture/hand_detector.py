"""
Hand detection module
MediaPipe Tasks API for hand detection (mediapipe 0.10+)
"""

import cv2
import numpy as np
import os

# Import from correct location (mediapipe 0.10+)
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
import mediapipe as mp

# Finger info for gesture detection (landmark indices)
FINGER_INFO = {
    'thumb': (4, 3, 0),
    'index': (8, 6, 5),
    'middle': (12, 10, 9),
    'ring': (16, 14, 13),
    'pinky': (20, 18, 17),
}

# Hand landmark connections for drawing
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # index
    (0, 9), (9, 10), (10, 11), (11, 12),  # middle
    (0, 13), (13, 14), (14, 15), (15, 16),  # ring
    (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (5, 9), (9, 13), (13, 17),  # palm
]


class HandDetector:
    """Hand detector using MediaPipe Tasks API"""

    def __init__(self, static_image_mode=False, max_hands=1,
                 min_detection_confidence=0.6, min_tracking_confidence=0.5):
        self.max_hands = max_hands
        self._last_results = None

        # Model path - look in common locations
        model_path = self._find_model()

        # Create hand landmarker - use IMAGE mode for synchronous detection
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            num_hands=max_hands,
            running_mode=vision.RunningMode.IMAGE
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        print(f"[HandDetector] Initialized with model: {model_path}")

    def _find_model(self):
        """Find hand landmarker model file"""
        paths = [
            'hand_landmarker.task',
            './models/hand_landmarker.task',
            './assets/hand_landmarker.task',
            os.path.join(os.path.dirname(__file__), 'hand_landmarker.task'),
        ]
        for p in paths:
            if os.path.exists(p):
                print(f"[HandDetector] Found model at: {p}")
                return p

        # Default path
        default = 'hand_landmarker.task'
        print(f"[HandDetector] Using default model path: {default}")
        return default

    def _on_results(self, result, output_image, timestamp_ms):
        """Callback for async results"""
        self._last_results = result

    def find_hands(self, image, draw=True):
        """Detect hands in image"""
        annotated = image.copy()

        # Create MediaPipe image
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)

        # Detect (synchronous)
        results = self.detector.detect(mp_image)

        landmarks_list = None
        if results and results.hand_landmarks:
            landmarks_list = results.hand_landmarks
            h, w = image.shape[:2]

            if draw:
                for hand_landmarks in landmarks_list:
                    # Draw connections
                    for start, end in HAND_CONNECTIONS:
                        x1 = int(hand_landmarks[start].x * w)
                        y1 = int(hand_landmarks[start].y * h)
                        x2 = int(hand_landmarks[end].x * w)
                        y2 = int(hand_landmarks[end].y * h)
                        cv2.line(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # Draw landmark points
                    for lm in hand_landmarks:
                        x = int(lm.x * w)
                        y = int(lm.y * h)
                        cv2.circle(annotated, (x, y), 4, (0, 0, 255), -1)

        return annotated, landmarks_list

    def get_landmarks(self, image):
        """Get hand landmarks from image"""
        _, results = self.find_hands(image, draw=False)
        if results and len(results) > 0:
            return results[0]
        return None

    def close(self):
        """Close hand detector"""
        if hasattr(self, 'detector') and self.detector:
            self.detector.close()


def is_finger_extended(landmarks, finger_name):
    """Check if finger is extended"""
    if landmarks is None:
        return False

    tip_idx, pip_idx, _ = FINGER_INFO[finger_name]

    # MediaPipe landmark format
    tip_y = landmarks[tip_idx].y
    pip_y = landmarks[pip_idx].y
    wrist_x = landmarks[0].x
    tip_x = landmarks[tip_idx].x
    pip_x = landmarks[pip_idx].x

    if finger_name == 'thumb':
        return abs(tip_x - wrist_x) > abs(pip_x - wrist_x)
    else:
        return tip_y < pip_y


def recognize_grab_gesture(landmarks):
    """
    Detect grab (fist) vs open hand gesture
    Returns: 'grab', 'open', or 'unknown'
    """
    if landmarks is None:
        return 'unknown'

    fingers_extended = {
        'thumb': is_finger_extended(landmarks, 'thumb'),
        'index': is_finger_extended(landmarks, 'index'),
        'middle': is_finger_extended(landmarks, 'middle'),
        'ring': is_finger_extended(landmarks, 'ring'),
        'pinky': is_finger_extended(landmarks, 'pinky'),
    }

    fingers = list(fingers_extended.values())
    extended_count = sum(fingers)

    # Grab: most fingers curled (1 or fewer extended)
    if extended_count <= 1:
        return 'grab'

    # Open: 3 or more fingers extended
    if extended_count >= 3:
        return 'open'

    return 'unknown'
