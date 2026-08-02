import json

from cmo.tools.import_tsv import parse_price, parse_cost

DISCONTINUED = [
    "블로그 상위노출 월보장", "지식인 상위노출 월보장",
    "포스트 관련 상품", "연관검색어 작업", "지식인 배포",
]
VALID_TYPES = {"고정", "직접입력", "예산배율", "등급선택"}


def test_parse_price_fixed():
    assert parse_price("₩ 30,000") == ("고정", 30000, None)
    assert parse_price("₩ 3,000,000") == ("고정", 3000000, None)


def test_parse_price_budget_multiplier():
    assert parse_price("예산의 1.3배") == ("예산배율", None, 1.3)
    assert parse_price("예산별") == ("예산배율", None, None)


def test_parse_price_manual():
    for text in ["협의", "셀럽별 상이", "먹스타별 상이", "키워드별 상이", "매체별 상이", ""]:
        kind, amount, mult = parse_price(text)
        assert kind == "직접입력", f"{text!r} 이 직접입력으로 판정되지 않았다"
        assert amount is None


def test_parse_cost_plain():
    assert parse_cost("₩ 8,000") == (8000, None)
    assert parse_cost("₩ -") == (0, None)


def test_parse_cost_with_internal_transfer():
    """괄호 값은 먹스타계좌 이체분이다. 실비는 괄호 밖 금액을 쓴다."""
    assert parse_cost("480000(200000)") == (480000, 200000)
    assert parse_cost("1440(1200)") == (1440, 1200)


def test_parse_cost_open_ended():
    """'20000~' 는 하한이다. 하한을 실비로 쓴다."""
    assert parse_cost("20000~") == (20000, None)


def test_parse_cost_non_numeric():
    for text in ["협의", "레뷰 협의", "예산별", "등급별 상이"]:
        assert parse_cost(text) == (None, None)


def test_all_products_load(products):
    assert len(products) >= 45, f"상품이 {len(products)}종뿐이다. 수입이 덜 됐다"


def test_every_product_has_valid_type(products):
    for p in products:
        assert p["가격유형"] in VALID_TYPES, f"{p['id']}: 알 수 없는 가격유형 {p['가격유형']}"


def test_ids_are_unique(products):
    ids = [p["id"] for p in products]
    assert len(ids) == len(set(ids)), "중복 id가 있다"


def test_fixed_products_have_margin(products):
    """고정 유형은 정가가 실비보다 커야 한다. 역전되면 팔수록 손해다."""
    for p in products:
        if p["가격유형"] == "고정" and p["실비"] is not None:
            assert p["정가"] >= p["실비"], f"{p['id']}: 정가 {p['정가']} < 실비 {p['실비']}"


def test_discontinued_products_present_and_locked(products):
    by_name = {p["상품명"]: p for p in products}
    for name in DISCONTINUED:
        assert name in by_name, f"판매중지 상품 '{name}' 이 없다"
        assert by_name[name]["판매중지"] is True


def test_active_products_are_not_locked(products):
    active = [p for p in products if not p["판매중지"]]
    assert len(active) >= 45


def test_budget_multiplier_products_have_rate(products):
    for p in products:
        if p["가격유형"] == "예산배율":
            assert isinstance(p["예산배율"], (int, float)), f"{p['id']}: 배율이 없다"
            assert p["예산배율"] >= 1.0


def test_meta_target_ad_is_1_3(products):
    """시트에 '예산의 1.3배'로 명시된 유일한 항목이다. 값이 바뀌면 마진이 틀어진다."""
    meta = next(p for p in products if p["id"] == "메타-타겟광고")
    assert meta["가격유형"] == "예산배율"
    assert meta["예산배율"] == 1.3


def test_grade_products_have_options(products):
    for p in products:
        if p["가격유형"] == "등급선택":
            assert len(p["등급"]) >= 2, f"{p['id']}: 등급 옵션이 부족하다"
            for g in p["등급"]:
                assert {"이름", "정가", "실비"} <= set(g)
