# sitelabs-graph-ui

A read-only web page for a graph server: run openCypher queries, and see the answer as a table, in 3D,
in 2D or as JSON. Used by [sitelabs-graph-database-conda](https://github.com/thompson42/sitelabs-graph-database-conda)
and [sitelabs-partitioned-graph](https://github.com/thompson42/sitelabs-partitioned-graph).

> **For:** developers of the page, and of a server that serves it. **You'll find:** what it does, how a
> project uses it, what a server must provide, how big a graph is worth drawing, and how to test it.

It is one page and two libraries, with nothing to build and nothing fetched from the internet, so it
works on a private network. The query box's highlighting and completion are its own, about 100 lines:
the usual editor libraries' language modes use a bare name for the language that both projects refuse.

## What it does

* **Queries** with parameters, in a box. Every query goes with `"read_only": true`, so the server
  refuses a write, whatever the key may do. **Explain** puts `EXPLAIN` before the query.
* **The query box** colours the language, completes keywords as you type and labels and types after a
  `:` (Tab or Enter to accept), and marks where a syntax error is. Tab indents; Escape, then Tab, leaves
  the box. Ctrl+Enter or ⌘+Enter runs.
* **History:** the last 50 queries, in this browser, newest first. Click one to load it. Their text
  only, not their parameters, which may be private. **Clear** forgets them.
* **The answer** as a table (the first 2,000 rows), in 3D, in 2D, or as JSON.
* **The graph views:** the nodes, relationships and paths in the answer, coloured by first label. Hover
  for a label, click a node for everything about it. A relationship whose ends the answer didn't
  return gets grey placeholders. Everything from the graph is escaped before it is shown.
* **Expanding:** click a node, then **Expand neighbours**, to add what it connects to (its first 100
  relationships), and carry on from there: the way to explore a graph too big to draw. What was
  expanded stays when you switch between 3D and 2D, is drawn whatever the size limit, and goes with the
  next query or **Back to the answer**. It sends `MATCH (a)-[r]-(b) WHERE id(a) = $id RETURN a, r, b`.
* **Labels and types** beside the query: click one to see some of them.
* **What a server has beyond that** shows only there: counts and properties (`schema`), paging (`pages`),
  profiles (`profile`), reading the past (`past`) and cancelling (`cancel`).

## Using it in a project

A project keeps a pinned copy of a release in its own repository, with a manifest of its version and
files' hashes, which the project's tests check. It needs no submodule or package, and builds offline.

```bash
python install.py ../sitelabs-partitioned-graph/app/static/graph-ui          # replaces the copy
python install.py --check ../sitelabs-partitioned-graph/app/static/graph-ui  # is it this release?
```

Change the page here, raise `VERSION`, then install into each project. Don't edit the copies: their
tests fail.

## What a server must provide

Each is about 30 lines in the projects' `app/routers/console.py`.

| Path | What |
|---|---|
| `GET /console` | `ui/console.html`, with the security policy below. Needs no key: the page asks for one |
| `GET /console/config.json` | `{"title", "schema", "pages", "profile", "past", "cancel"}`: the page's title, and which of those the server has |
| `GET /console/vendor/<file>` | `ui/vendor/3d-force-graph.min.js` and `force-graph.min.js`, and no other file |
| `POST /opencypher` | `{"query", "params", "read_only"}` answers `{"columns", "rows", "stats"}`, or `{"error"}`. With `read_only`, a write answers 400. `X-API-Key` is the key. A node is `{"id", "labels", "properties"}`, a relationship `{"id", "type", "start", "end", "properties"}`, a path `{"nodes", "relationships"}` |
| `CALL db.labels()`, `CALL db.relationshipTypes()` | Without `schema`, the page lists labels and types with these |
| `id(a) = $id` in a `WHERE` | Expanding finds a node by it |
| `offset N` in a syntax error's message | Optional: where the page marks the error |

With `schema`: `GET /schema`. With `pages`: `page_size` in the request, `cursor` in the answer, and `GET
/opencypher/cursors/{cursor}`. With `profile`: `profile` in the request and answer. With `past`:
`at_load`. With `cancel`: `DELETE /queries/{X-Request-ID}`.

The policy: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src
'self' data: blob:; connect-src 'self'; frame-ancestors 'none'`. It refuses `eval`, and the libraries
work under it.

## How big a graph

**What limits a graph is what you can read, long before what the browser can draw.** Measured on an
Apple M2 laptop (Chrome, its GPU) on connected data of about 8 relationships per node, all of it drawn:

| Nodes, relationships | View | Layout | While laid out | Turning or panning | Can you read it? |
|---|---|---:|---:|---:|---|
| 116, 794 | 3D | 5.1 s | 60 fps | 60 fps | Yes |
| | 2D | 5.0 s | 60 fps | 61 fps | Yes |
| 1,052, 8,032 | 3D | 4.0 s | 31 fps | 48 fps | The clusters only, as a hairball |
| | 2D | 2.0 s | 61 fps | 60 fps | The clusters only, as a hairball |
| 5,212, 40,198 | 3D | 15.4 s | 5 fps | 7 fps | No: a solid disc |
| | 2D | 3.5 s | 36 fps | 55 fps | No: a solid disc |

Focused answers read well in either view, at any size of graph. So the limit starts at 1,000 nodes, the
page says when a graph is too big to read, or too big for 3D, and expanding lets you start small. Very
large answers (cosmos.gl draws hundreds of thousands of points) aren't worth adding for that reason.

## Testing

```bash
pip install playwright pytest && playwright install chromium
python -m pytest
```

[`tests/test_ui.py`](tests/test_ui.py) runs the page in a real browser against a stand-in server, once
with every feature and once with none. Without Playwright, only the install is tested. Each project also
tests the page against itself.

## Licence

Apache-2.0 ([LICENSE.txt](LICENSE.txt)). The two libraries are MIT ([ui/vendor](ui/vendor/README.md),
[NOTICES.txt](NOTICES.txt)).
