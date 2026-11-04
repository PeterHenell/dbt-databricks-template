"""A minimal fake Databricks workspace API for running the Databricks CLI offline.

Answers just enough for `databricks bundle validate` (current user, workspace
status) and records every request. It is not a model of Databricks: anything it
doesn't know gets an empty 200 response.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USER = {"id": "1", "userName": "ci-bot@example.com", "displayName": "CI Bot", "active": True}


class MockWorkspace:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        workspace = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _reply(self, body: dict, code: int = 200) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                workspace.requests.append(("GET", self.path))
                path = self.path.split("?")[0]
                if path.endswith("/scim/v2/Me"):
                    return self._reply(USER)
                if path == "/api/2.0/workspace/get-status":
                    return self._reply({"object_type": "DIRECTORY", "path": "/", "object_id": 1})
                if path.startswith("/.well-known/") or "/oidc/" in path:
                    return self._reply({}, 404)
                return self._reply({})

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                workspace.requests.append(("POST", self.path))
                return self._reply({})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "MockWorkspace":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
