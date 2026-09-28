"""로컬 서버. 경로를 lib 함수에 연결만 한다. 계산 로직을 여기 두지 않는다.

미팅 장소의 와이파이는 못 믿는다. 그래서 127.0.0.1 에만 붙는다.

밖으로 나가는 경로는 `POST /api/collect` 하나뿐이고, 그것도 사람이 눌러야
한 건 돈다. 나머지 화면은 인터넷이 끊긴 자리에서도 전부 돌아간다.
"""
import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from cmo.lib.pricing import summarize
from cmo.lib.storage import ClientExists, PlanExists, Store

CMO = Path(__file__).resolve().parent
# `run_cmo.bat` 이 `cd ..` 로 들어오므로 cwd 가 아니라 코드 옆이다.
ENV_FILE = CMO / ".env"

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

NO_ADLOG_KEY = ("애드로그 조회에 필요한 값이 없습니다. "
                "ADLOG_API_KEY 와 ADLOG_USER_ID 를 환경변수에 넣으십시오.")
NOT_LINKED = ("이 매장은 애드로그에 연결돼 있지 않습니다. "
              "「애드로그에서 찾기」로 먼저 이으십시오.")

# 애드로그가 "과도한 트래픽 발생 시 사전 안내 없이 차단"을 경고한다.
# 목록 조회도 같은 간격을 쓴다.
SYNC_SLEEP = 0.3
# 이 코드들은 다음 키워드를 불러도 같은 답이 온다. 바로 멈춘다.
ACCOUNT_CODES = ("애드로그 계정 정보를 확인하십시오.",
                 "이 PC 의 IP 를 애드로그에 등록해야 합니다.",
                 "애드로그 서비스 기간이 만료됐습니다.")

CACHE_HOURS = 24


def _fresh(stamp: str | None) -> bool:
    """캐시가 아직 쓸 만한가. 모양이 깨졌으면 낡은 것으로 본다."""
    if not stamp:
        return False
    try:
        age = datetime.now() - datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return age.total_seconds() < CACHE_HOURS * 3600


def _archive_if_relinked(store: Store, slug: str, new_client: dict) -> None:
    """매장을 다시 이으면 옛 원장을 옆으로 치운다.

    플레이스ID 가 바뀌는 유일한 자리는 `POST /api/clients/{slug}` 다 —
    화면의 `linkAdlog` 가 새 애드로그 블록을 이 경로로 저장한다. 옛
    원장을 그대로 두면 옛 매장 키워드가 다음 스냅샷에 섞인다.
    """
    try:
        old = store.client_read(slug)
    except FileNotFoundError:
        return
    옛플레이스ID = (old.get("애드로그") or {}).get("플레이스ID")
    새플레이스ID = (new_client.get("애드로그") or {}).get("플레이스ID")
    if 옛플레이스ID and 새플레이스ID and 옛플레이스ID != 새플레이스ID:
        store.ranks_archive(slug, 옛플레이스ID)


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


def _adlog_keywords(key, uid):
    """애드로그 등록 목록 한 겹. 테스트가 여기를 갈아 끼운다."""
    from cmo.lib.adlog import keywords
    return keywords(key, uid)


def _adlog_ranks(key, uid, api_no):
    """애드로그 순위 한 겹. 테스트가 여기를 갈아 끼운다."""
    from cmo.lib.adlog import ranks
    return ranks(key, uid, api_no)


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

        # --- 애드로그 ---
        def _adlog_places(self, store, refresh: bool):
            """등록된 플레이스 키워드 목록. 하루는 캐시를 쓴다.

            목록 한 번에 20 회를 부른다. 매장 정보를 열 때마다 부르면
            그것만으로 하루 한도를 갉는다.
            """
            from cmo.lib.adlog import AdlogError, credentials

            cached = store.adlog_cache_read()
            if not refresh and _fresh(cached.get("갱신시각")):
                return self._json(cached)

            creds = credentials()
            if not creds:
                return self._json({"오류": NO_ADLOG_KEY}, 400)
            try:
                items = _adlog_keywords(*creds)
            except AdlogError as exc:
                return self._json({"오류": str(exc)}, 502)
            except Exception as exc:
                print(f"[애드로그] 목록 조회 실패: {exc!r}", file=sys.stderr)
                return self._json({"오류": "애드로그 조회에 실패했습니다."}, 502)

            data = {"갱신시각": datetime.now().isoformat(timespec="seconds"),
                    "items": items}
            store.adlog_cache_write(data)
            return self._json(data)

        def _adlog_sync(self, store, body: dict):
            """연결된 키워드 순위를 받아 원장에 쌓고 스냅샷 한 건을 붙인다.

            키워드 하나가 실패해도 나머지는 계속 본다 — 열 개 중 하나
            때문에 아홉 개를 못 보면 그날 미팅 자료가 통째로 빈다. 다만
            계정 단위 실패와 타임아웃은 다음 키워드를 불러도 나아지지
            않으므로 그 자리에서 멈춘다(중단 조건은 아래 두 가지).

            같은 날 두 번 누르면 스냅샷은 쌓지 않고 그 자리를 덮는다.
            """
            from cmo.lib.adlog import (AdlogError, credentials, metrics_by_date,
                                       series)
            from cmo.lib.collect import (append_or_replace_snapshot, merge_ranks,
                                         snapshot_from_ranks)

            slug = body["slug"]                 # 없으면 KeyError → 400
            client = store.client_read(slug)    # 없으면 FileNotFoundError → 404

            애드로그 = client.get("애드로그") or {}
            키워드들 = 애드로그.get("키워드") or []
            if not 애드로그.get("플레이스ID") or not 키워드들:
                return self._json({"오류": NOT_LINKED}, 400)

            creds = credentials()
            if not creds:
                return self._json({"오류": NO_ADLOG_KEY}, 400)

            # `받은것` 은 이번에 답을 받은 키워드다. 스냅샷은 이 목록만
            # 놓고 만든다 — 연결된 키워드 전부를 넘기면 못 물어본
            # 키워드가 「순위권밖」으로 찍힌다. 순위가 안 잡힌 날은 애드로그가
            # 그 날짜 줄을 아예 안 줘서 원장에 기록이 안 남으므로, 원장만
            # 봐서는 실패와 「아직 안 잡혔다」가 구분되지 않는다.
            # 2001 은 여기서 `rows` 에 줄이 쌓이므로 받은 것에 든다.
            rows, 받은것, 실패 = [], [], None
            for i, kw in enumerate(키워드들):
                if i:
                    time.sleep(SYNC_SLEEP)
                try:
                    items = _adlog_ranks(*creds, kw["api_no"])
                except AdlogError as exc:
                    실패 = str(exc)
                    print(f"[애드로그] {kw.get('keyword')!r} 조회 실패: {exc!r}",
                          file=sys.stderr)
                    # 계정 단위 실패는 나머지를 불러도 같다.
                    if 실패 in ACCOUNT_CODES:
                        break
                    continue
                except Exception as exc:
                    실패 = "애드로그 조회에 실패했습니다."
                    print(f"[애드로그] {kw.get('keyword')!r} 조회 실패: {exc!r}",
                          file=sys.stderr)
                    # 느린 날은 키워드마다 느리다. 이 서버는 요청을 하나씩
                    # 처리해서, 57 개를 다 기다리면 한 시간을 멈춘다.
                    break
                지표 = metrics_by_date(items)
                최신 = 지표[max(지표)] if 지표 else {}
                rows.append({
                    "키워드": kw["keyword"],
                    "api_no": kw["api_no"],
                    "월검색수": 최신.get("월검색수"),
                    "경쟁업체수": 최신.get("경쟁업체수"),
                    "순위": series(items),
                    "매장지표": {d: {k: v for k, v in m.items()
                                     if k in ("방문자리뷰", "블로그리뷰", "저장수")}
                                 for d, m in 지표.items()},
                })
                받은것.append(kw)

            if not rows and 실패:
                return self._json({"오류": 실패}, 502)

            원장 = merge_ranks(store.ranks_read(slug),
                               애드로그["플레이스ID"], rows)
            store.ranks_write(slug, 원장)

            snapshot = snapshot_from_ranks(원장, 받은것)
            if snapshot:
                store.client_write(slug, append_or_replace_snapshot(client, snapshot))

            # `요청` 이 있어야 화면이 「둘 중 하나만 받았다」를 말할 수
            # 있다. 못 받은 키워드는 `받은것` 에서 빠져 이번 스냅샷에
            # 줄이 안 서고, 그대로 이번 제안서에서 사라진다.
            return self._json({"갱신": len(rows), "요청": len(키워드들),
                               "스냅샷": snapshot, "경고": 실패})

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

                if path == "/api/adlog/places":
                    refresh = "refresh=1" in (parsed.query or "")
                    return self._adlog_places(store, refresh)

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
                    from cmo.lib.proposal import (ProposalBlocked,
                                                  build_payload, missing_pages)
                    slug, month = body["slug"], body["월"]
                    try:
                        payload = build_payload(store.client_read(slug),
                                                store.plan_read(slug, month),
                                                store.products())
                    except ProposalBlocked as exc:
                        return self._json({"오류": str(exc)}, 400)
                    out = CMO / "out" / f"{slug}_{month}_제안서.pdf"
                    # 막지 않는다. 진단 없이 나가야 하는 달도 있다 — 다만
                    # 빠진 줄 모르고 나가는 일은 없어야 한다.
                    return self._json({"경로": str(build(payload, out)),
                                       "경고": missing_pages(payload)})

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

                if path == "/api/adlog/sync":
                    return self._adlog_sync(store, body)

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
                    slug = m.group(1)
                    _archive_if_relinked(store, slug, body)
                    store.client_write(slug, body)
                    return self._json({"저장": slug})

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


def load_env(path: Path) -> None:
    """`.env` 를 환경에 싣는다. **`main()` 에서만 부른다.**

    `.env.example` 이 "옆에 .env 를 만들어 넣으라" 고 시키는데 그걸 읽는
    코드가 없었다. 여는 법은 `run_cmo.bat` 더블클릭 하나뿐이라 셸이
    없고, 그래서 키를 넣었다고 믿는 사람에게 「환경변수에 넣으십시오」가
    떴다.

    import 시점에 부르면 시험이 개발자 PC 의 실제 키를 집는다.

    이미 있는 환경변수는 덮지 않는다 — `setx`·CI·시험의 monkeypatch 가
    계속 이겨야 한다. 파일이 없으면 조용히 넘어간다(셸이나 `setx` 로
    넣은 PC 가 그렇다).

    메모장으로 저장하면 파일 앞에 보이지 않는 글자(BOM)가 붙는다. 그게
    남으면 첫 줄 이름이 `ADLOG_API_KEY` 가 아니게 돼서 "넣었는데 안
    된다" 가 그대로 재발한다.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return
    except UnicodeDecodeError:
        print(f"{path.name} 을 UTF-8 로 읽지 못했습니다. 건너뜁니다.",
              file=sys.stderr)
        return

    for 줄 in text.splitlines():
        줄 = 줄.strip()
        if not 줄 or 줄.startswith("#") or "=" not in 줄:
            continue
        이름, _, 값 = 줄.partition("=")
        이름, 값 = 이름.strip(), 값.strip()
        if len(값) >= 2 and 값[0] == 값[-1] and 값[0] in "\"'":
            값 = 값[1:-1]
        if 이름 and 이름 not in os.environ:
            os.environ[이름] = 값


def main() -> int:
    load_env(ENV_FILE)
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
