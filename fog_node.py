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
EAR_THRESHOLD = 0.22          # Eyes considered closed below this
EAR_CONSEC_FRAMES = 15        # Eyes must stay closed this many frames to trigger drowsy
MAR_THRESHOLD = 0.6           # Mouth considered open (yawning) above this
MAR_CONSEC_FRAMES = 10        # Yawn must last this many frames to count
HEAD_PITCH_THRESHOLD = 15     # Head tilt down in pixels (simplified metric)


class DrowsinessClassifier:
    """Tracks drowsiness state across consecutive frames."""

    def __init__(self):
        self.ear_counter = 0      # consecutive frames with low EAR
        self.mar_counter = 0      # consecutive frames with high MAR
        self.total_drowsy_events = 0
        self.total_yawn_events = 0

    def classify(self, ear, mar, head_pitch):
        """
        Decide if the person is drowsy based on current metrics.
        Returns a dict with status and supporting info.
        """
        drowsy_reasons = []

        # Eye closure check
        if ear < EAR_THRESHOLD:
            self.ear_counter += 1
            if self.ear_counter >= EAR_CONSEC_FRAMES:
                drowsy_reasons.append("eyes_closed")
        else:
            if self.ear_counter >= EAR_CONSEC_FRAMES:
                self.total_drowsy_events += 1
            self.ear_counter = 0

        # Yawn check
        if mar > MAR_THRESHOLD:
            self.mar_counter += 1
            if self.mar_counter >= MAR_CONSEC_FRAMES:
                drowsy_reasons.append("yawning")
        else:
            if self.mar_counter >= MAR_CONSEC_FRAMES:
                self.total_yawn_events += 1
            self.mar_counter = 0

        # Head nod check (simple pitch threshold)
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
    """
    Compute the Eye Aspect Ratio.
    eye_coords: list of 6 (x, y) points around the eye.
    Formula: (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    """
    # Vertical distances
    vertical_1 = dist.euclidean(eye_coords[1], eye_coords[5])
    vertical_2 = dist.euclidean(eye_coords[2], eye_coords[4])
    # Horizontal distance
    horizontal = dist.euclidean(eye_coords[0], eye_coords[3])

    if horizontal == 0:
        return 0.0
    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return ear


def calculate_mar(mouth_coords):
    """
    Compute the Mouth Aspect Ratio.
    mouth_coords: list of 8 (x, y) points around the mouth.
    Index layout matches the MOUTH list in sensor.py:
      [61, 291, 39, 181, 0, 17, 269, 405]
       0    1    2   3   4  5   6    7
    Vertical pairs: (2,3), (4,5), (6,7). Horizontal: (0,1).
    """
    v1 = dist.euclidean(mouth_coords[2], mouth_coords[3])
    v2 = dist.euclidean(mouth_coords[4], mouth_coords[5])
    v3 = dist.euclidean(mouth_coords[6], mouth_coords[7])
    horizontal = dist.euclidean(mouth_coords[0], mouth_coords[1])

    if horizontal == 0:
        return 0.0
    mar = (v1 + v2 + v3) / (3.0 * horizontal)
    return mar


def calculate_head_pitch(nose_coord, chin_coord):
    """
    Simple head pitch estimation based on vertical distance
    between nose tip and chin. When the head tilts down, this
    distance shrinks. We return an inverse proxy for 'nod amount'.
    For a basic project this is good enough.
    """
    # Pixel distance between nose tip and chin
    vertical = abs(chin_coord[1] - nose_coord[1])
    # Lower distance = more nod. We invert to get a pitch score.
    # Typical upright value around 60-90 pixels.
    if vertical == 0:
        return 0
    # Return 0 when upright, positive number when head tilts down
    baseline = 80
    pitch = max(0, baseline - vertical)
    return pitch


def build_payload(classification, timestamp=None):
    """
    Build the JSON payload that the fog node sends to the cloud.
    Only the processed result goes to the cloud - not raw frames.
    """
    if timestamp is None:
        timestamp = time.time()
    return {
        "timestamp": timestamp,
        "status": classification["status"],
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
