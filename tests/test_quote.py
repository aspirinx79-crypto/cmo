"""견적서 payload — 순수 함수.

금액은 계약가 하나에서만 온다. 정가·실비·마진은 한 글자도 들어가지
않는다 — 견적서는 고객이 받는 문서다.
"""
import json
from datetime import date

import pytest

from cmo.lib.quote import QUOTE_ISSUER, QuoteBlocked, build_quote_payload

TODAY = date(2026, 8, 12)

PRODUCTS = [
    {"id": "네이버-서비스툴관리", "매체": "네이버", "상품명": "서비스툴관리",
     "가격유형": "고정", "정가": 300000, "실비": 50000, "최소수량": 1,
     "단위": "개월", "판매중지": False, "고지사항": "", "프로세스": ""},
    {"id": "네이버-블로그_일반_체험단", "매체": "네이버", "상품명": "블로그 일반 체험단",
     "가격유형": "고정", "정가": 30000, "실비": 8000, "최소수량": 5,
     "단위": "팀", "판매중지": False, "고지사항": "", "프로세스": ""},
]
CLIENT = {"이름": "하루인 인계점", "업종": "고깃집", "지역": "수원 인계동"}
PLAN = {"월": "2026-09", "계약가": 1500000, "항목": [
    {"상품id": "네이버-서비스툴관리", "수량": 1},
    {"상품id": "네이버-블로그_일반_체험단", "수량": 10}]}


def test_total_is_the_contract_price():
    """합계는 계약가다. 정가합이 아니다."""
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    assert got["합계"] == 1500000
    assert got["부가세"] == 150000
    assert got["총합"] == 1650000
    assert got["부가세문구"] == "총합 (vat포함)"


def test_payload_never_carries_list_price_or_cost():
    """정가·실비·마진은 한 글자도 들어가지 않는다."""
    blob = json.dumps(build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY),
                      ensure_ascii=False)
    for word in ("정가", "실비", "마진", "300000", "30000"):
        assert word not in blob, f"견적서 payload 에 '{word}' 가 들어 있다"


def test_details_have_no_money():
    """내역 줄에 금액이 붙으면 원가 구조가 드러난다."""
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    항목 = got["항목"][0]
    assert 항목["세부"] == ["서비스툴관리 1개월", "블로그 일반 체험단 10팀"]
    for 줄 in 항목["세부"]:
        assert "원" not in 줄


def test_one_line_when_details_are_off():
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY, 내역펼침=False)
    assert got["항목"][0]["세부"] == []
    assert got["항목"][0]["단가"] == 1500000


def test_vat_can_be_excluded():
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY, 부가세별도=True)
    assert got["부가세"] == 0
    assert got["총합"] == 1500000
    assert got["부가세문구"] == "총합 (vat별도)"


def test_zero_contract_price_is_blocked():
    """0원짜리 견적서가 고객에게 가는 게 최악이다."""
    with pytest.raises(QuoteBlocked):
        build_quote_payload(CLIENT, {**PLAN, "계약가": 0}, PRODUCTS, today=TODAY)
    with pytest.raises(QuoteBlocked):
        build_quote_payload(CLIENT, {**PLAN, "계약가": None}, PRODUCTS, today=TODAY)


def test_header_is_built_from_the_store_name():
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    assert got["견적내용"] == "하루인 인계점 CMO 서비스"
    assert got["요청인"] == "하루인 인계점 귀하"
    assert got["견적일자"] == "2026-08-12"
    assert got["유효일"] == "15일"
    assert got["납기일"] == "협의"


def test_issuer_comes_from_the_constant():
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    assert got["발주처"] is QUOTE_ISSUER
    assert QUOTE_ISSUER["전화번호"] == "1688-2633"
    assert QUOTE_ISSUER["사업자등록번호"] == "356-88-02874"


def test_empty_plan_still_makes_one_line():
    """기획안 항목이 비어도 막지 않는다. 내역 없이 한 줄로 낸다."""
    got = build_quote_payload(CLIENT, {**PLAN, "항목": []}, PRODUCTS, today=TODAY)
    assert got["항목"][0]["합"] == 1500000
    assert got["항목"][0]["세부"] == []


def test_unknown_product_id_is_skipped_not_crashed():
    """상품이 지워져도 견적서는 나와야 한다 — 그 줄만 빠진다."""
    plan = {**PLAN, "항목": PLAN["항목"] + [{"상품id": "없는-상품", "수량": 1}]}
    got = build_quote_payload(CLIENT, plan, PRODUCTS, today=TODAY)
    assert len(got["항목"][0]["세부"]) == 2
