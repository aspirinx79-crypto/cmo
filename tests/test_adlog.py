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
