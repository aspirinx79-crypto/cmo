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
    append_snapshot,
    make_snapshot,
    merge_ranks,
    parse_place_counts,
    snapshot_from_ranks,
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


# --- 순위 원장 --------------------------------------------------------

ROWS = [
    {"키워드": "잠실새내 맛집", "api_no": 2978093, "월검색수": 22160,
     "경쟁업체수": 2520, "순위": {"2026-09-19": 26, "2026-09-18": 27},
     "매장지표": {"2026-09-19": {"방문자리뷰": 895, "블로그리뷰": 619,
                                 "저장수": "8,000+"}}},
]


def test_merge_ranks_into_an_empty_ledger():
    원장 = merge_ranks({}, "2069074461", ROWS)
    assert 원장["플레이스ID"] == "2069074461"
    assert 원장["키워드"]["잠실새내 맛집"]["순위"] == {"2026-09-19": 26,
                                                      "2026-09-18": 27}


def test_merge_ranks_records_when_it_ran():
    assert merge_ranks({}, "2069074461", ROWS)["갱신시각"]


def test_merge_ranks_is_idempotent():
    """같은 날을 두 번 넣어도 한 벌이다. 이게 빈 스냅샷이 쌓이던 자리다."""
    한번 = merge_ranks({}, "2069074461", ROWS)
    두번 = merge_ranks(한번, "2069074461", ROWS)
    assert 두번["키워드"]["잠실새내 맛집"]["순위"] == {"2026-09-19": 26,
                                                      "2026-09-18": 27}
    assert len(두번["매장지표"]) == 1


def test_merge_ranks_keeps_older_dates():
    """새 갱신이 지난 날짜를 지우면 성과의 증거가 사라진다."""
    옛날 = merge_ranks({}, "2069074461", [
        {**ROWS[0], "순위": {"2026-08-01": 40}, "매장지표": {}}])
    새것 = merge_ranks(옛날, "2069074461", ROWS)
    순위 = 새것["키워드"]["잠실새내 맛집"]["순위"]
    assert 순위["2026-08-01"] == 40
    assert 순위["2026-09-19"] == 26


def test_merge_ranks_does_not_touch_the_original():
    원본 = merge_ranks({}, "2069074461", ROWS)
    복사 = json.loads(json.dumps(원본, ensure_ascii=False))
    merge_ranks(원본, "2069074461", [
        {**ROWS[0], "순위": {"2026-09-20": 25}, "매장지표": {}}])
    assert 원본 == 복사


def test_merge_ranks_keeps_save_count_verbatim():
    원장 = merge_ranks({}, "2069074461", ROWS)
    assert 원장["매장지표"]["2026-09-19"]["저장수"] == "8,000+"


# --- 스냅샷 파생 ------------------------------------------------------

def test_snapshot_takes_the_latest_rank_per_keyword():
    """키워드마다 마지막 체크일이 다르다. 한 날짜로 못 자른다."""
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 100,
         "경쟁업체수": 10, "순위": {"2026-09-19": 26}, "매장지표": {}},
        {"키워드": "잠실 맛집", "api_no": 2, "월검색수": 200,
         "경쟁업체수": 20, "순위": {"2026-09-17": 59}, "매장지표": {}},
    ])
    순위 = {r["키워드"]: r["순위"] for r in snapshot_from_ranks(원장)["순위"]}
    assert 순위 == {"잠실새내 맛집": 26, "잠실 맛집": 59}


def test_snapshot_counts_tops():
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "가", "api_no": 1, "월검색수": 1, "경쟁업체수": 1,
         "순위": {"2026-09-19": 2}, "매장지표": {}},
        {"키워드": "나", "api_no": 2, "월검색수": 1, "경쟁업체수": 1,
         "순위": {"2026-09-19": 9}, "매장지표": {}},
        {"키워드": "다", "api_no": 3, "월검색수": 1, "경쟁업체수": 1,
         "순위": {"2026-09-19": 40}, "매장지표": {}},
    ])
    assert snapshot_from_ranks(원장)["순위요약"] == {"총키워드": 3, "TOP3": 1,
                                                    "TOP10": 2}


def test_snapshot_folds_save_count_into_a_number():
    """proposal 이 int() 로 찍는다. 문자열이 그대로 가면 제안서가 터진다."""
    원장 = merge_ranks({}, "2069074461", ROWS)
    assert snapshot_from_ranks(원장)["플레이스"]["저장수"] == 8000


def test_snapshot_carries_reviews():
    snap = snapshot_from_ranks(merge_ranks({}, "2069074461", ROWS))
    assert snap["플레이스"]["방문자리뷰"] == 895
    assert snap["플레이스"]["블로그리뷰"] == 619


def test_snapshot_of_an_empty_ledger_is_none():
    """값이 없으면 안 쌓는다. 수집시각만 든 스냅샷은 증거가 아니라 잡음이다."""
    assert snapshot_from_ranks({}) is None
    assert snapshot_from_ranks({"플레이스ID": "1", "키워드": {}}) is None


def test_snapshot_keeps_the_shape_the_proposal_reads():
    """제안서가 읽는 네 칸이 그대로 있어야 한다."""
    snap = snapshot_from_ranks(merge_ranks({}, "2069074461", ROWS))
    assert set(snap) == {"수집시각", "플레이스", "순위", "순위요약", "예상매출"}
    assert snap["예상매출"] is None


# --- 누출 차단 --------------------------------------------------------

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
    assert "플레이스 URL이 없습니다" in body["오류"]
    assert "플레이스 함께 수집" in body["오류"]
    assert calls == []


def test_collect_failure_returns_502_without_leaking_details(server, monkeypatch):
    def _boom(url, **kw):
        raise RuntimeError(SENSITIVE)

    monkeypatch.setattr(collect, "fetch_place", _boom)
    _post(server, "/api/clients/하루인_인계점", CLIENT)

    status, body = _post_error(server, "/api/collect", {"slug": "하루인_인계점"})

    assert status == 502
    assert "플레이스 함께 수집" in body["오류"]
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
