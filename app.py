from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import sqlite3, os, json, time
from datetime import datetime

app = Flask(__name__)
# Allow browser access to /api/* from anywhere (you can restrict origins later)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_PATH = "transactions.db"
API_KEY = os.getenv("API_KEY", "changeme")  # set in App Platform → Environment Variables

# -------- DB helpers --------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            units TEXT,
            taken INTEGER,
            payable REAL,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def fetch_since(last_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, name, price, units, taken, payable, created_at
        FROM transactions
        WHERE id > ?
        ORDER BY id ASC
        LIMIT 100
    """, (last_id,))
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

def authed(req):
    # Accept API key via header OR query param
    return (
        req.headers.get("x-api-key") == API_KEY
        or req.args.get("api_key") == API_KEY
    )

# -------- CORS headers for all responses (extra explicit) --------
@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, x-api-key"
    return resp

# -------- Routes --------
@app.route("/")
def home():
    return "✅ AutoBill API is running"

# Preflight (optional explicit handler)
@app.route("/api/transactions", methods=["OPTIONS"])
def tx_options():
    return ("", 204)

@app.route("/api/transactions", methods=["POST"])
def post_transaction():
    if not authed(request):
        return jsonify({"error": "Invalid API key"}), 401
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    if not isinstance(data, dict) or "name" not in data:
        return jsonify({"error": "Missing 'name'"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (name, price, units, taken, payable, created_at) VALUES (?,?,?,?,?,?)",
        (
            data.get("name"),
            float(data.get("price", 0)),
            data.get("units", "units"),
            int(data.get("taken", 1)),
            float(data.get("payable", 0)),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    print(f"Received: {data}")
    return jsonify({"status": "ok"}), 201

@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    if not authed(request):
        return jsonify({"error": "Invalid API key"}), 401
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, name, price, taken, payable, created_at
        FROM transactions
        ORDER BY id DESC
        LIMIT 50
    """)
    rows = c.fetchall()
    conn.close()
    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "price": r[2],
            "taken": r[3],
            "payable": r[4],
            "created_at": r[5],
        } for r in rows
    ])

@app.route("/api/stream")
def stream():
    # Auth
    if not authed(request):
        return jsonify({"error": "Invalid API key"}), 401

    # Start from a specific id if provided
    try:
        last_id = int(request.args.get("since", "0"))
    except ValueError:
        last_id = 0

    @stream_with_context
    def event_stream():
        nonlocal last_id
        heartbeat_every = 15  # seconds
        last_beat = time.time()

        while True:
            rows = fetch_since(last_id)
            if rows:
                for r in rows:
                    payload = {
                        "id": r[0],
                        "name": r[1],
                        "price": r[2],
                        "units": r[3],
                        "taken": r[4],
                        "payable": r[5],
                        "created_at": r[6],
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_id = r[0]

            # Heartbeat to keep the connection alive on proxies
            now_ts = time.time()
            if now_ts - last_beat > heartbeat_every:
                yield ": keep-alive\n\n"  # SSE comment line
                last_beat = now_ts

            time.sleep(1)  # light polling loop

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    }
    return Response(event_stream(), headers=headers)

if __name__ == "__main__":
    # Local dev only; on App Platform we use gunicorn via Procfile
    app.run(host="0.0.0.0", port=8080, debug=False)
