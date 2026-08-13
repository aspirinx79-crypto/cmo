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

# 수집이 막혔을 때 사용자가 다음에 할 일을 메시지에 적는다. 막다른 길로
# 끝나는 오류는 "도구가 고장났다"로 읽히고, 그러면 손으로 JSON 을 고치러
# 간다 — 이 패널을 만든 이유가 사라진다.
_ESCAPE = "「플레이스 함께 수집」을 끄고 다시 저장하면 손으로 넣은 값만 저장됩니다."
ESCAPE_HATCH_NO_URL = f"플레이스 URL이 없습니다. 매장 정보에 먼저 등록하십시오. {_ESCAPE}"
ESCAPE_HATCH_FAILED = f"플레이스 수집에 실패했습니다. {_ESCAPE}"

NO_READ_KEY = ("판독에 필요한 키가 없습니다. "
               "ANTHROPIC_API_KEY 를 환경변수에 넣으십시오.")


def _read_document(files, api_key, model=None):
    """판독 함수 한 겹. 테스트가 여기를 통째로 갈아 끼운다.

    캡처 여러 장을 받는다 — 조회수는 순위 추이 표에, 리뷰 목록은 기본정보
    화면에 있어 한 장으로는 그림이 안 맞춰진다.
    """
    from cmo.lib.read_doc import read_captures
    return read_captures(files, api_key)


def _read_captures(files, api_key):
    """오픈업 판독 함수 한 겹. 테스트가 여기를 통째로 갈아 끼운다."""
    from cmo.lib.read_openub import read_captures
    return read_captures(files, api_key)


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

            `플레이스수집: false` 면 플레이스를 건너뛰고 손으로 넣은 값만
            저장한다. 네이버가 화면을 바꾸는 날은 오는데, 그때 수집이
            막힌다고 순위·매출까지 못 넣으면 신규 매장을 아예 등록할 수
            없다. 실패는 빨간 줄 하나로 끝나야 한다.

            세 출처는 한 스냅샷에 함께 묶인다. 나눠 저장하면 나중에 두
            시점을 비교할 때 축이 어긋난다.
            """
            from cmo.lib.collect import append_snapshot, fetch_place, make_snapshot

            slug = body["slug"]                 # 없으면 KeyError → 400
            client = store.client_read(slug)    # 없으면 FileNotFoundError → 404

            place = {}
            if body.get("플레이스수집", True):
                url = (client.get("플레이스URL") or "").strip()
                if not url:
                    return self._json({"오류": ESCAPE_HATCH_NO_URL}, 400)
                try:
                    place = fetch_place(url)
                except Exception as exc:
                    # 예외 원문에는 URL·페이지 내용이 섞인다. 원문은 콘솔에만 남긴다.
                    print(f"[플레이스] {slug} 수집 실패: {exc!r}", file=sys.stderr)
                    return self._json({"오류": ESCAPE_HATCH_FAILED}, 502)

            snapshot = make_snapshot(place, body.get("순위") or [],
                                     body.get("예상매출"))
            store.client_write(slug, append_snapshot(client, snapshot))
            return self._json(snapshot)

        # --- 자료 판독 ---
        def _read_doc(self, store, body: dict):
            """파일 한 개를 판독해 돌려준다. **아무것도 저장하지 않는다.**

            판독이 1,082 를 108 로 읽는 날이 온다. 사람이 눈으로 보고
            저장을 누르기 전까지는 파일이 그대로여야 한다.
            """
            import base64 as b64

            from cmo.lib.read_doc import (api_key_from_env, store_mismatch,
                                          truncation_warning)

            slug = body["slug"]                 # 없으면 KeyError → 400
            client = store.client_read(slug)    # 없으면 FileNotFoundError → 404

            key = api_key_from_env()
            if not key:
                return self._json({"오류": NO_READ_KEY}, 400)

            # 옛 본문(파일명·내용 한 장)도 그대로 받는다 — 화면을 고치기
            # 전에 서버만 올라가는 순간이 있고, 그때 판독이 죽으면 안 된다.
            캡처 = body.get("캡처")
            if 캡처 is None:
                캡처 = [{"파일명": body.get("파일명") or "",
                        "내용": body.get("내용") or ""}]
            try:
                files = [(b64.b64decode(c["내용"]), c.get("파일명") or "")
                         for c in 캡처]
            except Exception:
                return self._json({"오류": "파일을 읽지 못했습니다."}, 400)

            reading = _read_document(files, key)

            mismatch = store_mismatch(reading, client)
            warnings = [w for w in (truncation_warning(reading),) if w]
            return self._json({"판독": reading, "경고": warnings,
                               "저장가능": mismatch is None,
                               "불일치": mismatch})

        def _apply_doc(self, store, body: dict):
            """사람이 확인한 판독을 저장한다.

            매장 대조를 **여기서 다시 한다.** 화면이 막았더라도 서버가
            최종 관문이다.

            들어온 판독을 `parse_reading` 에 다시 통과시킨다 — 화면이 보낸
            dict 를 그대로 믿고 저장하면 모양 검사를 한 번도 안 거친 값이
            매장 폴더에 들어간다. 판독 경로에서 통과한 값이면 여기서도
            그대로 통과하므로 사람에게는 아무 차이가 없다.
            """
            from cmo.lib.collect import append_snapshot
            from cmo.lib.read_doc import (merge_into_client, parse_reading,
                                          snapshot_from, store_mismatch)

            slug = body["slug"]
            client = store.client_read(slug)
            reading = parse_reading(json.dumps(body["판독"], ensure_ascii=False))

            mismatch = store_mismatch(reading, client)
            if mismatch:
                return self._json({"오류": mismatch}, 400)

            merged = merge_into_client(client, reading)
            store.client_write(slug, append_snapshot(merged,
                                                     snapshot_from(reading)))
            return self._json({"저장": slug})

        # --- 오픈업 판독 ---
        def _read_openub(self, store, body: dict):
            """캡처 여러 장을 판독해 돌려준다. **아무것도 저장하지 않는다.**"""
            import base64 as b64

            from cmo.lib.read_doc import api_key_from_env, name_mismatch

            slug = body["slug"]                 # 없으면 KeyError → 400
            client = store.client_read(slug)    # 없으면 FileNotFoundError → 404

            key = api_key_from_env()
            if not key:
                return self._json({"오류": NO_READ_KEY}, 400)

            try:
                files = [(b64.b64decode(c["내용"]), c.get("파일명") or "")
                         for c in (body.get("캡처") or [])]
            except Exception:
                return self._json({"오류": "파일을 읽지 못했습니다."}, 400)

            reading = _read_captures(files, key)

            mismatch = name_mismatch(reading.get("매장명"), client)
            return self._json({"판독": reading,
                               "저장가능": mismatch is None,
                               "불일치": mismatch})

        def _apply_openub(self, store, body: dict):
            """사람이 확인한 판독을 저장한다.

            매장 대조를 **여기서 다시 한다.** 화면이 막았더라도 서버가
            최종 관문이다.

            들어온 판독을 `parse_openub` 에 **다시 통과시킨다** — 화면이
            보낸 dict 를 그대로 믿고 저장하면 모양 검사를 한 번도 안 거친
            값이 매장 폴더에 들어간다. 애드로그 `_apply_doc` 이
            `parse_reading` 을 다시 태우는 것과 같은 이유다.

            기준월이 없는 판독은 저장하지 않는다 — 섞인 캡처를 파서가
            끊어 기준월이 비었거나, 화면을 건너뛰고 직접 부른 경우다.
            기준월 없이 저장하면 어느 달 값인지 영영 알 수 없다.

            `ValueError` 는 `do_POST` 가 이미 400 으로 바꾼다.
            """
            from cmo.lib.read_doc import name_mismatch
            from cmo.lib.read_openub import (merge_openub, openub_entry,
                                             parse_openub)

            slug = body["slug"]
            client = store.client_read(slug)
            reading = parse_openub(json.dumps(body["판독"], ensure_ascii=False))

            mismatch = name_mismatch(reading.get("매장명"), client)
            if mismatch:
                return self._json({"오류": mismatch}, 400)

            entry = openub_entry(reading)
            if not entry.get("기준월"):
                return self._json({"오류": "기준월을 읽지 못해 저장하지 않습니다."},
                                  400)

            store.client_write(slug, merge_openub(client, entry))
            return self._json({"저장": slug})

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

                if path == "/api/read-doc/ready":
                    from cmo.lib.read_doc import api_key_from_env
                    return self._json({"준비됨": bool(api_key_from_env())})

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
                    from cmo.build_pdf import build
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

                if path == "/api/quote":
                    from cmo.build_pdf import QUOTE, build
                    from cmo.lib.quote import QuoteBlocked, build_quote_payload
                    slug, month = body["slug"], body["월"]
                    try:
                        payload = build_quote_payload(
                            store.client_read(slug),
                            store.plan_read(slug, month),
                            store.products(),
                            부가세별도=bool(body.get("부가세별도")),
                            내역펼침=bool(body.get("내역펼침", True)))
                    except QuoteBlocked as exc:
                        return self._json({"오류": str(exc)}, 400)
                    out = CMO / "out" / f"{slug}_{month}_견적서.pdf"
                    return self._json({"경로": str(build(payload, out,
                                                         template=QUOTE))})

                if path == "/api/collect":
                    return self._collect(store, body)

                if path == "/api/read-doc":
                    return self._read_doc(store, body)

                if path == "/api/read-doc/apply":
                    return self._apply_doc(store, body)

                if path == "/api/read-openub":
                    return self._read_openub(store, body)

                if path == "/api/read-openub/apply":
                    return self._apply_openub(store, body)

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
