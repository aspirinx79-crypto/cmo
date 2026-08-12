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
    """`네이버-서비스툴관리` 는 프로세스가 "단톡방 소통" 한 줄이라 전부 걸린다.

    대체 줄 `— 진행` 은 "이 상품이 이 달에 돌아간다" 는 뜻이라 한 달 내내
    도는 단계로 본다(수정 라운드 3, K). 그래서 1~4주차에 모두 선다."""
    weeks = _schedule_of(products, "네이버-서비스툴관리")
    assert [w["항목"] for w in weeks] == [["서비스툴관리 — 진행"]] * 4, weeks


def test_progress_line_starts_where_the_first_step_was_and_runs_on(products):
    """대체 줄은 그 상품의 첫 단계가 놓였던 주차에서 시작해 4주차까지 이어진다.
    4주에 걸치는 상품과 같이 담아도 시작 주차가 밀리지 않아야 한다.

    **이 테스트가 구별하지 못하는 것을 분명히 해 둔다**: `weekly_plan()` 은
    항목마다 커서를 0으로 되돌리므로(`schedule.py:38`) 어떤 상품이든 첫 단계는
    언제나 1주차다. 따라서 여기서 뽑은 `expected` 는 늘 1이고, 이 테스트는
    "첫 단계의 주차를 계산했다" 와 "1주차로 하드코딩했다" 를 갈라내지 못한다.
    갈라내는 것은 대체 줄이 **엉뚱한 주차**(예: 마지막 주차)에 놓이는 경우다."""
    ids = ("네이버-서비스툴관리", "네이버-블로그_일반_체험단")
    chosen = [p for p in products if p["id"] in ids]
    raw = weekly_plan(products, [_item_for(p) for p in chosen])
    expected = next(w["주차"] for w in raw
                    if any(line.startswith("서비스툴관리 — ") for line in w["항목"]))

    weeks = _schedule_of(products, *ids)
    placed = [w["주차"] for w in weeks if "서비스툴관리 — 진행" in w["항목"]]
    assert placed == list(range(expected, 5)), \
        f"{expected}주차부터 4주차까지 있어야 하는데 {placed} 에 있다"


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


# --- 시트 작성자 메모 떼기 (수정 라운드 3, J) ---
# 실제로 나간 PDF 에 이런 줄이 찍혔다:
#   블로그 일반 체험단 — 2영업일 후 보고서 (약 1달 기간) _융통성 있게
#   블로그 프리미엄 체험단 — 10일 포스팅 원칙_융통성 있게
# "융통성 있게" 는 상무님이 시트에 남긴 본인용 메모다. 사장님은 이걸
# "일정 대충 하겠다는 거네" 로 읽는다. 금칙어와는 다른 종류라 안 걸렸다.


def _catalog_with_process(products: list[dict], pid: str, process: str):
    """실제 카탈로그를 얕게 복사해 상품 하나의 프로세스만 갈아 끼운다."""
    catalog = [dict(p) for p in products]
    target = next(p for p in catalog if p["id"] == pid)
    target["프로세스"] = process
    return catalog, target


def test_author_note_after_underscore_is_stripped(products):
    """`10일 포스팅 원칙_융통성 있게` 는 `10일 포스팅 원칙` 까지만 나간다."""
    lines = _lines(_schedule_of(products, "네이버-블로그_프리미엄_체험단"))
    assert "블로그 프리미엄 체험단 — 10일 포스팅 원칙" in lines, lines
    assert not any("융통성" in line for line in lines), lines


def test_no_author_note_survives_in_any_step(products):
    """카탈로그 전부를 한 기획안에 담아도 단계 쪽에 `_` 가 남으면 안 된다.
    상품명(왼쪽)은 검사 대상이 아니다 — 상품명에 `_` 가 든 상품이 실제로 있다."""
    plan = {"월": "2026-09", "계약가": 1000000, "진단메모": "",
            "항목": [_item_for(p) for p in products]}
    payload = build_payload(CLIENT, plan, products)
    for line in _lines(payload["일정"]):
        step = line.split(" — ", 1)[1]
        assert "_" not in step, f"단계에 시트 작성자 메모가 남았다: {line}"


def test_duration_note_in_parentheses_is_kept(products):
    """`(약 1달 기간)` 은 작성자 메모가 아니라 고객이 궁금해하는 기간 정보다.
    카탈로그 전체에서 괄호가 든 단계는 이 한 줄뿐이고 내용이 기간이라 남긴다.
    떼는 건 `_` 뒤 메모뿐이다."""
    lines = _lines(_schedule_of(products, "네이버-블로그_일반_체험단"))
    assert "블로그 일반 체험단 — 2영업일 후 보고서 (약 1달 기간)" in lines, lines


def test_underscore_in_the_product_name_is_untouched(products):
    """`1세대 블로거 _케케케라인 12팀` 은 **상품명 자체**에 `_` 가 있다.
    메모를 뗀다고 줄 전체에서 `_` 를 자르면 상품명이 잘려 나간다.

    지금 카탈로그에서 이 상품의 유일한 단계는 `단톡 통해…` 라 통째로 걸리고
    대체 줄로 바뀌어 메모 제거 경로를 아예 안 탄다. 상품명이 잘릴 수 있는
    자리는 **살아남은 단계를 렌더할 때**뿐이라, 시트에 고객용 단계가 들어온
    날을 가정해 프로세스를 갈아 끼우고 그 경로를 지나가게 한다."""
    catalog, target = _catalog_with_process(
        products, "네이버-1세대_블로거__케케케라인_12팀", "직접 포스팅")
    lines = _lines(_schedule_of(catalog, target["id"]))
    assert set(lines) == {"1세대 블로거 _케케케라인 12팀 — 직접 포스팅"}, lines


def test_step_that_is_only_an_author_note_falls_back_to_the_progress_line(products):
    """메모를 떼고 나니 단계가 통째로 비면, 걸러진 것과 같이 취급해
    기존 대체 줄(`{상품명} — 진행`) 경로로 넘어간다. `{상품명} — ` 같은
    꼬리 잘린 줄이 제안서에 나가면 안 된다."""
    catalog, target = _catalog_with_process(products, "네이버-푸드블로그", "_융통성 있게")
    lines = _lines(_schedule_of(catalog, target["id"]))
    assert set(lines) == {"푸드블로그 — 진행"}, lines


def test_emptied_step_does_not_add_a_progress_line_when_others_survive(products):
    """살아남은 단계가 있으면 대체 줄을 붙이지 않는다 — 빈 단계가 생겼다고
    같은 상품을 두 번 보여주면 안 된다."""
    catalog, target = _catalog_with_process(
        products, "네이버-푸드블로그", "직접 포스팅->_융통성 있게")
    lines = _lines(_schedule_of(catalog, target["id"]))
    assert set(lines) == {"푸드블로그 — 직접 포스팅"}, lines


def test_stripping_the_note_does_not_unblock_an_internal_line(products):
    """메모를 떼는 건 문구를 다듬는 일이지 방어선을 넓히는 일이 아니다.
    금칙어가 메모 안에 있었더라도 그 줄은 원문 기준으로 막힌다 — 실패는
    닫히는 쪽으로."""
    catalog, target = _catalog_with_process(
        products, "네이버-푸드블로그", "가이드 준비 _실장님께 알바풀 전달")
    lines = _lines(_schedule_of(catalog, target["id"]))
    assert set(lines) == {"푸드블로그 — 진행"}, lines


# --- '관리'류 단계를 매주 반복 표시 (수정 라운드 3, K) ---
# 실제로 만든 PDF 에서 1주차 14줄 / 2주차 3줄 / **3주차 0줄** / 4주차 1줄이
# 나왔다. 85개 단계 중 74개에 기간 정보가 없어 전부 1주차로 몰린 탓이다.
# 상무님 결정: "관리·운영·진행처럼 한 달 내내 하는 단계는 1~4주차에 모두
# 표시하고, 나머지 기간 없는 단계만 1주차에 둔다."

def _weeks_holding(weeks: list[dict], line: str) -> list[int]:
    """그 줄이 정확히 들어 있는 주차 번호들."""
    return [w["주차"] for w in weeks if line in w["항목"]]


def test_ongoing_steps_repeat_through_the_whole_month(products):
    """`관리`·`통계보며 보고 및 피드백` 은 한 달 내내 도는 단계라 매 주에 선다.
    1회성인 `소재 세팅` 은 자기 주차에만 남는다."""
    weeks = _schedule_of(products, "네이버-SA")
    assert _weeks_holding(weeks, "SA — 관리") == [1, 2, 3, 4], weeks
    assert _weeks_holding(weeks, "SA — 통계보며 보고 및 피드백") == [1, 2, 3, 4], weeks
    assert _weeks_holding(weeks, "SA — 소재 세팅") == [1], weeks


def test_one_off_steps_do_not_repeat(products):
    """`파티진행` 은 하루짜리 행사다. 1~4주차에 매주 세워 두면 거짓말이 된다.
    키워드를 `" 진행"`(앞 공백 포함)으로 잡는 이유가 바로 이 줄이다 —
    `배너 진행`·`소재 비즈톡 진행` 은 잡고 `파티진행` 은 안 잡는다."""
    weeks = _schedule_of(products, "IMC-상생_먹스타_파티")
    assert _weeks_holding(weeks, "상생 먹스타 파티 — 파티진행") == [1], weeks
    assert _weeks_holding(weeks, "상생 먹스타 파티 — 미팅 및 실사") == [1], weeks


def test_ongoing_check_looks_at_the_step_not_the_product_name(products):
    """반복 여부는 **단계**만 보고 정한다. 상품명까지 보면 `운영대행 — 미팅`
    (상품명에 `운영`)처럼 하루짜리 단계가 매주 반복돼 거짓말이 된다."""
    weeks = _schedule_of(products, "인스타-운영대행")
    assert _weeks_holding(weeks, "운영대행 — 운영대행") == [1, 2, 3, 4], weeks
    assert _weeks_holding(weeks, "운영대행 — 미팅") == [1], weeks
    assert _weeks_holding(weeks, "운영대행 — 컨셉 및 기획 회의") == [1], weeks


def test_repeated_lines_are_still_filtered_for_internal_wording(products):
    """반복으로 늘어난 줄에도 내부 문구 필터가 그대로 걸려야 한다.

    `1세대 블로거 _케케케라인 12팀` 의 유일한 단계 `단톡 통해 일정 조율 및
    진행` 은 반복 키워드(`" 진행"`)에도 걸리고 금칙어(`단톡`)에도 걸린다.
    필터를 반복보다 뒤에 걸면 `단톡` 이 네 번 인쇄된다."""
    weeks = _schedule_of(products, "네이버-1세대_블로거__케케케라인_12팀")
    blob = json.dumps(weeks, ensure_ascii=False)
    assert "단톡" not in blob, blob
    assert _weeks_holding(weeks, "1세대 블로거 _케케케라인 12팀 — 진행") == [1, 2, 3, 4], weeks


def test_a_realistic_plan_fills_every_week(products):
    """K 가 고치는 실제 증상. 이 구성으로 만든 PDF 의 3주차가 통째로 비어
    "3주차엔 아무것도 안 하네" 로 읽혔다."""
    weeks = _schedule_of(products,
                         "네이버-블로그_일반_체험단", "네이버-서비스툴관리",
                         "포털-언론송출", "네이버-SA", "유튜브-유튜버_PPL",
                         "IMC-CMO_서비스")
    for week in weeks:
        assert week["항목"], f"{week['주차']}주차가 비었다: {weeks}"


def test_identical_lines_are_not_duplicated_within_a_week(products):
    """`네이버-SA` 와 `구글-SA` 는 상품명·단계가 글자까지 같다. 같은 주에 같은
    줄이 두 번 찍히면 고객 눈에는 그냥 중복 오타다. 반복까지 하면 네 주 내내
    두 줄씩 늘어난다."""
    weeks = _schedule_of(products, "네이버-SA", "구글-SA")
    for week in weeks:
        assert len(week["항목"]) == len(set(week["항목"])), \
            f"{week['주차']}주차에 같은 줄이 두 번 있다: {week['항목']}"


# --- 고지사항에도 내부 문구가 산다 ---
# 일정표만 막고 끝낼 일이 아니었다. 실제 PDF 6쪽(고지사항)에
# "상위대행사에 마크업 필수" 가 그대로 찍혀 있었다 — 네이버/구글 SA·DA 와
# 유튜브 구글애즈 다섯 상품이 같은 문구를 달고 있다. 재하청 구조와 우리가
# 마크업을 붙인다는 사실을 한 줄로 알려주는 문장이라, 마진 유출이나 다름없다.
#
# 다만 고지사항은 프로세스와 달리 **원래 고객에게 보여주려고 쓴 칸**이다.
# 그래서 직함·단톡 같은 단어를 여기서 그대로 막으면 안 된다 — 서비스툴관리의
# 고지사항에 든 "대표키워드 변경", "단톡에서 얘기해주시면 담당자가 변경" 은
# 고객이 봐야 할 약속이다. 외주 구조·마진 어휘만 막는다.

def _notices_of(products, *ids):
    client = {"이름": "가게", "스냅샷": []}
    plan = {"월": "2026-09", "계약가": 1000000,
            "항목": [{"상품id": i, "수량": 1, "정가": 100000, "실비": 1000,
                     "예산": 100000, "수량표시": "1식"} for i in ids]}
    return build_payload(client, plan, products)["고지사항"]


def test_notice_does_not_reveal_upstream_agency_or_markup(products):
    """실제 카탈로그로 검사한다. 이 문구가 있는 상품이 다섯 개다."""
    ids = [p["id"] for p in products
           if "상위대행사" in (p.get("고지사항") or "")]
    assert ids, "카탈로그가 바뀌었다 — 이 테스트의 전제를 다시 보라"
    for notice in _notices_of(products, *ids):
        assert "상위대행사" not in notice, f"재하청 구조가 새 나갔다: {notice}"
        assert "마크업" not in notice, f"마크업이 새 나갔다: {notice}"


def test_notice_drops_only_the_internal_clause_not_the_whole_notice(products):
    """'레뷰 충전식으로 진행 / 공정위 문구 고지' 는 뒤쪽만 남아야 한다.

    공정위 문구 고지는 법적으로 알려야 하는 내용이다. 앞 절 하나 때문에
    통째로 버리면 지켜야 할 고지를 우리가 지운 셈이 된다.
    """
    notices = _notices_of(products, "네이버-블로그_프리미엄_체험단")
    joined = " ".join(notices)
    assert "레뷰" not in joined, f"외주처 이름이 남았다: {joined}"
    assert "공정위" in joined, f"공정위 고지까지 사라졌다: {joined}"


def test_notice_keeps_customer_facing_words_that_look_internal(products):
    """서비스툴관리의 고지사항은 통째로 살아야 한다.

    '대표키워드'·'단톡에서 얘기해주시면' 은 고객에게 하는 약속이다.
    일정표 필터를 그대로 가져다 쓰면 이 칸이 통째로 죽는다.
    """
    notices = _notices_of(products, "네이버-서비스툴관리")
    joined = " ".join(notices)
    assert "대표키워드" in joined, f"고객용 고지가 죽었다: {joined}"
    assert "단톡에서" in joined, f"고객용 고지가 죽었다: {joined}"


# ── 오픈업 ────────────────────────────────────────────────────

OPENUB_ENTRY = {
    "기준월": "2026-06",
    "매출": {"하한": 46000000, "상한": 56000000},
    "성별최다": {"값": "남성", "비율": 65},
    "연령최다": {"값": "남성 20대", "비율": 26},
    "요일최다": {"값": "토", "비율": 25},
    "평일비율": 65,
    "시간대최다": {"값": "밤", "비율": 40},
    "판독시각": "2026-08-12T09:30:00",
}


def test_payload_carries_the_latest_openub_month():
    """여러 달이 쌓여 있어도 제안서에는 최신 달만 나간다."""
    client = dict(CLIENT, 오픈업=[dict(OPENUB_ENTRY, 기준월="2026-05"),
                                  OPENUB_ENTRY])
    payload = build_payload(client, PLAN, PRODUCTS)
    assert payload["오픈업"]["기준월"] == "2026-06"
    assert payload["오픈업"]["매출"] == {"하한": 46000000, "상한": 56000000}
    assert payload["오픈업"]["성별최다"] == {"값": "남성", "비율": 65}


def test_payload_omits_openub_when_there_is_none():
    """오픈업 자료가 없으면 카드가 통째로 빠진다. 빈 카드를 만들지 않는다."""
    assert build_payload(CLIENT, PLAN, PRODUCTS)["오픈업"] is None


def test_payload_never_carries_the_reading_timestamp():
    """화이트리스트다. 명시한 필드 외에는 안 나간다."""
    client = dict(CLIENT, 오픈업=[OPENUB_ENTRY])
    payload = build_payload(client, PLAN, PRODUCTS)
    assert "판독시각" not in payload["오픈업"]
    assert "2026-08-12T09:30:00" not in json.dumps(payload, ensure_ascii=False)


def test_payload_never_carries_hand_typed_revenue():
    """손으로 넣은 단일 숫자는 근거가 약하고 기준월도 없다. 내부전용이다."""
    client = dict(CLIENT, 오픈업=[OPENUB_ENTRY])
    payload = build_payload(client, PLAN, PRODUCTS)
    blob = json.dumps(payload, ensure_ascii=False)
    assert "42000000" not in blob          # 스냅샷의 손입력 월매출
    assert payload["지표"]["상권순위"] == "상위 40%"   # 이건 그대로 나간다


def test_payload_skips_openub_entries_without_a_month():
    """기준월 없는 찌꺼기가 섞여 있어도 최신 달 계산이 흔들리지 않는다."""
    client = dict(CLIENT, 오픈업=[{"기준월": None, "매출": None}, OPENUB_ENTRY])
    payload = build_payload(client, PLAN, PRODUCTS)
    assert payload["오픈업"]["기준월"] == "2026-06"
