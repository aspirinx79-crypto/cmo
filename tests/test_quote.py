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
    """계좌만 환경변수에서 오고 나머지는 상수 한 곳에서 온다."""
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    for key, value in QUOTE_ISSUER.items():
        assert got["발주처"][key] == value
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


# ── 계좌번호는 저장소에 두지 않는다 ───────────────────────────

def test_account_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CMO_BANK_ACCOUNT", "○○은행 000-000-000 ㈜먹스타")
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    assert got["발주처"]["계좌"] == "○○은행 000-000-000 ㈜먹스타"


def test_account_line_is_empty_without_the_environment(monkeypatch):
    """환경변수가 없으면 계좌 줄이 빈다. 지어내지 않는다."""
    monkeypatch.delenv("CMO_BANK_ACCOUNT", raising=False)
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    assert got["발주처"]["계좌"] == ""


def test_the_constant_never_holds_an_account_number():
    """상수에 계좌를 두면 저장소에 남고, 저장소는 언젠가 공개된다."""
    assert "계좌" not in QUOTE_ISSUER


# ── 공정위 대가성 문구 ────────────────────────────────────

def test_ad_notice_appears_when_content_items_are_sold():
    """제안서에서 고지사항 장을 뺐다. 이 고지는 계약 문서에 남아야 한다."""
    from cmo.lib.quote import AD_NOTICE
    got = build_quote_payload(CLIENT, PLAN, PRODUCTS, today=TODAY)
    assert got["고지"] == AD_NOTICE
    assert "공정위" in AD_NOTICE


def test_no_ad_notice_without_content_items():
    """서비스툴관리만 파는 달에는 붙이지 않는다."""
    plan = {**PLAN, "항목": [{"상품id": "네이버-서비스툴관리", "수량": 1}]}
    got = build_quote_payload(CLIENT, plan, PRODUCTS, today=TODAY)
    assert got["고지"] == ""


def test_no_account_number_is_written_anywhere_in_the_source():
    """계좌번호처럼 생긴 글자가 코드·서식 어디에도 없어야 한다.

    한 번 커밋되면 히스토리에 영원히 남는다. 새로 들어가는 것만이라도
    여기서 막는다.
    """
    import re
    from pathlib import Path

    CMO = Path(__file__).resolve().parent.parent
    # 은행 계좌 꼴: 숫자 세 묶음 이상이 하이픈으로 이어진 것.
    계좌꼴 = re.compile(r"\b\d{2,6}-\d{2,6}-\d{2,6}(?:-\d{2,6})?\b")
    날짜꼴 = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    허용 = {"356-88-02874"}          # 사업자등록번호는 견적서에 찍히는 값이다

    def 계좌인가(글자: str) -> bool:
        if 글자 in 허용 or 날짜꼴.match(글자):
            return False
        return not 글자.startswith("0")   # 0 으로 시작하면 전화번호다

    샌것 = []
    for path in list(CMO.rglob("*.py")) + list(CMO.rglob("*.html")):
        if "__pycache__" in str(path) or path.name == Path(__file__).name:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in 계좌꼴.finditer(line):
                if 계좌인가(m.group()):
                    샌것.append(f"{path.name}:{n} {m.group()}")
    assert 샌것 == [], f"계좌번호처럼 생긴 값이 남아 있다: {샌것}"
