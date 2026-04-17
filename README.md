# Drowsiness Detection — Fog & Cloud Architecture

A real-time driver drowsiness detection system built on a three-tier fog and cloud architecture. The system integrates **three distinct sensor types** — a camera (vision), a temperature sensor, and a humidity sensor — processes the data on a virtual fog node, and serves a live dashboard from a Flask backend deployed on **AWS Elastic Beanstalk**.

Developed as part of the Fog and Edge Computing module coursework.

---

## Architecture

![Architecture Diagram](architecture_diagram.png)

The system follows a three-tier fog and cloud pattern:

1. **Sensor layer** — three sensor types generating data at configurable frequencies and dispatch rates:
   - **Camera (vision)** — webcam captured via OpenCV, facial landmarks via MediaPipe (10 FPS processing, 0.5s dispatch)
   - **Temperature** — simulated cabin temperature sensor (1 Hz sampling, 5s dispatch)
   - **Humidity** — simulated cabin humidity sensor (1 Hz sampling, 5s dispatch)

2. **Fog layer** — virtual Python processes on the local machine classify drowsiness using Eye Aspect Ratio (EAR), Mouth Aspect Ratio (MAR), and head pose thresholds. Only classified events and environmental readings (small JSON payloads) are forwarded to the cloud. Raw video never leaves the device.

3. **Cloud layer** — a Flask web service on AWS Elastic Beanstalk receives events via `POST /data`, stores them in SQLite, and serves a real-time dashboard with Chart.js visualisations of all three sensor streams.

---

## Tech stack

- **Python 3.12**
- **OpenCV** — webcam capture
- **MediaPipe** — 468-point facial landmark detection
- **SciPy** — Euclidean distance for EAR / MAR math
- **Flask 3.0 + Gunicorn** — backend web service
- **SQLite** — event persistence
- **Chart.js** — dashboard line charts
- **AWS Elastic Beanstalk** — cloud deployment
- **AWS EC2 / S3** — underlying compute and storage (managed by EB)

---

## Repository structure

```
drowsiness_detection/
├── application.py            # Flask cloud backend (Elastic Beanstalk entrypoint)
├── sensor.py                 # Camera sensor (vision) + fog dispatcher
├── temp_sensor.py            # Temperature sensor (mock environmental)
├── humidity_sensor.py        # Humidity sensor (mock environmental)
├── fog_node.py               # EAR / MAR / head pose logic and classifier
├── requirements.txt          # Cloud-only dependencies (Flask, gunicorn)
├── .ebignore                 # Files excluded from EB uploads
├── .gitignore                # Files excluded from Git
├── templates/
│   └── dashboard.html        # Live dashboard served by Flask
├── architecture_diagram.png  # System architecture image
└── README.md
```

---

## Sensor configuration

Each sensor has independently configurable frequency and dispatch rate, satisfying the "3–5 sensor types with configurable frequency and dispatch rates" requirement.

| Sensor | Type | Sample Frequency | Dispatch Rate | Source ID |
|--------|------|------------------|---------------|-----------|
| Camera | Vision | 10 Hz | 0.5 s | `camera_sensor_01` |
| Temperature | Environmental | 1 Hz | 5 s | `temp_sensor_01` |
| Humidity | Environmental | 1 Hz | 5 s | `humidity_sensor_01` |

---

## Prerequisites

- **Python 3.12** (MediaPipe does not yet support 3.13+)
- **A webcam**
- **An AWS account** with Elastic Beanstalk access (for cloud deployment)
- **Windows / macOS / Linux** (developed and tested on Windows 11 with PowerShell)

---

## Part 1 — Run locally

### Step 1. Clone the repository

```bash
git clone https://github.com/<your-username>/drowsiness-detection.git
cd drowsiness-detection
```

### Step 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3.12 -m venv venv
source venv/bin/activate
```

### Step 3. Install dependencies

Local development requires OpenCV and MediaPipe on top of the cloud requirements:

```bash
pip install --upgrade pip
pip install opencv-python mediapipe flask requests scipy
```

### Step 4. Point sensors to localhost

If your sensor files currently target the AWS URL, switch them back to local:

```powershell
(Get-Content sensor.py) -replace 'BACKEND_URL = "http://[^"]*"', 'BACKEND_URL = "http://localhost:5000/data"' | Set-Content sensor.py
(Get-Content temp_sensor.py) -replace 'BACKEND_URL = "http://[^"]*"', 'BACKEND_URL = "http://localhost:5000/data"' | Set-Content temp_sensor.py
(Get-Content humidity_sensor.py) -replace 'BACKEND_URL = "http://[^"]*"', 'BACKEND_URL = "http://localhost:5000/data"' | Set-Content humidity_sensor.py
```

### Step 5. Start the Flask backend

In terminal 1:
```bash
python application.py
```
You should see `Running on http://127.0.0.1:5000`. Keep this terminal open.

### Step 6. Open the dashboard

In your browser:
```
http://localhost:5000
```

You will see the dashboard with three grey sensor badges and "Waiting for sensor data..."

### Step 7. Start all three sensors

Open **three separate terminals**, activate the virtual environment in each, then run:

**Terminal 2 — camera:**
```bash
python sensor.py
```

**Terminal 3 — temperature:**
```bash
python temp_sensor.py
```

**Terminal 4 — humidity:**
```bash
python humidity_sensor.py
```

### Step 8. Watch the dashboard come alive

Within 5-10 seconds:
- All three sensor badges turn green
- The big status badge turns green AWAKE with live EAR/MAR values
- Temperature and humidity cards show live readings with mini charts
- Recent drowsiness events table populates

### Step 9. Test drowsiness detection

- **Close your eyes for 3 seconds** → status turns red `DROWSY` with reason `eyes_closed`
- **Open your mouth wide** (simulated yawn) → triggers a yawn event
- **Return to normal** → back to green `AWAKE`

Press **`q`** on the webcam window to stop the camera sensor. Press **Ctrl+C** in each terminal to stop the others.

---

## Part 2 — Deploy to AWS Elastic Beanstalk

### Prerequisites
- AWS account with an IAM user that has `AdministratorAccess`
- AWS CLI installed and configured (`aws configure`)

### Step 1. Install the EB CLI

```bash
pip install awsebcli
eb --version
```

### Step 2. Initialise the Elastic Beanstalk project

From inside the project folder:

```bash
eb init
```

Prompts:
- **Region:** pick the one closest to you (e.g. `eu-west-1` for Ireland)
- **Application:** `[ Create new Application ]`
- **Application name:** `drowsiness_detection`
- **Platform:** `Python 3.12 running on 64bit Amazon Linux 2023`
- **CodeCommit:** `n`
- **SSH:** `n` (or `y` if you want SSH access)

### Step 3. Create the environment and deploy

```bash
eb create drowsiness-env --single
```

The `--single` flag uses a single EC2 instance (no load balancer — cheaper for a basic deployment). Expect 4–7 minutes for the environment to launch.

### Step 4. Open the live dashboard

```bash
eb open
```

Your browser opens the public AWS URL, e.g.:
```
http://drowsiness-env.eba-xxxx.eu-west-1.elasticbeanstalk.com
```

### Step 5. Point all three sensors at the cloud URL

```powershell
(Get-Content sensor.py) -replace 'BACKEND_URL = "http://[^"]*"', 'BACKEND_URL = "http://your-env-name.eba-xxxx.eu-west-1.elasticbeanstalk.com/data"' | Set-Content sensor.py
(Get-Content temp_sensor.py) -replace 'BACKEND_URL = "http://[^"]*"', 'BACKEND_URL = "http://your-env-name.eba-xxxx.eu-west-1.elasticbeanstalk.com/data"' | Set-Content temp_sensor.py
(Get-Content humidity_sensor.py) -replace 'BACKEND_URL = "http://[^"]*"', 'BACKEND_URL = "http://your-env-name.eba-xxxx.eu-west-1.elasticbeanstalk.com/data"' | Set-Content humidity_sensor.py
```

Replace `your-env-name.eba-xxxx.eu-west-1.elasticbeanstalk.com` with your actual Elastic Beanstalk CNAME from Step 4.

### Step 6. Run the three sensors locally against the AWS backend

```bash
python sensor.py
python temp_sensor.py
python humidity_sensor.py
```

Your webcam data and environmental readings now stream to AWS, and the cloud dashboard is accessible from any device on the internet.

### Step 7. Redeploying after code changes

If you modify `application.py` or `templates/dashboard.html`:

```bash
eb deploy drowsiness-env
```

Takes about 2-3 minutes.

### Step 8. Clean up (important to avoid charges)

After your demo or grading is done:

```bash
eb terminate drowsiness-env
```

This removes the EC2 instance, security group, and CloudFormation stack to stop any billing.

---

## Configuration

Key parameters you can tune in `sensor.py`:

```python
FPS = 10                          # Camera processing frequency
DISPATCH_INTERVAL_SEC = 0.5       # How often to send to the backend
BACKEND_URL = "http://..."        # Backend endpoint (local or AWS)
```

Drowsiness thresholds in `fog_node.py`:

```python
EAR_THRESHOLD = 0.22              # Eyes considered closed below this
EAR_CONSEC_FRAMES = 15            # Frames of closure before marking drowsy
MAR_THRESHOLD = 0.6               # Mouth considered open (yawn) above this
MAR_CONSEC_FRAMES = 10
```

Environmental sensor parameters (`temp_sensor.py`, `humidity_sensor.py`):

```python
SAMPLE_FREQ_HZ = 1.0              # How often to generate a reading
DISPATCH_INTERVAL_SEC = 5         # How often to send to the backend
```

---

## API endpoints

| Method | Path            | Description                                              |
| ------ | --------------- | -------------------------------------------------------- |
| GET    | `/`             | Serves the live dashboard                                |
| POST   | `/data`         | All sensors post events / readings here                  |
| GET    | `/events`       | Returns recent drowsiness events (camera)                |
| GET    | `/environment`  | Returns recent temperature and humidity readings         |
| GET    | `/sensors`      | Lists sensors that posted in the last minute             |
| GET    | `/stats`        | Returns aggregate statistics                             |
| GET    | `/health`       | Health check endpoint                                    |

---

## Troubleshooting

**MediaPipe fails to install** — you're probably on Python 3.13+. Install Python 3.12 and recreate the virtual environment with `py -3.12 -m venv venv`.

**Backend unreachable in sensor console** — Flask is not running or your `BACKEND_URL` points to the wrong address. Check all three sensor files with `Select-String -Path sensor.py, temp_sensor.py, humidity_sensor.py -Pattern "BACKEND_URL"`.

**Dashboard shows "No recent data"** — sensors are not running or cannot reach the backend. Make sure all three sensor terminals are alive.

**Status badge stuck on "Waiting for sensor data..."** — the camera sensor is not reaching the backend. Hard-refresh the browser with Ctrl+Shift+R and confirm the sensor terminal shows an incrementing `Sent:` counter.

**`eb deploy` fails with "Source bundle exceeds maximum allowed size"** — your `.gitignore` or `.ebignore` is not excluding the `venv/` folder. Run `git rm -r --cached venv` and commit.

**`eb create` fails with IAM errors** — your IAM user needs `AdministratorAccess`. Learner Lab or restricted accounts often block Elastic Beanstalk role creation.

---

## License

Educational project. See the course submission for associated academic license terms.
