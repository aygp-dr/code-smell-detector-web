"""Web UI for code smell detection. Flask web app for Replit deployment."""
import os
import sqlite3
from flask import Flask, g, jsonify, render_template_string, request

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-in-production")

DB_PATH = "data/app.db"

def get_db():
    if "db" not in g:
        os.makedirs("data", exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("""CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    return g.db

@app.teardown_appcontext
def close_db(e):
    db = g.pop("db", None)
    if db: db.close()

TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Web UI for code smell detection</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
.container{max-width:800px;margin:0 auto}
h1{color:#58a6ff;margin-bottom:8px}
.subtitle{color:#8b949e;margin-bottom:24px}
.card{border:1px solid #30363d;border-radius:8px;padding:16px;margin:8px 0;background:#161b22}
.btn{padding:8px 16px;border:1px solid #30363d;background:#21262d;color:#c9d1d9;border-radius:6px;cursor:pointer}
.btn:hover{background:#30363d}
input,textarea{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:8px;width:100%;margin:4px 0}
</style>
</head><body>
<div class="container">
<h1>Web UI for code smell detection</h1>
<p class="subtitle">Scaffold — see CLAUDE.md for full implementation plan</p>
<div class="card">
<p>This is a working Flask scaffold ready for Replit deployment.</p>
<p style="margin-top:8px;color:#8b949e">Items in database: {{ count }}</p>
</div>
<form method="POST" style="margin-top:16px">
<input name="title" placeholder="Add an item..." required>
<button type="submit" class="btn" style="margin-top:8px">Add</button>
</form>
{% for item in items %}
<div class="card">
<strong>{{ item.title }}</strong>
<span style="color:#8b949e;font-size:12px"> — {{ item.created_at }}</span>
</div>
{% endfor %}
</div></body></html>"""

@app.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        db.execute("INSERT INTO items (title) VALUES (?)", (request.form["title"],))
        db.commit()
    items = db.execute("SELECT * FROM items ORDER BY created_at DESC LIMIT 50").fetchall()
    return render_template_string(TEMPLATE, items=items, count=len(items))

@app.route("/api/items")
def api_items():
    db = get_db()
    items = db.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
    return jsonify([dict(i) for i in items])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
