import pytest

from cmo.lib.schedule import parse_steps, weekly_plan

EXPERIENCE = {
    "id": "네이버-블로그_일반_체험단", "상품명": "블로그 일반 체험단",
    "프로세스": "클라이언트에게 양식 받기->5-7일 모집/1일 선정/1일 명단발표/14-20일 체험,포스팅/ 2영업일 후 보고서",
}
TOOLS = {
    "id": "네이버-서비스툴관리", "상품명": "서비스툴관리",
    "프로세스": "단톡방 소통",
}


def test_parse_steps_splits_on_arrows_and_slashes():
    steps = parse_steps(EXPERIENCE["프로세스"])
    labels = [s["단계"] for s in steps]
    assert labels[0].startswith("클라이언트에게 양식 받기")
    assert any("모집" in s for s in labels)
    assert any("보고서" in s for s in labels)


def test_parse_steps_reads_upper_bound_of_day_range():
    """'5-7일 모집' 은 최악의 경우로 7일을 잡는다."""
    steps = parse_steps(EXPERIENCE["프로세스"])
    recruit = next(s for s in steps if "모집" in s["단계"])
    assert recruit["일수"] == 7


def test_parse_steps_without_days_is_zero():
    steps = parse_steps(TOOLS["프로세스"])
    assert len(steps) == 1
    assert steps[0]["일수"] == 0


def test_parse_steps_empty_process():
    assert parse_steps("") == []


def test_weekly_plan_has_four_weeks():
    plan = weekly_plan([EXPERIENCE], [{"상품id": EXPERIENCE["id"]}])
    assert [w["주차"] for w in plan] == [1, 2, 3, 4]


def test_weekly_plan_places_recruiting_in_week_one():
    plan = weekly_plan([EXPERIENCE], [{"상품id": EXPERIENCE["id"]}])
    week1 = " ".join(plan[0]["항목"])
    assert "모집" in week1


def test_weekly_plan_places_report_in_last_week():
    """양식받기0 + 모집7 + 선정1 + 명단1 + 체험20 = 29일차에 보고서 → 4주차."""
    plan = weekly_plan([EXPERIENCE], [{"상품id": EXPERIENCE["id"]}])
    week4 = " ".join(plan[3]["항목"])
    assert "보고서" in week4


def test_weekly_plan_labels_include_product_name():
    plan = weekly_plan([EXPERIENCE], [{"상품id": EXPERIENCE["id"]}])
    assert any("블로그 일반 체험단" in line for line in plan[0]["항목"])


def test_weekly_plan_no_day_info_goes_to_week_one():
    plan = weekly_plan([TOOLS], [{"상품id": TOOLS["id"]}])
    assert any("서비스툴관리" in line for line in plan[0]["항목"])
    assert plan[1]["항목"] == []


def test_weekly_plan_ignores_unknown_product():
    plan = weekly_plan([TOOLS], [{"상품id": "없는-상품"}])
    assert all(w["항목"] == [] for w in plan)


# 시트 원문이 일수 사이에 '/' 없이 공백만 써서(예: "10일 모집 10일 체험 10일 포스팅")
# parse_steps 가 세 단계를 하나로 뭉쳐 첫 일수만 읽는 상품이 있었다. overrides.json 이
# 이 두 상품의 프로세스 표기를 '/' 로 정규화했다 (소요일수는 그대로 30). 실제
# products.json 을 써서 정규화가 적용됐는지, 그리고 회귀하지 않는지 검증한다.
@pytest.mark.parametrize("product_id", [
    "네이버-블로그_프리미엄_체험단",
    "인스타-인스타_체험단",
])
def test_weekly_plan_spreads_normalized_experience_products_across_weeks(products, product_id):
    plan = weekly_plan(products, [{"상품id": product_id}])
    weeks_with_items = [w["주차"] for w in plan if w["항목"]]
    assert len(weeks_with_items) > 1, (
        f"{product_id} 의 단계가 1주차에만 몰려 있다 — overrides.json 정규화가 안 먹었다."
    )


def test_parse_steps_day_sum_matches_소요일수_for_every_product(products):
    """프로세스가 있는 모든 상품에서, parse_steps 가 낸 단계별 일수의 합이
    import_tsv.py 가 계산한 소요일수(parse_days)와 같아야 한다. 어긋나면
    구분자 표기 문제(공백만 쓰고 '/' 가 없는 등)로 단계가 뭉쳐 일정표가
    실제보다 짧게 표시된다는 신호다."""
    mismatches = [
        (p["id"], sum(s["일수"] for s in parse_steps(p["프로세스"])), p["소요일수"])
        for p in products
        if p.get("프로세스")
    ]
    mismatches = [m for m in mismatches if m[1] != m[2]]
    assert mismatches == []
