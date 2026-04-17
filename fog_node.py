"""
Fog node layer - Processes sensor data and classifies drowsiness.
Calculates EAR (Eye Aspect Ratio), MAR (Mouth Aspect Ratio), head pose,
and applies the drowsiness classification logic.

In a real deployment this would run on a separate fog device. For this
basic project, it runs as a module imported by sensor.py on the same machine.
"""

from scipy.spatial import distance as dist
import time

# Drowsiness detection thresholds
EAR_THRESHOLD = 0.22
EAR_CONSEC_FRAMES = 15
MAR_THRESHOLD = 0.6
MAR_CONSEC_FRAMES = 10
HEAD_PITCH_THRESHOLD = 15


class DrowsinessClassifier:
    """Tracks drowsiness state across consecutive frames."""

    def __init__(self):
        self.ear_counter = 0
        self.mar_counter = 0
        self.total_drowsy_events = 0
        self.total_yawn_events = 0

    def classify(self, ear, mar, head_pitch):
        drowsy_reasons = []

        if ear < EAR_THRESHOLD:
            self.ear_counter += 1
            if self.ear_counter >= EAR_CONSEC_FRAMES:
                drowsy_reasons.append("eyes_closed")
        else:
            if self.ear_counter >= EAR_CONSEC_FRAMES:
                self.total_drowsy_events += 1
            self.ear_counter = 0

        if mar > MAR_THRESHOLD:
            self.mar_counter += 1
            if self.mar_counter >= MAR_CONSEC_FRAMES:
                drowsy_reasons.append("yawning")
        else:
            if self.mar_counter >= MAR_CONSEC_FRAMES:
                self.total_yawn_events += 1
            self.mar_counter = 0

        if head_pitch > HEAD_PITCH_THRESHOLD:
            drowsy_reasons.append("head_nod")

        status = "DROWSY" if drowsy_reasons else "AWAKE"

        return {
            "status": status,
            "reasons": drowsy_reasons,
            "ear": round(ear, 3),
            "mar": round(mar, 3),
            "head_pitch": round(head_pitch, 2),
            "ear_counter": self.ear_counter,
            "mar_counter": self.mar_counter,
            "total_drowsy_events": self.total_drowsy_events,
            "total_yawn_events": self.total_yawn_events
        }


def calculate_ear(eye_coords):
    vertical_1 = dist.euclidean(eye_coords[1], eye_coords[5])
    vertical_2 = dist.euclidean(eye_coords[2], eye_coords[4])
    horizontal = dist.euclidean(eye_coords[0], eye_coords[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def calculate_mar(mouth_coords):
    v1 = dist.euclidean(mouth_coords[2], mouth_coords[3])
    v2 = dist.euclidean(mouth_coords[4], mouth_coords[5])
    v3 = dist.euclidean(mouth_coords[6], mouth_coords[7])
    horizontal = dist.euclidean(mouth_coords[0], mouth_coords[1])
    if horizontal == 0:
        return 0.0
    return (v1 + v2 + v3) / (3.0 * horizontal)


def calculate_head_pitch(nose_coord, chin_coord):
    vertical = abs(chin_coord[1] - nose_coord[1])
    if vertical == 0:
        return 0
    baseline = 80
    return max(0, baseline - vertical)


def build_payload(classification, timestamp=None):
    """
    Build the JSON payload that the fog node sends to the cloud.
    Includes source and sensor_type so the backend can distinguish
    camera events from environmental readings.
    """
    if timestamp is None:
        timestamp = time.time()
    return {
        "timestamp": timestamp,
        "status": classification["status"],
        "source": "camera_sensor_01",
        "sensor_type": "vision",
        "reasons": classification["reasons"],
        "metrics": {
            "ear": classification["ear"],
            "mar": classification["mar"],
            "head_pitch": classification["head_pitch"]
        },
        "totals": {
            "drowsy_events": classification["total_drowsy_events"],
            "yawn_events": classification["total_yawn_events"]
        }
    }
