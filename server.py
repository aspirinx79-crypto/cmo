"""로컬 서버. 경로를 lib 함수에 연결만 한다. 계산 로직을 여기 두지 않는다.

미팅 장소의 와이파이는 못 믿는다. 그래서 127.0.0.1 에만 붙고
외부로 나가는 요청을 하지 않는다.
"""
import json
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from cmo.lib.pricing import summarize
from cmo.lib.storage import PlanExists, Store

CMO = Path(__file__).resolve().parent

CLIENT_RE = re.compile(r"^/api/clients/([^/]+)$")
PLANS_RE = re.compile(r"^/api/clients/([^/]+)/plans$")
PLAN_RE = re.compile(r"^/api/clients/([^/]+)/plans/(\d{4}-\d{2})$")
COPY_RE = re.compile(r"^/api/clients/([^/]+)/plans/(\d{4}-\d{2})/copy$")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
}


def make_handler(store: Store, app_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # 미팅 중 콘솔이 시끄러우면 안 된다

        # --- 응답 도우미 ---
        def _json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        def _static(self, path: str):
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (app_dir / name).resolve()
            if not str(target).startswith(str(app_dir.resolve())) or not target.exists():
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # --- 라우팅 ---
        def do_GET(self):
            parsed = urlparse(self.path)
            path = unquote(parsed.path)

            if not path.startswith("/api/"):
                return self._static(path)

            try:
                if path == "/api/products":
                    return self._json(store.products())
                if path == "/api/presets":
                    return self._json(store.presets())
                if path == "/api/clients":
                    return self._json(store.clients())

                m = CLIENT_RE.match(path)
                if m:
                    return self._json(store.client_read(m.group(1)))

                m = PLANS_RE.match(path)
                if m:
                    return self._json(store.plan_months(m.group(1)))

                m = PLAN_RE.match(path)
                if m:
                    return self._json(store.plan_read(m.group(1), m.group(2)))
            except ValueError as exc:
                return self._json({"오류": str(exc)}, 400)
            except FileNotFoundError as exc:
                return self._json({"오류": str(exc)}, 404)

            self.send_error(404)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            force = "force=1" in (parsed.query or "")

            try:
                body = self._body()

                if path == "/api/summary":
                    return self._json(
                        summarize(store.products(), body.get("항목", []),
                                  int(body.get("계약가") or 0))
                    )

                m = CLIENT_RE.match(path)
                if m:
                    store.client_write(m.group(1), body)
                    return self._json({"저장": m.group(1)})

                m = COPY_RE.match(path)
                if m:
                    try:
                        return self._json(store.plan_copy(m.group(1), m.group(2),
                                                          body["대상월"]))
                    except PlanExists as exc:
                        return self._json({"오류": str(exc)}, 409)

                m = PLAN_RE.match(path)
                if m:
                    try:
                        store.plan_write(m.group(1), m.group(2), body, force=force)
                    except PlanExists as exc:
                        return self._json({"오류": str(exc)}, 409)
                    return self._json({"저장": f"{m.group(1)}/{m.group(2)}"})
            except (ValueError, KeyError) as exc:
                return self._json({"오류": str(exc)}, 400)
            except FileNotFoundError as exc:
                return self._json({"오류": str(exc)}, 404)

            self.send_error(404)

    return Handler


def serve(port: int, store: Store, app_dir: Path) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), make_handler(store, app_dir))


def main() -> int:
    store = Store(CMO / "data")
    httpd = serve(8765, store, CMO / "app")
    url = "http://127.0.0.1:8765/"
    print(f"CMO 기획 도구 — {url}\n창을 닫으면 종료됩니다.")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
