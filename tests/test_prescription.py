"""순위 변동 처방 — 순수 함수.

원인은 쓰지 않는다. 관측된 것과 우리가 할 것만 쓴다.
"""
import json
from pathlib import Path

from cmo.lib.prescription import NONE, PUSH, ROLE, SUPPORT, role_of

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
