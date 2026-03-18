"""Tests for the code smell detector."""
import json

import pytest

from main import (
    app,
    detect_dead_code,
    detect_deep_nesting,
    detect_duplicate_blocks,
    detect_god_class,
    detect_long_method,
    detect_magic_numbers,
    detect_smells,
)


@pytest.fixture
def client(tmp_path):
    app.config["TESTING"] = True
    app.config["DB_PATH"] = str(tmp_path / "test.db")
    with app.test_client() as c:
        yield c


# --- Long Method ---


class TestLongMethod:
    def test_short_function(self):
        code = "def foo():\n" + "    pass\n" * 5
        assert detect_long_method(code, "python") == []

    def test_long_function(self):
        code = "def foo():\n" + "    x = 1\n" * 35
        smells = detect_long_method(code, "python")
        assert len(smells) == 1
        assert smells[0]["type"] == "long-method"
        assert "foo" in smells[0]["message"]

    def test_multiple_functions(self):
        short = "def short():\n" + "    pass\n" * 3
        long_fn = "def long_one():\n" + "    x = 1\n" * 35
        smells = detect_long_method(short + long_fn, "python")
        assert len(smells) == 1
        assert "long_one" in smells[0]["message"]

    def test_js_long_function(self):
        code = "function foo() {\n" + "    let x = 1;\n" * 35 + "}\n"
        smells = detect_long_method(code, "javascript")
        assert len(smells) == 1
        assert smells[0]["type"] == "long-method"

    def test_go_long_function(self):
        code = "func foo() {\n" + "\tx := 1\n" * 35 + "}\n"
        smells = detect_long_method(code, "go")
        assert len(smells) == 1
        assert smells[0]["type"] == "long-method"

    def test_async_function(self):
        code = "async def handler():\n" + "    await do()\n" * 35
        smells = detect_long_method(code, "python")
        assert len(smells) == 1
        assert "handler" in smells[0]["message"]


# --- Deep Nesting ---


class TestDeepNesting:
    def test_shallow_code(self):
        code = "def foo():\n    if x:\n        pass\n"
        assert detect_deep_nesting(code, "python") == []

    def test_deep_nesting(self):
        code = (
            "if a:\n"
            "    if b:\n"
            "        if c:\n"
            "            if d:\n"
            "                if e:\n"
            "                    x = 1\n"
        )
        smells = detect_deep_nesting(code, "python")
        assert len(smells) == 1
        assert smells[0]["line"] == 6

    def test_comments_ignored(self):
        code = "                    # deep comment\n"
        assert detect_deep_nesting(code, "python") == []

    def test_js_deep_nesting(self):
        # 2-space indent, depth > 4 means > 8 spaces
        code = "if (a) {\n" + "  " * 5 + "x = 1;\n" + "}\n"
        smells = detect_deep_nesting(code, "javascript")
        assert len(smells) == 1


# --- Magic Numbers ---


class TestMagicNumbers:
    def test_no_magic(self):
        code = "x = 0\ny = 1\nz = 2\n"
        assert detect_magic_numbers(code, "python") == []

    def test_magic_detected(self):
        code = "timeout = 3600\n"
        smells = detect_magic_numbers(code, "python")
        assert len(smells) == 1
        assert "3600" in smells[0]["message"]

    def test_constant_ignored(self):
        code = "MAX_RETRIES = 5\n"
        assert detect_magic_numbers(code, "python") == []

    def test_comment_ignored(self):
        code = "# some number 42\n"
        assert detect_magic_numbers(code, "python") == []

    def test_import_ignored(self):
        code = "import os\nfrom sys import argv\n"
        assert detect_magic_numbers(code, "python") == []

    def test_js_const_ignored(self):
        code = "const MAX_SIZE = 1024;\n"
        assert detect_magic_numbers(code, "javascript") == []

    def test_string_numbers_ignored(self):
        code = 'label = "Error 404 occurred"\n'
        assert detect_magic_numbers(code, "python") == []


# --- Dead Code ---


class TestDeadCode:
    def test_no_dead_code(self):
        code = "def foo():\n    x = 1\n    return x\n"
        assert detect_dead_code(code, "python") == []

    def test_code_after_return(self):
        code = "def foo():\n    return 1\n    x = 2\n"
        smells = detect_dead_code(code, "python")
        assert len(smells) == 1
        assert smells[0]["line"] == 3

    def test_consecutive_dead_lines(self):
        code = "def foo():\n    return 1\n    x = 2\n    y = 3\n"
        smells = detect_dead_code(code, "python")
        assert len(smells) >= 2

    def test_if_false(self):
        code = "if False:\n    x = 1\n"
        smells = detect_dead_code(code, "python")
        assert any("if False" in s["message"] for s in smells)

    def test_js_if_false(self):
        code = "if (false) {\n    x = 1;\n}\n"
        smells = detect_dead_code(code, "javascript")
        assert any("if (false)" in s["message"] for s in smells)

    def test_else_not_flagged(self):
        code = "def foo():\n    if x:\n        return 1\n    else:\n        return 2\n"
        assert detect_dead_code(code, "python") == []

    def test_except_not_flagged(self):
        code = "def foo():\n    try:\n        raise ValueError\n    except:\n        pass\n"
        assert detect_dead_code(code, "python") == []


# --- Duplicate Blocks ---


class TestDuplicateBlocks:
    def test_no_duplicates(self):
        code = "a = 1\nb = 2\nc = 3\nd = 4\ne = 5\nf = 6\n"
        assert detect_duplicate_blocks(code, "python") == []

    def test_duplicate_detected(self):
        block = "    x = compute()\n    y = transform(x)\n    save(y)\n"
        code = "def foo():\n" + block + "def bar():\n" + block
        smells = detect_duplicate_blocks(code, "python")
        assert len(smells) == 1
        assert smells[0]["type"] == "duplicate-blocks"

    def test_short_code(self):
        assert detect_duplicate_blocks("x = 1\n", "python") == []

    def test_empty_lines_ignored(self):
        code = "\n\n\n\n\n\n"
        assert detect_duplicate_blocks(code, "python") == []


# --- God Class ---


class TestGodClass:
    def test_small_class(self):
        code = "class Foo:\n" + "    pass\n" * 10
        assert detect_god_class(code, "python") == []

    def test_god_class(self):
        code = "class Huge:\n" + "    x = 1\n" * 305
        smells = detect_god_class(code, "python")
        assert len(smells) == 1
        assert "Huge" in smells[0]["message"]

    def test_js_god_class(self):
        code = "class BigClass {\n" + "    method() {}\n" * 305 + "}\n"
        smells = detect_god_class(code, "javascript")
        assert len(smells) == 1

    def test_multiple_classes(self):
        small = "class Small:\n" + "    pass\n" * 10
        big = "class Big:\n" + "    x = 1\n" * 305
        smells = detect_god_class(small + big, "python")
        assert len(smells) == 1
        assert "Big" in smells[0]["message"]


# --- Orchestrator ---


class TestDetectSmells:
    def test_sorted_by_line(self):
        code = "timeout = 3600\n" + "def foo():\n" + "    x = 1\n" * 35
        smells = detect_smells(code, "python")
        lines = [s["line"] for s in smells]
        assert lines == sorted(lines)

    def test_empty_code(self):
        assert detect_smells("", "python") == []

    def test_all_languages(self):
        for lang in ("python", "javascript", "go"):
            assert isinstance(detect_smells("x = 1", lang), list)


# --- Routes ---


class TestRoutes:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Code Smell Detector" in resp.data

    def test_analyze(self, client):
        resp = client.post(
            "/analyze",
            json={"code": "timeout = 3600\n", "language": "python"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "smells" in data
        assert "count" in data
        assert data["count"] >= 1

    def test_analyze_clean_code(self, client):
        resp = client.post(
            "/analyze",
            json={"code": "x = 0\n", "language": "python"},
        )
        data = resp.get_json()
        assert data["count"] == 0

    def test_analyze_no_code(self, client):
        resp = client.post("/analyze", json={})
        assert resp.status_code == 400

    def test_analyze_bad_language(self, client):
        resp = client.post(
            "/analyze",
            json={"code": "x = 1", "language": "rust"},
        )
        assert resp.status_code == 400

    def test_analyze_too_large(self, client):
        resp = client.post(
            "/analyze",
            json={"code": "x" * 60000, "language": "python"},
        )
        assert resp.status_code == 400

    def test_history(self, client):
        client.post("/analyze", json={"code": "x = 42\n", "language": "python"})
        resp = client.get("/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1

    def test_history_detail(self, client):
        client.post("/analyze", json={"code": "x = 42\n", "language": "python"})
        history = client.get("/history").get_json()
        resp = client.get(f"/history/{history[0]['id']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["code"] == "x = 42\n"
        assert isinstance(data["results"], list)

    def test_history_not_found(self, client):
        resp = client.get("/history/99999")
        assert resp.status_code == 404
