"""제안서 PDF 검증. 원가가 새는지 여기서 잡는다.

언젠가 서식을 고치다 실수로 실비를 노출시키는 날이 온다.
사람 주의력이 아니라 이 테스트가 잡아야 한다.
"""
import fitz
import pytest

from cmo.build_pdf import build
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


# ── 오픈업 카드 ───────────────────────────────────────────────

OPENUB_CLIENT = {**CLIENT, "오픈업": [{
    "기준월": "2026-06",
    "매출": {"하한": 46000000, "상한": 56000000},
    "성별최다": {"값": "남성", "비율": 65},
    "연령최다": {"값": "남성 20대", "비율": 26},
    "요일최다": {"값": "토", "비율": 25},
    "평일비율": 65,
    "시간대최다": {"값": "밤", "비율": 40},
    "판독시각": "2026-08-12T09:30:00",
}]}


@pytest.fixture(scope="module")
def openub_pdf_text(tmp_path_factory):
    payload = build_payload(OPENUB_CLIENT, PLAN, PRODUCTS)
    out = tmp_path_factory.mktemp("pdf") / "제안서_오픈업.pdf"
    build(payload, out)
    doc = fitz.open(out)
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    return text


def test_openub_cards_are_printed(openub_pdf_text):
    """서식의 자바스크립트가 죽으면 카드가 통째로 빠진다. 실제로 찍어 본다."""
    assert "4,600~5,600만원" in openub_pdf_text
    assert "남성 65%" in openub_pdf_text
    assert "남성 20대 26%" in openub_pdf_text
    assert "토 25% · 밤 40%" in openub_pdf_text


def test_openub_footnote_names_the_source_and_month(openub_pdf_text):
    """추정치가 확정 숫자로 읽히면 안 된다."""
    assert "오픈업 추정(2026년 6월)" in openub_pdf_text


def test_openub_pdf_never_shows_the_reading_timestamp(openub_pdf_text):
    assert "판독시각" not in openub_pdf_text
    assert "2026-08-12T09:30" not in openub_pdf_text


def test_openub_pdf_still_hides_forbidden_words(openub_pdf_text):
    """오픈업 카드가 붙어도 기존 금지선은 그대로다."""
    for word in FORBIDDEN_WORDS:
        assert word not in openub_pdf_text, f"제안서에 '{word}' 가 찍혔다"


# ── 견적서 ────────────────────────────────────────────────────

QUOTE_CLIENT = {"이름": "하루인 인계점", "업종": "고깃집", "지역": "수원 인계동"}
QUOTE_PLAN = {"월": "2026-09", "계약가": 1500000, "항목": [
    {"상품id": "네이버-블로그_일반_체험단", "수량": 10},
    {"상품id": "네이버-서비스툴관리", "수량": 1}]}


@pytest.fixture(scope="module")
def quote_pdf_text(tmp_path_factory):
    from cmo.build_pdf import QUOTE, build
    from cmo.lib.quote import build_quote_payload

    payload = build_quote_payload(QUOTE_CLIENT, QUOTE_PLAN, PRODUCTS)
    out = tmp_path_factory.mktemp("pdf") / "견적서.pdf"
    build(payload, out, template=QUOTE)
    doc = fitz.open(out)
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    pages = doc.page_count
    doc.close()
    return {"text": text, "pages": pages}


def test_quote_is_one_page(quote_pdf_text):
    assert quote_pdf_text["pages"] == 1


def test_quote_prints_the_totals(quote_pdf_text):
    text = quote_pdf_text["text"]
    assert "1,500,000" in text
    assert "150,000" in text
    assert "1,650,000" in text
    assert "vat포함" in text


def test_quote_prints_the_header(quote_pdf_text):
    text = quote_pdf_text["text"]
    assert "하루인 인계점 CMO 서비스" in text
    assert "하루인 인계점 귀하" in text
    assert "15일" in text and "협의" in text


def test_quote_prints_the_issuer_from_the_constant(quote_pdf_text):
    from cmo.lib.quote import QUOTE_ISSUER

    text = quote_pdf_text["text"]
    assert QUOTE_ISSUER["사업자등록번호"] in text
    assert QUOTE_ISSUER["전화번호"] in text
    assert QUOTE_ISSUER["계좌"].split()[0] in text


def test_quote_never_shows_cost_words(quote_pdf_text):
    """견적서도 고객 문서다. 제안서와 같은 금지선이 온다."""
    for word in FORBIDDEN_WORDS:
        assert word not in quote_pdf_text["text"], f"견적서에 '{word}' 가 찍혔다"


def test_quote_details_carry_no_money(quote_pdf_text):
    """내역 줄에 항목별 금액이 붙으면 원가 구조가 드러난다."""
    text = quote_pdf_text["text"]
    assert "블로그 일반 체험단 10팀" in text
    assert "300,000" not in text
    assert "30,000" not in text


def test_quote_template_has_no_hardcoded_issuer():
    """서식과 값이 한 파일에 있으면 값을 고치러 서식을 열게 된다.

    받은 견적서 세 건이 서로 달라진 경로가 그것이다.
    """
    from cmo.build_pdf import QUOTE

    source = QUOTE.read_text(encoding="utf-8")
    for 값 in ("356-88-02874", "1688-2633", "210-112344-04-015", "압구정로2길"):
        assert 값 not in source, f"서식에 발주처 값 '{값}' 이 박혀 있다"


# ── 검색 현황 네 장 ───────────────────────────────────────────

RICH_CLIENT_PDF = {**CLIENT, "스냅샷": [{
    "수집시각": "2026-08-13T09:00:00",
    "플레이스": {"방문자리뷰": 775, "블로그리뷰": 1415},
    "순위": [
        {"키워드": "서초맛집", "순위": None, "순위권밖": True,
         "조회수": 5740, "비교순위": 81},
        {"키워드": "방배동맛집", "순위": 77, "순위권밖": False,
         "조회수": 4900, "비교순위": 18},
        {"키워드": "예술의전당정육식당", "순위": 1, "순위권밖": False,
         "조회수": 50, "비교순위": 1},
    ],
    "예상매출": None,
    "순위요약": {"총키워드": 51, "TOP3": 6, "TOP10": 11},
    "진단": {"기준일": "08-12", "비교일": "07-29",
             "대표키워드": [], "히든키워드": ["예술의전당한우", "방배역 곰탕"],
             "리뷰": {"방문자": [{"제목": "아이들이 한우 먹고싶다고",
                                  "조회수": 1479, "작성일": "2026-07-16",
                                  "작성자": "ljw20566"}],
                      "블로그": [{"제목": "방배동 소고기 맛집 추천",
                                  "작성일": "2026-05-26",
                                  "실명여부": "톰바미설치"}]}},
}]}


@pytest.fixture(scope="module")
def rich_pdf_text(tmp_path_factory):
    payload = build_payload(RICH_CLIENT_PDF, PLAN, PRODUCTS)
    out = tmp_path_factory.mktemp("pdf") / "제안서_보강.pdf"
    build(payload, out)
    doc = fitz.open(out)
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    return text


def test_opportunity_table_is_printed(rich_pdf_text):
    assert "서초맛집" in rich_pdf_text
    assert "5,740" in rich_pdf_text
    assert "30위 밖" in rich_pdf_text


def test_headline_is_printed(rich_pdf_text):
    assert "아직 안 보입니다" in rich_pdf_text


def test_rank_moves_are_printed(rich_pdf_text):
    assert "07-29" in rich_pdf_text and "08-12" in rich_pdf_text
    assert "18위" in rich_pdf_text and "77위" in rich_pdf_text


def test_hidden_and_reviews_are_printed(rich_pdf_text):
    assert "예술의전당한우" in rich_pdf_text
    assert "1,479" in rich_pdf_text


def test_internal_marks_never_reach_the_pdf(rich_pdf_text):
    """블로그 실명여부·톰바설치와 작성자 아이디는 고객 문서에 없어야 한다."""
    for word in ("톰바", "실명여부", "ljw20566"):
        assert word not in rich_pdf_text, f"제안서에 '{word}' 가 찍혔다"


def test_plain_client_pdf_has_no_diagnosis_section(pdf_text):
    """기존 매장은 네 장이 안 나온다. 빈 표를 만들지 않는다."""
    assert "30위 밖" not in pdf_text["text"]
    assert "아직 안 보입니다" not in pdf_text["text"]
    assert "키워드 기회표" not in pdf_text["text"]
