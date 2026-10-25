"""Quick test for camera and hand detection"""
import cv2
import time
import sys
sys.path.insert(0, '.')

from camera import WebcamCamera

def test():
    print("Initializing camera...")
    cam = WebcamCamera(640, 480)

    print("Starting detection test...")
    print("Press Ctrl+C to exit")

    frame_count = 0
    last_time = time.time()

    try:
        while True:
            frame, depth, hand_data = cam.read()

            if frame is None:
                print("No frame!")
                continue

            frame_count += 1

            # Print FPS every second
            now = time.time()
            if now - last_time >= 1.0:
                fps = frame_count / (now - last_time)
                print(f"FPS: {fps:.1f}, Hand: {'Yes' if hand_data and hand_data.is_valid() else 'No'}")
                frame_count = 0
                last_time = now

            # Draw hand position if detected
            if hand_data and hand_data.is_valid():
                x, y = hand_data.palm_x, hand_data.palm_y
                gesture = hand_data.gesture.value
                cv2.circle(frame, (x, y), 20, (0, 255, 0), 2)
                cv2.putText(frame, gesture, (x-30, y-30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            cv2.imshow("Test", frame)
            cv2.waitKey(1)

    except KeyboardInterrupt:
        print("\nExiting...")

    cam.close()
    cv2.destroyAllWindows()
    print("Done")

if __name__ == '__main__':
    test()
