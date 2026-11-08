"""The real urllib transport against a local HTTP server (no Google involved).

Checks that timeouts, HTTP errors and refused connections map to the exceptions the
classifier expects, and that an error body is never passed on (it may echo our request).
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.classifiers.gemini import ProviderHttpError, urllib_transport


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.path == "/slow":
            time.sleep(1.0)
        status = {"/ok": 200, "/slow": 200, "/429": 429, "/500": 500}[self.path]
        reply = body if status == 200 else b'{"error": "echo of the request: SECRET"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


HEADERS = {"Content-Type": "application/json"}


def test_returns_the_body(server: str) -> None:
    assert urllib_transport(f"{server}/ok", HEADERS, b'{"a": 1}', 5) == b'{"a": 1}'


@pytest.mark.parametrize("status", [429, 500])
def test_http_errors_keep_only_the_status(server: str, status: int) -> None:
    with pytest.raises(ProviderHttpError) as exc:
        urllib_transport(f"{server}/{status}", HEADERS, b"{}", 5)
    assert exc.value.status == status
    assert "SECRET" not in str(exc.value) and exc.value.__cause__ is None


def test_slow_answer_is_a_timeout(server: str) -> None:
    with pytest.raises(TimeoutError):
        urllib_transport(f"{server}/slow", HEADERS, b"{}", 0.2)


def test_refused_connection_is_a_connection_error() -> None:
    with pytest.raises((ConnectionError, TimeoutError)):
        urllib_transport("http://127.0.0.1:9/", HEADERS, b"{}", 2)
