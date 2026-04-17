# Drowsiness Detection — Fog & Cloud Architecture

A real-time driver drowsiness detection system built on a three-tier fog and cloud architecture. The system uses a webcam as a sensor, a virtual fog node for on-device classification, and a Flask backend deployed on **AWS Elastic Beanstalk** to serve a live dashboard.

Developed as part of the Fog and Edge Computing module coursework.

---

## Architecture

![Architecture Diagram](architecture_diagram.png)

The system follows a three-tier pattern:

1. **Sensor layer** — a webcam captures frames locally using OpenCV and MediaPipe. Three logical sensor streams are derived from the single camera feed: Eye Aspect Ratio (EAR), Mouth Aspect Ratio (MAR), and head pose angle.
2. **Fog layer** — a virtual Python process on the local machine classifies drowsiness using rule-based thresholds and forwards only the classified event (a small JSON payload) to the cloud. Raw video never leaves the device.
3. **Cloud layer** — a Flask web service on AWS Elastic Beanstalk receives events via `POST /data`, stores them in SQLite, and serves a real-time dashboard with Chart.js visualisations.

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
├── application.py           # Flask cloud backend (Elastic Beanstalk entrypoint)
├── sensor.py                # Camera sensor + fog dispatcher
├── fog_node.py              # EAR / MAR / head pose logic and classifier
├── requirements.txt         # Cloud-only dependencies (Flask, gunicorn)
├── .ebignore                # Files excluded from EB uploads
├── templates/
│   └── dashboard.html       # Live dashboard served by Flask
├── architecture_diagram.png # System architecture image
└── README.md
```

---

## Prerequisites

- **Python 3.12** (MediaPipe does not yet support 3.13+)
- **A webcam**
- **An AWS account** with Elastic Beanstalk access (for cloud deployment — optional if running locally only)
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

Local development needs OpenCV and MediaPipe on top of the cloud requirements:

```bash
pip install --upgrade pip
pip install opencv-python mediapipe flask requests scipy
```

### Step 4. Run the Flask backend

In terminal 1:

```bash
python application.py
```

You should see `Running on http://127.0.0.1:5000`.

### Step 5. Open the dashboard

In your browser, open:

```
http://localhost:5000
```

You will see the dashboard with a "Waiting for sensor data..." message.

### Step 6. Run the sensor

In a **second** terminal (with the virtual environment activated):

```bash
python sensor.py
```

A webcam window opens showing your face with landmark dots drawn on your eyes and mouth. The sensor will:
- Process frames at 10 FPS (configurable via `FPS` in `sensor.py`)
- Classify drowsiness locally in the fog node
- POST events to the backend every 0.5 seconds (configurable via `DISPATCH_INTERVAL_SEC`)

### Step 7. Test drowsiness detection

Watch the dashboard while you:
- **Close your eyes for 3 seconds** → dashboard turns red with `DROWSY` status
- **Open your mouth wide** (simulate yawning) → triggers a yawn event
- **Open eyes normally** → returns to green `AWAKE`

Press **`q`** on the webcam window to stop the sensor.

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

Answers to the prompts:
- **Region:** pick the one closest to you (e.g. `eu-west-1` for Ireland)
- **Application:** `[ Create new Application ]`
- **Application name:** `drowsiness_detection`
- **Platform:** `Python 3.12 running on 64bit Amazon Linux 2023`
- **CodeCommit:** `n`
- **SSH:** `n` (or `y` if you want to SSH into the instance)

### Step 3. Create the environment and deploy

```bash
eb create drowsiness-env --single
```

The `--single` flag uses a single EC2 instance without a load balancer (cheaper; suitable for a basic deployment). Expect 4–7 minutes for the environment to launch.

### Step 4. Open the live dashboard

```bash
eb open
```

Your browser opens to the public AWS URL (e.g. `http://drowsiness-env.eba-xxxx.eu-west-1.elasticbeanstalk.com`).

### Step 5. Point the sensor at the cloud

Edit the `BACKEND_URL` variable near the top of `sensor.py`:

```python
BACKEND_URL = "http://your-env-name.eba-xxxx.eu-west-1.elasticbeanstalk.com/data"
```

Then run the sensor locally:

```bash
python sensor.py
```

Your webcam data will now stream to the AWS backend, and the dashboard URL will update live — accessible from any device on the internet.

### Step 6. Clean up (important to avoid charges)

After your demo / grading is done:

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
BACKEND_URL = "http://..."        # Cloud endpoint
```

Drowsiness thresholds in `fog_node.py`:

```python
EAR_THRESHOLD = 0.22              # Eyes considered closed below this
EAR_CONSEC_FRAMES = 15            # Frames of closure before marking drowsy
MAR_THRESHOLD = 0.6               # Mouth open (yawn) above this
MAR_CONSEC_FRAMES = 10
```

---

## API endpoints

| Method | Path       | Description                                 |
| ------ | ---------- | ------------------------------------------- |
| GET    | `/`        | Serves the live dashboard                   |
| POST   | `/data`    | Fog node posts drowsiness events here       |
| GET    | `/events`  | Returns the last 50 events as JSON          |
| GET    | `/stats`   | Returns aggregate statistics                |
| GET    | `/health`  | Health check endpoint                       |

---

## Troubleshooting

**MediaPipe fails to install** — you're probably on Python 3.13+. Install Python 3.12 and recreate the virtual environment with `py -3.12 -m venv venv`.

**Backend unreachable in sensor console** — Flask is not running. Start it in a separate terminal with `python application.py`.

**Dashboard shows "No recent data"** — sensor is not running or cannot reach the backend. Check the `BACKEND_URL` in `sensor.py`.

**`eb create` fails with IAM errors** — your IAM user needs `AdministratorAccess`. Learner Lab or restricted accounts often block Elastic Beanstalk role creation.

---

## License

Educational project. See the course submission for associated academic license terms.
