"""Code Smell Detector - Web UI for detecting and teaching about code smells."""
import hashlib
import json
import os
import re
import sqlite3

from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
app.config.setdefault(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app.db"),
)

SMELL_TYPES = {
    "long-method": {
        "color": "#f97583",
        "label": "Long Method",
        "description": "Function exceeds 30 lines. Extract smaller, focused functions.",
    },
    "deep-nesting": {
        "color": "#d2a8ff",
        "label": "Deep Nesting",
        "description": "Nesting exceeds 4 levels. Use early returns or extract logic.",
    },
    "magic-numbers": {
        "color": "#ffa657",
        "label": "Magic Number",
        "description": "Unexplained numeric literal. Use a named constant.",
    },
    "dead-code": {
        "color": "#8b949e",
        "label": "Dead Code",
        "description": "Unreachable or unused code. Remove it.",
    },
    "duplicate-blocks": {
        "color": "#79c0ff",
        "label": "Duplicate Block",
        "description": "Repeated code block. Extract to a shared function.",
    },
    "god-class": {
        "color": "#f85149",
        "label": "God Class",
        "description": "Class exceeds 300 lines. Split into focused classes.",
    },
}


# --- Database ---


def get_db():
    if "db" not in g:
        db_path = app.config["DB_PATH"]
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute(
            """CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                language TEXT NOT NULL,
                smell_count INTEGER DEFAULT 0,
                results TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


# --- Detection Engine ---


def _get_indent_depth(line, indent_size=4):
    """Get nesting depth from indentation."""
    expanded = line.expandtabs(4)
    stripped = expanded.lstrip()
    if not stripped:
        return 0
    return (len(expanded) - len(stripped)) // indent_size


def detect_long_method(code, language):
    """Detect functions/methods longer than 30 lines."""
    smells = []
    lines = code.split("\n")

    if language == "python":
        func_pattern = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)")
        func_start = None
        func_name = None

        for i, line in enumerate(lines):
            m = func_pattern.match(line)
            if m:
                if func_start is not None:
                    length = i - func_start
                    if length > 30:
                        smells.append(
                            {
                                "type": "long-method",
                                "line": func_start + 1,
                                "end_line": i,
                                "message": f"Function '{func_name}' is {length} lines (>30)",
                            }
                        )
                func_start = i
                func_name = m.group(2)

        if func_start is not None:
            length = len(lines) - func_start
            if length > 30:
                smells.append(
                    {
                        "type": "long-method",
                        "line": func_start + 1,
                        "end_line": len(lines),
                        "message": f"Function '{func_name}' is {length} lines (>30)",
                    }
                )

    elif language in ("javascript", "go"):
        if language == "javascript":
            start_pattern = re.compile(
                r"function\s+(\w+)|"
                r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\()|"
                r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{"
            )
        else:
            start_pattern = re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)")

        i = 0
        while i < len(lines):
            m = start_pattern.search(lines[i])
            if m:
                name = next((x for x in m.groups() if x), "anonymous")
                start = i
                brace_depth = 0
                seen_brace = False

                for j in range(i, len(lines)):
                    opens = lines[j].count("{")
                    closes = lines[j].count("}")
                    brace_depth += opens - closes
                    if opens > 0:
                        seen_brace = True
                    if seen_brace and brace_depth <= 0:
                        length = j - start + 1
                        if length > 30:
                            smells.append(
                                {
                                    "type": "long-method",
                                    "line": start + 1,
                                    "end_line": j + 1,
                                    "message": f"Function '{name}' is {length} lines (>30)",
                                }
                            )
                        i = j
                        break
            i += 1

    return smells


def detect_deep_nesting(code, language):
    """Detect code nested more than 4 levels deep."""
    smells = []
    lines = code.split("\n")
    indent_size = {"python": 4, "javascript": 2, "go": 4}.get(language, 4)

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*")):
            continue

        depth = _get_indent_depth(line, indent_size)
        if depth > 4:
            smells.append(
                {
                    "type": "deep-nesting",
                    "line": i + 1,
                    "end_line": i + 1,
                    "message": f"Nesting depth is {depth} (>4)",
                }
            )

    return smells


def detect_magic_numbers(code, language):
    """Detect unexplained numeric literals."""
    smells = []
    lines = code.split("\n")
    allowed = {"0", "1", "-1", "2", "0.0", "1.0"}
    num_pattern = re.compile(r"(?<![a-zA-Z_\d.])(\d+\.?\d*)(?![a-zA-Z_\d])")

    skip_starts = {
        "python": ("#", "import ", "from "),
        "javascript": ("//", "/*", "import ", "require("),
        "go": ("//", "/*", "import "),
    }.get(language, ())

    const_patterns = {
        "python": re.compile(r"^\s*[A-Z_][A-Z0-9_]*\s*="),
        "javascript": re.compile(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+[A-Z_][A-Z0-9_]*\s*="
        ),
        "go": re.compile(r"^\s*(?:const\s|[A-Z_][A-Z0-9_]*\s*=)"),
    }
    const_pattern = const_patterns.get(language)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if any(stripped.startswith(s) for s in skip_starts):
            continue
        if const_pattern and const_pattern.match(line):
            continue

        # Strip inline comments
        code_part = line.split("#")[0] if language == "python" else line.split("//")[0]

        # Strip string literals (simple heuristic)
        code_part = re.sub(r'"[^"]*"', '""', code_part)
        code_part = re.sub(r"'[^']*'", "''", code_part)

        for m in num_pattern.finditer(code_part):
            num = m.group(1)
            if num not in allowed:
                smells.append(
                    {
                        "type": "magic-numbers",
                        "line": i + 1,
                        "end_line": i + 1,
                        "message": f"Magic number {num}",
                    }
                )
                break  # One per line

    return smells


def detect_dead_code(code, language):
    """Detect unreachable code after return/break/continue."""
    smells = []
    lines = code.split("\n")
    prev_was_exit = False
    prev_indent = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip())

        # Check for dead code
        is_dead = False
        if prev_was_exit and indent >= prev_indent and stripped:
            if stripped not in ("}", ")", "]"):
                if not stripped.startswith(("#", "//", "/*", "*")):
                    skip_kw = (
                        "except", "catch", "finally", "else", "elif",
                        "case", "default", "def ", "class ", "function ",
                    )
                    if not any(stripped.startswith(k) for k in skip_kw):
                        smells.append(
                            {
                                "type": "dead-code",
                                "line": i + 1,
                                "end_line": i + 1,
                                "message": "Unreachable code after return/break/continue",
                            }
                        )
                        is_dead = True

        if not is_dead:
            if language == "python":
                exit_kw = ("return", "break", "continue", "raise")
            elif language == "javascript":
                exit_kw = ("return", "break", "continue", "throw")
            else:
                exit_kw = ("return", "break", "continue", "panic")
            prev_was_exit = any(stripped.startswith(k) for k in exit_kw) and not stripped.endswith("{")
            prev_indent = indent

        # Detect if False / if (false)
        if language == "python" and re.match(r"\s*if\s+False\s*:", line):
            smells.append(
                {
                    "type": "dead-code",
                    "line": i + 1,
                    "end_line": i + 1,
                    "message": "'if False' — dead code block",
                }
            )
            prev_was_exit = False
        elif language == "javascript" and re.match(r"\s*if\s*\(\s*false\s*\)", line):
            smells.append(
                {
                    "type": "dead-code",
                    "line": i + 1,
                    "end_line": i + 1,
                    "message": "'if (false)' — dead code block",
                }
            )
            prev_was_exit = False

    return smells


def detect_duplicate_blocks(code, language):
    """Detect duplicate blocks of 3+ consecutive lines."""
    smells = []
    lines = code.split("\n")
    window_size = 3

    if len(lines) < window_size * 2:
        return smells

    window_hashes = {}
    reported = set()

    for i in range(len(lines) - window_size + 1):
        window = tuple(ln.strip() for ln in lines[i : i + window_size])
        if all(not ln for ln in window):
            continue
        if all(ln in ("{", "}", "(", ")", "[", "]", "") for ln in window):
            continue

        h = hashlib.md5("\n".join(window).encode()).hexdigest()
        if h in window_hashes:
            orig = window_hashes[h]
            if orig not in reported:
                smells.append(
                    {
                        "type": "duplicate-blocks",
                        "line": i + 1,
                        "end_line": i + window_size,
                        "message": f"Duplicate of lines {orig + 1}-{orig + window_size}",
                    }
                )
                reported.add(orig)
        else:
            window_hashes[h] = i

    return smells


def detect_god_class(code, language):
    """Detect classes longer than 300 lines."""
    smells = []
    lines = code.split("\n")

    if language == "python":
        class_pattern = re.compile(r"^class\s+(\w+)")
        class_start = None
        class_name = None

        for i, line in enumerate(lines):
            m = class_pattern.match(line)
            if m:
                if class_start is not None:
                    length = i - class_start
                    if length > 300:
                        smells.append(
                            {
                                "type": "god-class",
                                "line": class_start + 1,
                                "end_line": i,
                                "message": f"Class '{class_name}' is {length} lines (>300)",
                            }
                        )
                class_start = i
                class_name = m.group(1)

        if class_start is not None:
            length = len(lines) - class_start
            if length > 300:
                smells.append(
                    {
                        "type": "god-class",
                        "line": class_start + 1,
                        "end_line": len(lines),
                        "message": f"Class '{class_name}' is {length} lines (>300)",
                    }
                )

    elif language in ("javascript", "go"):
        if language == "javascript":
            class_pattern = re.compile(r"^\s*(?:export\s+)?class\s+(\w+)")
        else:
            class_pattern = re.compile(r"^type\s+(\w+)\s+struct")

        i = 0
        while i < len(lines):
            m = class_pattern.match(lines[i])
            if m:
                name = m.group(1)
                start = i
                brace_depth = 0
                seen_brace = False

                for j in range(i, len(lines)):
                    opens = lines[j].count("{")
                    closes = lines[j].count("}")
                    brace_depth += opens - closes
                    if opens > 0:
                        seen_brace = True
                    if seen_brace and brace_depth <= 0:
                        length = j - start + 1
                        if length > 300:
                            smells.append(
                                {
                                    "type": "god-class",
                                    "line": start + 1,
                                    "end_line": j + 1,
                                    "message": f"Class/struct '{name}' is {length} lines (>300)",
                                }
                            )
                        i = j
                        break
            i += 1

    return smells


def detect_smells(code, language):
    """Run all detectors and return sorted findings."""
    smells = []
    smells.extend(detect_long_method(code, language))
    smells.extend(detect_deep_nesting(code, language))
    smells.extend(detect_magic_numbers(code, language))
    smells.extend(detect_dead_code(code, language))
    smells.extend(detect_duplicate_blocks(code, language))
    smells.extend(detect_god_class(code, language))
    smells.sort(key=lambda s: s["line"])
    return smells


# --- Routes ---


@app.route("/")
def index():
    return render_template("index.html", smell_types=SMELL_TYPES)


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "No code provided"}), 400

    code = data["code"]
    language = data.get("language", "python")

    if language not in ("python", "javascript", "go"):
        return jsonify({"error": f"Unsupported language: {language}"}), 400
    if len(code) > 50000:
        return jsonify({"error": "Code too large (max 50KB)"}), 400

    smells = detect_smells(code, language)

    db = get_db()
    db.execute(
        "INSERT INTO analyses (code, language, smell_count, results) VALUES (?, ?, ?, ?)",
        (code, language, len(smells), json.dumps(smells)),
    )
    db.commit()

    return jsonify({"smells": smells, "count": len(smells), "smell_types": SMELL_TYPES})


@app.route("/history")
def history():
    db = get_db()
    rows = db.execute(
        "SELECT id, language, smell_count, created_at, substr(code, 1, 100) as preview "
        "FROM analyses ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/history/<int:analysis_id>")
def history_detail(analysis_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    result = dict(row)
    result["results"] = json.loads(result["results"])
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
