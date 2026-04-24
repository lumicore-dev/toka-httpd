# toka-httpd

A minimal HTTP server library for the [Toka](https://github.com/lumicore-dev/tokalang) programming language.

Built entirely on top of Toka's standard library (`std/net`, `std/net_http`), with zero external dependencies.

## Features

- ✅ **Static file serving** — Serve files from a directory with MIME type detection
- ✅ **JSON API** — Build REST endpoints with `json_res()` helper
- ✅ **Query string parsing** — `parse_query()` splits URL params
- ✅ **Path routing** — `match_path()` strips query strings for clean routes
- ✅ **404 handling** — Automatic `not_found()` for missing files
- ✅ **MIME types** — Auto-detects `.html`, `.css`, `.js`, `.json`, `.svg`, `.txt`, `.wasm`, `.xml`

## Quick Start

```bash
git clone https://github.com/lumicore-dev/toka-httpd.git
cd toka-httpd/demo

# Requires toka-source lib path:
tokac -o server \
  -I /path/to/toka-source/lib \
  -I .. \
  demo.tk

./server &
curl http://localhost:8080/hello
# → Hello from Toka!
```

## API Reference

### Response Builders

```toka
text_res(body: String)     → HttpResponse  # text/plain
html_res(body: String)     → HttpResponse  # text/html
json_res(body: String)     → HttpResponse  # application/json
file_res(filepath: String) → HttpResponse  # auto-detect MIME
not_found_res()            → HttpResponse  # 404
```

### URL Utilities

```toka
parse_query(path: String)  → (path, query_string)
match_path(path: String)   → path_without_query
get_query_param(qs, key)   → value or ""
```

## Demo Routes

| Route | Response |
|---|---|
| `GET /` | `www/index.html` |
| `GET /hello` | `Hello from Toka!` |
| `GET /json` | `{"msg":"Hello from Toka-httpd!"}` |
| `GET /echo?msg=hi` | `You said: hi` |
| `GET /anything` | `www/anything` or 404 |

## Project Structure

```
toka-httpd/
├── httpd.tk            # Core library
├── demo/
│   ├── demo.tk         # Demo server
│   └── www/
│       ├── index.html  # Landing page
│       └── sample.txt  # Sample static file
└── README.md
```

## Known Issues

- `String::eq` miscompares equal-length strings (use `find_str()` for routing)
- Toka string literals don't support escape sequences (use `push_char()` for CR/LF)
- Single-threaded blocking accept loop (async TcpListener coming soon)

## License

Apache 2.0
