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
    """수입이 덜 된 걸 잡는다.

    기준이 45 였는데 25 로 내렸다 — 안 파는 상품 25종을 `_제외` 로
    걸러내면서 목록이 30종이 됐다. 제외 규칙이 너무 넓어지는 쪽은
    test_enough_products_survive_the_exclusion 이 따로 본다.
    """
    assert len(products) >= 25, f"상품이 {len(products)}종뿐이다. 수입이 덜 됐다"


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


def test_discontinued_products_are_dropped(products):
    """없어진 상품은 목록에 아예 안 나온다.

    예전에는 남겨 두고 잠갔다 — 「예전에 하던 그거」를 사장님이 물을 때
    화면에서 짚어 주려던 것이다. 안 팔기로 하면서 뺐다. 서랍이 짧을수록
    미팅에서 손이 빠르다. 규칙은 overrides.json 의 `_제외.판매중지` 다.
    """
    by_name = {p["상품명"]: p for p in products}
    for name in DISCONTINUED:
        assert name not in by_name, f"판매중지 상품 '{name}' 이 아직 있다"


def test_no_product_is_locked(products):
    """판매중지를 전부 뺐으므로 목록에 잠긴 상품이 하나도 없어야 한다."""
    locked = [p["상품명"] for p in products if p["판매중지"]]
    assert locked == [], f"잠긴 상품이 남아 있다: {locked}"


def test_enough_products_survive_the_exclusion(products):
    """제외 규칙이 너무 넓어져 서랍이 텅 비면 여기서 잡는다."""
    assert len(products) >= 25


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
    """시트에 있는 (매체, 상품명) 조합이 products.json 에서 조용히 빠지면 여기서 잡는다.

    build_products 의 스킵 규칙(매체/상품명 공백, 가격·원가·프로세스 전부 공백)이
    나중에 시트가 갱신되면서 진짜 상품 행을 걸러버릴 수 있다. 26행(커뮤니티외
    먹스타PPL), 51행(먹스타 기자단 패키지)이 실제로 이렇게 걸렸었고
    overrides.json 의 "_추가" 목록으로 되살렸다 — 회귀를 막는 가드 테스트다.

    반드시 (매체, 상품명) 튜플로 비교한다. 상품명만 비교하면 동명이품에서
    한쪽이 조용히 빠져도 짝이 되는 이름이 남아 있어 테스트가 무력화된다.
    TSV 에 이미 이런 동명이품이 3쌍 있다: SA(네이버/구글), DA(네이버/구글),
    리뷰작업(구글/카카오).

    제외 목록:
    - ("기타", "디자인팀 / 영상사업부 / 개발팀 연계"): 52행. 가격·원가·
      프로세스 칸이 전부 비어 있는 진짜 비상품 행(다른 팀 연계 안내문)이라
      build_products 가 의도적으로 건너뛴다.

    매체 칸이 통째로 빈 행(51행, "먹스타 기자단 패키지")은 TSV 만 봐서는
    (매체, 상품명) 튜플을 만들 수 없다 — 그게 애초에 이 행이 스킵되던
    원인이다. 이런 행은 overrides.json 의 "_추가" 목록에 그 상품명으로
    명시적으로 등록돼 있고, 그게 실제로 products.json 에 존재할 때만
    통과시킨다. "매체 칸이 비었으면 이름만 맞아도 봐준다"는 식으로
    풀면 안 된다 — 그러면 카카오-리뷰작업처럼 이미 동명이품이 있는
    상품의 매체 칸이 나중에 빈 채로 새로 생겨도, 짝(구글-리뷰작업)의
    이름이 남아 있어 조용히 통과해버린다(직접 재현해서 확인함, 아래
    "회귀 가드 확인" 참고). `_추가` 로 명시 등록된 이름만 예외로 인정해야
    이 사각지대가 막힌다.
    """
    EXCLUDED_PAIRS = {
        ("기타", "디자인팀 / 영상사업부 / 개발팀 연계"),
    }

    tsv_path = cmo_dir / "data" / "_source" / "products.tsv"
    lines = [ln for ln in tsv_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    tsv_pairs = set()      # (매체, 상품명) — 매체 칸이 채워진 행만
    tsv_name_only = set()  # 매체 칸이 빈 행의 상품명 — _추가 등록 여부로만 검사
    for ln in lines[2:]:  # 0=안내문, 1=머리글
        cells = ln.split("\t")
        if len(cells) < 2:
            continue
        media, name = cells[0].strip(), cells[1].strip()
        if not name:
            continue
        if media:
            tsv_pairs.add((media, name))
        else:
            tsv_name_only.add(name)

    tsv_pairs -= EXCLUDED_PAIRS

    # 일부러 뺀 상품은 「조용히 사라진 것」이 아니다. overrides._제외 에
    # 적힌 것만 면제한다 — 규칙을 여기 다시 적으면 두 벌이 된다.
    from cmo.tools.import_tsv import make_id

    overrides_for_drop = json.loads(
        (cmo_dir / "data" / "overrides.json").read_text(encoding="utf-8"))
    rule = overrides_for_drop.get("_제외") or {}
    dropped_ids = set(rule.get("상품id") or [])
    dropped_media = set(rule.get("매체") or [])
    tsv_pairs = {(m, n) for m, n in tsv_pairs
                 if m not in dropped_media and make_id(m, n) not in dropped_ids}

    product_pairs = {(p["매체"], p["상품명"]) for p in products}
    product_names = {p["상품명"] for p in products}

    missing_pairs = tsv_pairs - product_pairs
    assert not missing_pairs, f"TSV에는 있지만 products.json에는 없는 (매체,상품명): {missing_pairs}"

    overrides_path = cmo_dir / "data" / "overrides.json"
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    added_names = {item["상품명"] for item in overrides.get("_추가", [])}

    unrecovered = tsv_name_only - added_names
    assert not unrecovered, (
        f"매체 칸이 빈 TSV 상품인데 overrides._추가로 복구되지 않았다: {unrecovered}"
    )

    still_missing = (tsv_name_only & added_names) - product_names
    assert not still_missing, (
        f"overrides._추가에 등록됐지만 products.json에 실제로 없다: {still_missing}"
    )


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
