"""수집 로직 테스트. 네트워크를 타는 건 network 마커로 분리한다.

플레이스 화면 구조는 언젠가 반드시 바뀐다. 그때 도구 전체가
멈추면 안 되므로 실패해도 수동 입력으로 진행할 수 있어야 한다.

이 파일의 검사는 크게 넷이다.
  1. 파싱·스냅샷 — 값이 없으면 None, 시각은 반드시 남는다.
  2. 전송 안전 — 키를 평문 http 로 내보내지 않는다.
  3. 누출 차단 — 예외 문자열과 매출 금액이 고객 손에 닿는 JSON 에 안 실린다.
  4. 서버 계약 — 실패해도 사람이 읽을 수 있는 400/404/502 로 돌아온다.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from cmo.lib import collect
from cmo.lib.collect import (
    ADLOG_ENDPOINT,
    ADLOG_KEY_ENV,
    api_key_from_env,
    append_snapshot,
    fetch_ranks,
    make_snapshot,
    parse_place_counts,
)
from cmo.lib.proposal import build_payload
from cmo.lib.storage import Store
from cmo.server import serve

PLACE_TEXT = "방문자리뷰 312 블로그리뷰 14 저장 88"

# 예외 메시지·응답 본문에 섞여 들어올 수 있는 고객 식별 문자열.
# 이게 클라이언트로 돌아가는 JSON 에 한 글자라도 보이면 그 자체가 실패다.
SENSITIVE = "하루인인계점-010-1234-5678"

PRODUCTS = [{"id": "네이버-블로그_일반_체험단", "매체": "네이버",
             "상품명": "블로그 일반 체험단", "가격유형": "고정",
             "정가": 30000, "실비": 8000, "최소수량": 5, "단위": "팀",
             "판매중지": False, "고지사항": "", "프로세스": ""}]
PLAN = {"월": "2026-09", "계약가": 1000000,
        "항목": [{"상품id": "네이버-블로그_일반_체험단", "수량": 10}]}


# --- 파싱 -------------------------------------------------------------

def test_parse_place_counts_reads_both():
    got = parse_place_counts(PLACE_TEXT)
    assert got["방문자리뷰"] == 312
    assert got["블로그리뷰"] == 14


def test_parse_place_counts_reads_saves():
    """반환은 2키가 아니라 3키다 — make_snapshot 이 저장수를 쓴다."""
    assert parse_place_counts(PLACE_TEXT)["저장수"] == 88


def test_parse_place_counts_handles_commas():
    got = parse_place_counts("방문자리뷰 1,204 블로그리뷰 87")
    assert got["방문자리뷰"] == 1204
    assert got["블로그리뷰"] == 87


def test_parse_place_counts_missing_fields_are_none():
    got = parse_place_counts("영업시간 11:00 - 22:00")
    assert got["방문자리뷰"] is None
    assert got["블로그리뷰"] is None
    assert got["저장수"] is None


# --- 스냅샷 -----------------------------------------------------------

def test_make_snapshot_records_time():
    snap = make_snapshot({"방문자리뷰": 312, "블로그리뷰": 14}, [], None)
    assert "수집시각" in snap and len(snap["수집시각"]) >= 19
    assert snap["플레이스"]["블로그리뷰"] == 14


def test_make_snapshot_includes_ranks():
    snap = make_snapshot({}, [{"키워드": "인계동 삼겹살", "순위": 17, "지수": 812}], None)
    assert snap["순위"][0]["순위"] == 17


def test_make_snapshot_revenue_is_optional():
    assert make_snapshot({}, [], None)["예상매출"] is None
    snap = make_snapshot({}, [], {"월매출": 42000000, "상권순위": "상위 40%"})
    assert snap["예상매출"]["상권순위"] == "상위 40%"


def test_append_snapshot_keeps_history():
    client = {"이름": "하루인 인계점", "스냅샷": [{"수집시각": "2026-03-01T09:00:00"}]}
    updated = append_snapshot(client, make_snapshot({}, [], None))
    assert len(updated["스냅샷"]) == 2
    assert updated["스냅샷"][0]["수집시각"] == "2026-03-01T09:00:00"


def test_append_snapshot_creates_list_when_absent():
    updated = append_snapshot({"이름": "새가게"}, make_snapshot({}, [], None))
    assert len(updated["스냅샷"]) == 1


def test_append_snapshot_does_not_mutate_input():
    client = {"이름": "하루인 인계점", "스냅샷": []}
    append_snapshot(client, make_snapshot({}, [], None))
    assert client["스냅샷"] == []


# --- 애드로그 전송 안전 -----------------------------------------------

class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _install_urlopen(monkeypatch, handler):
    """urllib.request.urlopen 을 대역으로 갈아 끼우고 호출 기록을 돌려준다."""
    calls = []

    def fake(req, timeout=None):
        calls.append((req.full_url, req.get_header("Authorization")))
        return handler(len(calls))

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


def test_adlog_endpoint_is_https():
    """평문 http 로 Bearer 키를 실어 보내면 중간에서 키가 그대로 읽힌다."""
    assert ADLOG_ENDPOINT.startswith("https://")


def test_fetch_ranks_refuses_http_before_touching_network(monkeypatch):
    """http 로 바뀌어 있으면 요청을 아예 만들지 않고 거절한다."""
    def _boom(index):
        raise AssertionError("http 인데 네트워크를 탔다")

    calls = _install_urlopen(monkeypatch, _boom)
    monkeypatch.setattr(collect, "ADLOG_ENDPOINT", "http://adlog.ai.kr/api/place/rank")

    with pytest.raises(ValueError) as exc:
        fetch_ranks("키값", "2069074461", ["인계동 삼겹살"])

    assert "https" in str(exc.value).lower()
    assert calls == []


def test_fetch_ranks_sends_key_in_header_over_https(monkeypatch):
    calls = _install_urlopen(monkeypatch, lambda index: _FakeResponse(b"{}"))

    fetch_ranks("테스트키", "2069074461", ["인계동 삼겹살"])

    assert len(calls) == 1
    url, auth = calls[0]
    assert url.startswith("https://")
    assert auth == "Bearer 테스트키"
    assert "인계동" not in url  # 한글은 퍼센트 인코딩되어야 한다
    assert "%EC%9D%B8%EA%B3%84%EB%8F%99" in url


def test_fetch_ranks_reads_fields_from_response(monkeypatch):
    payload = json.dumps({"rank": 17, "score": 812, "date": "2026-07-26"})
    _install_urlopen(monkeypatch,
                     lambda index: _FakeResponse(payload.encode("utf-8")))

    rows = fetch_ranks("키값", "2069074461", ["인계동 삼겹살"])

    assert rows == [{"키워드": "인계동 삼겹살", "순위": 17,
                     "지수": 812, "기준일": "2026-07-26"}]


def test_fetch_ranks_missing_fields_become_none(monkeypatch):
    """필드명이 추정값이다. 없으면 None 으로 두고 수동 입력으로 간다."""
    _install_urlopen(monkeypatch, lambda index: _FakeResponse(b"{}"))

    rows = fetch_ranks("키값", "2069074461", ["인계동 삼겹살"])

    assert rows == [{"키워드": "인계동 삼겹살", "순위": None,
                     "지수": None, "기준일": None}]


# --- 누출 차단 --------------------------------------------------------

@pytest.mark.parametrize("raiser,expected", [
    (lambda: (_ for _ in ()).throw(
        urllib.error.HTTPError("https://adlog.ai.kr/", 401, SENSITIVE, {}, None)),
     "인증 실패"),
    (lambda: (_ for _ in ()).throw(
        urllib.error.URLError(SENSITIVE)),
     "조회 실패"),
])
def test_fetch_ranks_error_is_a_short_human_phrase(monkeypatch, raiser, expected):
    """예외 원문은 스냅샷에 넣지 않는다 — 그 스냅샷이 클라이언트 JSON 이 된다."""
    _install_urlopen(monkeypatch, lambda index: raiser())

    rows = fetch_ranks("키값", "2069074461", ["인계동 삼겹살"])

    assert rows[0]["오류"] == expected
    assert rows[0]["순위"] is None and rows[0]["지수"] is None
    assert SENSITIVE not in json.dumps(rows, ensure_ascii=False)


def test_fetch_ranks_bad_json_is_format_error(monkeypatch):
    _install_urlopen(monkeypatch,
                     lambda index: _FakeResponse(SENSITIVE.encode("utf-8")))

    rows = fetch_ranks("키값", "2069074461", ["인계동 삼겹살"])

    assert rows[0]["오류"] == "응답 형식 오류"
    assert SENSITIVE not in json.dumps(rows, ensure_ascii=False)


def test_fetch_ranks_original_error_goes_to_stderr_only(monkeypatch, capsys):
    def _raise(index):
        raise urllib.error.URLError(SENSITIVE)

    _install_urlopen(monkeypatch, _raise)

    rows = fetch_ranks("키값", "2069074461", ["인계동 삼겹살"])

    assert SENSITIVE in capsys.readouterr().err
    assert SENSITIVE not in json.dumps(rows, ensure_ascii=False)


def test_fetch_ranks_continues_after_one_keyword_fails(monkeypatch):
    payload = json.dumps({"rank": 3, "score": 900, "date": "2026-07-26"})

    def handler(index):
        if index == 1:
            raise urllib.error.URLError(SENSITIVE)
        return _FakeResponse(payload.encode("utf-8"))

    _install_urlopen(monkeypatch, handler)

    rows = fetch_ranks("키값", "2069074461", ["망한키워드", "인계동 삼겹살"])

    assert len(rows) == 2
    assert rows[0]["오류"] == "조회 실패" and rows[0]["순위"] is None
    assert rows[1]["순위"] == 3 and "오류" not in rows[1]


def test_revenue_amount_never_reaches_proposal_payload():
    """스냅샷에 월매출이 있어도 제안서로는 상권순위만 나간다.

    오픈업 추정 매출의 절대금액은 상무님 판단 재료지 고객에게 보일 숫자가
    아니다. 화면에서 가리는 게 아니라 payload 에 값 자체가 없어야 한다.
    """
    snapshot = make_snapshot(
        {"방문자리뷰": 312, "블로그리뷰": 14, "저장수": 88},
        [{"키워드": "인계동 삼겹살", "순위": 17, "지수": 812}],
        {"월매출": 42000000, "상권순위": "상위 40%"},
    )
    client = {"이름": "하루인 인계점", "스냅샷": [snapshot]}

    payload = build_payload(client, PLAN, PRODUCTS)
    dumped = json.dumps(payload, ensure_ascii=False)

    assert "월매출" not in dumped
    assert "42000000" not in dumped and "42,000,000" not in dumped
    assert payload["지표"]["상권순위"] == "상위 40%"
    assert payload["지표"]["방문자리뷰"] == 312


# --- API 키 ------------------------------------------------------------

def test_api_key_comes_from_environment(monkeypatch):
    monkeypatch.setenv(ADLOG_KEY_ENV, "  진짜키값  ")
    assert api_key_from_env() == "진짜키값"


def test_api_key_absent_returns_none_with_a_message(monkeypatch, capsys):
    """키가 없다고 수집 전체가 멈추면 안 된다. 순위만 건너뛴다."""
    monkeypatch.delenv(ADLOG_KEY_ENV, raising=False)
    assert api_key_from_env() is None
    assert ADLOG_KEY_ENV in capsys.readouterr().err


def test_env_example_names_the_key_without_a_value(cmo_dir):
    """.env.example 에는 이름만 둔다. 값이 붙는 순간 키가 저장소에 올라간다."""
    path = cmo_dir / ".env.example"
    assert path.exists(), ".env.example 이 없다"
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    assert f"{ADLOG_KEY_ENV}=" in lines
    for line in lines:
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        assert value == "", f"{name} 에 값이 들어 있다"


# --- 서버 경로 ---------------------------------------------------------

CLIENT = {"이름": "하루인 인계점", "업종": "고깃집", "상태": "진행중",
          "플레이스URL": "https://m.place.naver.com/restaurant/2069074461",
          "스냅샷": []}
PLACE = {"매장명": "하루인 인계점",
         "플레이스URL": "https://m.place.naver.com/restaurant/2069074461",
         "방문자리뷰": 312, "블로그리뷰": 14, "저장수": 88}


@pytest.fixture
def server(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
    httpd = serve(0, Store(tmp_data), cmo_dir / "app")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=5)


def _post(base, path, body):
    from urllib.parse import quote
    req = urllib.request.Request(
        base + quote(path, safe="/?=&"), data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _post_error(base, path, body):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, path, body)
    return exc.value.code, json.loads(exc.value.read().decode("utf-8"))


def _get(base, path):
    from urllib.parse import quote
    with urllib.request.urlopen(base + quote(path, safe="/?=&")) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_collect_saves_snapshot_and_returns_it(server, monkeypatch):
    monkeypatch.setattr(collect, "fetch_place", lambda url, **kw: dict(PLACE))
    _post(server, "/api/clients/하루인_인계점", CLIENT)

    status, snap = _post(server, "/api/collect", {
        "slug": "하루인_인계점",
        "순위": [{"키워드": "인계동 삼겹살", "순위": 17, "지수": 812}],
        "예상매출": {"월매출": 42000000, "상권순위": "상위 40%"},
    })

    assert status == 200
    assert snap["플레이스"]["방문자리뷰"] == 312
    assert snap["순위"][0]["순위"] == 17
    assert len(snap["수집시각"]) >= 19

    _, saved = _get(server, "/api/clients/하루인_인계점")
    assert len(saved["스냅샷"]) == 1
    assert saved["스냅샷"][0]["플레이스"]["저장수"] == 88


def test_collect_without_place_url_returns_readable_400(server, monkeypatch):
    """맨 KeyError 문자열('플레이스URL')이 그대로 나가면 안 된다."""
    calls = []
    monkeypatch.setattr(collect, "fetch_place",
                        lambda url, **kw: calls.append(url) or dict(PLACE))
    _post(server, "/api/clients/URL없음", {"이름": "URL 없는 가게"})

    status, body = _post_error(server, "/api/collect", {"slug": "URL없음"})

    assert status == 400
    assert body["오류"] == "플레이스 URL이 없습니다. 고객사 정보에 먼저 등록하십시오."
    assert calls == []


def test_collect_failure_returns_502_without_leaking_details(server, monkeypatch):
    def _boom(url, **kw):
        raise RuntimeError(SENSITIVE)

    monkeypatch.setattr(collect, "fetch_place", _boom)
    _post(server, "/api/clients/하루인_인계점", CLIENT)

    status, body = _post_error(server, "/api/collect", {"slug": "하루인_인계점"})

    assert status == 502
    assert "수동" in body["오류"]
    assert SENSITIVE not in json.dumps(body, ensure_ascii=False)


def test_collect_missing_client_returns_404(server, monkeypatch):
    monkeypatch.setattr(collect, "fetch_place", lambda url, **kw: dict(PLACE))
    status, body = _post_error(server, "/api/collect", {"slug": "없는가게"})
    assert status == 404
    assert "오류" in body


def test_collect_missing_slug_returns_400(server):
    status, body = _post_error(server, "/api/collect", {})
    assert status == 400
    assert "오류" in body


@pytest.mark.network
def test_fetch_place_real():
    """실제 네트워크. 평소에는 -m 'not network' 로 건너뛴다."""
    from cmo.lib.collect import fetch_place
    got = fetch_place("https://m.place.naver.com/restaurant/2069074461")
    assert got["매장명"]
    assert got["방문자리뷰"] is None or isinstance(got["방문자리뷰"], int)


@pytest.mark.network
def test_fetch_ranks_real():
    """애드로그 실제 호출. 엔드포인트·필드명 교정 전까지 이걸로만 확인한다."""
    key = api_key_from_env()
    if not key:
        pytest.skip(f"{ADLOG_KEY_ENV} 가 없습니다")
    rows = fetch_ranks(key, "2069074461", ["인계동 삼겹살"])
    assert rows and rows[0]["키워드"] == "인계동 삼겹살"
