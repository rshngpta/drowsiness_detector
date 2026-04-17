"""
Sensor layer - Camera sensor for drowsiness detection.
Captures webcam frames, extracts facial landmarks via MediaPipe,
passes data to the fog node for classification, and dispatches
processed events to the cloud backend via HTTP POST.

The POST happens on a background thread so the webcam stays smooth
even if the network is slow.
"""

import cv2
import mediapipe as mp
import time
import threading
import queue
import requests

from fog_node import (
    DrowsinessClassifier,
    calculate_ear,
    calculate_mar,
    calculate_head_pitch,
    build_payload
)

# ==========================================
# CONFIGURATION (change these as needed)
# ==========================================
FPS = 10                                   # Camera/processing frames per second
DISPATCH_INTERVAL_SEC = 0.5                # How often to send to backend (seconds)
BACKEND_URL = "http://drowsiness-env.eba-nnmq8rw3.eu-west-1.elasticbeanstalk.com/data" # Cloud backend endpoint
POST_TIMEOUT_SEC = 2                       # HTTP timeout
# ==========================================

FRAME_INTERVAL = 1.0 / FPS

# Initialize MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Landmark indices
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
MOUTH = [61, 291, 39, 181, 0, 17, 269, 405]
NOSE_TIP = 1
CHIN = 152

# Background dispatch queue and stop flag
dispatch_queue = queue.Queue(maxsize=100)
stop_flag = threading.Event()


def dispatch_worker():
    """Background thread: reads payloads from queue and POSTs them to the backend."""
    sent = 0
    failed = 0
    while not stop_flag.is_set():
        try:
            payload = dispatch_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            resp = requests.post(BACKEND_URL, json=payload, timeout=POST_TIMEOUT_SEC)
            if resp.status_code == 200:
                sent += 1
                if sent % 10 == 0:
                    print(f"  [dispatch] {sent} events sent to backend")
            else:
                failed += 1
                print(f"  [dispatch] Backend returned {resp.status_code}")
        except requests.exceptions.ConnectionError:
            failed += 1
            if failed % 5 == 1:  # Log every 5th failure to avoid spam
                print(f"  [dispatch] Backend unreachable at {BACKEND_URL}")
        except Exception as e:
            failed += 1
            print(f"  [dispatch] Error: {e}")
        finally:
            dispatch_queue.task_done()

    print(f"  [dispatch] Thread stopped. Sent: {sent}, Failed: {failed}")


def get_landmark_coords(landmarks, indices, image_width, image_height):
    coords = []
    for idx in indices:
        lm = landmarks.landmark[idx]
        coords.append((int(lm.x * image_width), int(lm.y * image_height)))
    return coords


def get_single_coord(landmarks, index, image_width, image_height):
    lm = landmarks.landmark[index]
    return (int(lm.x * image_width), int(lm.y * image_height))


def draw_overlay(frame, payload, events_sent):
    """Draw status overlay on the frame."""
    status = payload["status"]
    ear = payload["metrics"]["ear"]
    mar = payload["metrics"]["mar"]
    pitch = payload["metrics"]["head_pitch"]

    color = (0, 0, 255) if status == "DROWSY" else (0, 200, 0)
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 50), color, -1)
    cv2.putText(frame, f"STATUS: {status}", (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    y0 = frame.shape[0] - 100
    cv2.putText(frame, f"EAR: {ear:.3f}", (10, y0),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"MAR: {mar:.3f}", (10, y0 + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Pitch: {pitch:.1f}", (10, y0 + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Dispatched: {events_sent}", (10, y0 + 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam")
        return

    classifier = DrowsinessClassifier()

    # Start dispatch worker thread
    dispatch_thread = threading.Thread(target=dispatch_worker, daemon=True)
    dispatch_thread.start()

    print(f"Camera sensor started. Processing at {FPS} FPS.")
    print(f"Dispatching to {BACKEND_URL} every {DISPATCH_INTERVAL_SEC}s.")
    print("Press 'q' on the video window to quit.\n")

    last_process_time = 0
    last_dispatch_time = 0
    frame_count = 0
    dispatch_count = 0
    last_payload = None

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break

            current_time = time.time()

            # Throttle processing
            if current_time - last_process_time < FRAME_INTERVAL:
                if last_payload:
                    draw_overlay(frame, last_payload, dispatch_count)
                cv2.imshow('Drowsiness Sensor', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            last_process_time = current_time
            frame_count += 1

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)
            image_height, image_width = frame.shape[:2]

            payload = None
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    left_eye = get_landmark_coords(face_landmarks, LEFT_EYE, image_width, image_height)
                    right_eye = get_landmark_coords(face_landmarks, RIGHT_EYE, image_width, image_height)
                    mouth = get_landmark_coords(face_landmarks, MOUTH, image_width, image_height)
                    nose = get_single_coord(face_landmarks, NOSE_TIP, image_width, image_height)
                    chin = get_single_coord(face_landmarks, CHIN, image_width, image_height)

                    avg_ear = (calculate_ear(left_eye) + calculate_ear(right_eye)) / 2.0
                    mar = calculate_mar(mouth)
                    head_pitch = calculate_head_pitch(nose, chin)

                    classification = classifier.classify(avg_ear, mar, head_pitch)
                    payload = build_payload(classification)
                    last_payload = payload

                    # Draw landmarks
                    for (x, y) in left_eye + right_eye:
                        cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)
                    for (x, y) in mouth:
                        cv2.circle(frame, (x, y), 2, (255, 0, 0), -1)
                    cv2.circle(frame, nose, 3, (0, 255, 255), -1)
                    cv2.circle(frame, chin, 3, (0, 255, 255), -1)

                    # Dispatch to backend at configured interval
                    if current_time - last_dispatch_time >= DISPATCH_INTERVAL_SEC:
                        last_dispatch_time = current_time
                        try:
                            dispatch_queue.put_nowait(payload)
                            dispatch_count += 1
                        except queue.Full:
                            print("  [dispatch] Queue full, dropping event")

                    if frame_count % 10 == 0:
                        print(f"Frame {frame_count} | "
                              f"Status: {payload['status']:6} | "
                              f"EAR: {payload['metrics']['ear']:.3f} | "
                              f"MAR: {payload['metrics']['mar']:.3f} | "
                              f"Pitch: {payload['metrics']['head_pitch']:.1f} | "
                              f"Sent: {dispatch_count}")
            else:
                if frame_count % 20 == 0:
                    print(f"Frame {frame_count}: No face detected")

            if payload:
                draw_overlay(frame, payload, dispatch_count)

            cv2.imshow('Drowsiness Sensor', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        # Cleanup
        stop_flag.set()
        cap.release()
        cv2.destroyAllWindows()
        face_mesh.close()
        dispatch_thread.join(timeout=2)
        print(f"\nSensor stopped.")
        print(f"Total frames: {frame_count}")
        print(f"Events dispatched: {dispatch_count}")


if __name__ == "__main__":
    main()
