"""
Quick test script to verify all modules can be imported.
Run this before starting the game to check dependencies.
"""

import sys

def test_imports():
    """Test that all required modules can be imported."""
    errors = []

    try:
        import pygame
        print("[OK] pygame")
    except ImportError as e:
        errors.append(f"[FAIL] pygame: {e}")

    try:
        import cv2
        print(f"[OK] opencv-python (version: {cv2.__version__})")
    except ImportError as e:
        errors.append(f"[FAIL] opencv-python: {e}")

    try:
        import numpy as np
        print(f"[OK] numpy (version: {np.__version__})")
    except ImportError as e:
        errors.append(f"[FAIL] numpy: {e}")

    try:
        import mediapipe as mp
        print(f"[OK] mediapipe (version: {mp.__version__})")
    except ImportError as e:
        print(f"[WARN] mediapipe not installed - will use fallback detection")

    # Test local modules
    try:
        import sys
        sys.path.insert(0, '.')
        from config import WINDOW_WIDTH, WINDOW_HEIGHT
        print(f"[OK] config module")
    except ImportError as e:
        errors.append(f"[FAIL] config: {e}")

    try:
        from camera import CameraSource, HandData, GestureState, create_camera
        print(f"[OK] camera module")
    except ImportError as e:
        errors.append(f"[FAIL] camera: {e}")

    try:
        from objects import GameObject, ObjectManager, ObjectShape
        print(f"[OK] objects module")
    except ImportError as e:
        errors.append(f"[FAIL] objects: {e}")

    try:
        from game_logic import GameLogic, CollisionSystem
        print(f"[OK] game_logic module")
    except ImportError as e:
        errors.append(f"[FAIL] game_logic: {e}")

    try:
        from ui import UIManager, CameraPreview, ParticleSystem
        print(f"[OK] ui module")
    except ImportError as e:
        errors.append(f"[FAIL] ui: {e}")

    try:
        from utils import normalize_hand_position, smooth_value, MovingAverage
        print(f"[OK] utils module")
    except ImportError as e:
        errors.append(f"[FAIL] utils: {e}")

    print()
    if errors:
        print("ERRORS FOUND:")
        for err in errors:
            print(f"  {err}")
        return False
    else:
        print("All modules OK!")
        return True


if __name__ == "__main__":
    print("Testing imports...")
    print("-" * 40)
    success = test_imports()
    print("-" * 40)
    sys.exit(0 if success else 1)
