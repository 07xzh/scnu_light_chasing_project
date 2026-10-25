"""Minimal test for camera and hand detection - no GUI"""
import time
import sys
sys.path.insert(0, '.')

from camera import WebcamCamera

def test():
    print("Initializing camera...")
    cam = WebcamCamera(640, 480)
    print("Camera initialized!")

    print("Starting detection test (5 seconds)...")

    start_time = time.time()
    frame_count = 0
    hand_detected_count = 0

    while time.time() - start_time < 5:
        frame, depth, hand_data = cam.read()

        if frame is None:
            print("No frame!")
            continue

        frame_count += 1
        if hand_data and hand_data.is_valid():
            hand_detected_count += 1
            if frame_count % 30 == 0:
                print(f"Frame {frame_count}: Hand at ({hand_data.palm_x}, {hand_data.palm_y}), gesture={hand_data.gesture.value}")

    cam.close()
    print(f"\nResults:")
    print(f"  Total frames: {frame_count}")
    print(f"  Hand detected: {hand_detected_count} times")
    print(f"  Detection rate: {hand_detected_count/max(frame_count,1)*100:.1f}%")
    print("Done!")

if __name__ == '__main__':
    test()
