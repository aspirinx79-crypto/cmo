"""순위 변동 처방 — 순수 함수.

원인은 쓰지 않는다. 관측된 것과 우리가 할 것만 쓴다.
"""
import json
from pathlib import Path

from cmo.lib.prescription import (
    DOWN_LINE,
    NONE,
    PUSH,
    ROLE,
    SUPPORT,
    UP_LINE,
    placements,
    prescribe,
    role_of,
)

CMO = Path(__file__).resolve().parent.parent


def _active_products() -> list[dict]:
    rows = json.loads((CMO / "data" / "products.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("상품") or rows.get("products") or []
    return [r for r in rows if not r.get("판매중지")]


def test_every_active_product_has_a_role():
    """새 상품이 조용히 새는 것을 막는다.

    표에 없는 상품은 `제외`로 떨어져 처방에서 빠진다. 조용히 빠지면
    아무도 모르니 여기서 잡는다 — 이 테스트가 이 작업에서 가장 오래
    살아남는다.
    """
    빠진것 = [p["id"] for p in _active_products() if p["id"] not in ROLE]
    assert 빠진것 == [], f"분류표에 없는 판매중 상품: {빠진것}"


def test_role_counts_match_the_design():
    있는것 = [p["id"] for p in _active_products()]
    센다 = lambda 갈래: sum(1 for i in 있는것 if ROLE.get(i) == 갈래)
    assert (센다(PUSH), 센다(SUPPORT), 센다(NONE)) == (7, 13, 10)


def test_unknown_product_falls_back_to_none():
    """지워진 상품이 기획안에 남아 있어도 터지지 않는다."""
    assert role_of("없는-상품") == NONE


LINES = [
    {"상품id": "네이버-서비스툴관리", "상품명": "서비스툴관리", "수량표시": "1건"},
    {"상품id": "네이버-자동완성어", "상품명": "자동완성어", "수량표시": "1건"},
    {"상품id": "네이버-SA", "상품명": "SA", "수량표시": "월 150,000원 집행"},
    {"상품id": "네이버-블로그_일반_체험단", "상품명": "블로그 일반 체험단",
     "수량표시": "5팀"},
    {"상품id": "카카오-리뷰작업", "상품명": "리뷰작업", "수량표시": "5건"},
    {"상품id": "인스타-먹스타_PPL", "상품명": "먹스타 PPL", "수량표시": "1식"},
]
변화 = {
    "기준일": "2026-08-12", "비교일": "2026-06-12",
    "오름": [{"키워드": "잠실종합운동장맛집", "전": "12위", "후": "8위"}],
    "내림": [{"키워드": "송파양꼬치", "전": "7위", "후": "14위"}],
}


def test_placements_pick_only_that_role():
    """기반(서비스툴관리)과 브랜딩(PPL)은 어느 쪽에도 안 붙는다."""
    assert placements(LINES, PUSH) == ["자동완성어 1건", "SA 월 150,000원 집행"]
    assert placements(LINES, SUPPORT) == ["블로그 일반 체험단 5팀", "리뷰작업 5건"]


def test_prescription_carries_both_directions():
    got = prescribe(변화, LINES)
    assert got["오름문장"] == UP_LINE
    assert got["내림문장"] == DOWN_LINE
    assert got["오름배치"] == ["자동완성어 1건", "SA 월 150,000원 집행"]
    assert got["내림배치"] == ["블로그 일반 체험단 5팀", "리뷰작업 5건"]
    assert got["기준일"] == "2026-08-12"


def test_no_matching_items_means_no_placement_line():
    """빈 약속을 만들지 않는다. 「이번 달 배치 —」 뒤가 비면 안 된다."""
    기반만 = [LINES[0], LINES[5]]
    got = prescribe(변화, 기반만)
    assert got["오름배치"] == []
    assert got["내림배치"] == []
    assert got["오름문장"] == UP_LINE      # 원칙 문장은 남는다


def test_one_sided_movement_keeps_only_that_side():
    한쪽 = {**변화, "내림": []}
    got = prescribe(한쪽, LINES)
    assert got["내림"] == []
    assert got["내림문장"] is None
    assert got["내림배치"] == []


def test_no_movement_at_all_gives_nothing():
    assert prescribe(None, LINES) is None
    assert prescribe({"오름": [], "내림": []}, LINES) is None


def test_sentences_never_claim_a_cause():
    """원인은 확인할 수 없다. 한 번 틀리면 제안서 전체가 무너진다."""
    for 문장 in (UP_LINE, DOWN_LINE):
        for 금칙 in ("때문", "탓", "경쟁", "원인"):
            assert 금칙 not in 문장


def test_sentences_never_promise_a_result():
    """우리가 **할 일**만 쓴다. 결과는 약속하지 않는다.

    이 검사가 없던 사이 `DOWN_LINE` 이 "…총량으로 되돌립니다" 였다.
    떨어진 키워드 바로 옆에서 순위를 되돌려 주겠다고 말한 셈이다.
    카탈로그는 같은 상품에 「상위노출 보장은 아니란거 고지」를 달아 두고
    있는데, 제안서가 그 반대를 약속하면 그 고지가 무슨 소용인가.

    `가장`·`확실` 은 효과 크기를 단정하는 말이라 같이 막는다 — 스냅샷은
    순위만 재지 효과 크기를 재지 않는다.
    """
    for 문장 in (UP_LINE, DOWN_LINE):
        for 금칙 in ("보장", "되돌", "올려드", "약속", "가장", "확실", "무조건"):
            assert 금칙 not in 문장, f"결과를 약속했다: {문장}"
