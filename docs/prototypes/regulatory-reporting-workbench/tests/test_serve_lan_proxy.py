from __future__ import annotations

import http.client
import importlib.util
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
PROXY_MODULE_PATH = ROOT / "scripts" / "serve_lan_proxy.py"


def load_proxy_module():
    if not PROXY_MODULE_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("serve_lan_proxy", PROXY_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PROXY_MODULE = load_proxy_module()


class UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.seen_requests.append(("GET", self.path, self.headers, b""))
        if self.path.startswith("/spoon/redirect"):
            host, port = self.server.server_address
            self.send_response(302)
            self.send_header("Location", f"http://{host}:{port}/spoon/spoon")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/spoon/cookie"):
            body = b"cookie"
            self.send_response(200)
            self.send_header("Set-Cookie", "session=abc; Path=/spoon; Domain=127.0.0.1")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = f"upstream:{self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.seen_requests.append(("POST", self.path, self.headers, body))
        response = b"posted:" + body
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, _format, *_args):
        pass


@unittest.skipIf(PROXY_MODULE is None, "proxy module has not been implemented")
class LanProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = TemporaryDirectory()
        static_root = Path(cls.temp_dir.name)
        (static_root / "index.html").write_text("prototype-shell", encoding="utf-8")
        (static_root / "asset.txt").write_text("static-asset", encoding="utf-8")

        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        cls.upstream.seen_requests = []
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()

        upstream_host, upstream_port = cls.upstream.server_address
        cls.proxy = PROXY_MODULE.create_server(
            "127.0.0.1",
            0,
            static_root,
            f"http://{upstream_host}:{upstream_port}",
        )
        cls.proxy_thread = threading.Thread(target=cls.proxy.serve_forever, daemon=True)
        cls.proxy_thread.start()
        cls.proxy_host, cls.proxy_port = cls.proxy.server_address

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown()
        cls.proxy.server_close()
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.proxy_thread.join(timeout=2)
        cls.upstream_thread.join(timeout=2)
        cls.temp_dir.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(self.proxy_host, self.proxy_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read()
        result = response.status, response.getheaders(), response_body
        connection.close()
        return result

    def test_serves_static_files(self):
        status, _headers, body = self.request("GET", "/asset.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"static-asset")

    def test_falls_back_to_app_shell_for_unknown_page(self):
        status, _headers, body = self.request("GET", "/reporting/workbench")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"prototype-shell")

    def test_forwards_spoon_path_and_query(self):
        status, _headers, body = self.request("GET", "/spoon/spoon?mode=edit")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"upstream:/spoon/spoon?mode=edit")
        method, path, headers, _body = self.upstream.seen_requests[-1]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/spoon/spoon?mode=edit")
        self.assertEqual(headers["Host"], f"{self.upstream.server_address[0]}:{self.upstream.server_address[1]}")

    def test_forwards_post_body(self):
        status, _headers, body = self.request(
            "POST",
            "/spoon/service",
            body=b"payload",
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"posted:payload")
        method, path, _headers, request_body = self.upstream.seen_requests[-1]
        self.assertEqual((method, path, request_body), ("POST", "/spoon/service", b"payload"))

    def test_rewrites_upstream_redirect_to_proxy_origin(self):
        status, headers, _body = self.request(
            "GET",
            "/spoon/redirect",
            headers={"Host": "workbench.test:8766"},
        )
        self.assertEqual(status, 302)
        self.assertEqual(dict(headers)["Location"], "http://workbench.test:8766/spoon/spoon")

    def test_removes_upstream_cookie_domain(self):
        status, headers, _body = self.request("GET", "/spoon/cookie")
        self.assertEqual(status, 200)
        cookie = dict(headers)["Set-Cookie"]
        self.assertIn("session=abc", cookie)
        self.assertNotIn("Domain=", cookie)


class ProxyIntegrationContractTests(unittest.TestCase):
    def test_proxy_module_exists(self):
        self.assertIsNotNone(PROXY_MODULE, "scripts/serve_lan_proxy.py must provide the LAN proxy server")

    def test_iframe_uses_same_origin_spoon_path(self):
        source = (ROOT / "src" / "SchedulingManagement.jsx").read_text(encoding="utf-8")
        self.assertIn('src="/spoon/spoon"', source)
        self.assertNotIn('src="http://192.168.107.72:8881/spoon/spoon"', source)

    def test_vite_dev_server_proxies_spoon_path(self):
        source = (ROOT / "vite.config.mjs").read_text(encoding="utf-8")
        self.assertIn('"/spoon"', source)
        self.assertIn('target: "http://192.168.107.72:8881"', source)

    def test_version_management_hides_svn_branding(self):
        scheduling_source = (ROOT / "src" / "SchedulingManagement.jsx").read_text(encoding="utf-8")
        app_source = (ROOT / "src" / "App.jsx").read_text(encoding="utf-8")

        self.assertNotIn("SVN", scheduling_source)
        self.assertNotIn("SVN 与发布", app_source)
        self.assertIn("管理版本提交、生产发布与历史恢复", scheduling_source)
        self.assertIn("版本历史", scheduling_source)

    @unittest.skipIf(PROXY_MODULE is None, "proxy module has not been implemented")
    def test_request_logging_is_safe_without_console_streams(self):
        handler = object.__new__(PROXY_MODULE.LanProxyHandler)
        original_stderr = sys.stderr
        try:
            sys.stderr = None
            handler.log_message("request %s", "/")
        finally:
            sys.stderr = original_stderr


if __name__ == "__main__":
    unittest.main()
