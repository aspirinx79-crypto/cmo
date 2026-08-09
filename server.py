"""로컬 서버. 경로를 lib 함수에 연결만 한다. 계산 로직을 여기 두지 않는다.

미팅 장소의 와이파이는 못 믿는다. 그래서 127.0.0.1 에만 붙는다.

밖으로 나가는 경로는 `POST /api/collect` 하나뿐이고, 그것도 사람이 눌러야
한 건 돈다. 나머지 화면은 인터넷이 끊긴 자리에서도 전부 돌아간다.
"""
import json
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from cmo.lib.pricing import summarize
from cmo.lib.storage import ClientExists, PlanExists, Store

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
            root = app_dir.resolve()
            target = (app_dir / name).resolve()
            inside_root = target == root or root in target.parents
            if not inside_root or not target.exists():
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # --- 수집 ---
        def _collect(self, store, body: dict):
            """플레이스를 1건 읽어 스냅샷으로 붙인다. 사람이 눌러야 돈다.

            순위·예상매출은 본문으로 받는다. 애드로그 엔드포인트가 아직
            추정값이고 오픈업은 자동 수집을 하지 않기 때문이다.

            실패해도 400/404/502 로 사람이 읽을 수 있게 돌려준다 — 여기서
            멈추면 미팅 자료를 손으로 채우면 그만이다.
            """
            from cmo.lib.collect import append_snapshot, fetch_place, make_snapshot

            slug = body["slug"]                 # 없으면 KeyError → 400
            client = store.client_read(slug)    # 없으면 FileNotFoundError → 404

            url = (client.get("플레이스URL") or "").strip()
            if not url:
                return self._json(
                    {"오류": "플레이스 URL이 없습니다. 고객사 정보에 먼저 등록하십시오."},
                    400)

            try:
                place = fetch_place(url)
            except Exception as exc:
                # 예외 원문에는 URL·페이지 내용이 섞인다. 원문은 콘솔에만 남긴다.
                print(f"[플레이스] {slug} 수집 실패: {exc!r}", file=sys.stderr)
                return self._json(
                    {"오류": "플레이스 수집에 실패했습니다. 수동으로 입력하십시오."}, 502)

            snapshot = make_snapshot(place, body.get("순위") or [],
                                     body.get("예상매출"))
            store.client_write(slug, append_snapshot(client, snapshot))
            return self._json(snapshot)

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

                if path == "/api/proposal":
                    from cmo.build_proposal import build
                    from cmo.lib.proposal import ProposalBlocked, build_payload
                    slug, month = body["slug"], body["월"]
                    try:
                        payload = build_payload(store.client_read(slug),
                                                store.plan_read(slug, month),
                                                store.products())
                    except ProposalBlocked as exc:
                        return self._json({"오류": str(exc)}, 400)
                    out = CMO / "out" / f"{slug}_{month}_제안서.pdf"
                    return self._json({"경로": str(build(payload, out))})

                if path == "/api/collect":
                    return self._collect(store, body)

                if path == "/api/clients":
                    return self._json({"slug": store.client_create(body)}, 201)

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
            except ClientExists as exc:
                return self._json({"오류": str(exc)}, 409)
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
