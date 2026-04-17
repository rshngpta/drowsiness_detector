"""
Cloud backend - Flask web service for drowsiness detection.
Receives processed events from the fog node, stores them in SQLite,
and serves the dashboard.

This file is named application.py and the Flask app variable is named
'application' because AWS Elastic Beanstalk looks for these exact names
by default.
"""

from flask import Flask, request, jsonify, render_template
import sqlite3
import os
import json
from datetime import datetime

# Initialize Flask app - MUST be named 'application' for Elastic Beanstalk
application = Flask(__name__)

# Database file - stored next to this script
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'events.db')


def get_db():
    """Get a new database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the events table if it doesn't exist."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            status TEXT NOT NULL,
            reasons TEXT,
            ear REAL,
            mar REAL,
            head_pitch REAL,
            drowsy_events INTEGER,
            yawn_events INTEGER,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


# Initialize database when the app starts
init_db()


@application.route('/')
def dashboard():
    """Serve the dashboard HTML page."""
    return render_template('dashboard.html')


@application.route('/data', methods=['POST'])
def receive_data():
    """
    Endpoint for the fog node to POST drowsiness events.
    Expected JSON payload:
    {
      "timestamp": 1234567890.12,
      "status": "AWAKE" | "DROWSY",
      "reasons": ["eyes_closed", ...],
      "metrics": {"ear": 0.25, "mar": 0.3, "head_pitch": 0.0},
      "totals": {"drowsy_events": 1, "yawn_events": 2}
    }
    """
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "No JSON body"}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events
            (timestamp, status, reasons, ear, mar, head_pitch, drowsy_events, yawn_events)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            payload.get('timestamp'),
            payload.get('status'),
            json.dumps(payload.get('reasons', [])),
            payload.get('metrics', {}).get('ear'),
            payload.get('metrics', {}).get('mar'),
            payload.get('metrics', {}).get('head_pitch'),
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
    """
    Return the most recent events for the dashboard.
    Query params:
      limit (int, default 50) - max events to return
    """
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 500)  # safety cap

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, timestamp, status, reasons, ear, mar, head_pitch,
                   drowsy_events, yawn_events, received_at
            FROM events
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
                "reasons": json.loads(row["reasons"]) if row["reasons"] else [],
                "ear": row["ear"],
                "mar": row["mar"],
                "head_pitch": row["head_pitch"],
                "drowsy_events": row["drowsy_events"],
                "yawn_events": row["yawn_events"],
                "received_at": row["received_at"]
            })

        # Reverse so chart gets oldest-first
        events.reverse()
        return jsonify({"events": events, "count": len(events)})

    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"error": str(e)}), 500


@application.route('/health', methods=['GET'])
def health():
    """Simple health check endpoint for Elastic Beanstalk."""
    return jsonify({"status": "healthy", "time": datetime.utcnow().isoformat()})


@application.route('/stats', methods=['GET'])
def stats():
    """Return summary statistics."""
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
    # Local development server
    # On Elastic Beanstalk, gunicorn will serve the 'application' object directly
    application.run(host='0.0.0.0', port=5000, debug=True)
