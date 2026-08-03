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


def test_all_tsv_products_present(products, cmo_dir):
    """시트에 있는 상품명이 products.json 에서 조용히 빠지면 여기서 잡는다.

    build_products 의 스킵 규칙(매체/상품명 공백, 가격·원가·프로세스 전부 공백)이
    나중에 시트가 갱신되면서 진짜 상품 행을 걸러버릴 수 있다. 26행(커뮤니티외
    먹스타PPL), 51행(먹스타 기자단 패키지)이 실제로 이렇게 걸렸었고
    overrides.json 의 "_추가" 목록으로 되살렸다 — 회귀를 막는 가드 테스트다.

    제외 목록:
    - "디자인팀 / 영상사업부 / 개발팀 연계": 52행. 매체="기타", 가격·원가·
      프로세스 칸이 전부 비어 있는 진짜 비상품 행(다른 팀 연계 안내문)이라
      build_products 가 의도적으로 건너뛴다.
    """
    EXCLUDED_NAMES = {
        "디자인팀 / 영상사업부 / 개발팀 연계",
    }

    tsv_path = cmo_dir / "data" / "_source" / "products.tsv"
    lines = [ln for ln in tsv_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    tsv_names = set()
    for ln in lines[2:]:  # 0=안내문, 1=머리글
        cells = ln.split("\t")
        if len(cells) < 2:
            continue
        name = cells[1].strip()
        if name:
            tsv_names.add(name)

    product_names = {p["상품명"] for p in products}
    missing = (tsv_names - EXCLUDED_NAMES) - product_names
    assert not missing, f"TSV에는 있지만 products.json에는 없는 상품: {missing}"


def test_added_product_gijadan_package_is_pinned(products):
    """overrides._추가로 되살린 상품의 정가가 바뀌지 않았는지 고정한다."""
    p = next(p for p in products if p["id"] == "인스타-먹스타_기자단_패키지")
    assert p["가격유형"] == "고정"
    assert p["정가"] == 1800000


def test_sangsaeng_party_cost_is_pinned(products):
    """'대략 3000000(3600000)' 을 수동 판정한 값이 바뀌지 않았는지 고정한다."""
    p = next(p for p in products if p["id"] == "IMC-상생_먹스타_파티")
    assert p["실비"] == 3000000
    assert p["실비_내부이체"] == 3600000
