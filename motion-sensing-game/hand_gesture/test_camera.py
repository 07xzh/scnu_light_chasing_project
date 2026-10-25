"""Test camera and hand detection"""
import cv2
import sys
sys.path.insert(0, '.')

from hand_detector import HandDetector, recognize_grab_gesture

def test_camera():
    """Test camera and hand detection"""
    detector = HandDetector(
        static_image_mode=False,
        max_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5
    )

    cap = cv2.VideoCapture(3)
    if not cap.isOpened():
        print("Cannot open camera!")
        return

    print("Press 'q' to quit")
    print("=" * 50)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame")
            break

        # Mirror
        frame = cv2.flip(frame, 1)

        # Detect hands
        annotated, landmarks = detector.find_hands(frame, draw=True)

        gesture = "unknown"
        if landmarks and len(landmarks) > 0:
            lm = landmarks[0].landmark
            gesture = recognize_grab_gesture(lm)

            # Calculate palm center
            palm_indices = [0, 5, 9, 13, 17]
            palm_x = sum(lm[i].x for i in palm_indices) / 5
            palm_y = sum(lm[i].y for i in palm_indices) / 5

            print(f"\rGesture: {gesture:6} | Palm: ({palm_x:.2f}, {palm_y:.2f})", end="")

        cv2.imshow("Hand Detection Test", annotated)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

    print("\n" + "=" * 50)
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print("Test complete")

if __name__ == '__main__':
    test_camera()
