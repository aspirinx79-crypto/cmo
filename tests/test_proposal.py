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

# 목록에서 뺀 상품들(overrides.json 의 `_제외`). 일정표 필터가 막아야 할
# 문구가 이 프로세스 안에 있는데, 남은 카탈로그에는 그 문구가 하나도 없다
# — 「입금요청」·「클라이언트 소통」·「대행가」·밑줄 든 상품명 전부 0개다.
#
# 상품을 안 판다고 필터의 보호까지 없앨 수는 없다. 뺄 당시의 프로세스
# 문구를 글자 그대로 고정해 둔다. 이제 이 테스트들은 상무님이 무엇을
# 파느냐와 무관하게 `_client_facing_schedule` 의 동작만 본다.
RETIRED = [
    {"id": "네이버-카페_월_배너광고", "매체": "네이버", "상품명": "카페 월 배너광고",
     "가격유형": "직접입력", "정가": None, "실비": None, "예산배율": None,
     "최소수량": 1, "단위": "건", "판매중지": False, "고지사항": "",
     "프로세스": "카페와 대행가 협의->클라이언트 소통 및 디자인 컨펌 -> 배너 진행"},
    {"id": "IMC-CMO_서비스", "매체": "IMC", "상품명": "CMO 서비스",
     "가격유형": "예산배율", "정가": None, "실비": None, "예산배율": 1.0,
     "최소수량": 1, "단위": "원", "판매중지": False, "고지사항": "",
     "프로세스": "예산 선정 -> 매월 시작 및 종료일 스케줄링 체크 ->수시 관리 -> 월별 관리->입금요청"},
    {"id": "인스타-운영대행", "매체": "인스타", "상품명": "운영대행",
     "가격유형": "예산배율", "정가": None, "실비": None, "예산배율": 1.0,
     "최소수량": 1, "단위": "원", "판매중지": False, "고지사항": "",
     "프로세스": "컨셉 및 기획 회의->미팅->운영대행"},
    {"id": "네이버-1세대_블로거__케케케라인_12팀", "매체": "네이버",
     "상품명": "1세대 블로거 _케케케라인 12팀", "가격유형": "고정",
     "정가": 3000000, "실비": 0, "예산배율": None, "최소수량": 1, "단위": "팀",
     "판매중지": False, "고지사항": "", "프로세스": "단톡 통해 일정 조율 및 진행"},
    {"id": "구글-SA", "매체": "구글", "상품명": "SA", "가격유형": "예산배율",
     "정가": None, "실비": None, "예산배율": 1.15, "최소수량": 1, "단위": "원",
     "판매중지": False, "고지사항": "",
     "프로세스": "상위대행사 이관-> 소재 세팅->통계보며 보고 및 피드백 -> 관리"},
    {"id": "커뮤니티-전국_대학생_동아리_단톡_침투", "매체": "커뮤니티",
     "상품명": "전국 대학생 동아리 단톡 침투", "가격유형": "고정",
     "정가": 200000, "실비": 0, "예산배율": None, "최소수량": 1, "단위": "건",
     "판매중지": False, "고지사항": "", "프로세스": ""},
]


def _schedule_of(products: list[dict], *ids: str) -> list[dict]:
    """카탈로그에서 상품 몇 개만 골라 기획안을 만들고 고객용 일정표를 낸다.

    목록에서 뺀 상품(RETIRED)도 함께 본다 — 그 문구를 막는 게 이 테스트들의
    일이고, 상품이 빠졌다고 검사까지 빠지면 안 된다.
    """
    # 이미 들어 있는 건 다시 붙이지 않는다 — `_catalog_with_process` 가
    # 넘겨준 카탈로그에는 RETIRED 가 이미 섞여 있어 두 번 더하면 같은
    # 상품이 두 벌이 된다.
    있는것 = {p["id"] for p in products}
    catalog = list(products) + [r for r in RETIRED if r["id"] not in 있는것]
    chosen = [p for p in catalog if p["id"] in ids]
    assert len(chosen) == len(ids), f"카탈로그에 없는 id 가 있다: {ids}"
    plan = {"월": "2026-09", "계약가": 1000000, "진단메모": "",
            "항목": [_item_for(p) for p in chosen]}
    return build_payload(CLIENT, plan, catalog)["일정"]


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
    언제든 채워진다. 그날 상품명으로 `단톡` 이 새어 나가면 안 된다.

    이 상품은 목록에서 뺐다. 그래도 검사는 남긴다 — 막는 것은 상품이
    아니라 상품명에 금칙어가 든 경우이고, 그런 상품은 또 생긴다."""
    catalog, target = _catalog_with_process(
        products, "커뮤니티-전국_대학생_동아리_단톡_침투", "실장님께 명단 전달")

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
    """카탈로그를 얕게 복사해 상품 하나의 프로세스만 갈아 끼운다.

    `_schedule_of` 와 같은 이유로 뺀 상품(RETIRED)도 함께 본다.
    """
    catalog = [dict(p) for p in list(products) + RETIRED]
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


# --- 고지사항은 제안서에서 뺐다 ---
# 고지사항 장을 통째로 지우면서 payload 의 「고지사항」 열쇠와 그것을
# 만들던 필터(`NOTICE_INTERNAL_WORDS`·`_client_facing_notice`)도 같이
# 지웠다. 싣는 곳이 없는데 거르는 기계만 남으면 나중에 읽는 사람이
# 「고객이 고지를 받는구나」로 오해한다.
#
# 여기 있던 검사 세 개가 막던 것: 카탈로그 고지사항 원문에 든
# "상위대행사에 마크업 필수"(네이버/구글 SA·DA, 유튜브 구글애즈 다섯 상품)
# 가 제안서에 그대로 찍히는 일. **다시 고지를 실으려면 그 필터부터
# 되살려야 한다** — 원문은 지금도 외주처 이름과 마크업을 달고 있다.


def test_payload_no_longer_carries_notices(products):
    """제안서 payload 에 고지사항이 없다.

    거르는 기계 없이 이 열쇠만 되살아나면 카탈로그 원문이 그대로 실린다.
    그 순간 "상위대행사에 마크업 필수" 가 고객 문서로 나간다.
    """
    client = {"이름": "가게", "스냅샷": []}
    ids = [p["id"] for p in products
           if "상위대행사" in (p.get("고지사항") or "")]
    assert ids, "카탈로그가 바뀌었다 — 이 테스트의 전제를 다시 보라"
    plan = {"월": "2026-09", "계약가": 1000000,
            "항목": [{"상품id": i, "수량": 1, "정가": 100000, "실비": 1000,
                     "예산": 100000, "수량표시": "1식"} for i in ids]}
    payload = build_payload(client, plan, products)
    assert "고지사항" not in payload
    blob = json.dumps(payload, ensure_ascii=False)
    assert "상위대행사" not in blob
    assert "마크업" not in blob


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


# ── 진단자료: 기회표·변화·히든키워드·리뷰 ─────────────────────

RICH_SNAP = {
    "수집시각": "2026-08-13T09:00:00",
    "플레이스": {"방문자리뷰": 775, "블로그리뷰": 1415, "저장수": 100},
    "순위": [
        {"키워드": "서초맛집", "순위": None, "순위권밖": True,
         "조회수": 5740, "비교순위": 81},
        {"키워드": "방배동맛집", "순위": 77, "순위권밖": False,
         "조회수": 4900, "비교순위": 18},
        {"키워드": "방배동 회식", "순위": 5, "순위권밖": False,
         "조회수": 10, "비교순위": 22},
        {"키워드": "예술의전당정육식당", "순위": 1, "순위권밖": False,
         "조회수": 50, "비교순위": 1},
    ],
    "예상매출": None,
    "순위요약": {"총키워드": 51, "TOP3": 6, "TOP10": 11},
    "진단": {
        "기준일": "08-12", "비교일": "07-29",
        "대표키워드": ["방배역가족모임밥집"],
        "히든키워드": ["예술의전당한우", "방배역 곰탕", "방배동한우"],
        "리뷰": {
            "방문자": [{"제목": "아이들이 한우 먹고싶다고", "조회수": 1479,
                        "작성일": "2026-07-16", "작성자": "ljw20566"}],
            "블로그": [{"제목": "방배동 소고기 맛집 추천",
                        "작성일": "2026-05-26", "실명여부": "톰바미설치"}],
        },
    },
}
RICH_CLIENT = dict(CLIENT, 스냅샷=[RICH_SNAP])


def test_opportunity_table_is_sorted_by_search_volume():
    표 = build_payload(RICH_CLIENT, PLAN, PRODUCTS)["진단자료"]["검색"]["기회표"]
    assert [r["키워드"] for r in 표][:2] == ["서초맛집", "방배동맛집"]
    assert 표[0]["조회수"] == 5740
    assert 표[0]["순위표시"] == "30위 밖"
    assert 표[1]["순위표시"] == "77위"


def test_headline_pairs_the_biggest_miss_with_the_smallest_win():
    """조회수가 가장 큰데 안 잡힌 키워드와, 1위인데 조회수가 작은 키워드."""
    문장 = build_payload(RICH_CLIENT, PLAN, PRODUCTS)["진단자료"]["검색"]["헤드라인"]
    assert "5,740" in 문장
    assert "서초맛집" in 문장
    assert "예술의전당정육식당" in 문장


def test_rank_moves_are_split_into_up_and_down():
    변화 = build_payload(RICH_CLIENT, PLAN, PRODUCTS)["진단자료"]["처방"]
    assert 변화["기준일"] == "08-12" and 변화["비교일"] == "07-29"
    # 서초맛집은 81위에서 순위권 밖으로 밀렸다 — 그것도 내림이다.
    # 낙폭이 큰 순서로 선다.
    assert [r["키워드"] for r in 변화["내림"]] == ["서초맛집", "방배동맛집"]
    assert 변화["내림"][0]["전"] == "81위"
    assert 변화["내림"][0]["후"] == "30위 밖"
    assert [r["키워드"] for r in 변화["오름"]] == ["방배동 회식"]


def test_hidden_keywords_carry_a_count():
    히든 = build_payload(RICH_CLIENT, PLAN, PRODUCTS)["진단자료"]["검색"]["히든키워드"]
    assert 히든["개수"] == 3
    assert "예술의전당한우" in 히든["목록"]


def test_reviews_drop_internal_marks_and_author_ids():
    """실명여부·톰바설치는 우리 사정이고 작성자 아이디는 개인정보다."""
    payload = build_payload(RICH_CLIENT, PLAN, PRODUCTS)
    blob = json.dumps(payload, ensure_ascii=False)
    assert "톰바" not in blob
    assert "실명여부" not in blob
    assert "ljw20566" not in blob
    assert "작성자" not in blob
    리뷰 = payload["진단자료"]["리뷰"]
    assert 리뷰["방문자수"] == 775 and 리뷰["블로그수"] == 1415
    assert 리뷰["많이읽힌"][0]["조회수"] == 1479


def test_sections_vanish_when_there_is_nothing_to_show():
    """기존 PDF 한 장만 넣은 매장은 네 장이 통째로 빠진다."""
    진단 = build_payload(CLIENT, PLAN, PRODUCTS)["진단자료"]
    assert 진단["검색"]["기회표"] is None
    assert 진단["검색"]["헤드라인"] is None
    assert 진단["처방"] is None
    assert 진단["검색"]["히든키워드"] is None


def test_opportunity_table_needs_search_volume():
    """순위만 있고 조회수가 없으면 기회표가 안 나온다."""
    snap = json.loads(json.dumps(RICH_SNAP, ensure_ascii=False))
    for row in snap["순위"]:
        row["조회수"] = None
    진단 = build_payload(dict(CLIENT, 스냅샷=[snap]), PLAN, PRODUCTS)["진단자료"]
    assert 진단["검색"]["기회표"] is None


def test_headline_picks_the_right_particle():
    """받침에 따라 은/는이 갈린다. 고객이 받는 글이라 눈에 띈다."""
    from cmo.lib.proposal import _josa

    assert _josa("예술의전당정육식당", "은", "는") == "은"   # 받침 있음
    assert _josa("방배동맛집", "은", "는") == "은"
    assert _josa("서초구", "은", "는") == "는"              # 받침 없음
    assert _josa("한우", "은", "는") == "는"
    assert _josa("SA", "은", "는") == "는"                  # 한글이 아니면 기본


def test_headline_sentence_reads_correctly():
    문장 = build_payload(RICH_CLIENT, PLAN, PRODUCTS)["진단자료"]["검색"]["헤드라인"]
    assert "「예술의전당정육식당」은" in 문장
    assert "「예술의전당정육식당」는" not in 문장


# ── 빈 스냅샷이 진단을 덮지 않는다 ───────────────────────────

def test_empty_snapshot_does_not_bury_the_reading():
    """고장난 순위조회가 뒤에 붙어도 판독 자료가 살아 있어야 한다.

    실제로 이것 때문에 제안서 진단 장이 통째로 비어 나갔다.
    """
    from cmo.lib.proposal import _latest_snapshot
    좋은것 = {"수집시각": "2026-08-12T08:52:26",
              "플레이스": {"방문자리뷰": 1082, "블로그리뷰": 170},
              "순위": [{"키워드": "잠실맛집", "순위": 8}]}
    껍데기 = {"수집시각": "2026-08-14T00:26:35",
              "플레이스": {"방문자리뷰": None, "블로그리뷰": None},
              "순위": []}
    got = _latest_snapshot({"스냅샷": [좋은것, 껍데기, 껍데기]})
    assert got is 좋은것


def test_latest_of_several_real_snapshots_wins():
    """자료가 여럿이면 그중 가장 늦은 것을 쓴다."""
    from cmo.lib.proposal import _latest_snapshot
    앞 = {"수집시각": "2026-08-01",
          "순위": [{"키워드": "가", "순위": 1, "조회수": 500}]}
    뒤 = {"수집시각": "2026-08-10",
          "순위": [{"키워드": "나", "순위": 2, "조회수": 800}]}
    assert _latest_snapshot({"스냅샷": [앞, 뒤]}) is 뒤


def test_all_empty_snapshots_give_nothing():
    """전부 껍데기면 빈 것을 준다 — 없는 자료를 지어내지 않는다."""
    from cmo.lib.proposal import _latest_snapshot
    껍데기 = {"수집시각": "2026-08-14", "플레이스": {"방문자리뷰": None}, "순위": []}
    assert _latest_snapshot({"스냅샷": [껍데기, 껍데기]}) == {}
    assert _latest_snapshot({"스냅샷": []}) == {}


def test_an_empty_capture_is_not_counted_as_data():
    """캡처가 아무것도 못 읽은 날 넣는 껍데기를 자료로 세면 안 된다.

    판독기는 못 읽은 날에도 진단의 키를 다 채운다. 키가 있다고 자료로
    세면 그 껍데기가 앞서 읽어 둔 스냅샷을 가린다.
    """
    from cmo.lib.proposal import _has_data, _latest_snapshot
    좋은것 = {"수집시각": "2026-09-01",
              "플레이스": {"방문자리뷰": 1082, "블로그리뷰": 170},
              "순위": [{"키워드": "잠실맛집", "순위": 8}]}
    빈캡처 = {"수집시각": "2026-09-15",
              "플레이스": {"방문자리뷰": None, "블로그리뷰": None},
              "순위": [],
              "진단": {"기준일": None, "비교일": None, "대표키워드": [],
                       "히든키워드": [], "리뷰": {"방문자": [], "블로그": []}}}
    assert not _has_data(빈캡처)
    assert _latest_snapshot({"스냅샷": [좋은것, 빈캡처]}) is 좋은것


def test_a_capture_with_only_a_hidden_keyword_still_counts():
    """히든키워드 하나만 읽어 온 캡처는 자료다 — 지나치게 엄해지면 안 된다."""
    from cmo.lib.proposal import _has_data
    assert _has_data({"진단": {"기준일": None, "히든키워드": ["숨은키워드"],
                               "리뷰": {"방문자": [], "블로그": []}}})
    assert _has_data({"진단": {"기준일": "2026-09-01", "히든키워드": []}})
    # 리뷰 축은 「조회수 있는 방문자 줄」이 있어야 자료다. 제목만 남은
    # 줄은 제안서가 한 글자도 안 찍으므로(`_reviews`) 자료로 안 센다.
    assert _has_data({"진단": {"리뷰": {"방문자": [{"제목": "맛있어요",
                                                    "조회수": 500}],
                                        "블로그": []}}})
    assert not _has_data({"진단": {"리뷰": {"방문자": [{"제목": "맛있어요"}],
                                            "블로그": []}}})


def test_snapshot_with_picks_the_last_one_that_has_the_field():
    """칸별로 고른다 — 그 값을 가진 마지막 스냅샷이다."""
    from cmo.lib.proposal import _snapshot_with
    앞 = {"수집시각": "2026-09-01", "순위": [{"키워드": "가", "순위": 1}]}
    뒤 = {"수집시각": "2026-09-10", "순위": []}
    client = {"스냅샷": [앞, 뒤]}
    assert _snapshot_with(client, lambda s: s.get("순위")) is 앞
    assert _snapshot_with(client, lambda s: s.get("없는칸")) == {}
    assert _snapshot_with({"스냅샷": []}, lambda s: True) == {}


def test_has_place_value_sees_values_not_the_dict():
    """플레이스 dict 는 있는데 값이 전부 None 인 껍데기를 걸러낸다."""
    from cmo.lib.proposal import _has_place_value
    assert _has_place_value({"플레이스": {"방문자리뷰": 10, "블로그리뷰": None}})
    assert not _has_place_value({"플레이스": {"방문자리뷰": None, "블로그리뷰": None}})
    assert not _has_place_value({"플레이스": {}})
    assert not _has_place_value({})


def test_has_review_value_sees_the_rows_the_proposal_prints():
    """리뷰에서 제안서가 종이에 찍는 것은 조회수 있는 방문자 줄뿐이다.

    캡처가 리뷰를 못 찾은 날 채워 넣는 빈 껍데기(`read_doc.snapshot_from`
    이 `{"방문자": [], "블로그": []}` 를 늘 채운다)도, 줄은 남았지만 찍을
    값이 없는 줄도 걸러낸다. `_review_rows` 는 **제목만 있으면** 줄을
    남기는데(`read_doc`), `_reviews` 는 **조회수 있는 방문자 줄만** 쓴다.
    블로그 줄은 한 글자도 안 나간다.
    """
    from cmo.lib.proposal import _has_review_value
    있음 = {"진단": {"리뷰": {"방문자": [{"제목": "맛있어요", "조회수": 500}],
                              "블로그": []}}}
    조회수없음 = {"진단": {"리뷰": {"방문자": [{"제목": "맛있어요", "조회수": None}],
                                    "블로그": []}}}
    제목만 = {"진단": {"리뷰": {"방문자": [{"제목": "맛있어요"}], "블로그": []}}}
    블로그만 = {"진단": {"리뷰": {"방문자": [],
                                  "블로그": [{"제목": "방배동 소고기 맛집",
                                              "작성일": "2026-05-26"}]}}}
    빈것 = {"진단": {"리뷰": {"방문자": [], "블로그": []}}}
    assert _has_review_value(있음)
    assert not _has_review_value(조회수없음)
    assert not _has_review_value(제목만)
    assert not _has_review_value(블로그만)
    assert not _has_review_value(빈것)
    assert not _has_review_value({"진단": {}})
    assert not _has_review_value({})


# ── 상권 한 줄 ────────────────────────────────────────────

def test_weekday_heavy_is_called_a_weekday_trade_area():
    from cmo.lib.proposal import _trade_area
    assert _trade_area(63) == "평일 상권입니다"
    assert _trade_area(60) == "평일 상권입니다"


def test_weekend_heavy_is_called_a_weekend_trade_area():
    from cmo.lib.proposal import _trade_area
    assert _trade_area(37) == "주말 상권입니다"
    assert _trade_area(40) == "주말 상권입니다"


def test_the_middle_gets_no_name():
    """55%를 「평일 상권」이라 부르면 그 뒤 문장이 전부 틀어진다."""
    from cmo.lib.proposal import _trade_area
    assert _trade_area(55) is None
    assert _trade_area(41) is None
    assert _trade_area(59) is None
    assert _trade_area(None) is None


# ── 진단 세 장 ────────────────────────────────────────────

def test_lines_carry_the_product_id():
    """처방이 갈래를 판정하려면 줄에 상품id 가 있어야 한다."""
    got = build_payload(CLIENT, PLAN, PRODUCTS)
    assert all("상품id" in ln for ln in got["구성"])


def test_diagnosis_has_three_parts():
    got = build_payload(CLIENT, PLAN, PRODUCTS)["진단자료"]
    assert set(got) == {"손님", "검색", "처방", "리뷰"}


def test_customer_page_vanishes_without_openub():
    """빈 카드를 만들지 않는다."""
    got = build_payload(CLIENT, PLAN, PRODUCTS)["진단자료"]
    assert got["손님"] is None


def test_customer_page_carries_openub_and_trade_area():
    client = {**CLIENT, "오픈업": [{
        "기준월": "2026-06",
        "매출": {"하한": 46000000, "상한": 56000000},
        "성별최다": {"값": "남성", "비율": 62},
        "연령최다": {"값": "30대", "비율": 34},
        "요일최다": {"값": "금요일", "비율": 21},
        "시간대최다": {"값": "19~21시", "비율": 41},
        "평일비율": 63,
    }]}
    손님 = build_payload(client, PLAN, PRODUCTS)["진단자료"]["손님"]
    assert 손님["기준월"] == "2026-06"
    assert 손님["상권"] == "평일 상권입니다"
    assert 손님["평일비율"] == 63


def test_search_page_carries_the_idle_numbers():
    """총키워드·TOP3·TOP10·저장수는 읽어 놓고 안 쓰던 값이다.

    스냅샷 모양은 `read_doc._snapshot()` 이 실제로 만드는 그대로다 —
    여기서 `진단` 에 넣으면 생산 코드가 안 쓰는 자리를 검사하게 된다.
    실제로 그래서 이 값들이 한 번도 종이에 안 찍혔다.
    """
    client = {**CLIENT, "스냅샷": [{
        "수집시각": "2026-08-12T08:52:26",
        "플레이스": {"방문자리뷰": 1082, "블로그리뷰": 170, "저장수": 100},
        "순위": [{"키워드": "잠실맛집", "순위": 8}],
        "순위요약": {"총키워드": 47, "TOP3": 3, "TOP10": 11},
    }]}
    수치 = build_payload(client, PLAN, PRODUCTS)["진단자료"]["검색"]["수치"]
    이름별 = {c["이름"]: c["값"] for c in 수치}
    assert 이름별["추적 키워드"] == "47개"
    assert 이름별["TOP 3"] == "3개"
    assert 이름별["TOP 10"] == "11개"
    assert 이름별["저장수"] == "100개"


def test_search_page_reads_the_shape_read_doc_writes():
    """판독기가 만드는 스냅샷을 그대로 먹여 본다.

    두 모듈이 키 이름을 두 벌로 갖고 있으면 어느 날 조용히 어긋난다.
    실제로 `순위요약`(쓰는 쪽)과 `진단`(읽는 쪽)이 어긋나 있었다.
    """
    from cmo.lib.read_doc import snapshot_from

    reading = {"방문자리뷰": 1082, "블로그리뷰": 170, "저장수": 100,
               "총키워드": 48, "TOP3": 1, "TOP10": 15,
               "순위": [{"키워드": "잠실맛집", "순위": 8}]}
    client = {**CLIENT, "스냅샷": [snapshot_from(reading)]}
    수치 = build_payload(client, PLAN, PRODUCTS)["진단자료"]["검색"]["수치"]
    assert {"추적 키워드", "TOP 3", "TOP 10"} <= {c["이름"] for c in 수치}


# ── 빠진 진단 장 경고 ─────────────────────────────────────
#
# 실제로 이것 때문에 방이점 제안서가 4장으로 조용히 나갔다. 자료가 없으면
# 장이 사라지는 것은 맞는 동작이지만, **사라진 줄 모르고 나가는 것**이
# 사고다. 뽑는 사람에게 그 자리에서 알린다.

# 방이점 실물 모양 — 자동수집만 두 번 눌려 껍데기 스냅샷만 쌓인 매장.
BARE_CLIENT = {
    "이름": "미친양꼬치 방이점", "업종": "", "지역": "", "평수": None,
    "스냅샷": [
        {"수집시각": "2026-08-15T21:37:12",
         "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
         "순위": [], "예상매출": None},
        {"수집시각": "2026-08-15T21:37:21",
         "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
         "순위": [], "예상매출": None},
    ],
}

WARN_OPENUB = {
    "기준월": "2026-07", "매출": {"하한": 46000000, "상한": 56000000},
    "성별최다": {"값": "남성", "비율": 62},
    "연령최다": {"값": "남성 30대", "비율": 28},
    "요일최다": {"값": "금", "비율": 22},
    "시간대최다": {"값": "밤", "비율": 45},
    "평일비율": 64,
}


def _warnings(client, plan=None):
    from cmo.lib.proposal import missing_pages
    return missing_pages(build_payload(client, plan or PLAN, PRODUCTS))


def test_bare_client_warns_about_all_three_diagnosis_pages():
    """자료가 한 줄도 없는 매장은 세 장이 전부 빠진다. 셋 다 알린다."""
    경고 = _warnings(BARE_CLIENT)
    붙인것 = " ".join(경고)
    assert len(경고) == 3
    assert "이 가게에 오는 손님" in 붙인것
    assert "검색에서의 자리" in 붙인것
    assert "순위 변동과 이번 달 처방" in 붙인것


def test_warnings_say_which_capture_to_upload():
    """무엇이 빠졌는지만 알리면 다음에 뭘 해야 할지 모른다."""
    경고 = _warnings(BARE_CLIENT)
    손님 = next(w for w in 경고 if "손님" in w)
    검색 = next(w for w in 경고 if "검색에서의 자리" in w)
    처방 = next(w for w in 경고 if "처방" in w)
    assert "오픈업" in 손님
    assert "애드로그" in 검색
    assert "애드로그" in 처방 and "비교순위" in 처방


def test_a_client_with_everything_gets_no_warning():
    """세 장이 다 서면 조용해야 한다. 늘 짖는 경고는 아무도 안 본다."""
    client = dict(RICH_CLIENT, 오픈업=[WARN_OPENUB])
    assert _warnings(client) == []


def test_openub_alone_still_warns_about_the_two_adlog_pages():
    """오픈업만 넣으면 손님 장만 선다."""
    경고 = _warnings(dict(BARE_CLIENT, 오픈업=[WARN_OPENUB]))
    붙인것 = " ".join(경고)
    assert "이 가게에 오는 손님" not in 붙인것
    assert "검색에서의 자리" in 붙인것
    assert "순위 변동과 이번 달 처방" in 붙인것


def test_adlog_alone_still_warns_about_the_customer_page():
    """애드로그만 넣으면 손님 장이 빈다 — 오픈업은 따로 넣어야 한다."""
    경고 = _warnings(RICH_CLIENT)
    붙인것 = " ".join(경고)
    assert "이 가게에 오는 손님" in 붙인것
    assert "검색에서의 자리" not in 붙인것
    assert "순위 변동과 이번 달 처방" not in 붙인것


def test_a_half_filled_search_page_is_not_reported_missing():
    """방문자 리뷰 하나만 있어도 검색 장은 선다 — 선 장을 빠졌다고 하지 않는다.

    서식은 `헤드라인·수치·기회표·히든키워드` 중 **하나만** 있어도 장을
    띄운다(`proposal.html:203`). 경고가 그보다 엄하면 거짓말이 된다.
    """
    경고 = " ".join(_warnings(CLIENT))
    assert "검색에서의 자리" not in 경고


def test_warning_does_not_touch_the_payload():
    """경고는 읽기만 한다. 뽑는 값을 건드리면 안 된다."""
    from cmo.lib.proposal import missing_pages
    payload = build_payload(BARE_CLIENT, PLAN, PRODUCTS)
    before = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    missing_pages(payload)
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == before


# ── 칸별로 최신 스냅샷을 읽는다 (두 출처) ─────────────────────
#
# 애드로그가 못 주는 칸이 둘 있다 — 히든키워드와 리뷰 목록. 캡처 판독에만
# 있다. 마지막 한 건만 보면 애드로그로 갱신할 때마다 캡처가 넣어 둔 이
# 둘이 가려진다. 칸마다 그 값을 가진 마지막 스냅샷에서 따로 읽는다.

def test_proposal_keeps_capture_only_fields_after_an_adlog_sync():
    """애드로그 갱신 한 번에 히든키워드·리뷰가 사라지면 안 된다.

    API 에 이 둘이 없다. 캡처가 넣어 둔 것을 칸별로 살려 읽는다.
    실데이터로 방이점 기회표가 8줄에서 0줄이 되는 걸 확인하고 고친 자리다.
    """
    캡처 = {
        "수집시각": "2026-09-10T10:00:00",
        "플레이스": {"방문자리뷰": 100, "블로그리뷰": 20, "저장수": 30},
        "순위": [{"키워드": "캡처키워드", "순위": 5, "조회수": 1000}],
        "순위요약": {"총키워드": 1, "TOP3": 0, "TOP10": 1},
        "진단": {"기준일": "2026-09-10", "비교일": "2026-08-10",
                 "히든키워드": ["숨은키워드"],
                 "리뷰": {"방문자": [{"제목": "맛있어요", "조회수": 500}],
                          "블로그": []}},
    }
    애드로그 = {
        "수집시각": "2026-09-21T14:00:00",
        "출처": "애드로그",
        "플레이스": {"방문자리뷰": 120, "블로그리뷰": 25, "저장수": 40},
        "순위": [{"키워드": "잠실새내 맛집", "순위": 26, "순위권밖": False,
                  "조회수": 22160, "비교순위": 30}],
        "순위요약": {"총키워드": 1, "TOP3": 0, "TOP10": 0},
        "진단": {"기준일": "2026-09-21", "비교일": "2026-08-22"},
    }
    client = {**CLIENT, "스냅샷": [캡처, 애드로그]}
    진단자료 = build_payload(client, PLAN, PRODUCTS)["진단자료"]

    assert 진단자료["검색"]["히든키워드"], "히든키워드가 사라졌다"
    assert 진단자료["리뷰"]["많이읽힌"], "리뷰 목록이 사라졌다"
    assert 진단자료["검색"]["기회표"], "기회표가 사라졌다"
    assert 진단자료["처방"], "처방이 사라졌다"


def test_search_page_carries_the_rank_date():
    """사장님이 「이 순위는 언제 것인가」를 종이에서 알아야 한다."""
    client = {**CLIENT, "스냅샷": [{
        "수집시각": "2026-09-21T14:00:00",
        "출처": "애드로그",
        "플레이스": {"방문자리뷰": 120, "블로그리뷰": 25, "저장수": 40},
        "순위": [{"키워드": "가", "순위": 3, "순위권밖": False,
                  "조회수": 100, "비교순위": None}],
        "순위요약": {"총키워드": 1, "TOP3": 1, "TOP10": 1},
        "진단": {"기준일": "2026-09-21", "비교일": None},
    }]}
    assert build_payload(client, PLAN, PRODUCTS)["진단자료"]["검색"]["기준일"] == "2026-09-21"


def test_search_page_shows_the_span_but_the_prescription_shows_one_date():
    """키워드마다 잰 날이 다르면 검색 장은 범위를, 처방 제목은 날짜 하나를 쓴다.

    처방 제목이 `비교일 → 기준일` 이라, 그 자리에 범위가 들어가면
    「8월 20일에서 9월 1일~9월 23일로」가 된다. 사장님이 읽는 종이다.
    """
    client = {**CLIENT, "스냅샷": [{
        "수집시각": "2026-09-23T14:00:00",
        "출처": "애드로그",
        "플레이스": {"방문자리뷰": 120, "블로그리뷰": 25, "저장수": 40},
        "순위": [{"키워드": "가", "순위": 3, "순위권밖": False,
                  "조회수": 100, "비교순위": 9}],
        "순위요약": {"총키워드": 1, "TOP3": 1, "TOP10": 1},
        "진단": {"기준일": "2026-09-23",
                 "기준일범위": "2026-09-01~2026-09-23",
                 "비교일": "2026-08-20"},
    }]}
    진단자료 = build_payload(client, PLAN, PRODUCTS)["진단자료"]

    assert 진단자료["검색"]["기준일"] == "2026-09-01~2026-09-23"
    assert 진단자료["처방"]["기준일"] == "2026-09-23"
    assert 진단자료["처방"]["비교일"] == "2026-08-20"


def test_search_page_falls_back_to_the_single_date_without_a_span():
    """날짜가 하나뿐인 날은 예전 그대로다. 옛 스냅샷에는 범위 칸이 아예 없다."""
    client = {**CLIENT, "스냅샷": [{
        "수집시각": "2026-09-21T14:00:00",
        "출처": "애드로그",
        "플레이스": {"방문자리뷰": 120, "블로그리뷰": 25, "저장수": 40},
        "순위": [{"키워드": "가", "순위": 3, "순위권밖": False,
                  "조회수": 100, "비교순위": None}],
        "순위요약": {"총키워드": 1, "TOP3": 1, "TOP10": 1},
        "진단": {"기준일": "2026-09-21", "비교일": None},
    }]}
    assert build_payload(client, PLAN, PRODUCTS)["진단자료"]["검색"]["기준일"] \
        == "2026-09-21"


def test_an_empty_second_capture_does_not_erase_the_first_reviews():
    """캡처가 그날 리뷰를 못 찾아도 앞서 읽어 둔 리뷰가 살아 있어야 한다.

    판독기는 리뷰를 못 찾은 날에도 `{"방문자": [], "블로그": []}` 를
    채워 넣는다. 그 껍데기를 「리뷰가 있는 스냅샷」으로 세면 사장님께
    보여 줄 리뷰가 캡처 한 번에 사라진다.
    """
    캡처1 = {
        "수집시각": "2026-09-01T10:00:00",
        "플레이스": {"방문자리뷰": 100, "블로그리뷰": 20},
        "순위": [{"키워드": "가", "순위": 5, "조회수": 1000}],
        "진단": {"기준일": "2026-09-01", "비교일": "2026-08-01",
                 "히든키워드": ["숨은"],
                 "리뷰": {"방문자": [{"제목": "맛있어요", "조회수": 500}],
                          "블로그": []}},
    }
    캡처2 = {**캡처1,
             "수집시각": "2026-09-15T10:00:00",
             "진단": {**캡처1["진단"], "기준일": "2026-09-15",
                      "리뷰": {"방문자": [], "블로그": []}}}
    client = {**CLIENT, "스냅샷": [캡처1, 캡처2]}

    많이읽힌 = build_payload(client, PLAN, PRODUCTS)["진단자료"]["리뷰"]["많이읽힌"]
    assert [r["제목"] for r in 많이읽힌] == ["맛있어요"]


def test_rank_date_follows_the_snapshot_that_gave_the_ranks():
    """순위와 히든키워드가 다른 시점에서 와도 기준일은 순위 쪽이다.

    애드로그에는 히든키워드가 없다. 캡처 쪽 기준일을 찍으면 사장님이
    보는 날짜와 종이의 순위가 어긋난다.
    """
    캡처 = {
        "수집시각": "2026-09-10T10:00:00",
        "플레이스": {"방문자리뷰": 100, "블로그리뷰": 20},
        "진단": {"기준일": "2026-09-10", "비교일": "2026-08-10",
                 "히든키워드": ["숨은키워드"]},
    }
    애드로그 = {
        "수집시각": "2026-09-21T14:00:00",
        "출처": "애드로그",
        "플레이스": {"방문자리뷰": 120, "블로그리뷰": 25},
        "순위": [{"키워드": "가", "순위": 3, "순위권밖": False,
                  "조회수": 100, "비교순위": None}],
        "순위요약": {"총키워드": 1, "TOP3": 1, "TOP10": 1},
        "진단": {"기준일": "2026-09-21", "비교일": "2026-08-22"},
    }
    검색 = build_payload({**CLIENT, "스냅샷": [캡처, 애드로그]},
                         PLAN, PRODUCTS)["진단자료"]["검색"]

    assert 검색["기준일"] == "2026-09-21"
    assert 검색["히든키워드"], "히든키워드는 캡처에서 살아 있어야 한다"


# ── 순위는 「줄이 있나」가 아니라 「값이 있나」로 센다 ──────────────
#
# 순위 줄은 칸 하나가 아니라 다섯 칸짜리 줄의 묶음이다. 줄이 몇 개
# 있다는 사실과 그 줄에 찍을 값이 들었다는 사실은 다르다. 「지표 저장」
# 은 손으로 친 순위를 `{키워드, 순위}` 두 칸으로만 담는데(`collect.
# make_snapshot`), 줄이 있나만 보면 이 얇은 줄이 캡처·애드로그의 다섯
# 칸짜리 줄을 이긴다. 오픈업 상권순위 하나 넣으려고 누른 저장 한 번에
# 헤드라인·기회표·요약 카드·기준일·처방이 함께 사라졌다.

HAND_TYPED_SNAP = {
    "수집시각": "2026-08-20T11:00:00",
    "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
    "순위": [{"키워드": "서초맛집", "순위": 2}],
    "예상매출": {"상권순위": "상위 40%"},
}


def test_has_rank_value_sees_the_fields_the_proposal_prints():
    """키워드가 종이에 닿는 문은 둘뿐이다 — 기회표(조회수)와 처방(비교순위)."""
    from cmo.lib.proposal import _has_rank_value
    assert _has_rank_value({"순위": [{"키워드": "가", "순위": 2, "조회수": 100}]})
    assert _has_rank_value({"순위": [{"키워드": "가", "순위": 2, "비교순위": 9}]})
    assert not _has_rank_value({"순위": [{"키워드": "가", "순위": 2}]})
    assert not _has_rank_value({"순위": [{"키워드": "가", "순위": 2,
                                          "순위권밖": False, "조회수": None,
                                          "비교순위": None}]})
    assert not _has_rank_value({"순위": []})
    assert not _has_rank_value({})


def test_hand_typed_ranks_are_not_counted_as_data():
    """두 칸짜리 손입력 줄은 제안서가 읽을 칸이 없다 — 자료로 세면 안 된다."""
    from cmo.lib.proposal import _has_data
    assert not _has_data({"순위": [{"키워드": "서초맛집", "순위": 2}]})
    assert _has_data({"순위": [{"키워드": "서초맛집", "순위": 2, "조회수": 5740}]})


def test_a_hand_typed_rank_row_does_not_bury_the_capture():
    """「지표 저장」 한 번에 검색 장이 비면 안 된다.

    손입력 줄에는 조회수도 비교순위도 없다. 그 줄이 캡처를 이기면
    사장님 앞에 놓을 근거가 통째로 사라진다.
    """
    client = dict(CLIENT, 스냅샷=[RICH_SNAP, HAND_TYPED_SNAP])
    D = build_payload(client, PLAN, PRODUCTS)["진단자료"]
    검색 = D["검색"]

    assert 검색["헤드라인"] and "서초맛집" in 검색["헤드라인"]
    assert [r["키워드"] for r in 검색["기회표"]][:2] == ["서초맛집", "방배동맛집"]
    assert {c["이름"] for c in 검색["수치"]} >= {"추적 키워드", "TOP 3", "TOP 10"}
    assert 검색["기준일"] == "08-12"
    assert D["처방"], "처방이 사라졌다"


def test_a_hand_typed_save_raises_no_missing_page_warning():
    """장이 다 서 있으면 경고도 조용해야 한다 — 손님 장만 빈다."""
    client = dict(CLIENT, 스냅샷=[RICH_SNAP, HAND_TYPED_SNAP])
    붙인것 = " ".join(_warnings(client))
    assert "검색에서의 자리" not in 붙인것
    assert "순위 변동과 이번 달 처방" not in 붙인것


# ── 요약 카드는 순위를 준 그 스냅샷에서 온다 ────────────────────
#
# 총키워드·TOP3·TOP10 은 기회표와 같은 판독에서 나온 숫자다. 따로 고르면
# 「총 키워드 48개」라고 적힌 카드 밑에 기회표가 두어 줄만 있는 종이가
# 나간다 — 숫자 둘이 서로 다른 시점을 말한다. 종이에 찍히는 날짜
# (`기준일`)도 순위 쪽 것 하나뿐이라, 카드만 다른 날에서 오면 그 카드가
# 남의 날짜를 달고 나간다.

def test_rank_summary_comes_from_the_snapshot_that_gave_the_ranks():
    """순위는 있는데 요약이 없는 스냅샷이 뽑히면 카드가 사라진다 — 그게 맞다.

    그 시점에 요약이 없었다는 게 사실이다. 없는 걸 남의 시점에서
    빌려 오지 않는다.
    """
    요약없는캡처 = {
        "수집시각": "2026-08-20T10:00:00",
        "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
        "순위": [{"키워드": "서초맛집", "순위": 4, "순위권밖": False,
                  "조회수": 5740, "비교순위": None}],
        "순위요약": {"총키워드": None, "TOP3": None, "TOP10": None},
        "진단": {"기준일": "08-19", "비교일": None},
    }
    client = dict(CLIENT, 스냅샷=[RICH_SNAP, 요약없는캡처])
    검색 = build_payload(client, PLAN, PRODUCTS)["진단자료"]["검색"]
    이름들 = {c["이름"] for c in 검색["수치"]}

    assert "추적 키워드" not in 이름들, "08-13 요약이 08-19 순위 위에 올라왔다"
    assert 이름들.isdisjoint({"TOP 3", "TOP 10"})
    assert [r["키워드"] for r in 검색["기회표"]] == ["서초맛집"]
    assert 검색["기준일"] == "08-19"


def test_a_summary_only_capture_does_not_outlive_the_ranks():
    """순위를 한 줄도 못 읽고 요약만 읽힌 캡처가 카드를 갈아치우면 안 된다.

    판독은 플레이스명이나 방문자리뷰만 읽혀도 통과하므로(`read_doc.
    parse_reading`) 이런 캡처가 실제로 저장된다. 리더가 말한
    「총 키워드 48개인데 기회표가 두어 줄인 종이」가 이 입력이다.
    """
    요약만읽힌캡처 = {
        "수집시각": "2026-08-24T10:00:00",
        "플레이스": {"방문자리뷰": 800, "블로그리뷰": None, "저장수": None},
        "순위": [],
        "순위요약": {"총키워드": 48, "TOP3": 9, "TOP10": 20},
        "진단": {"기준일": None, "비교일": None},
    }
    client = dict(CLIENT, 스냅샷=[RICH_SNAP, 요약만읽힌캡처])
    검색 = build_payload(client, PLAN, PRODUCTS)["진단자료"]["검색"]
    이름별 = {c["이름"]: c["값"] for c in 검색["수치"]}

    assert 이름별["추적 키워드"] == "51개", "기회표와 다른 날의 카드가 찍혔다"
    assert 이름별["TOP 3"] == "6개"
    assert 이름별["TOP 10"] == "11개"
    assert len(검색["기회표"]) == 4
    assert 검색["기준일"] == "08-12"


def test_the_summary_stands_when_no_snapshot_has_usable_ranks():
    """순위를 준 스냅샷이 아예 없으면 요약은 그걸 가진 스냅샷에서 읽는다.

    기회표도 헤드라인도 안 서고 기준일도 안 찍히는 매장이다. 어긋날
    상대가 없는데 카드까지 지우면 읽어 둔 값을 버리는 것이다.
    """
    요약과줄만 = {
        "수집시각": "2026-08-24T10:00:00",
        "플레이스": {"방문자리뷰": 800, "블로그리뷰": None, "저장수": None},
        "순위": [{"키워드": "서초맛집", "순위": 4, "순위권밖": False,
                  "조회수": None, "비교순위": None}],
        "순위요약": {"총키워드": 48, "TOP3": 9, "TOP10": 20},
        "진단": {"기준일": "08-23", "비교일": None},
    }
    검색 = build_payload(dict(CLIENT, 스냅샷=[요약과줄만]),
                         PLAN, PRODUCTS)["진단자료"]["검색"]
    이름별 = {c["이름"]: c["값"] for c in 검색["수치"]}

    assert 이름별["추적 키워드"] == "48개", "읽어 둔 요약 카드가 사라졌다"
    assert 검색["기회표"] is None
    assert 검색["기준일"] is None


def test_a_missing_prescription_warns_even_when_reviews_survive():
    """리뷰가 살아 있다고 처방이 빠진 걸 넘기면 안 된다.

    서식은 처방이 없으면 장 제목(`d-moves-title`)을 감추고 리뷰 현황만
    남긴다. 경고는 그 조건과 한 뜻이어야 한다.
    """
    from cmo.lib.proposal import missing_pages
    snap = json.loads(json.dumps(RICH_SNAP, ensure_ascii=False))
    for row in snap["순위"]:
        row["비교순위"] = None            # 처방은 죽이고 리뷰는 살린다
    payload = build_payload(dict(CLIENT, 스냅샷=[snap]), PLAN, PRODUCTS)

    assert payload["진단자료"]["처방"] is None
    assert payload["진단자료"]["리뷰"], "리뷰 현황은 그대로 서야 한다"
    assert "순위 변동과 이번 달 처방" in " ".join(missing_pages(payload))


# ── 플레이스 세 칸을 한 덩이로 고르지 않는다 ────────────────────
#
# 캡처 판독은 플레이스명만 읽히면 통과한다(`read_doc.parse_reading`).
# 그래서 저장수 한 칸만 읽힌 판독이 실제로 만들어지는데, 세 칸을 한 덩이로
# 고르면 그 판독이 앞선 판독의 방문자리뷰·블로그리뷰를 지운다. 서식은 그
# 자리를 `0` 으로 찍는다 — 값이 빠지는 것보다 나쁘다. 없는 걸 0 이라고 말한다.

두터운판독 = {"수집시각": "2026-09-20T09:00:00",
              "플레이스": {"방문자리뷰": 895, "블로그리뷰": 619, "저장수": 8000}}


def test_place_fields_are_read_one_box_at_a_time():
    """저장수만 읽힌 판독이 앞선 판독의 리뷰수 둘을 가리면 안 된다."""
    저장수만 = {"수집시각": "2026-09-22T09:00:00",
                "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": 8100}}
    payload = build_payload(dict(CLIENT, 스냅샷=[두터운판독, 저장수만]),
                            PLAN, PRODUCTS)

    assert payload["지표"]["방문자리뷰"] == 895
    assert payload["지표"]["블로그리뷰"] == 619
    수치 = {c["이름"]: c["값"] for c in payload["진단자료"]["검색"]["수치"]}
    assert 수치["방문자 리뷰"] == "895건"
    assert 수치["저장수"] == "8,100개", "저장수는 새 판독 것이어야 한다"
    assert payload["진단자료"]["리뷰"]["방문자수"] == 895
    assert payload["진단자료"]["리뷰"]["블로그수"] == 619


def test_a_reading_without_the_save_count_keeps_the_earlier_one():
    """반대 방향도 같다 — 리뷰수만 읽힌 판독이 앞선 저장수를 지우면 안 된다."""
    리뷰수만 = {"수집시각": "2026-09-22T09:00:00",
                "플레이스": {"방문자리뷰": 910, "블로그리뷰": 630, "저장수": None}}
    payload = build_payload(dict(CLIENT, 스냅샷=[두터운판독, 리뷰수만]),
                            PLAN, PRODUCTS)

    수치 = {c["이름"]: c["값"] for c in payload["진단자료"]["검색"]["수치"]}
    assert 수치["방문자 리뷰"] == "910건"
    assert 수치["저장수"] == "8,000개", "저장수가 사라졌다"


# ── 상권순위도 칸별로 읽는다 ────────────────────────────────────
#
# 사용법은 `플레이스 직접 긁기` 를 꺼 두라고 권하고 기본값도 꺼져 있다.
# 그래서 오픈업 상권순위만 넣는 저장이 **정상 경로**인데, 상권순위를
# 플레이스 값으로 골라서 그 스냅샷이 한 번도 안 뽑혔다 — 넣은 값이
# 제안서에 아예 안 갔다. I-1 과 같은 뿌리다.

상권순위만 = {"수집시각": "2026-09-22T11:00:00",
              "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
              "순위": [],
              "예상매출": {"월매출": None, "상권순위": "상위 40%",
                           "출처": "오픈업", "입력방식": "수동"}}


def test_the_market_rank_is_read_from_the_snapshot_that_has_it():
    """예상매출만 든 스냅샷에서도 상권순위가 제안서로 가야 한다."""
    payload = build_payload(dict(CLIENT, 스냅샷=[상권순위만]), PLAN, PRODUCTS)
    assert payload["지표"]["상권순위"] == "상위 40%"


def test_a_later_capture_does_not_erase_the_market_rank():
    """캡처가 뒤에 와도 앞서 넣은 상권순위는 살아 있어야 한다.

    캡처 스냅샷에는 예상매출이 없다(`read_doc.snapshot_from`).
    """
    캡처 = {"수집시각": "2026-09-23T09:00:00",
            "플레이스": {"방문자리뷰": 895, "블로그리뷰": 619, "저장수": 8000},
            "순위": [], "예상매출": None}
    payload = build_payload(dict(CLIENT, 스냅샷=[상권순위만, 캡처]), PLAN, PRODUCTS)
    assert payload["지표"]["상권순위"] == "상위 40%"


def test_an_empty_market_rank_box_does_not_bury_the_earlier_one():
    """월매출만 넣은 저장은 `{"상권순위": ""}` 를 남긴다(`app/client.js`).

    빈 글자를 값으로 세면 그 저장이 앞서 넣어 둔 상권순위를 가린다.
    다섯 번 밟은 함정이 예상매출 쪽에서 되풀이되는 자리다.
    """
    월매출만 = {"수집시각": "2026-09-23T11:00:00",
                "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
                "순위": [],
                "예상매출": {"월매출": 42000000, "상권순위": "",
                             "출처": "오픈업", "입력방식": "수동"}}
    payload = build_payload(dict(CLIENT, 스냅샷=[상권순위만, 월매출만]),
                            PLAN, PRODUCTS)
    assert payload["지표"]["상권순위"] == "상위 40%"


def test_has_revenue_value_sees_the_box_the_proposal_prints():
    """제안서가 예상매출에서 읽는 칸은 상권순위 하나다 — 월매출은 안 나간다."""
    from cmo.lib.proposal import _has_revenue_value
    assert _has_revenue_value({"예상매출": {"상권순위": "상위 40%"}})
    assert not _has_revenue_value({"예상매출": {"월매출": 42000000,
                                                "상권순위": ""}})
    assert not _has_revenue_value({"예상매출": {"상권순위": None}})
    assert not _has_revenue_value({"예상매출": None})
    assert not _has_revenue_value({})


def test_a_snapshot_with_only_the_market_rank_counts_as_data():
    """상권순위 한 칸만 든 스냅샷도 자료다 — 제안서가 읽는 칸이다."""
    from cmo.lib.proposal import _has_data
    assert _has_data({"예상매출": {"상권순위": "상위 40%"}})
    assert not _has_data({"예상매출": {"월매출": 42000000, "상권순위": ""}})


# ── 리뷰도 「줄이 있나」가 아니라 「값이 있나」로 센다 ──────────────
#
# 판정 함수 넷 중 이것만 리스트가 비었나만 봤다. `_review_rows` 는 제목만
# 있으면 줄을 남기고(`read_doc`), `_reviews` 는 조회수 있는 방문자 줄만
# 쓴다. 그래서 조회수를 못 읽은 한 줄짜리 캡처나 블로그만 읽힌 캡처가
# 앞선 캡처의 「많이 읽힌 리뷰」를 지웠다. 이 저장소가 다섯 번 밟은 함정의
# 마지막 자리다.

리뷰있는캡처 = {
    "수집시각": "2026-08-13T09:00:00",
    "플레이스": {"방문자리뷰": 775, "블로그리뷰": 1415, "저장수": 100},
    "순위": [], "예상매출": None,
    "진단": {"기준일": "08-12", "비교일": None,
             "리뷰": {"방문자": [{"제목": "아이들이 한우 먹고싶다고", "조회수": 1479,
                                  "작성일": "2026-07-16"}],
                      "블로그": []}},
}


def _많이읽힌(스냅샷들):
    payload = build_payload(dict(CLIENT, 스냅샷=스냅샷들), PLAN, PRODUCTS)
    return [r["제목"] for r in payload["진단자료"]["리뷰"]["많이읽힌"]]


def test_a_capture_that_lost_the_view_counts_keeps_the_earlier_reviews():
    """조회수를 못 읽은 리뷰 한 줄짜리 캡처가 앞선 리뷰를 지우면 안 된다."""
    조회수없는캡처 = {
        "수집시각": "2026-08-26T09:00:00",
        "플레이스": {"방문자리뷰": 800, "블로그리뷰": 1500, "저장수": 110},
        "순위": [], "예상매출": None,
        "진단": {"기준일": "08-25", "비교일": None,
                 "리뷰": {"방문자": [{"제목": "조회수를 못 읽은 리뷰",
                                      "조회수": None, "작성일": "2026-08-20"}],
                          "블로그": []}},
    }
    assert _많이읽힌([리뷰있는캡처, 조회수없는캡처]) == ["아이들이 한우 먹고싶다고"]


def test_a_blog_only_capture_keeps_the_earlier_reviews():
    """블로그 줄만 읽힌 캡처도 같다 — 블로그는 종이에 한 글자도 안 나간다."""
    블로그만읽힌캡처 = {
        "수집시각": "2026-08-26T09:00:00",
        "플레이스": {"방문자리뷰": 800, "블로그리뷰": 1500, "저장수": 110},
        "순위": [], "예상매출": None,
        "진단": {"기준일": "08-25", "비교일": None,
                 "리뷰": {"방문자": [],
                          "블로그": [{"제목": "방배동 소고기 맛집 추천",
                                      "작성일": "2026-05-26"}]}},
    }
    assert _많이읽힌([리뷰있는캡처, 블로그만읽힌캡처]) == ["아이들이 한우 먹고싶다고"]


def test_a_thin_capture_does_not_silently_empty_the_review_page():
    """얇은 캡처 한 번에 리뷰 장이 통째로 사라지면서 경고도 안 뜨는 일이 없어야 한다.

    최종 리뷰 I-1(플레이스를 덩이로 고른다)과 겹쳤을 때의 모양이다.
    저장수만 읽힌 캡처가 리뷰 건수를 지우고, 조회수 없는 리뷰 줄이 목록을
    지우면 `_reviews` 가 `None` 을 낸다. 그런데 경고는 처방만 보므로
    (`MISSING_MOVES`) 조용하다 — 빠진 줄 모르고 나가는 바로 그 모양이다.
    """
    from cmo.lib.proposal import missing_pages
    얇은캡처 = {
        "수집시각": "2026-08-26T09:00:00",
        "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": 8100},
        "순위": [], "예상매출": None,
        "진단": {"기준일": "08-25", "비교일": None,
                 "리뷰": {"방문자": [{"제목": "조회수를 못 읽은 리뷰",
                                      "조회수": None}], "블로그": []}},
    }
    payload = build_payload(dict(CLIENT, 스냅샷=[리뷰있는캡처, 얇은캡처]),
                            PLAN, PRODUCTS)
    리뷰 = payload["진단자료"]["리뷰"]

    assert 리뷰, "리뷰 장이 통째로 사라졌다 — 경고도 안 뜨는 자리다"
    assert 리뷰["방문자수"] == 775
    assert [r["제목"] for r in 리뷰["많이읽힌"]] == ["아이들이 한우 먹고싶다고"]
    assert "리뷰" not in " ".join(missing_pages(payload))
