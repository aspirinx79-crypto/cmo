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
    append_or_replace_snapshot,
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


# --- 같은 날 애드로그 스냅샷 바꿔 끼우기 --------------------------------

def test_append_or_replace_appends_when_nothing_matches_today():
    client = {"스냅샷": [
        {"수집시각": "2026-09-19T09:00:00", "출처": "애드로그", "순위": []},
    ]}
    새것 = {"수집시각": "2026-09-23T12:00:00", "출처": "애드로그", "순위": []}
    결과 = append_or_replace_snapshot(client, 새것)
    assert len(결과["스냅샷"]) == 2
    assert 결과["스냅샷"][-1] == 새것


def test_append_or_replace_replaces_the_same_day_adlog_snapshot():
    client = {"스냅샷": [
        {"수집시각": "2026-09-23T09:00:00", "출처": "애드로그", "순위": []},
    ]}
    새것 = {"수집시각": "2026-09-23T12:00:00", "출처": "애드로그", "순위": []}
    결과 = append_or_replace_snapshot(client, 새것)
    assert 결과["스냅샷"] == [새것]


def test_append_or_replace_keeps_a_same_day_capture_snapshot():
    """캡처 스냅샷은 출처가 없어 애드로그와 겹쳐도 지워지지 않는다."""
    client = {"스냅샷": [
        {"수집시각": "2026-09-23T09:00:00",
         "순위": [{"키워드": "캡처키워드"}]},
    ]}
    새것 = {"수집시각": "2026-09-23T12:00:00", "출처": "애드로그", "순위": []}
    결과 = append_or_replace_snapshot(client, 새것)
    assert len(결과["스냅샷"]) == 2
    assert 결과["스냅샷"][0]["순위"][0]["키워드"] == "캡처키워드"


def test_append_or_replace_puts_the_new_snapshot_last_even_with_a_capture_between():
    """오전 캡처, 정오 애드로그, 오후 애드로그 갱신 — 최신이 끝에 와야 한다.

    자리를 그대로 바꿔 끼우면(리스트를 거꾸로 훑어 첫 자리를 덮으면)
    새 스냅샷이 캡처보다 앞에 낀다. 그러면 `paintLastSnapshot` 과
    `_latest_snapshot` 이 방금 갱신한 순위 대신 옛 캡처를 읽는다.
    """
    client = {"스냅샷": [
        {"수집시각": "2026-09-23T09:00:00", "출처": "애드로그", "순위": []},
        {"수집시각": "2026-09-23T11:00:00", "순위": []},  # 캡처, 출처 없음
    ]}
    새것 = {"수집시각": "2026-09-23T12:00:00", "출처": "애드로그", "순위": []}
    결과 = append_or_replace_snapshot(client, 새것)
    assert len(결과["스냅샷"]) == 2
    assert 결과["스냅샷"][-1] == 새것


def test_append_or_replace_does_not_mutate_input():
    client = {"스냅샷": [
        {"수집시각": "2026-09-23T09:00:00", "출처": "애드로그", "순위": []},
    ]}
    원본 = json.loads(json.dumps(client, ensure_ascii=False))
    append_or_replace_snapshot(
        client, {"수집시각": "2026-09-23T12:00:00", "출처": "애드로그", "순위": []})
    assert client == 원본


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


def test_merge_keeps_store_metrics_a_later_keyword_did_not_carry():
    """같은 날 뒤에 오는 키워드가 앞 키워드의 매장지표를 지우면 안 된다.

    날짜 단위 통째 교체라, 리뷰수가 빠진 응답이 하나 끼면 그날 매장지표
    전체가 `None` 이 됐다. 순서를 뒤집으면 값이 살아나는 자리다.
    `월검색수`·`경쟁업체수` 가 이미 쓰는 규칙(`None` 으로 안 덮는다)을
    매장지표에도 쓴다 — 값 병합이 아니라 칸 병합이다.
    """
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 22160,
         "경쟁업체수": 2520, "순위": {},
         "매장지표": {"2026-09-23": {"방문자리뷰": 1250, "블로그리뷰": 312,
                                     "저장수": "8,900"}}},
        {"키워드": "잠실 맛집", "api_no": 2, "월검색수": 77000,
         "경쟁업체수": 3100, "순위": {},
         "매장지표": {"2026-09-23": {"방문자리뷰": None, "블로그리뷰": None,
                                     "저장수": None}}},
    ])
    assert 원장["매장지표"]["2026-09-23"] == {
        "방문자리뷰": 1250, "블로그리뷰": 312, "저장수": "8,900"}


def test_merge_keeps_store_metrics_the_new_answer_lost():
    """다시 갱신한 날 응답에서 리뷰수가 빠져도 원장의 그 값은 남는다."""
    첫번 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 22160,
         "경쟁업체수": 2520, "순위": {},
         "매장지표": {"2026-09-23": {"방문자리뷰": 1250, "블로그리뷰": 312,
                                     "저장수": "8,900"}}},
    ])
    두번 = merge_ranks(첫번, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 22160,
         "경쟁업체수": 2520, "순위": {},
         "매장지표": {"2026-09-23": {"방문자리뷰": None, "블로그리뷰": None,
                                     "저장수": "9,100"}}},
    ])
    assert 두번["매장지표"]["2026-09-23"] == {
        "방문자리뷰": 1250, "블로그리뷰": 312, "저장수": "9,100"}


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
    assert set(snap) == {"수집시각", "플레이스", "순위", "순위요약", "예상매출",
                          "진단", "출처"}
    assert snap["예상매출"] is None


LINKED_KW = [
    {"api_no": 2978093, "keyword": "잠실새내 맛집", "month_count": 22160},
    {"api_no": 9, "keyword": "강남역 맛집", "month_count": 92300},
]


def test_snapshot_carries_the_fields_the_proposal_reads():
    """제안서 순위 줄은 다섯 칸을 읽는다 — 키워드·순위·순위권밖·조회수·비교순위.

    둘만 실으면 기회표(_opportunity)와 처방(_moves)이 통째로 빠진다.
    실데이터로 방이점 기회표가 8줄에서 0줄이 되는 걸 확인했다.
    """
    원장 = merge_ranks({}, "2069074461", ROWS)
    줄 = snapshot_from_ranks(원장, LINKED_KW)["순위"][0]
    assert set(줄) == {"키워드", "순위", "순위권밖", "조회수", "비교순위"}


def test_snapshot_reads_view_count_from_the_ledger():
    원장 = merge_ranks({}, "2069074461", ROWS)
    줄 = snapshot_from_ranks(원장, LINKED_KW)["순위"][0]
    assert 줄["조회수"] == 22160


def test_outside_top30_keyword_still_carries_its_view_count():
    """한 번도 안 잡힌 키워드는 애드로그가 2001 로 답해 순위가 없다. 조회수는 연결 정보에서 온다.

    이게 빠지면 「월 92,300번 검색되는 곳에서 아직 안 보입니다」라는
    가장 센 문장을 못 만든다.
    """
    원장 = merge_ranks({}, "2069074461", [
        *ROWS,
        {"키워드": "강남역 맛집", "api_no": 9, "월검색수": None,
         "경쟁업체수": None, "순위": {}, "매장지표": {}},
    ])
    줄별 = {r["키워드"]: r for r in snapshot_from_ranks(원장, LINKED_KW)["순위"]}
    밖 = 줄별["강남역 맛집"]
    assert 밖["순위권밖"] is True
    assert 밖["순위"] is None
    assert 밖["조회수"] == 92300


def test_snapshot_picks_a_comparison_about_thirty_days_back():
    """비교순위가 없으면 처방 장이 빠진다. 원장에 석 달치가 있으니 거기서 고른다."""
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 2978093, "월검색수": 22160,
         "경쟁업체수": 2520,
         "순위": {"2026-09-19": 26, "2026-08-20": 30, "2026-07-01": 55},
         "매장지표": {}},
    ])
    snap = snapshot_from_ranks(원장, LINKED_KW)
    assert snap["순위"][0]["비교순위"] == 30
    assert snap["진단"]["기준일"] == "2026-09-19"
    assert snap["진단"]["비교일"] == "2026-08-20"


def test_snapshot_without_old_dates_has_no_comparison():
    """한 달이 안 쌓인 매장은 비교를 지어내지 않는다."""
    원장 = merge_ranks({}, "2069074461", ROWS)
    assert snapshot_from_ranks(원장, LINKED_KW)["순위"][0]["비교순위"] is None


def test_snapshot_counts_only_linked_keywords():
    """총키워드는 연결된 수다. 원장에 남은 옛 매장 키워드를 세면 안 된다."""
    원장 = merge_ranks({}, "2069074461", [
        *ROWS,
        {"키워드": "남의 키워드", "api_no": 999, "월검색수": 1,
         "경쟁업체수": 1, "순위": {"2026-09-19": 1}, "매장지표": {}},
    ])
    assert snapshot_from_ranks(원장, LINKED_KW)["순위요약"]["총키워드"] == 2
    assert all(r["키워드"] != "남의 키워드"
               for r in snapshot_from_ranks(원장, LINKED_KW)["순위"])


def test_snapshot_marks_its_source():
    """같은 날 두 번 갱신했을 때 바꿔 끼울 자리를 찾는 표다."""
    원장 = merge_ranks({}, "2069074461", ROWS)
    assert snapshot_from_ranks(원장, LINKED_KW)["출처"] == "애드로그"


def test_merge_keeps_old_view_count_when_the_new_one_is_none():
    """2001 로 답한 날 옛 조회수를 None 으로 덮으면 기회표에서 그 줄이 빠진다."""
    첫번 = merge_ranks({}, "2069074461", ROWS)
    두번 = merge_ranks(첫번, "2069074461", [
        {**ROWS[0], "월검색수": None, "경쟁업체수": None, "순위": {}, "매장지표": {}},
    ])
    assert 두번["키워드"]["잠실새내 맛집"]["월검색수"] == 22160


def test_snapshot_without_linked_keywords_falls_back_to_the_ledger():
    """연결 정보를 안 주면 옛 동작 그대로 — 원장의 키워드를 전부 본다."""
    원장 = merge_ranks({}, "2069074461", ROWS)
    assert snapshot_from_ranks(원장)["순위요약"]["총키워드"] == 1


def test_snapshot_stacks_when_every_keyword_is_outside_top30_but_has_a_view_count():
    """신규 매장은 키워드가 대부분 안 잡힌다. 조회수만 있어도 쌓아야
    「월 92,300번 검색되는 곳에서 아직 안 보입니다」를 만들 수 있다.
    순위만 보면 신규 매장일수록 기능이 안 먹는다."""
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "강남역 맛집", "api_no": 9, "월검색수": None,
         "경쟁업체수": None, "순위": {}, "매장지표": {}},
    ])
    snap = snapshot_from_ranks(원장, [
        {"api_no": 9, "keyword": "강남역 맛집", "month_count": 92300},
    ])
    assert snap is not None
    assert snap["순위"][0]["순위권밖"] is True
    assert snap["순위"][0]["조회수"] == 92300


def test_snapshot_of_all_empty_fields_is_still_none():
    """순위도 조회수도 플레이스도 없으면 신규 키워드라도 쌓지 않는다."""
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "강남역 맛집", "api_no": 9, "월검색수": None,
         "경쟁업체수": None, "순위": {}, "매장지표": {}},
    ])
    snap = snapshot_from_ranks(원장, [
        {"api_no": 9, "keyword": "강남역 맛집"},  # month_count 없음
    ])
    assert snap is None


def test_snapshot_diagnosis_dates_span_multiple_linked_keywords():
    """연결 키워드가 여럿이면 기준일·비교일은 그 중 가장 늦은 날짜다.

    한 키워드만 보고 계산하면, 마지막 체크일이 서로 다른 여러 키워드를
    연결했을 때 다른 키워드의 최신 날짜가 묻힌다. 「언제부터 언제까지
    잰 것인가」는 `기준일범위` 가 따로 들고 있다.
    """
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 22160,
         "경쟁업체수": 2520,
         "순위": {"2026-09-19": 26, "2026-08-20": 30}, "매장지표": {}},
        {"키워드": "강남역 맛집", "api_no": 9, "월검색수": 92300,
         "경쟁업체수": 100,
         "순위": {"2026-09-21": 15, "2026-08-15": 20}, "매장지표": {}},
    ])
    연결 = [{"api_no": 1, "keyword": "잠실새내 맛집"},
            {"api_no": 9, "keyword": "강남역 맛집"}]
    snap = snapshot_from_ranks(원장, 연결)
    assert snap["진단"]["기준일"] == "2026-09-21"
    assert snap["진단"]["기준일범위"] == "2026-09-19~2026-09-21"
    assert snap["진단"]["비교일"] == "2026-08-20"


def test_diagnosis_carries_a_span_next_to_the_single_date():
    """가장 늦은 날 하나만 찍으면 묵은 순위가 오늘 것으로 읽힌다.

    A 를 9/1 에, B 를 9/23 에 마지막으로 쟀는데 종이에 「순위 기준
    2026-09-23」이 찍히면 A 의 11위도 그날 잰 것이 된다. 범위를 함께
    실어 검색 장이 그걸 찍는다.

    **범위가 `기준일` 을 대신하면 안 된다.** 처방 장 제목이
    `비교일 → 기준일` 이라, 거기 범위가 들어가면 「8월 20일에서
    9월 1일~9월 23일로」가 된다. 계산용과 표시용을 나눠 둔다.
    """
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 22160,
         "경쟁업체수": 2520, "순위": {"2026-09-01": 11}, "매장지표": {}},
        {"키워드": "강남역 맛집", "api_no": 9, "월검색수": 92300,
         "경쟁업체수": 100, "순위": {"2026-09-23": 3}, "매장지표": {}},
    ])
    연결 = [{"api_no": 1, "keyword": "잠실새내 맛집"},
            {"api_no": 9, "keyword": "강남역 맛집"}]

    진단 = snapshot_from_ranks(원장, 연결)["진단"]
    assert 진단["기준일"] == "2026-09-23"
    assert 진단["기준일범위"] == "2026-09-01~2026-09-23"


def test_diagnosis_has_no_span_when_every_keyword_agrees():
    """같은 날 잰 것들이면 범위를 안 만든다. 읽는 사람만 번거롭다."""
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 1, "월검색수": 22160,
         "경쟁업체수": 2520, "순위": {"2026-09-23": 11}, "매장지표": {}},
        {"키워드": "강남역 맛집", "api_no": 9, "월검색수": 92300,
         "경쟁업체수": 100, "순위": {"2026-09-23": 3}, "매장지표": {}},
    ])
    연결 = [{"api_no": 1, "keyword": "잠실새내 맛집"},
            {"api_no": 9, "keyword": "강남역 맛집"}]

    진단 = snapshot_from_ranks(원장, 연결)["진단"]
    assert 진단["기준일"] == "2026-09-23"
    assert 진단["기준일범위"] is None


def test_a_keyword_that_fell_out_today_is_not_shown_at_its_old_rank():
    """오늘 답이 왔는데 순위가 없으면 안 잡힌 것이다. 며칠 전 순위를 오늘 것으로 싣지 않는다.

    `series()` 가 순위 `None` 인 날을 일부러 남겨 두는 이유가 이것이다.
    9/24 에 밀려난 키워드를 9/24 자 종이에 「3위」로 찍으면, 사장님께
    하는 그 말이 사실이 아니다. TOP 3 에도 한 개로 센다.
    """
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 2978093, "월검색수": 22160,
         "경쟁업체수": 2520,
         "순위": {"2026-09-20": 3, "2026-09-24": None}, "매장지표": {}},
    ])
    snap = snapshot_from_ranks(원장, LINKED_KW[:1])

    줄 = snap["순위"][0]
    assert 줄["순위"] is None
    assert 줄["순위권밖"] is True
    assert snap["순위요약"]["TOP3"] == 0
    assert snap["진단"]["기준일"] == "2026-09-24"


def test_a_keyword_that_fell_out_today_compares_from_today():
    """한 달 전 5위에서 오늘 밀려났다 — 처방 장의 「내림」이 그 이야기다.

    비교 대상은 순위가 남은 마지막 날이 아니라 **답을 받은 마지막 날**에서
    30 일을 거슬러 센다. 앞의 날로 세면 비교가 그만큼씩 밀린다.
    """
    원장 = merge_ranks({}, "2069074461", [
        {"키워드": "잠실새내 맛집", "api_no": 2978093, "월검색수": 22160,
         "경쟁업체수": 2520,
         "순위": {"2026-08-25": 5, "2026-09-20": 3, "2026-09-24": None},
         "매장지표": {}},
    ])
    snap = snapshot_from_ranks(원장, LINKED_KW[:1])

    assert snap["순위"][0]["비교순위"] == 5
    assert snap["진단"]["비교일"] == "2026-08-25"


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
