import json

import pytest

from cmo.lib.proposal import FORBIDDEN_KEYS, ProposalBlocked, build_payload

PRODUCTS = [
    {"id": "네이버-블로그_일반_체험단", "매체": "네이버", "상품명": "블로그 일반 체험단",
     "가격유형": "고정", "정가": 30000, "실비": 8000, "최소수량": 5, "단위": "팀",
     "고지사항": "방문형 5팀 이상 / 공정위 문구 고지", "판매중지": False,
     "프로세스": "양식 받기->5-7일 모집/14-20일 체험,포스팅/2영업일 후 보고서"},
    {"id": "네이버-서비스툴관리", "매체": "네이버", "상품명": "서비스툴관리",
     "가격유형": "고정", "정가": 300000, "실비": 0, "최소수량": 1, "단위": "개월",
     "고지사항": "", "판매중지": False, "프로세스": "단톡방 소통"},
    {"id": "네이버-플레이스_트래픽", "매체": "네이버", "상품명": "플레이스 트래픽",
     "가격유형": "직접입력", "정가": None, "실비": None, "최소수량": 1, "단위": "건",
     "고지사항": "상위노출 보장은 아니란거 고지", "판매중지": False, "프로세스": ""},
]
CLIENT = {
    "이름": "하루인 인계점", "업종": "고깃집", "지역": "수원 인계동",
    "평수": 60, "객단가": 18000,
    "스냅샷": [{"수집시각": "2026-08-01T09:00:00",
              "플레이스": {"방문자리뷰": 312, "블로그리뷰": 14},
              "순위": [{"키워드": "인계동 삼겹살", "순위": 17}],
              "예상매출": {"월매출": 42000000, "상권순위": "상위 40%"}}],
}
PLAN = {
    "월": "2026-09", "계약가": 1000000, "진단메모": "블로그 리뷰가 14건뿐입니다.",
    "항목": [
        {"상품id": "네이버-블로그_일반_체험단", "수량": 10},
        {"상품id": "네이버-서비스툴관리", "수량": 1},
        {"상품id": "네이버-플레이스_트래픽", "정가": 900000, "실비": 400000},
    ],
}


def test_payload_has_no_cost_keys_anywhere():
    """실비가 payload 어디에도 없어야 한다. 숨기는 게 아니라 없다."""
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    blob = json.dumps(payload, ensure_ascii=False)
    for key in FORBIDDEN_KEYS:
        assert key not in blob, f"제안서 payload 에 '{key}' 가 들어 있다"


def test_payload_does_not_leak_cost_values():
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    blob = json.dumps(payload, ensure_ascii=False)
    for value in ("8000", "400000", "80,000", "400,000"):
        assert value not in blob, f"실비 금액 {value} 가 새어 나갔다"


def test_payload_lists_every_line_with_list_price():
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    assert len(payload["구성"]) == 3
    blog = next(c for c in payload["구성"] if c["상품명"] == "블로그 일반 체험단")
    assert blog["정가"] == 300000
    assert blog["수량표시"] == "10팀"


def test_payload_totals_and_multiplier_wording():
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    assert payload["정가합"] == 1500000
    assert payload["계약가"] == 1000000
    assert "1.5배" in payload["혜택배율문구"]
    assert "1,500,000" in payload["혜택배율문구"]
    assert "1,000,000" in payload["혜택배율문구"]


def test_payload_collects_notices_without_duplicates():
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    notices = payload["고지사항"]
    assert any("공정위" in n for n in notices)
    assert any("보장은 아니" in n for n in notices)
    assert len(notices) == len(set(notices))


def test_payload_includes_weekly_schedule():
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    assert [w["주차"] for w in payload["일정"]] == [1, 2, 3, 4]
    assert any("모집" in line for line in payload["일정"][0]["항목"])


def test_payload_metrics_use_rank_and_reviews():
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    assert payload["지표"]["블로그리뷰"] == 14
    assert payload["지표"]["순위"][0]["키워드"] == "인계동 삼겹살"


def test_payload_omits_absolute_revenue_by_default():
    """오픈업 추정 매출의 절대금액은 기본 서식에 싣지 않는다."""
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    blob = json.dumps(payload, ensure_ascii=False)
    assert "42000000" not in blob and "4,200" not in blob
    assert payload["지표"]["상권순위"] == "상위 40%"


def test_payload_carries_differentiators():
    """차별점 카피에 두 가지 요지가 살아 있는지만 본다: (1) 주간 보고 주기
    — 브리프 원문 카피는 "매주" 라는 표기를 쓰므로 "주간" 이 아니라 "매주" 를
    찾는다 (표기가 아니라 의도를 검사), (2) 다음 달로 이어가는 개선 사이클."""
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    joined = " ".join(payload["차별점"])
    assert "매주" in joined and "다음 달" in joined


def test_blocked_when_manual_price_missing():
    plan = {**PLAN, "항목": [{"상품id": "네이버-플레이스_트래픽", "실비": 400000}]}
    with pytest.raises(ProposalBlocked, match="플레이스 트래픽"):
        build_payload(CLIENT, plan, PRODUCTS)


def test_client_without_snapshot_still_builds():
    payload = build_payload({**CLIENT, "스냅샷": []}, PLAN, PRODUCTS)
    assert payload["지표"]["블로그리뷰"] is None
