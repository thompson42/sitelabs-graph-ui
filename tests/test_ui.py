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
import os
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
        if "$id" in q:
            near = {"id": "b", "labels": ["Person"], "properties": {"name": "Bob"}}
            return self.answer({"columns": ["a", "r", "b"], "rows": [{"a": NODE, "r": REL, "b": near}], "stats": {}})
        if q.startswith("ONE"):
            return self.answer({"columns": ["a"], "rows": [{"a": NODE}], "stats": {}})
        if q.startswith("BAD"):
            return self.answer({"error": "OpenCypherSyntaxError: expected ')' (near 'x', offset 4)"}, 400)
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


def no_browser(reason: str):
    """Skip, unless CI asked for the browser (REQUIRE_BROWSER=1), where a skip would hide a broken setup."""
    if os.environ.get("REQUIRE_BROWSER") == "1":
        pytest.fail(f"{reason} (and REQUIRE_BROWSER=1)", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright import sync_api as api
    except ImportError:
        no_browser("Playwright is not installed")
    with api.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except api.Error as ex:
            no_browser(f"no browser: {str(ex)[:80]}")
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
        sent = next(x for x in reversed(handler.seen) if "db." not in x["query"])
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


@pytest.fixture
def page(browser):
    server, handler = serve(FULL)
    p = browser.new_page(viewport={"width": 1200, "height": 900})
    p.problems = []
    p.on("pageerror", lambda e: p.problems.append(str(e)))
    p.handler = handler
    p.goto(f"http://127.0.0.1:{server.server_address[1]}/console")
    until(p, "document.querySelector('#labels li')")
    yield p
    p.close()
    server.shutdown()


def run(p, query):
    p.fill("#query", query)
    p.click("#run")
    until(p, "document.getElementById('cancel').disabled")


@pytest.mark.parametrize("kind", ["g2d", "g3d"])
def test_expanding_a_node_adds_its_neighbours(page, kind):
    run(page, "ONE")
    page.click(f".tabs button[data-pane={kind}]")
    until(page, "document.getElementById('stage').dataset.laidOut")
    assert "1 of 1 nodes" in page.inner_text("#graphnote")
    page.wait_for_timeout(700)
    box = page.locator("#stage").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(400)                                           # picking happens on a drawn frame
    page.mouse.down()
    page.mouse.up()
    until(page, "!document.getElementById('inspect').hidden", 20)
    assert "Ann" in page.inner_text("#details")
    page.click("#expand")
    until(page, "document.getElementById('graphnote').textContent.includes('2 of 2 nodes')")
    sent = page.handler.seen[-1]
    assert sent["read_only"] is True and sent["params"] == {"id": "a"} and "1 expanded" in page.inner_text("#graphnote")
    assert page.is_disabled("#expand") and page.is_visible("#resetgraph")
    other = "g3d" if kind == "g2d" else "g2d"
    page.click(f".tabs button[data-pane={other}]")                       # it carries over to the other view
    until(page, "document.getElementById('stage').dataset.laidOut")
    assert "2 of 2 nodes" in page.inner_text("#graphnote")
    page.click("#resetgraph")
    until(page, "document.getElementById('stage').dataset.laidOut")
    assert "1 of 1 nodes" in page.inner_text("#graphnote") and not page.is_visible("#resetgraph")
    assert page.problems == []


def test_a_new_answer_forgets_what_was_expanded(page):
    run(page, "ONE")
    page.evaluate("extra.done.add('a'); extra.nodes.set('z', {id: 'z', labels: ['X'], properties: {}})")
    run(page, "ONE")
    assert page.evaluate("extra.nodes.size") == 0 and page.evaluate("extra.done.size") == 0


def test_the_box_highlights_and_shows_where_a_syntax_error_is(page):
    run(page, "MATCH (p:Person {name: $n}) RETURN p.name // who\nLIMIT 3")
    html = page.inner_html("#highlight")
    for mark in ('t-key">MATCH', 't-lab">:Person', 't-par">$n', 't-com">// who', 't-num">3'):
        assert mark in html, mark
    assert page.evaluate("document.getElementById('highlight').textContent.trimEnd()") == page.input_value("#query")
    page.fill("#query", "<img src=x onerror=window.__xss=1>")
    assert page.locator("#highlight img").count() == 0 and page.evaluate("window.__xss") is None
    run(page, "BAD x y")
    assert 't-err">' in page.inner_html("#highlight") and "offset 4" in page.inner_text("#error")
    page.locator("#query").press("End")
    page.locator("#query").type("z")
    assert "t-err" not in page.inner_html("#highlight")                  # typing clears it


def test_completing_labels_and_keywords(page):
    q = page.locator("#query")
    page.fill("#query", "")
    q.type("MATCH (n:Per")
    assert page.inner_text("#complete").strip() == "Person"
    q.press("Tab")
    assert page.input_value("#query") == "MATCH (n:Person" and not page.is_visible("#complete")
    q.type(") RET")
    assert "RETURN" in page.inner_text("#complete")
    q.press("Enter")
    assert page.input_value("#query") == "MATCH (n:Person) RETURN"
    q.type(" LI")
    assert page.is_visible("#complete")
    q.press("Escape")
    assert not page.is_visible("#complete")
    page.fill("#query", "")
    q.press("Tab")
    assert page.input_value("#query") == "  "                            # Tab indents...
    q.press("Escape")
    q.press("Tab")
    assert page.evaluate("document.activeElement.id") != "query"         # ...and Escape, Tab leaves the box


def test_history_keeps_the_last_queries_not_their_parameters(page):
    page.fill("#params", '{"secret": "hunter2"}')
    for q in ("ONE", "ONE two", "ONE"):
        run(page, q)
    items = page.locator("#history li").all_inner_texts()
    assert items == ["ONE", "ONE two"]                                   # newest first, no repeats
    assert "hunter2" not in page.evaluate("localStorage.getItem('graph-ui.history')")
    page.locator("#history li").nth(1).click()
    assert page.input_value("#query") == "ONE two"
    page.reload()
    until(page, "document.querySelector('#labels li')")
    assert page.locator("#history li").count() == 2                      # it survives a reload
    page.click("#clearhistory")
    assert page.locator("#history li").count() == 0 and not page.is_visible("#clearhistory")
