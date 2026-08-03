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
