from __future__ import annotations

import argparse
import http.client
import os
import re
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class LanProxyHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        if sys.stderr is not None:
            super().log_message(format, *args)

    def do_GET(self):
        if self._is_spoon_request():
            self._proxy_spoon()
            return
        self._serve_static_with_fallback(head_only=False)

    def do_HEAD(self):
        if self._is_spoon_request():
            self._proxy_spoon()
            return
        self._serve_static_with_fallback(head_only=True)

    def do_POST(self):
        self._proxy_or_reject()

    def do_PUT(self):
        self._proxy_or_reject()

    def do_PATCH(self):
        self._proxy_or_reject()

    def do_DELETE(self):
        self._proxy_or_reject()

    def do_OPTIONS(self):
        self._proxy_or_reject()

    def _proxy_or_reject(self):
        if self._is_spoon_request():
            self._proxy_spoon()
            return
        self.send_error(405, "Only WebSpoon requests support this method")

    def _is_spoon_request(self):
        path = urlsplit(self.path).path
        return path == "/spoon" or path.startswith("/spoon/")

    def _serve_static_with_fallback(self, head_only):
        original_path = self.path
        requested_path = Path(self.translate_path(self.path))
        url_path = Path(urlsplit(self.path).path)
        if not requested_path.exists() and not url_path.suffix:
            self.path = "/index.html"
        try:
            if head_only:
                super().do_HEAD()
            else:
                super().do_GET()
        finally:
            self.path = original_path

    def _proxy_spoon(self):
        upstream = self.server.spoon_origin
        connection_class = (
            http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_class(upstream.hostname, upstream.port, timeout=60)
        content_length = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(content_length) if content_length else None

        request_headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS | {"host", "content-length"}
        }
        request_headers["Host"] = upstream.netloc
        request_headers["X-Forwarded-For"] = self.client_address[0]
        request_headers["X-Forwarded-Host"] = self.headers.get("Host", "")
        request_headers["X-Forwarded-Proto"] = "http"

        try:
            connection.request(self.command, self.path, body=request_body, headers=request_headers)
            upstream_response = connection.getresponse()
            response_body = upstream_response.read()
        except (OSError, http.client.HTTPException) as error:
            self._send_proxy_error(error)
            return
        finally:
            connection.close()

        self.send_response(upstream_response.status, upstream_response.reason)
        for name, value in upstream_response.getheaders():
            lower_name = name.lower()
            if lower_name in HOP_BY_HOP_HEADERS | {"content-length", "server", "date"}:
                continue
            if lower_name == "location":
                value = self._rewrite_location(value)
            elif lower_name == "set-cookie":
                value = re.sub(r";\s*Domain=[^;]+", "", value, flags=re.IGNORECASE)
            self.send_header(name, value)

        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response_body)

    def _rewrite_location(self, value):
        upstream_origin = f"{self.server.spoon_origin.scheme}://{self.server.spoon_origin.netloc}"
        if not value.startswith(upstream_origin):
            return value
        public_host = self.headers.get("Host", "")
        return f"http://{public_host}{value[len(upstream_origin):]}"

    def _send_proxy_error(self, error):
        body = f"WebSpoon proxy unavailable: {error}".encode("utf-8", errors="replace")
        self.send_response(502, "Bad Gateway")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def create_server(host, port, static_root, spoon_origin):
    static_root = Path(static_root).resolve()
    if not (static_root / "index.html").is_file():
        raise FileNotFoundError(f"Static build not found: {static_root / 'index.html'}")

    parsed_origin = urlsplit(spoon_origin)
    if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.hostname:
        raise ValueError(f"Invalid WebSpoon origin: {spoon_origin}")

    handler = partial(LanProxyHandler, directory=str(static_root))
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server.spoon_origin = parsed_origin
    return server


def parse_args():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Serve the prototype and proxy WebSpoon for LAN users")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--static-root", type=Path, default=root / "dist" / "client")
    parser.add_argument(
        "--spoon-origin",
        default=os.environ.get("SPOON_ORIGIN", "http://192.168.107.72:8881"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    server = create_server(args.host, args.port, args.static_root, args.spoon_origin)
    if sys.stdout is not None:
        print(
            f"Serving {args.static_root} on http://{args.host}:{args.port} "
            f"with /spoon proxied to {args.spoon_origin}",
            flush=True,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
