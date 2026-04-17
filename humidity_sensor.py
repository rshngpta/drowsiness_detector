"""
Environmental sensor - Humidity.
Simulates an in-cabin humidity sensor. Posts readings to the cloud
backend at a configurable interval.
"""

import requests
import time
import random
import math

# ==========================================
# CONFIGURATION
# ==========================================
SENSOR_ID = "humidity_sensor_01"
SENSOR_TYPE = "humidity"
UNIT = "percent"

SAMPLE_FREQ_HZ = 1.0       # Generate one reading per second
DISPATCH_INTERVAL_SEC = 5  # Send to backend every 5 seconds
BACKEND_URL = "http://drowsiness-env.eba-nnmq8rw3.eu-west-1.elasticbeanstalk.com/data"  # Change to your AWS URL for cloud mode
POST_TIMEOUT_SEC = 3

# Humidity simulation parameters (%)
BASE_HUMIDITY = 55.0
MIN_HUMIDITY = 30.0
MAX_HUMIDITY = 85.0
DRIFT_AMOUNT = 0.5         # How much humidity drifts per reading
# ==========================================


def generate_humidity(current_humidity, t):
    """Simulate realistic humidity drift."""
    # Slow sine wave + random drift (humidity changes slower than temp)
    sine_component = math.sin(t / 90.0) * 1.0
    noise = random.uniform(-DRIFT_AMOUNT, DRIFT_AMOUNT)
    new_humidity = current_humidity + noise + (sine_component * 0.08)
    return max(MIN_HUMIDITY, min(MAX_HUMIDITY, new_humidity))


def build_payload(humidity):
    """Build JSON payload matching the backend's expected schema."""
    return {
        "timestamp": time.time(),
        "status": "ENV_READING",
        "source": SENSOR_ID,
        "sensor_type": SENSOR_TYPE,
        "reasons": [],
        "metrics": {
            "value": round(humidity, 1),
            "unit": UNIT
        },
        "totals": {
            "drowsy_events": 0,
            "yawn_events": 0
        }
    }


def main():
    print(f"Humidity sensor started.")
    print(f"  Sensor ID: {SENSOR_ID}")
    print(f"  Sample frequency: {SAMPLE_FREQ_HZ} Hz")
    print(f"  Dispatch interval: {DISPATCH_INTERVAL_SEC} s")
    print(f"  Backend: {BACKEND_URL}")
    print("Press Ctrl+C to stop.\n")

    current_humidity = BASE_HUMIDITY
    start_time = time.time()
    last_dispatch = 0
    sent = 0
    failed = 0
    sample_interval = 1.0 / SAMPLE_FREQ_HZ

    try:
        while True:
            t = time.time() - start_time
            current_humidity = generate_humidity(current_humidity, t)

            now = time.time()
            if now - last_dispatch >= DISPATCH_INTERVAL_SEC:
                last_dispatch = now
                payload = build_payload(current_humidity)

                try:
                    resp = requests.post(BACKEND_URL, json=payload, timeout=POST_TIMEOUT_SEC)
                    if resp.status_code == 200:
                        sent += 1
                        print(f"[humidity] Sent {current_humidity:.1f}% "
                              f"at {time.strftime('%H:%M:%S')} "
                              f"(total sent: {sent})")
                    else:
                        failed += 1
                        print(f"[humidity] Backend returned {resp.status_code}")
                except requests.exceptions.ConnectionError:
                    failed += 1
                    if failed % 3 == 1:
                        print(f"[humidity] Backend unreachable at {BACKEND_URL}")
                except Exception as e:
                    failed += 1
                    print(f"[humidity] Error: {e}")

            time.sleep(sample_interval)

    except KeyboardInterrupt:
        print(f"\nHumidity sensor stopped.")
        print(f"Total sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    main()
