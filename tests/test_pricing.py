import pytest

from cmo.lib.pricing import line_amount, summarize

FIXED = {
    "id": "네이버-블로그_일반_체험단", "상품명": "블로그 일반 체험단",
    "가격유형": "고정", "정가": 30000, "실비": 8000,
    "최소수량": 5, "단위": "팀", "판매중지": False,
}
META = {
    "id": "메타-타겟광고", "상품명": "타겟광고",
    "가격유형": "예산배율", "정가": None, "실비": None,
    "예산배율": 1.3, "최소수량": 1, "단위": "원", "판매중지": False,
}
MANUAL = {
    "id": "네이버-플레이스_트래픽", "상품명": "플레이스 트래픽",
    "가격유형": "직접입력", "정가": None, "실비": None,
    "최소수량": 1, "단위": "건", "판매중지": False,
}
GRADE = {
    "id": "포털-언론송출", "상품명": "언론송출", "가격유형": "등급선택",
    "정가": None, "실비": None, "최소수량": 1, "단위": "건", "판매중지": False,
    "등급": [
        {"이름": "일반~B급", "정가": 150000, "실비": 100000},
        {"이름": "A급", "정가": 300000, "실비": 200000},
    ],
}
DEAD = {
    "id": "네이버-지식인_배포", "상품명": "지식인 배포",
    "가격유형": "직접입력", "정가": None, "실비": None,
    "최소수량": 1, "단위": "건", "판매중지": True,
}


def test_fixed_multiplies_by_quantity():
    got = line_amount(FIXED, {"상품id": FIXED["id"], "수량": 10})
    assert got == {"정가": 300000, "실비": 80000}


def test_budget_multiplier_uses_budget_as_cost():
    """실비는 집행예산 그대로, 정가는 예산 × 배율."""
    got = line_amount(META, {"상품id": META["id"], "예산": 1000000})
    assert got == {"정가": 1300000, "실비": 1000000}


def test_budget_multiplier_rounds_to_won():
    got = line_amount(META, {"상품id": META["id"], "예산": 333333})
    assert got["정가"] == 433333
    assert isinstance(got["정가"], int)


def test_manual_uses_typed_values():
    got = line_amount(MANUAL, {"상품id": MANUAL["id"], "정가": 500000, "실비": 200000})
    assert got == {"정가": 500000, "실비": 200000}


def test_grade_looks_up_selected_option():
    got = line_amount(GRADE, {"상품id": GRADE["id"], "등급": "A급", "수량": 2})
    assert got == {"정가": 600000, "실비": 400000}


def test_grade_unknown_option_raises():
    with pytest.raises(ValueError, match="등급"):
        line_amount(GRADE, {"상품id": GRADE["id"], "등급": "SSS급", "수량": 1})


def test_unknown_price_kind_raises_without_leaking_amount():
    """오타·미지원 가격유형은 조용히 0원이 아니라 시끄럽게 실패해야 한다."""
    typo = {**FIXED, "가격유형": "예산배수"}
    with pytest.raises(ValueError) as exc_info:
        line_amount(typo, {"상품id": typo["id"], "수량": 10, "정가": 999999, "실비": 888888})
    message = str(exc_info.value)
    assert typo["상품명"] in message
    assert "예산배수" in message
    assert "999999" not in message
    assert "888888" not in message


def test_summary_core_numbers():
    """스펙의 예시: 정가 150만 / 계약가 100만 / 실비 40만."""
    products = [FIXED, MANUAL]
    items = [
        {"상품id": FIXED["id"], "수량": 10},                       # 정가 30만 / 실비 8만
        {"상품id": MANUAL["id"], "정가": 1200000, "실비": 320000},  # 정가 120만 / 실비 32만
    ]
    s = summarize(products, items, 계약가=1000000)
    assert s["정가합"] == 1500000
    assert s["실비합"] == 400000
    assert s["마진"] == 600000
    assert s["마진율"] == pytest.approx(0.60)
    assert s["혜택배율"] == pytest.approx(1.5)


def test_summary_returns_per_line_amounts():
    """화면이 줄별 금액을 쓰려고 항목마다 서버를 다시 부르면 안 된다."""
    products = [FIXED, MANUAL]
    items = [
        {"상품id": FIXED["id"], "수량": 10},
        {"상품id": MANUAL["id"], "정가": 1200000, "실비": 320000},
    ]
    s = summarize(products, items, 계약가=1000000)
    by_id = {line["상품id"]: line for line in s["줄별"]}
    assert by_id[FIXED["id"]]["정가"] == 300000
    assert by_id[MANUAL["id"]]["정가"] == 1200000
    assert sum(line["정가"] for line in s["줄별"]) == s["정가합"]


def test_summary_line_order_matches_input():
    products = [FIXED, MANUAL]
    items = [
        {"상품id": MANUAL["id"], "정가": 1200000, "실비": 320000},
        {"상품id": FIXED["id"], "수량": 10},
    ]
    s = summarize(products, items, 계약가=1000000)
    assert [line["상품id"] for line in s["줄별"]] == [MANUAL["id"], FIXED["id"]]


def test_summary_warns_below_minimum_quantity():
    s = summarize([FIXED], [{"상품id": FIXED["id"], "수량": 3}], 계약가=1000000)
    assert any("5" in w and "블로그 일반 체험단" in w for w in s["경고"])


def test_summary_warns_on_discontinued():
    s = summarize([DEAD], [{"상품id": DEAD["id"], "정가": 1, "실비": 1}], 계약가=100)
    assert any("판매중지" in w for w in s["경고"])


def test_summary_warns_on_missing_manual_price():
    """직접입력 항목의 정가가 비면 혜택 배율이 성립하지 않는다."""
    s = summarize([MANUAL], [{"상품id": MANUAL["id"], "실비": 100000}], 계약가=1000000)
    assert any("정가" in w for w in s["경고"])


def test_summary_allows_budget_overrun():
    """예산 초과를 막지 않는다. 미팅에서 일부러 넘겨놓고 협상한다."""
    s = summarize([FIXED], [{"상품id": FIXED["id"], "수량": 100}], 계약가=100000)
    assert s["정가합"] == 3000000
    assert s["마진"] < 0
    assert s["경고"] == [] or all("초과" not in w for w in s["경고"])


def test_summary_zero_contract_price_does_not_divide_by_zero():
    s = summarize([FIXED], [{"상품id": FIXED["id"], "수량": 10}], 계약가=0)
    assert s["혜택배율"] is None
    assert s["마진율"] is None
