"""제안서 PDF 검증. 원가가 새는지 여기서 잡는다.

언젠가 서식을 고치다 실수로 실비를 노출시키는 날이 온다.
사람 주의력이 아니라 이 테스트가 잡아야 한다.
"""
import fitz
import pytest

from cmo.build_proposal import build
from cmo.lib.proposal import INTERNAL_STEP_WORDS, build_payload

PRODUCTS = [
    {"id": "네이버-블로그_일반_체험단", "매체": "네이버", "상품명": "블로그 일반 체험단",
     "가격유형": "고정", "정가": 30000, "실비": 8000, "최소수량": 5, "단위": "팀",
     "고지사항": "방문형 5팀 이상 / 공정위 문구 고지", "판매중지": False,
     "프로세스": "양식 받기->5-7일 모집/14-20일 체험,포스팅/2영업일 후 보고서"},
    {"id": "네이버-서비스툴관리", "매체": "네이버", "상품명": "서비스툴관리",
     "가격유형": "고정", "정가": 300000, "실비": 0, "최소수량": 1, "단위": "개월",
     "고지사항": "", "판매중지": False, "프로세스": "단톡방 소통"},
]
CLIENT = {"이름": "하루인 인계점", "업종": "고깃집", "지역": "수원 인계동", "평수": 60,
          "스냅샷": [{"수집시각": "2026-08-01T09:00:00",
                    "플레이스": {"방문자리뷰": 312, "블로그리뷰": 14},
                    "순위": [{"키워드": "인계동 삼겹살", "순위": 17}],
                    "예상매출": {"월매출": 42000000, "상권순위": "상위 40%"}}]}
PLAN = {"월": "2026-09", "계약가": 1000000, "진단메모": "블로그 리뷰가 14건뿐입니다.",
        "항목": [{"상품id": "네이버-블로그_일반_체험단", "수량": 40},
                {"상품id": "네이버-서비스툴관리", "수량": 1}]}

FORBIDDEN_WORDS = ("실비", "원가", "마진", "마진율", "내부전용", "월매출")


@pytest.fixture(scope="module")
def pdf_text(tmp_path_factory):
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    out = tmp_path_factory.mktemp("pdf") / "제안서.pdf"
    build(payload, out)
    doc = fitz.open(out)
    page_texts = [doc[i].get_text() for i in range(doc.page_count)]
    text = "".join(page_texts)
    pages = doc.page_count
    rect = doc[0].rect
    doc.close()
    return {"text": text, "쪽별": page_texts, "pages": pages, "rect": rect}


def test_pdf_is_a4_portrait(pdf_text):
    r = pdf_text["rect"]
    assert r.height > r.width, "세로 판형이 아니다"
    assert 580 < r.width < 610, f"A4 폭이 아니다 ({r.width:.0f}pt)"


def test_korean_text_is_extractable(pdf_text):
    assert "하루인 인계점" in pdf_text["text"], "한글이 추출되지 않는다 (폰트 임베드 실패)"


def test_no_cost_words_in_pdf(pdf_text):
    for word in FORBIDDEN_WORDS:
        assert word not in pdf_text["text"], f"제안서에 '{word}' 가 노출됐다"


def test_no_cost_amounts_in_pdf(pdf_text):
    """40팀 × 실비 8,000 = 320,000. 이 숫자가 보이면 안 된다.

    월매출 42,000,000 도 같이 막는다 — payload 단계 검사(test_proposal.py)는
    이미 있지만 PDF 쪽에는 없었다. 서식을 고치다 payload 는 안 새는데 PDF
    렌더링 쪽에서 실수로 꽂아 넣는 경우까지 여기서 잡는다."""
    for amount in ("320,000", "8,000원", "320000", "42,000,000", "42000000"):
        assert amount not in pdf_text["text"], f"실비/추정매출 금액 {amount} 이 노출됐다"


def test_every_line_appears_with_list_price(pdf_text):
    assert "블로그 일반 체험단" in pdf_text["text"]
    assert "1,200,000" in pdf_text["text"]   # 40팀 × 30,000
    assert "300,000" in pdf_text["text"]     # 서비스툴관리


def test_totals_and_multiplier_sentence(pdf_text):
    assert "1,500,000" in pdf_text["text"]
    assert "1,000,000" in pdf_text["text"]
    assert "1.5배" in pdf_text["text"]


def test_notices_are_printed(pdf_text):
    assert "공정위" in pdf_text["text"]


def test_schedule_is_printed(pdf_text):
    assert "1주차" in pdf_text["text"] and "4주차" in pdf_text["text"]
    assert "모집" in pdf_text["text"]


def test_no_internal_wording_on_the_schedule_page(pdf_text):
    """일정표 쪽에 직함·단톡방·외주 구조가 인쇄되면 안 된다.

    PDF 전체가 아니라 일정표 쪽만 본다 — "저희가 다른 점" 쪽의 차별점 카피는
    "단톡방으로 바로 소통합니다" 를 일부러 쓴다(고객에게 파는 강점이지 내부
    유출이 아니다). 문제가 난 곳은 프로세스 원문이 그대로 실리는 일정표다.
    """
    page = next((t for t in pdf_text["쪽별"] if "실행 일정" in t), None)
    assert page is not None, "일정표 쪽을 찾지 못했다"
    for word in INTERNAL_STEP_WORDS:
        assert word not in page, f"일정표에 내부 문구 '{word}' 가 인쇄됐다"


def test_differentiators_are_printed(pdf_text):
    assert "매주" in pdf_text["text"] and "다음 달" in pdf_text["text"]


def test_rank_metric_is_printed(pdf_text):
    assert "인계동 삼겹살" in pdf_text["text"] and "17" in pdf_text["text"]


def test_absolute_revenue_is_not_printed(pdf_text):
    """오픈업 추정 매출 절대금액은 싣지 않는다. 반박당하면 제안서 전체가 흔들린다."""
    assert "42,000,000" not in pdf_text["text"]
    assert "상위 40%" in pdf_text["text"]
