"""
Cloud backend - Flask web service for drowsiness detection.
Receives processed events from the fog node and environmental sensors,
stores them in SQLite, and serves the dashboard.

Named application.py with Flask app named 'application' for Elastic Beanstalk.
"""

from flask import Flask, request, jsonify, render_template
import sqlite3
import os
import json
from datetime import datetime, timezone

# Initialize Flask app - MUST be named 'application' for Elastic Beanstalk
application = Flask(__name__)

# Database file - use /tmp on EB (writable), else next to script locally
if os.environ.get('EB_DEPLOYED') == '1':
    DB_PATH = '/tmp/events.db'
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'events.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # Main events table (drowsiness events from camera)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            status TEXT NOT NULL,
            source TEXT DEFAULT 'camera',
            sensor_type TEXT DEFAULT 'vision',
            reasons TEXT,
            ear REAL,
            mar REAL,
            head_pitch REAL,
            env_value REAL,
            env_unit TEXT,
            drowsy_events INTEGER,
            yawn_events INTEGER,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # Migrate older DBs that don't yet have the new columns
    cursor.execute("PRAGMA table_info(events)")
    columns = [row[1] for row in cursor.fetchall()]
    for col, sql in [
        ('source',       "ALTER TABLE events ADD COLUMN source TEXT DEFAULT 'camera'"),
        ('sensor_type',  "ALTER TABLE events ADD COLUMN sensor_type TEXT DEFAULT 'vision'"),
        ('env_value',    "ALTER TABLE events ADD COLUMN env_value REAL"),
        ('env_unit',     "ALTER TABLE events ADD COLUMN env_unit TEXT"),
    ]:
        if col not in columns:
            try:
                cursor.execute(sql)
                conn.commit()
                print(f"Migrated: added column '{col}'")
            except Exception as e:
                print(f"Migration warning for '{col}': {e}")

    conn.close()
    print(f"Database initialized at {DB_PATH}")


init_db()


@application.after_request
def add_cors_headers(response):
    """Allow sensors to POST from any origin (needed when hitting the cloud URL)."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@application.route('/')
def dashboard():
    return render_template('dashboard.html')


@application.route('/data', methods=['POST', 'OPTIONS'])
def receive_data():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "No JSON body"}), 400

        metrics = payload.get('metrics', {})
        # For drowsiness events metrics has ear/mar/head_pitch
        # For env sensors metrics has value/unit
        env_value = metrics.get('value')
        env_unit = metrics.get('unit')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events
            (timestamp, status, source, sensor_type, reasons, ear, mar, head_pitch,
             env_value, env_unit, drowsy_events, yawn_events)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            payload.get('timestamp'),
            payload.get('status'),
            payload.get('source', 'camera'),
            payload.get('sensor_type', 'vision'),
            json.dumps(payload.get('reasons', [])),
            metrics.get('ear'),
            metrics.get('mar'),
            metrics.get('head_pitch'),
            env_value,
            env_unit,
            payload.get('totals', {}).get('drowsy_events', 0),
            payload.get('totals', {}).get('yawn_events', 0)
        ))
        conn.commit()
        event_id = cursor.lastrowid
        conn.close()
        return jsonify({"ok": True, "id": event_id}), 200
    except Exception as e:
        print(f"Error receiving data: {e}")
        return jsonify({"error": str(e)}), 500


@application.route('/events', methods=['GET'])
def get_events():
    """Returns camera-derived drowsiness events (for the main dashboard panel)."""
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 500)

        conn = get_db()
        cursor = conn.cursor()
        # Filter to camera/vision events for the main drowsiness dashboard
        cursor.execute('''
            SELECT id, timestamp, status, source, sensor_type, reasons,
                   ear, mar, head_pitch, drowsy_events, yawn_events, received_at
            FROM events
            WHERE sensor_type = 'vision' OR sensor_type IS NULL
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()

        events = []
        for row in rows:
            events.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "status": row["status"],
                "source": row["source"] or "camera",
                "sensor_type": row["sensor_type"] or "vision",
                "reasons": json.loads(row["reasons"]) if row["reasons"] else [],
                "ear": row["ear"],
                "mar": row["mar"],
                "head_pitch": row["head_pitch"],
                "drowsy_events": row["drowsy_events"],
                "yawn_events": row["yawn_events"],
                "received_at": row["received_at"]
            })
        events.reverse()
        return jsonify({"events": events, "count": len(events)})
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"error": str(e)}), 500


@application.route('/environment', methods=['GET'])
def get_environment():
    """Returns recent temperature and humidity readings."""
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 500)

        conn = get_db()
        cursor = conn.cursor()

        # Last N temperature readings
        cursor.execute('''
            SELECT timestamp, env_value, env_unit, source
            FROM events
            WHERE sensor_type = 'temperature'
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        temp_rows = cursor.fetchall()

        # Last N humidity readings
        cursor.execute('''
            SELECT timestamp, env_value, env_unit, source
            FROM events
            WHERE sensor_type = 'humidity'
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        humidity_rows = cursor.fetchall()

        conn.close()

        def to_list(rows):
            out = []
            for r in rows:
                out.append({
                    "timestamp": r["timestamp"],
                    "value": r["env_value"],
                    "unit": r["env_unit"],
                    "source": r["source"]
                })
            out.reverse()  # oldest first for charting
            return out

        return jsonify({
            "temperature": to_list(temp_rows),
            "humidity": to_list(humidity_rows)
        })
    except Exception as e:
        print(f"Error fetching environment data: {e}")
        return jsonify({"error": str(e)}), 500


@application.route('/sensors', methods=['GET'])
def get_sensors():
    """Returns a summary of all sensors active in the last minute."""
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - 60  # last 60s
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sensor_type, source, MAX(timestamp) as last_seen,
                   COUNT(*) as readings
            FROM events
            WHERE timestamp >= ?
            GROUP BY sensor_type, source
        ''', (cutoff,))
        rows = cursor.fetchall()
        conn.close()

        sensors = []
        for r in rows:
            sensors.append({
                "sensor_type": r["sensor_type"],
                "source": r["source"],
                "last_seen": r["last_seen"],
                "readings_last_minute": r["readings"]
            })
        return jsonify({"sensors": sensors, "count": len(sensors)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@application.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "time": datetime.now(timezone.utc).isoformat()
    })


@application.route('/stats', methods=['GET'])
def stats():
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) as total FROM events')
        total = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as cnt FROM events WHERE status = 'DROWSY'")
        drowsy_count = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM events WHERE status = 'AWAKE'")
        awake_count = cursor.fetchone()['cnt']
        cursor.execute('SELECT MAX(drowsy_events) as max_d, MAX(yawn_events) as max_y FROM events')
        row = cursor.fetchone()
        max_drowsy = row['max_d'] or 0
        max_yawn = row['max_y'] or 0
        conn.close()

        return jsonify({
            "total_events": total,
            "drowsy_readings": drowsy_count,
            "awake_readings": awake_count,
            "total_drowsy_events": max_drowsy,
            "total_yawn_events": max_yawn
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5000, debug=True)
