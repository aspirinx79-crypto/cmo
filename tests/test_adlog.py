"""애드로그 OpenAPI 층 테스트.

애드로그는 실패를 HTTP 로 알리지 않는다. 200 을 주고 본문 `code` 에
적는다. 그래서 검사의 절반이 `code` 분기다.

네트워크를 타는 건 network 마커로 분리한다 — 평소 스위트는
`-m "not network"` 로 돈다.
"""
import pytest

from cmo.lib.adlog import (DETAIL, LIST, NO_DATA, OK, AdlogError, as_int,
                           metrics_by_date, series)

# 애드로그 순위 조회가 실제로 돌려준 모양. 필드 이름을 여기서 박아 둔다.
DETAIL_ITEMS = [
    {"api_no": 3022620, "rank_date": "2026-09-19", "rank_num": 3,
     "blog_review_count": 619, "visit_review_count": 895,
     "save_count": "8,000+", "newopen": 0, "pc_month_count": 180,
     "mo_month_count": 1900, "total_month_count": 2080, "place_count": 227,
     "place_n1": "0.000000", "place_n2": "0.000000", "place_n3": "0.000000"},
    {"api_no": 3022620, "rank_date": "2026-09-18", "rank_num": 4,
     "blog_review_count": 619, "visit_review_count": 895,
     "save_count": "8,000+", "newopen": 0, "pc_month_count": 180,
     "mo_month_count": 1930, "total_month_count": 2110, "place_count": 227,
     "place_n1": "0.000000", "place_n2": "0.000000", "place_n3": "0.000000"},
]


# --- 숫자 읽기 -------------------------------------------------------

def test_as_int_strips_commas_and_plus():
    """저장수는 `"8,000+"` 로 온다. proposal 이 int() 로 찍어서 그대로 두면 터진다."""
    assert as_int("8,000+") == 8000


def test_as_int_passes_numbers_through():
    assert as_int(895) == 895


def test_as_int_returns_none_when_unreadable():
    for 값 in (None, "", "—", "정보없음"):
        assert as_int(값) is None, f"{값!r} 에서 None 이 아니다"


# --- 일자별 순위 -----------------------------------------------------

def test_series_maps_date_to_rank():
    assert series(DETAIL_ITEMS) == {"2026-09-19": 3, "2026-09-18": 4}


def test_series_skips_rows_without_a_date():
    """날짜가 없으면 원장에 넣을 자리가 없다. 조용히 버린다."""
    assert series([{"rank_num": 3}, *DETAIL_ITEMS]) == {
        "2026-09-19": 3, "2026-09-18": 4}


def test_series_keeps_none_rank():
    """순위가 비는 날이 있다. 그 날짜를 지우면 '못 봤다'가 '없었다'가 된다."""
    assert series([{"rank_date": "2026-09-17", "rank_num": None}]) == {
        "2026-09-17": None}


def test_series_of_nothing_is_empty():
    assert series([]) == {}


# --- 날짜별 매장 지표 ------------------------------------------------

def test_metrics_by_date_reads_reviews_and_saves():
    got = metrics_by_date(DETAIL_ITEMS)
    assert got["2026-09-19"] == {"방문자리뷰": 895, "블로그리뷰": 619,
                                 "저장수": "8,000+", "경쟁업체수": 227,
                                 "월검색수": 2080}


def test_metrics_by_date_keeps_save_count_verbatim():
    """원장에는 원문을 둔다 — 8000 으로 적으면 '이상'이 사라진다."""
    assert metrics_by_date(DETAIL_ITEMS)["2026-09-19"]["저장수"] == "8,000+"


# --- 에러 ------------------------------------------------------------

def test_adlog_error_is_an_exception():
    with pytest.raises(AdlogError):
        raise AdlogError("애드로그 계정 정보를 확인하십시오.")


def test_codes_are_strings_not_numbers():
    """애드로그는 `"0000"` 을 준다. 0 으로 비교하면 영원히 안 맞는다."""
    assert OK == "0000"
    assert NO_DATA == "2001"


def test_endpoints_are_https():
    """Bearer 키를 헤더에 싣는다. 평문이면 그대로 읽힌다."""
    assert LIST.startswith("https://")
    assert DETAIL.startswith("https://")


# --- 호출 -------------------------------------------------------------

import io
import json as _json

from cmo.lib import adlog


class FakeResponse(io.BytesIO):
    """urlopen 이 돌려주는 것처럼 굴되 컨텍스트 매니저로 쓰인다."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def fake_urlopen(payloads):
    """호출할 때마다 payloads 를 하나씩 돌려준다. 보낸 요청도 모아 둔다."""
    sent = []

    def _open(req, timeout=None):
        sent.append(req)
        body = payloads[len(sent) - 1] if len(sent) <= len(payloads) else payloads[-1]
        return FakeResponse(_json.dumps(body).encode("utf-8"))

    _open.sent = sent
    return _open


LIST_PAGE = {"code": "0000", "msg": "성공", "total_count": "2", "page": 1,
             "items": [{"api_no": 1, "place_id": "2069074461",
                        "place_name": "미친양꼬치 잠실점", "keyword": "잠실새내 맛집",
                        "month_count": 22160, "group_name": "기본"},
                       {"api_no": 2, "place_id": "2069074461",
                        "place_name": "미친양꼬치 잠실점", "keyword": "잠실 맛집",
                        "month_count": 77000, "group_name": "기본"}]}


def test_credentials_reads_both_from_env(monkeypatch):
    monkeypatch.setenv(adlog.KEY_ENV, "  키값  ")
    monkeypatch.setenv(adlog.USER_ENV, "  테스트아이디  ")
    assert adlog.credentials() == ("키값", "테스트아이디")


def test_credentials_is_none_when_either_is_missing(monkeypatch, capsys):
    """키만 있고 아이디가 없으면 부를 수가 없다. 조용히 건너뛴다."""
    monkeypatch.setenv(adlog.KEY_ENV, "키값")
    monkeypatch.delenv(adlog.USER_ENV, raising=False)
    assert adlog.credentials() is None
    assert adlog.USER_ENV in capsys.readouterr().err


def test_keywords_sends_key_in_header_and_menu_in_body(monkeypatch):
    opener = fake_urlopen([LIST_PAGE])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    adlog.keywords("키값", "테스트아이디")

    req = opener.sent[0]
    assert req.full_url == adlog.LIST
    assert req.get_header("Authorization") == "Bearer 키값"
    body = _json.loads(req.data.decode("utf-8"))
    assert body["user_id"] == "테스트아이디"
    assert body["api_menu"] == adlog.PLACE_MENU


def test_keywords_stops_when_total_is_reached(monkeypatch):
    """total_count 를 채우면 멈춘다. 안 그러면 같은 페이지를 영원히 돈다."""
    opener = fake_urlopen([LIST_PAGE])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    got = adlog.keywords("키값", "테스트아이디", sleep=0)

    assert len(got) == 2
    assert len(opener.sent) == 1


def test_keywords_walks_pages(monkeypatch):
    page1 = {**LIST_PAGE, "total_count": "4", "page": 1}
    page2 = {**LIST_PAGE, "total_count": "4", "page": 2,
             "items": [{"api_no": 3, "place_id": "2079228615",
                        "place_name": "미친양꼬치 방이점", "keyword": "방이동 맛집",
                        "month_count": 29740, "group_name": "기본"},
                       {"api_no": 4, "place_id": "2079228615",
                        "place_name": "미친양꼬치 방이점", "keyword": "방이 맛집",
                        "month_count": 1000, "group_name": "기본"}]}
    opener = fake_urlopen([page1, page2])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    got = adlog.keywords("키값", "테스트아이디", sleep=0)

    assert len(got) == 4
    assert _json.loads(opener.sent[1].data.decode("utf-8"))["page"] == 2


def test_keywords_raises_a_human_phrase_on_auth_failure(monkeypatch):
    opener = fake_urlopen([{"code": "4002", "msg": "API 접근정보를 확인해주세요."}])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    with pytest.raises(AdlogError) as caught:
        adlog.keywords("틀린키", "테스트아이디", sleep=0)
    assert str(caught.value) == "애드로그 계정 정보를 확인하십시오."


def test_keywords_raises_fallback_on_unknown_code(monkeypatch):
    opener = fake_urlopen([{"code": "9999", "msg": "모르는 코드"}])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    with pytest.raises(AdlogError) as caught:
        adlog.keywords("키값", "테스트아이디", sleep=0)
    assert str(caught.value) == adlog.FALLBACK


def test_keywords_treats_no_data_as_empty(monkeypatch):
    """2001 은 실패가 아니다. 아직 아무것도 안 등록한 계정이다."""
    opener = fake_urlopen([{"code": "2001", "msg": "데이터가 존재하지 않습니다."}])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    assert adlog.keywords("키값", "테스트아이디", sleep=0) == []


def test_ranks_sends_api_no(monkeypatch):
    opener = fake_urlopen([{"code": "0000", "msg": "성공", "items": DETAIL_ITEMS}])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    got = adlog.ranks("키값", "테스트아이디", 3022620)

    assert got == DETAIL_ITEMS
    assert opener.sent[0].full_url == adlog.DETAIL
    assert _json.loads(opener.sent[0].data.decode("utf-8"))["api_no"] == 3022620


def test_ranks_of_a_new_keyword_is_empty(monkeypatch):
    """등록은 됐는데 아직 순위가 안 잡힌 키워드가 있다. 빈 목록이다."""
    opener = fake_urlopen([{"code": "2001", "msg": "데이터가 존재하지 않습니다."}])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)

    assert adlog.ranks("키값", "테스트아이디", 999) == []


def test_calls_refuse_plain_http_before_touching_network(monkeypatch):
    """Bearer 키를 싣기 때문에 http 는 곧 키 유출이다. 네트워크 전에 끊는다."""
    monkeypatch.setattr(adlog, "LIST", "http://api.adlog.kr/api/getKeywordList.php")

    def boom(*args, **kwargs):
        raise AssertionError("네트워크를 탔다")

    monkeypatch.setattr(adlog.urllib.request, "urlopen", boom)

    with pytest.raises(ValueError):
        adlog.keywords("키값", "테스트아이디", sleep=0)


# --- 재시도 -----------------------------------------------------------
#
# 953 건짜리 계정에서 목록을 다 읽으려면 페이지를 스무 번 넘게 넘긴다.
# 애드로그는 이따금 한 페이지를 20 초 넘게 붙들고 끊는다 — 세 번
# 재현했다. 한 번만 걸려도 전체가 무너지므로 느려서 끊긴 요청만
# 다시 문다.

def test_retries_after_a_timeout_then_succeeds(monkeypatch):
    """첫 호출이 느려서 끊겨도 둘째에서 받으면 정상 결과가 돌아온다."""
    sent = []

    def _open(req, timeout=None):
        sent.append(req)
        if len(sent) == 1:
            raise TimeoutError("The read operation timed out")
        return FakeResponse(_json.dumps(LIST_PAGE).encode("utf-8"))

    monkeypatch.setattr(adlog.urllib.request, "urlopen", _open)
    monkeypatch.setattr(adlog.time, "sleep", lambda *_: None)

    got = adlog.keywords("키값", "테스트아이디", sleep=0)

    assert len(got) == 2
    assert len(sent) == 2


def test_gives_up_after_exhausting_retries(monkeypatch):
    """세 번 다 끊기면 TimeoutError 를 그대로 올린다. 삼키면 '못 받았다'가 '없다'가 된다."""
    sent = []

    def _open(req, timeout=None):
        sent.append(req)
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(adlog.urllib.request, "urlopen", _open)
    monkeypatch.setattr(adlog.time, "sleep", lambda *_: None)

    with pytest.raises(TimeoutError):
        adlog.keywords("키값", "테스트아이디", sleep=0)
    assert len(sent) == 3


def test_does_not_retry_an_adlog_error(monkeypatch):
    """애드로그가 code 로 명확히 거절한 응답은 다시 묻지 않는다. 물어도 같은 답이다."""
    opener = fake_urlopen([{"code": "4002", "msg": "API 접근정보를 확인해주세요."}])
    monkeypatch.setattr(adlog.urllib.request, "urlopen", opener)
    monkeypatch.setattr(adlog.time, "sleep", lambda *_: None)

    with pytest.raises(AdlogError):
        adlog.keywords("키값", "테스트아이디", sleep=0)
    assert len(opener.sent) == 1


def test_env_example_names_both_keys_without_values(cmo_dir):
    """.env.example 에는 이름만 둔다. 값이 붙는 순간 키가 저장소에 올라간다.

    `tests/test_collect.py` 에서 옮겨 왔다. 애드로그 키가 `adlog.py` 로
    갔고, 이제 아이디까지 둘이라 둘 다 본다.
    """
    path = cmo_dir / ".env.example"
    assert path.exists(), ".env.example 이 없다"
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    assert f"{adlog.KEY_ENV}=" in lines
    assert f"{adlog.USER_ENV}=" in lines
    for line in lines:
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        assert value == "", f"{name} 에 값이 붙어 있다"


@pytest.mark.network
def test_real_call_lists_keywords():
    """실제 애드로그를 한 번 친다. 평소 스위트에서는 빠진다."""
    creds = adlog.credentials()
    if not creds:
        pytest.skip(f"{adlog.KEY_ENV}/{adlog.USER_ENV} 가 없습니다")
    got = adlog.keywords(*creds)
    assert got, "등록된 키워드가 한 건도 없다"
    assert "place_id" in got[0]
