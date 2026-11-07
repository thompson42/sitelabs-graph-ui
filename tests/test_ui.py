# Copyright 2026 S. Alex Thompson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The UI against a stand-in server, for each set of features a backend can have, and the install.
The browser tests need Playwright, and skip without it:

    pip install playwright pytest && playwright install chromium
    python -m pytest
"""
import http.server
import json
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install as I  # noqa: E402

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'")
FULL = {"title": "Full", "schema": True, "pages": True, "profile": True, "past": True, "cancel": True}
PLAIN = {"title": "Plain", "schema": False, "pages": False, "profile": False, "past": False, "cancel": False}
NODE = {"id": "a", "labels": ["Person"], "properties": {"name": "Ann"}}
REL = {"id": "r", "type": "KNOWS", "start": "a", "end": "b", "properties": {}}


class Backend(http.server.BaseHTTPRequestHandler):
    config, seen = FULL, []

    def log_message(self, *a):
        pass

    def answer(self, body, status=200, kind="application/json", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/console":
            return self.answer((I.UI / "console.html").read_bytes(), kind="text/html",
                               headers={"Content-Security-Policy": CSP})
        if self.path == "/console/config.json":
            return self.answer(type(self).config)
        if self.path.startswith("/console/vendor/"):
            return self.answer((I.UI / "vendor" / self.path.rsplit("/", 1)[1]).read_bytes(), kind="text/javascript")
        if self.path == "/schema":
            return self.answer({"load": 1, "vertices": 2, "edges": 1, "labels": [{"name": "Person", "count": 2}],
                                "vertex_types": [], "edge_types": [{"name": "KNOWS", "count": 1}]})
        self.answer({"error": "not here"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append(body)
        q = body["query"]
        if "db.labels" in q:
            return self.answer({"columns": ["label"], "rows": [{"label": "Person"}], "stats": {}})
        if "db.relationshipTypes" in q:
            return self.answer({"columns": ["relationshipType"], "rows": [{"relationshipType": "KNOWS"}], "stats": {}})
        if q.startswith("CREATE"):
            return self.answer({"error": "read-only"}, 400)
        self.answer({"columns": ["a", "r"], "rows": [{"a": NODE, "r": REL}], "stats": {}})


def serve(config):
    handler = type("H", (Backend,), {"config": config, "seen": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, handler


def test_install_copies_and_checks(tmp_path):
    target = tmp_path / "graph-ui"
    manifest = I.install(target)
    assert manifest["version"] == I.version() and I.check(target) == []
    assert set(manifest["files"]) >= {"console.html", "vendor/3d-force-graph.min.js", "vendor/force-graph.min.js",
                                      "vendor/LICENSE-force-graph", "vendor/LICENSE-3d-force-graph"}
    (target / "console.html").write_text("edited")
    assert I.check(target) == ["console.html differs"]
    (target / "extra").write_text("x")
    assert "extra differs" in I.check(target)
    I.install(target)                                                    # its own copy: replaced
    assert I.check(target) == [] and not (target / "extra").exists()
    other = tmp_path / "other"
    other.mkdir()
    (other / "mine").write_text("x")
    with pytest.raises(SystemExit, match="not replacing"):
        I.install(other)
    assert (other / "mine").exists()


def until(page, expression, seconds=60):
    end = time.time() + seconds
    while not page.evaluate(expression):
        assert time.time() < end, expression
        page.wait_for_timeout(50)


@pytest.fixture(scope="module")
def browser():
    api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")
    with api.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except api.Error as ex:
            pytest.skip(f"no browser: {str(ex)[:80]}")
        yield b
        b.close()


@pytest.mark.parametrize("config", [FULL, PLAIN])
def test_the_page_shows_what_the_server_has(browser, config):
    server, handler = serve(config)
    page = browser.new_page()
    problems = []
    page.on("pageerror", lambda e: problems.append(str(e)))
    try:
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/console")
        until(page, "document.querySelector('#labels li')")
        assert page.title() == config["title"]
        assert page.is_visible("#profile") == config["profile"] and page.is_visible("#cancel") == config["cancel"]
        assert page.is_visible("#atload") == config["past"]
        assert page.is_visible(".tabs button[data-pane=prof]") == config["profile"]
        assert page.is_visible("#labels li small") == config["schema"]
        page.click("#run")
        until(page, "document.querySelector('#table td')")
        sent = handler.seen[-1]
        assert sent["read_only"] is True and ("page_size" in sent) == config["pages"] and "profile" not in sent
        for kind in ("g2d", "g3d"):
            page.click(f".tabs button[data-pane={kind}]")
            until(page, "document.getElementById('stage').dataset.laidOut")
            assert "ends not in the answer" in page.inner_text("#graphnote")
        page.fill("#query", "CREATE (:Item)")
        page.click("#run")
        until(page, "document.getElementById('error').textContent")
        assert "read-only" in page.inner_text("#error") and problems == []
    finally:
        page.close()
        server.shutdown()
