"""
Environmental sensor - Temperature.
Simulates an in-cabin temperature sensor. Posts readings to the cloud
backend at a configurable interval. Temperature drifts slowly with
occasional random spikes to look realistic.
"""

import requests
import time
import random
import math

# ==========================================
# CONFIGURATION
# ==========================================
SENSOR_ID = "temp_sensor_01"
SENSOR_TYPE = "temperature"
UNIT = "celsius"

SAMPLE_FREQ_HZ = 1.0       # Generate one reading per second
DISPATCH_INTERVAL_SEC = 5  # Send to backend every 5 seconds
BACKEND_URL = "http://drowsiness-env.eba-nnmq8rw3.eu-west-1.elasticbeanstalk.com/data"  # Change to your AWS URL for cloud mode
POST_TIMEOUT_SEC = 3

# Temperature simulation parameters (in Celsius)
BASE_TEMP = 24.0           # Normal cabin temperature
MIN_TEMP = 18.0
MAX_TEMP = 32.0
DRIFT_AMOUNT = 0.15        # How much temp drifts per reading
# ==========================================


def generate_temperature(current_temp, t):
    """Simulate realistic temperature drift with gentle sine wave."""
    # Slow sine wave + small random drift
    sine_component = math.sin(t / 60.0) * 0.5
    noise = random.uniform(-DRIFT_AMOUNT, DRIFT_AMOUNT)
    new_temp = current_temp + noise + (sine_component * 0.05)
    # Clamp to realistic range
    return max(MIN_TEMP, min(MAX_TEMP, new_temp))


def build_payload(temperature):
    """Build JSON payload matching the backend's expected schema."""
    return {
        "timestamp": time.time(),
        "status": "ENV_READING",              # Not AWAKE/DROWSY - it's an env reading
        "source": SENSOR_ID,
        "sensor_type": SENSOR_TYPE,
        "reasons": [],
        "metrics": {
            "value": round(temperature, 2),
            "unit": UNIT
        },
        "totals": {
            "drowsy_events": 0,
            "yawn_events": 0
        }
    }


def main():
    print(f"Temperature sensor started.")
    print(f"  Sensor ID: {SENSOR_ID}")
    print(f"  Sample frequency: {SAMPLE_FREQ_HZ} Hz")
    print(f"  Dispatch interval: {DISPATCH_INTERVAL_SEC} s")
    print(f"  Backend: {BACKEND_URL}")
    print("Press Ctrl+C to stop.\n")

    current_temp = BASE_TEMP
    start_time = time.time()
    last_dispatch = 0
    sent = 0
    failed = 0
    sample_interval = 1.0 / SAMPLE_FREQ_HZ

    try:
        while True:
            t = time.time() - start_time
            current_temp = generate_temperature(current_temp, t)

            # Dispatch at configured interval
            now = time.time()
            if now - last_dispatch >= DISPATCH_INTERVAL_SEC:
                last_dispatch = now
                payload = build_payload(current_temp)

                try:
                    resp = requests.post(BACKEND_URL, json=payload, timeout=POST_TIMEOUT_SEC)
                    if resp.status_code == 200:
                        sent += 1
                        print(f"[temp] Sent {current_temp:.1f}°C "
                              f"at {time.strftime('%H:%M:%S')} "
                              f"(total sent: {sent})")
                    else:
                        failed += 1
                        print(f"[temp] Backend returned {resp.status_code}")
                except requests.exceptions.ConnectionError:
                    failed += 1
                    if failed % 3 == 1:
                        print(f"[temp] Backend unreachable at {BACKEND_URL}")
                except Exception as e:
                    failed += 1
                    print(f"[temp] Error: {e}")

            time.sleep(sample_interval)

    except KeyboardInterrupt:
        print(f"\nTemperature sensor stopped.")
        print(f"Total sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    main()
