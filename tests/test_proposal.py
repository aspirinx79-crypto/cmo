import copy
import json

import pytest

from cmo.lib import proposal
from cmo.lib.proposal import (
    FORBIDDEN_KEYS,
    INTERNAL_STEP_WORDS,
    ProposalBlocked,
    build_payload,
)
from cmo.lib.schedule import weekly_plan

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


# --- 일정표의 내부 문구 걸러내기 ---
# 실제로 만든 PDF 의 고객용 일정표에 "언론송출 — 컨펌된 원고 및 사진 김대한
# 대표에게 전달", "SA — 상위대행사 이관", "리뷰작업 — 실장님께 알바풀 전달"
# 같은 줄이 그대로 실려 나갔다. 사장님에게 우리 내부 사람 이름·단톡방·외주
# 구조를 보여주는 문서가 됐다.

# products.json 원문에서 그대로 가져온, 실제로 새어 나갔던 프로세스들.
LEAKY_PRODUCTS = [
    {"id": "포털-언론송출", "매체": "포털", "상품명": "언론송출",
     "가격유형": "고정", "정가": 150000, "실비": 100000, "최소수량": 1, "단위": "건",
     "고지사항": "", "판매중지": False,
     "프로세스": "컨펌된 원고 및 사진 김대한 대표에게 전달"},
    {"id": "네이버-서비스툴관리", "매체": "네이버", "상품명": "서비스툴관리",
     "가격유형": "고정", "정가": 300000, "실비": 0, "최소수량": 1, "단위": "개월",
     "고지사항": "", "판매중지": False, "프로세스": "단톡방 소통"},
    {"id": "네이버-SA", "매체": "네이버", "상품명": "SA",
     "가격유형": "고정", "정가": 500000, "실비": 300000, "최소수량": 1, "단위": "개월",
     "고지사항": "", "판매중지": False,
     "프로세스": "상위대행사 이관->소재 세팅->통계보며 보고 및 피드백->관리"},
    {"id": "해외-중국_체험단", "매체": "해외", "상품명": "중국 체험단",
     "가격유형": "고정", "정가": 400000, "실비": 250000, "최소수량": 1, "단위": "건",
     "고지사항": "", "판매중지": False, "프로세스": "레뷰차이나측 소통"},
    {"id": "구글-리뷰작업", "매체": "구글", "상품명": "리뷰작업",
     "가격유형": "고정", "정가": 200000, "실비": 120000, "최소수량": 1, "단위": "건",
     "고지사항": "", "판매중지": False, "프로세스": "실장님께 알바풀 전달"},
    {"id": "네이버-플레이스_상위노출_일_보장", "매체": "네이버",
     "상품명": "플레이스 상위노출 일 보장",
     "가격유형": "고정", "정가": 600000, "실비": 400000, "최소수량": 1, "단위": "일",
     "고지사항": "", "판매중지": False, "프로세스": "홍인표이사와 소통"},
    # 고객이 체감하는 단계만으로 이루어진 상품 — 필터가 이걸 건드리면 안 된다.
    {"id": "네이버-블로그_일반_체험단", "매체": "네이버", "상품명": "블로그 일반 체험단",
     "가격유형": "고정", "정가": 30000, "실비": 8000, "최소수량": 5, "단위": "팀",
     "고지사항": "", "판매중지": False,
     "프로세스": ("클라이언트에게 양식 받기->5-7일 모집/1일 선정/1일 명단발표/"
                "14-20일 체험,포스팅/ 2영업일 후 보고서")},
]
LEAKY_PLAN = {
    "월": "2026-09", "계약가": 1000000, "진단메모": "",
    "항목": [{"상품id": p["id"], "수량": 1} for p in LEAKY_PRODUCTS],
}


def _schedule_blob(payload: dict) -> str:
    return json.dumps(payload["일정"], ensure_ascii=False)


def test_schedule_drops_internal_wording():
    """제안서 일정표 어디에도 직함·단톡방·외주 구조가 남으면 안 된다."""
    payload = build_payload(CLIENT, LEAKY_PLAN, LEAKY_PRODUCTS)
    blob = _schedule_blob(payload)
    for word in INTERNAL_STEP_WORDS:
        assert word not in blob, f"제안서 일정표에 내부 문구 '{word}' 가 남아 있다"
    for phrase in ("김대한", "홍인표", "상위대행사 이관", "알바풀", "레뷰차이나"):
        assert phrase not in blob, f"제안서 일정표에 '{phrase}' 가 남아 있다"


def test_schedule_keeps_client_facing_steps():
    """거르는 김에 고객이 봐야 할 단계까지 지우면 일정표가 빈 종이가 된다."""
    payload = build_payload(CLIENT, LEAKY_PLAN, LEAKY_PRODUCTS)
    blob = _schedule_blob(payload)
    for word in ("모집", "선정", "명단발표", "체험", "포스팅", "보고서", "세팅"):
        assert word in blob, f"고객이 봐야 하는 단계 '{word}' 가 걸러졌다"


def test_weekly_plan_still_returns_the_raw_process_wording():
    """구성판 내부 화면은 프로세스 원문을 그대로 봐야 한다 — 상무님은 실제
    진행 절차를 다 봐야 하기 때문이다. 필터를 schedule.weekly_plan() 안으로
    옮기면 여기서 잡힌다."""
    raw = json.dumps(weekly_plan(LEAKY_PRODUCTS, LEAKY_PLAN["항목"]),
                     ensure_ascii=False)
    assert "김대한 대표에게 전달" in raw
    assert "단톡방 소통" in raw
    assert "상위대행사 이관" in raw
    assert "실장님께 알바풀 전달" in raw


def test_schedule_filter_does_not_mutate_what_weekly_plan_returned(monkeypatch):
    """필터가 받은 리스트를 제자리에서 고치면, 같은 반환값을 내부 화면과
    나눠 쓰는 호출자가 생기는 날 조용히 원문을 잃는다. 사본을 만들어야 한다.

    weekly_plan 은 호출할 때마다 새 리스트를 만들기 때문에 그냥 두 번 불러
    비교하면 무엇을 해도 통과한다(공허하다). build_payload 가 실제로 받는
    바로 그 객체를 쥐고 확인한다."""
    handed = weekly_plan(LEAKY_PRODUCTS, LEAKY_PLAN["항목"])
    original = copy.deepcopy(handed)
    monkeypatch.setattr(proposal, "weekly_plan", lambda *a, **k: handed)

    payload = build_payload(CLIENT, LEAKY_PLAN, LEAKY_PRODUCTS)

    assert handed == original, "build_payload 가 weekly_plan 의 반환값을 제자리에서 고쳤다"
    assert "김대한" not in _schedule_blob(payload)


def _item_for(product: dict) -> dict:
    """실제 상품 하나를 기획안 항목 한 줄로 만든다 (가격유형별 최소 입력)."""
    item = {"상품id": product["id"], "수량": 1, "예산": 1000000, "정가": 100000}
    grades = product.get("등급") or []
    if grades:
        item["등급"] = grades[0]["이름"]
    return item


def test_no_internal_wording_across_every_real_product(products):
    """products.json 의 상품 전부를 한 기획안에 담아도 일정표가 깨끗해야 한다.
    시트가 손편집이라 새 프로세스 문구가 언제든 들어온다."""
    plan = {"월": "2026-09", "계약가": 1000000, "진단메모": "",
            "항목": [_item_for(p) for p in products]}
    payload = build_payload(CLIENT, plan, products)
    blob = _schedule_blob(payload)
    for word in INTERNAL_STEP_WORDS:
        assert word not in blob, f"제안서 일정표에 내부 문구 '{word}' 가 남아 있다"


# --- 목록 조정 (수정 라운드 2) ---
# `소통`·`전달` 을 뺐다. 진짜 유출 줄은 전부 다른 단어에도 걸려 이 둘이 막고
# 있는 게 없는데, 대신 고객에게 보여줘야 할 줄을 죽이고 있었다.
# `입금요청` 을 넣었다. 유출이라서가 아니라 문서 격 때문이다.

def _schedule_of(products: list[dict], *ids: str) -> list[dict]:
    """실제 카탈로그에서 상품 몇 개만 골라 기획안을 만들고 고객용 일정표를 낸다."""
    chosen = [p for p in products if p["id"] in ids]
    assert len(chosen) == len(ids), f"카탈로그에 없는 id 가 있다: {ids}"
    plan = {"월": "2026-09", "계약가": 1000000, "진단메모": "",
            "항목": [_item_for(p) for p in chosen]}
    return build_payload(CLIENT, plan, products)["일정"]


def _lines(weeks: list[dict]) -> list[str]:
    return [line for week in weeks for line in week["항목"]]


def test_client_facing_communication_and_shooting_survive(products):
    """`클라이언트 소통 및 디자인 컨펌` 은 고객'과의' 소통이라 오히려 보여줄
    약속이고, `유튜버 전달 및 촬영` 은 카탈로그에서 `촬영` 이 든 유일한 줄이다.
    `소통`·`전달` 로 겹쳐 막느라 이 둘을 죽이면 안 된다."""
    lines = _lines(_schedule_of(products, "네이버-카페_월_배너광고", "유튜브-유튜버_PPL"))
    assert any("클라이언트 소통 및 디자인 컨펌" in line for line in lines)
    assert any("촬영" in line for line in lines), "카탈로그에서 촬영이 통째로 사라졌다"
    # 같은 상품의 진짜 유출 줄은 여전히 막힌다 — 필터를 통째로 푼 게 아니다.
    assert not any("대행가" in line for line in lines)


def test_payment_request_step_is_dropped(products):
    """제안서의 실행 일정 마지막 줄이 '입금요청' 이면 안 된다."""
    lines = _lines(_schedule_of(products, "IMC-CMO_서비스"))
    assert not any("입금요청" in line for line in lines)
    assert any("예산 선정" in line for line in lines)
    assert any("월별 관리" in line for line in lines)


# --- 단계가 전부 걸린 상품의 대체 줄 (수정 라운드 2) ---
# 프로세스가 한 줄뿐이고 그 한 줄이 내부 문구인 상품이 16개다. 그런 상품만
# 판 달은 제안서 일정 쪽이 빈 종이가 됐다. 돈을 냈는데 일정표에 자기가 산 게
# 안 보이면 안 된다. 내부 절차는 감추되 "이 상품이 이 달에 돌아간다" 는
# 사실은 남긴다.

def test_fully_filtered_product_shows_a_progress_line(products):
    """`네이버-서비스툴관리` 는 프로세스가 "단톡방 소통" 한 줄이라 전부 걸린다."""
    lines = _lines(_schedule_of(products, "네이버-서비스툴관리"))
    assert lines == ["서비스툴관리 — 진행"], f"기대와 다르다: {lines}"


def test_progress_line_sits_in_the_week_the_first_step_was_in(products):
    """대체 줄은 아무 데나가 아니라 그 상품의 첫 단계가 놓였을 주차에 들어간다.
    4주에 걸치는 상품과 같이 담아도 주차가 밀리지 않아야 한다."""
    ids = ("네이버-서비스툴관리", "네이버-블로그_일반_체험단")
    chosen = [p for p in products if p["id"] in ids]
    raw = weekly_plan(products, [_item_for(p) for p in chosen])
    expected = next(w["주차"] for w in raw
                    if any(line.startswith("서비스툴관리 — ") for line in w["항목"]))

    weeks = _schedule_of(products, *ids)
    placed = [w["주차"] for w in weeks if "서비스툴관리 — 진행" in w["항목"]]
    assert placed == [expected], f"{expected}주차에 있어야 하는데 {placed} 에 있다"


def test_progress_line_is_suppressed_when_the_product_name_is_internal(products):
    """상품명 자체에 금칙어가 든 상품은 대체 줄도 내보내지 않는다. 실패는
    닫히는 쪽으로.

    `커뮤니티-전국_대학생_동아리_단톡_침투` 는 상품명에 `단톡` 이 들어 있다.
    지금은 프로세스가 비어 있어 일정표에 안 나오지만 시트는 손편집이라
    언제든 채워진다. 그날 상품명으로 `단톡` 이 새어 나가면 안 된다."""
    catalog = [dict(p) for p in products]
    target = next(p for p in catalog
                  if p["id"] == "커뮤니티-전국_대학생_동아리_단톡_침투")
    target["프로세스"] = "실장님께 명단 전달"

    lines = _lines(_schedule_of(catalog, target["id"]))
    assert lines == [], f"상품명에 금칙어가 있는데 줄이 나갔다: {lines}"


def test_product_without_a_process_gets_no_progress_line(products):
    """걸러서 사라진 것과 애초에 단계가 없던 것은 다른 경우다. 프로세스가 빈
    상품(`네이버-플레이스_트래픽`)은 원래도 일정표에 안 나왔고 지금도 안 나온다."""
    lines = _lines(_schedule_of(products, "네이버-플레이스_트래픽"))
    assert lines == [], f"프로세스가 없는 상품에 줄이 생겼다: {lines}"


def test_partially_filtered_product_gets_no_progress_line(products):
    """`네이버-SA` 는 `상위대행사 이관` 만 걸리고 세 줄이 남는다. 남은 줄이
    있으면 대체 줄을 덧붙이지 않는다 — 같은 상품이 두 번 나오게 된다."""
    lines = _lines(_schedule_of(products, "네이버-SA"))
    assert "SA — 진행" not in lines
    assert any("소재 세팅" in line for line in lines)
    assert not any("이관" in line for line in lines)
