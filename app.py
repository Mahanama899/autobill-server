from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, os
from datetime import datetime


app = Flask(__name__)
# Allow browsers to call anything under /api/*
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    supports_credentials=False
)

DB_PATH = "transactions.db"
API_KEY = os.getenv("API_KEY", "changeme")  # set this in DigitalOcean later

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            units TEXT,
            taken INTEGER,
            payable REAL,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def authed(req):
    # Accept key in header OR as ?api_key=... for easy testing in browser
    key = req.headers.get("x-api-key") or req.args.get("api_key")
    return key == API_KEY

@app.route("/api/transactions", methods=["POST"])
def post_transaction():
    if not authed(request):
        return jsonify({"error": "Invalid API key"}), 401

    data = request.get_json(force=True)

    # minimal validation
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
            datetime.utcnow().isoformat()
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
    c.execute("SELECT id, name, price, taken, payable, created_at FROM transactions ORDER BY id DESC LIMIT 50")
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

@app.route("/")
def home():
    return "✅ AutoBill API is running"
