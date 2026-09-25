"""제안서 PDF 검증. 원가가 새는지 여기서 잡는다.

언젠가 서식을 고치다 실수로 실비를 노출시키는 날이 온다.
사람 주의력이 아니라 이 테스트가 잡아야 한다.
"""
import copy

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


def test_bare_rank_without_search_signal_is_not_printed(pdf_text):
    """진단자료가 손님·검색·처방 세 장으로 바뀌면서, 조회수도 비교순위도 없는

    맨 순위 한 줄은 더 이상 실릴 자리가 없다(기회표는 조회수가, 처방은
    비교순위가 있어야 뜬다). 대신 판독이 안 된 클라이언트도 검색 장의
    일반 수치(방문자 리뷰 등)는 그대로 뜬다 — 세 장이 아예 안 뜨는 게
    아니라 키워드 카드만 없는 것이다.
    """
    assert "인계동 삼겹살" not in pdf_text["text"]
    assert "312건" in pdf_text["text"]


def test_absolute_revenue_is_not_printed(pdf_text):
    """오픈업 추정 매출 절대금액은 싣지 않는다. 반박당하면 제안서 전체가 흔들린다.

    상권순위(예: "상위 40%")는 예전 「매장 진단」 장의 카드였다. 손님·검색·
    처방 세 장으로 바뀌며 이 값을 쓰는 자리가 없어졌다 — 실을 자리가
    없어졌을 뿐 일부러 가린 게 아니다.
    """
    assert "42,000,000" not in pdf_text["text"]


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
    # 계좌는 상수가 아니라 환경변수에서 온다. 없으면 그 줄이 통째로
    # 빠지는 게 맞다 — 빈 「기업은행 :」 이 찍히면 더 이상하다.
    assert "계좌" not in QUOTE_ISSUER


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


def test_quote_pdf_prints_the_ad_notice(quote_pdf_text):
    """대가성 고지는 payload 에 담기는 것으로 끝나지 않는다.

    고객이 받는 종이에 찍혀야 지킨 것이다. 서식의 `#q-notice` 배선이
    끊기면 payload 검사는 그대로 통과하면서 종이에서만 사라진다.
    """
    from cmo.lib.quote import AD_NOTICE

    assert AD_NOTICE in quote_pdf_text["text"]
    assert "공정위" in quote_pdf_text["text"]


def test_quote_template_has_no_hardcoded_issuer():
    """서식과 값이 한 파일에 있으면 값을 고치러 서식을 열게 된다.

    받은 견적서 세 건이 서로 달라진 경로가 그것이다.
    """
    from cmo.build_pdf import QUOTE

    source = QUOTE.read_text(encoding="utf-8")
    for 값 in ("356-88-02874", "1688-2633", "압구정로2길"):
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


def test_the_span_prints_on_the_search_page_only(tmp_path):
    """측정일이 갈린 날, 범위는 검색 장에만 찍힌다.

    처방 제목은 `비교일 → 기준일` 이라 그 자리에 범위가 들어가면
    「2026-08-20 → 2026-09-01~2026-09-23」이 된다. 사장님이 읽는
    종이다. 값 쪽은 `test_proposal` 이 잠그고, 여기서는 종이에 실제로
    찍히는 두 줄을 본다.

    날짜가 하나뿐인 경우는 `test_rank_moves_are_printed` 가 본다 —
    `RICH_CLIENT_PDF` 에는 `기준일범위` 가 아예 없다.
    """
    client = copy.deepcopy(RICH_CLIENT_PDF)
    client["스냅샷"][0]["진단"].update({
        "기준일": "2026-09-23", "기준일범위": "2026-09-01~2026-09-23",
        "비교일": "2026-08-20"})

    글 = "\n".join(_쪽별글(client, tmp_path, "기준일범위.pdf"))

    assert "순위 기준 2026-09-01~2026-09-23" in 글
    assert "순위 변동과 이번 달 처방 (2026-08-20 → 2026-09-23)" in 글


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


# ── 처방 장, 고지사항 장 삭제 ───────────────────────────────────


def test_proposal_has_no_notice_page(tmp_path):
    """고지사항 장을 뺐다. 대가성 고지는 견적서로 갔다."""
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    out = tmp_path / "p.pdf"
    build(payload, out)
    doc = fitz.open(out)
    글자 = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    assert "고지사항" not in 글자


def test_prescription_page_prints_placements(tmp_path):
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    payload["진단자료"] = {
        "손님": None, "검색": {"헤드라인": None, "수치": [],
                               "기회표": None, "히든키워드": None},
        "리뷰": None,
        "처방": {
            "기준일": "2026-08-12", "비교일": "2026-06-12",
            "오름": [{"키워드": "잠실종합운동장맛집", "전": "12위", "후": "8위"}],
            "내림": [{"키워드": "송파양꼬치", "전": "7위", "후": "14위"}],
            "오름문장": "상승 중인 키워드는 지금 밀어붙일 때 효과가 가장 큽니다.",
            "내림문장": "떨어진 키워드는 콘텐츠와 리뷰 총량으로 되돌립니다.",
            "오름배치": ["자동완성어 1건"],
            "내림배치": ["블로그 일반 체험단 5팀"],
        },
    }
    out = tmp_path / "r.pdf"
    build(payload, out)
    doc = fitz.open(out)
    글자 = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    assert "잠실종합운동장맛집" in 글자
    assert "이번 달 배치" in 글자
    assert "자동완성어 1건" in 글자
    assert "블로그 일반 체험단 5팀" in 글자


def test_placement_line_disappears_when_empty(tmp_path):
    """빈 약속을 만들지 않는다."""
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    payload["진단자료"] = {
        "손님": None, "검색": {"헤드라인": None, "수치": [],
                               "기회표": None, "히든키워드": None},
        "리뷰": None,
        "처방": {
            "기준일": None, "비교일": None,
            "오름": [{"키워드": "잠실맛집", "전": "12위", "후": "8위"}],
            "내림": [],
            "오름문장": "상승 중인 키워드는 지금 밀어붙일 때 효과가 가장 큽니다.",
            "내림문장": None, "오름배치": [], "내림배치": [],
        },
    }
    out = tmp_path / "e.pdf"
    build(payload, out)
    doc = fitz.open(out)
    글자 = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    assert "잠실맛집" in 글자
    assert "이번 달 배치" not in 글자


def test_no_null_is_ever_printed(tmp_path):
    """판독 날짜가 없어도 「null」이 고객 문서에 찍히면 안 된다."""
    payload = build_payload(CLIENT, PLAN, PRODUCTS)
    payload["진단자료"] = {
        "손님": None,
        "검색": {"헤드라인": None, "수치": [], "기회표": None, "히든키워드": None},
        "리뷰": None,
        "처방": {
            "기준일": None, "비교일": None,
            "오름": [{"키워드": "잠실맛집", "전": "12위", "후": "8위"}],
            "내림": [],
            "오름문장": "상승 중인 키워드는 지금 밀어붙일 때 효과가 가장 큽니다.",
            "내림문장": None, "오름배치": [], "내림배치": [],
        },
    }
    out = tmp_path / "n.pdf"
    build(payload, out)
    doc = fitz.open(out)
    글자 = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    assert "null" not in 글자
    assert "undefined" not in 글자


# ── 빠진 장 경고가 서식과 어긋나지 않는다 ─────────────────────
#
# `missing_pages()` 는 서식의 노출 조건을 손으로 옮겨 적은 거울이다.
# 거울은 언젠가 깨진다 — 서식만 고치고 여기를 잊는 날이 온다. 그날
# 경고는 서 있는 장을 빠졌다 하거나 빠진 장을 조용히 넘긴다. 둘 다
# 경고를 못 믿게 만들고, 못 믿는 경고는 없느니만 못하다.
#
# 그래서 말로 대조하지 않고 **실제로 PDF 를 찍어서** 대조한다.

_BARE_CLIENT = {"이름": "미친양꼬치 방이점", "업종": "", "지역": "", "평수": None,
                "스냅샷": [{"수집시각": "2026-08-15T21:37:21",
                          "플레이스": {"방문자리뷰": None, "블로그리뷰": None,
                                     "저장수": None},
                          "순위": [], "예상매출": None}]}

_RICH_SNAP = {
    "수집시각": "2026-08-14T00:26:31",
    "플레이스": {"방문자리뷰": 1082, "블로그리뷰": 170, "저장수": 100},
    "순위": [{"키워드": "잠실새내역맛집", "순위": 14, "순위권밖": False,
             "조회수": 9100, "비교순위": 9},
            {"키워드": "잠실양꼬치", "순위": 3, "순위권밖": False,
             "조회수": 4800, "비교순위": 7}],
    "예상매출": None,
    "진단": {"기준일": "08-13", "비교일": "07-30", "총키워드": 47,
            "TOP3": 3, "TOP10": 11, "히든키워드": ["잠실 룸술집"],
            "리뷰": {"방문자": [{"제목": "양꼬치가 두툼합니다", "조회수": 900,
                              "작성일": "2026-07-16"}], "블로그": []}},
}
_OPENUB = [{"기준월": "2026-07", "매출": {"하한": 46000000, "상한": 56000000},
            "성별최다": {"값": "남성", "비율": 62},
            "연령최다": {"값": "남성 30대", "비율": 28},
            "요일최다": {"값": "금", "비율": 22},
            "시간대최다": {"값": "밤", "비율": 45}, "평일비율": 64}]

# 잠실점 실물 모양. **이 사례가 제일 중요하다** — 조회수가 없어 기회표는
# 안 서지만 방문자 리뷰·저장수가 있어서 「검색에서의 자리」장은 선다.
# 이 줄이 없으면 경고 조건을 `기회표` 하나로 좁혀 놔도 시험이 통과한다
# (실제로 그렇게 넣어 보고 확인했다).
_THIN_SNAP = {
    "수집시각": "2026-08-14T00:26:31",
    "플레이스": {"방문자리뷰": 1082, "블로그리뷰": 170, "저장수": 100},
    "순위": [{"키워드": "잠실종합운동장맛집", "순위": 8, "순위권밖": False,
             "조회수": None, "비교순위": 12}],
    "예상매출": None,
    "진단": {"기준일": "08-13", "비교일": "07-30", "리뷰": {"방문자": [], "블로그": []}},
}

# 비교순위가 없어 처방은 못 서고 리뷰만 남는 매장. 장 제목이 종이에서
# 사라지는 자리라, 경고가 그걸 말해야 한다. 이 줄이 없으면 「처방이
# 빠졌는데 리뷰 덕에 조용한」 경우가 시험에 한 번도 안 걸린다.
_NO_MOVES_SNAP = {**_RICH_SNAP,
                  "순위": [{**r, "비교순위": None} for r in _RICH_SNAP["순위"]]}

_CASES = {
    "빈매장": _BARE_CLIENT,
    "애드로그만": dict(_BARE_CLIENT, 스냅샷=[_RICH_SNAP]),
    "오픈업만": dict(_BARE_CLIENT, 오픈업=_OPENUB),
    "조회수없음": dict(_BARE_CLIENT, 스냅샷=[_THIN_SNAP]),
    "처방없이리뷰만": dict(_BARE_CLIENT, 스냅샷=[_NO_MOVES_SNAP]),
    "다찬매장": dict(_BARE_CLIENT, 스냅샷=[_RICH_SNAP], 오픈업=_OPENUB),
}


@pytest.mark.parametrize("사례", list(_CASES))
def test_missing_page_warning_matches_what_the_pdf_prints(사례, tmp_path):
    """경고가 「빠졌다」고 한 장은 종이에 없고, 안 한 장은 있어야 한다."""
    from cmo.lib.proposal import (MISSING_CUSTOMER, MISSING_MOVES,
                                  MISSING_SEARCH, missing_pages)

    제목 = {MISSING_CUSTOMER: "이 가게에 오는 손님",
            MISSING_SEARCH: "검색에서의 자리",
            MISSING_MOVES: "순위 변동과 이번 달 처방"}

    payload = build_payload(_CASES[사례], PLAN, PRODUCTS)
    경고 = missing_pages(payload)

    out = tmp_path / f"{사례}.pdf"
    build(payload, out)
    doc = fitz.open(out)
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()

    for 문구, 이름 in 제목.items():
        assert (문구 in 경고) == (이름 not in text), (
            f"[{사례}] 「{이름}」— 경고는 "
            f"{'빠졌다' if 문구 in 경고 else '있다'}는데 종이에는 "
            f"{'없다' if 이름 not in text else '있다'}")


# ── 제안서는 네 쪽이다 ──
#
# 상무님이 일곱 쪽은 너무 복잡하다고 하셨다. 쪽 수는 서식을 손볼 때마다
# 조용히 늘어나는 값이라 사람 눈으로 지킬 수 없다. 여기서 못박는다.

def _쪽별글(client, tmp_path, 이름="쪽수.pdf"):
    """PDF 를 뽑아 쪽마다의 글을 리스트로 낸다."""
    payload = build_payload(client, PLAN, PRODUCTS)
    out = tmp_path / 이름
    build(payload, out)
    doc = fitz.open(out)
    쪽들 = [doc[i].get_text().strip() for i in range(doc.page_count)]
    doc.close()
    return 쪽들


def test_a_full_proposal_fits_on_four_pages(tmp_path):
    """자료가 다 찬 매장이라도 네 쪽을 넘지 않는다."""
    쪽들 = _쪽별글(_CASES["다찬매장"], tmp_path)
    assert len(쪽들) == 4, (
        f"네 쪽이 아니라 {len(쪽들)}쪽이다. 쪽별 첫 줄: "
        + " / ".join(글.splitlines()[0] if 글 else "(빈 쪽)" for 글 in 쪽들))


def test_the_four_pages_carry_the_agreed_grouping(tmp_path):
    """묶기로 한 대로 붙었는지 본다. 쪽 수만 맞고 순서가 엉키면 소용없다."""
    쪽들 = _쪽별글(_CASES["다찬매장"], tmp_path, "묶음.pdf")
    # 손님과 처방을 한 쪽에 두고 「검색에서의 자리」를 2쪽 통째로 준다.
    # 검색 장은 기회표 여덟 줄에 미확보 키워드 목록까지 붙어서 제일 길다 —
    # 손님과 같은 쪽에 묶으면 A4 를 넘긴다(방이점 실물로 확인).
    묶음 = [("이 가게에 오는 손님", "순위 변동과 이번 달 처방"),
            ("검색에서의 자리",),
            ("실행 구성", "저희가 다른 점"),
            ("1개월차 실행 일정",)]
    for 번호, (글, 제목들) in enumerate(zip(쪽들, 묶음), start=1):
        for 제목 in 제목들:
            assert 제목 in 글, f"{번호}쪽에 「{제목}」이 없다. 있는 글: {글[:80]!r}"


def test_the_first_page_names_the_month_and_the_store(tmp_path):
    """표지를 없앴으니 그 정보가 첫 쪽 머리글로 살아 있어야 한다."""
    쪽들 = _쪽별글(_CASES["다찬매장"], tmp_path, "머리글.pdf")
    assert "2026-09" in 쪽들[0], f"첫 쪽에 월이 없다: {쪽들[0][:120]!r}"
    assert "미친양꼬치 방이점" in 쪽들[0], f"첫 쪽에 상호가 없다: {쪽들[0][:120]!r}"


def test_the_issuer_still_appears_somewhere(tmp_path):
    """표지에 있던 회사 정보가 사라지면 안 된다 — 어느 쪽이든 남아야 한다."""
    쪽들 = _쪽별글(_CASES["다찬매장"], tmp_path, "발행처.pdf")
    전체 = "".join(쪽들)
    assert "상생어벤져스" in 전체, "발행처가 통째로 사라졌다"
    assert "1551-0723" in 전체, "연락처가 통째로 사라졌다"


# 서식에 있는 장 제목 전부. 쪽마다 이 중 하나는 있어야 한다.
_장제목 = ("이 가게에 오는 손님", "검색에서의 자리", "순위 변동과 이번 달 처방",
           "실행 구성", "저희가 다른 점", "1개월차 실행 일정")

# 처방이 빠진 날에는 「리뷰 현황」이 장 제목 자리로 올라온다
# (`proposal.html` 의 `d-moves-title` 주석). 평소에는 처방 장 안의 작은
# 제목이라 `_장제목` 에는 넣지 않는다 — 넣으면 장 사이 틈을 재는 시험이
# 그 작은 제목을 장 경계로 착각한다.
_쪽제목 = (*_장제목, "리뷰 현황")


@pytest.mark.parametrize("사례", list(_CASES))
def test_every_page_carries_a_real_section(사례, tmp_path):
    """진단 장이 숨으면 묶음 껍데기가 남아 머리글만 있는 쪽이 생긴다.

    「빈 쪽」을 보면 안 잡힌다 — 껍데기 쪽에도 머리글 두 줄은 찍혀서
    글자가 있긴 있다(실제로 그렇게 넣어 보고 확인했다). 장 제목이
    하나도 없는 쪽을 찾아야 잡힌다.
    """
    쪽들 = _쪽별글(_CASES[사례], tmp_path, f"{사례}_껍데기.pdf")
    맹탕 = [번호 for 번호, 글 in enumerate(쪽들, start=1)
            if not any(제목 in 글 for 제목 in _쪽제목)]
    assert not 맹탕, (
        f"[{사례}] {맹탕} 쪽에 장이 하나도 없다 (전체 {len(쪽들)}쪽). "
        f"그 쪽 내용: {쪽들[맹탕[0] - 1][:80]!r}")


# ── 실물 밀도로 다시 본다 ──
#
# 위의 `다찬매장` 은 키워드가 두 개뿐이라 헐겁다. 그걸로 「네 쪽」을 재면
# 통과하지만 방이점 실물은 다섯 쪽이 나왔다. 종이가 넘치는지는 **자료가
# 많을 때**만 드러나므로, 실물만큼 채운 사례를 따로 둔다.

_DENSE_PRODUCTS = PRODUCTS + [
    {"id": "네이버-SA", "매체": "네이버", "상품명": "SA", "가격유형": "예산배율",
     "정가": None, "실비": None, "예산배율": 1.15, "최소수량": 1, "단위": "건",
     "고지사항": "상위대행사에 마크업 필수", "판매중지": False,
     "프로세스": "상위대행사 이관-> 소재 세팅->통계보며 보고 및 피드백 -> 관리"},
    {"id": "메타-타겟광고", "매체": "메타", "상품명": "타겟광고", "가격유형": "예산배율",
     "정가": None, "실비": None, "예산배율": 1.3, "최소수량": 1, "단위": "건",
     "고지사항": "운용수수료 별도", "판매중지": False,
     "프로세스": "기획회의-> 디자인 및 영상소재 제작->타겟광고 ->통계 분석"},
    {"id": "네이버-카페_여론형성형_침투_바이럴", "매체": "네이버",
     "상품명": "카페 여론형성형 침투 바이럴", "가격유형": "고정", "정가": 50000,
     "실비": 9000, "최소수량": 1, "단위": "건", "고지사항": "조회수 보고",
     "판매중지": False, "프로세스": "단톡방 컨트롤"},
    {"id": "네이버-자동완성어", "매체": "네이버", "상품명": "자동완성어",
     "가격유형": "고정", "정가": 250000, "실비": 60000, "최소수량": 1, "단위": "건",
     "고지사항": "", "판매중지": False, "프로세스": "단톡방 컨트롤"},
    {"id": "카카오-리뷰작업", "매체": "카카오", "상품명": "리뷰작업",
     "가격유형": "고정", "정가": 5000, "실비": 1500, "최소수량": 10, "단위": "건",
     "고지사항": "", "판매중지": False, "프로세스": "실장님께 알바풀 전달"},
]
_DENSE_PLAN = {**PLAN, "항목": [
    {"상품id": "네이버-서비스툴관리", "수량": 1},
    {"상품id": "네이버-SA", "수량": 1, "예산": 300000},
    {"상품id": "메타-타겟광고", "수량": 1, "예산": 500000},
    {"상품id": "네이버-블로그_일반_체험단", "수량": 5},
    {"상품id": "네이버-카페_여론형성형_침투_바이럴", "수량": 3},
    {"상품id": "네이버-자동완성어", "수량": 1},
    {"상품id": "카카오-리뷰작업", "수량": 10},
]}
# 조회수가 큰 키워드 17개 → 기회표가 8줄까지 선다. 방이점 실물과 같은 수다.
_DENSE_RANKS = [
    {"키워드": f"방이동맛집{i}", "순위": 20 + i, "순위권밖": False,
     "조회수": 30000 - i * 1500, "비교순위": 5 + i} for i in range(17)
]
_DENSE_SNAP = {
    "수집시각": "2026-08-15T21:37:21",
    "플레이스": {"방문자리뷰": 826, "블로그리뷰": 25, "저장수": 100},
    "순위": _DENSE_RANKS,
    "예상매출": None,
    "순위요약": {"총키워드": 60, "TOP3": 2, "TOP10": 5},
    "진단": {"기준일": "08-13", "비교일": "07-30",
            "대표키워드": ["양꼬치무한리필", "방이동양꼬치"],
            # 방이점 실물과 같은 43개. 이 글자벽이 1쪽을 넘긴 주범이었다.
            "히든키워드": [f"방이동 회식 후보 {i}" for i in range(43)],
            "리뷰": {"방문자": [{"제목": "양꼬치가 두툼합니다", "조회수": 900,
                              "작성일": "2026-07-16"}], "블로그": []}},
}
# 업종·지역·평수를 채운다. 빈 매장으로 재면 이 줄들이 아예 안 찍혀서
# 「같은 정보가 두 번 나오는지」를 볼 수가 없다(잠실점 실물이 이 모양이다).
_DENSE_CLIENT = {**_BARE_CLIENT, "스냅샷": [_DENSE_SNAP], "오픈업": _OPENUB,
                 "업종": "양꼬치", "지역": "잠실새내역", "평수": 55}


def _쪽별글_밀도(tmp_path, 이름):
    payload = build_payload(_DENSE_CLIENT, _DENSE_PLAN, _DENSE_PRODUCTS)
    out = tmp_path / 이름
    build(payload, out)
    doc = fitz.open(out)
    쪽들 = [doc[i].get_text().strip() for i in range(doc.page_count)]
    doc.close()
    return 쪽들


def test_a_dense_real_world_proposal_still_fits_on_four_pages(tmp_path):
    """키워드 17개·히든 43개·상품 7종이라도 네 쪽이다.

    상품 일곱 종은 잠실점 실물 구성이다. 다섯 종짜리로 재면 일정이 한 장에
    들어가 버려서 넘침을 못 본다 — 실제로 그 상태로 통과했다.
    """
    쪽들 = _쪽별글_밀도(tmp_path, "밀도.pdf")
    assert len(쪽들) == 4, (
        f"네 쪽이 아니라 {len(쪽들)}쪽이다. 쪽별 첫 줄: "
        + " / ".join((글.splitlines() or ["(빈 쪽)"])[0] for 글 in 쪽들))


def test_the_dense_proposal_keeps_every_keyword(tmp_path):
    """쪽을 맞추려고 자료를 조용히 잘라내면 안 된다."""
    쪽들 = _쪽별글_밀도(tmp_path, "밀도_보존.pdf")
    전체 = "".join(쪽들)
    assert "방이동맛집7" in 전체, "기회표 8번째 줄이 잘렸다"
    assert "방이동 회식 후보 42" in 전체, "히든키워드 43번째가 잘렸다"


def test_stacked_sections_are_not_glued_together(tmp_path):
    """한 쪽에 장 둘이 쌓이면 그 사이에 눈에 보이는 틈이 있어야 한다.

    장마다 쪽이 따로였을 때는 간격이 필요 없었다. 이제 손님과 처방이,
    실행 구성과 차별점이 한 쪽에 붙으므로 아래 장 제목이 위 장 끝줄에
    달라붙는다(실측 11pt — 문단 사이 간격과 구별이 안 된다).
    """
    최소틈 = 22        # pt. 문단 사이(11pt)의 두 배는 되어야 장 경계로 읽힌다.
    payload = build_payload(_DENSE_CLIENT, _DENSE_PLAN, _DENSE_PRODUCTS)
    out = tmp_path / "틈.pdf"
    build(payload, out)
    doc = fitz.open(out)
    좁은곳 = []
    for 번호 in range(doc.page_count):
        덩이 = sorted(doc[번호].get_text("blocks"), key=lambda b: b[1])
        for i, b in enumerate(덩이):
            if i == 0:
                continue                      # 쪽 첫 덩이는 위가 없다
            제목 = next((t for t in _장제목 if b[4].strip().startswith(t)), None)
            if 제목 is None:
                continue
            틈 = b[1] - 덩이[i - 1][3]
            if 틈 < 최소틈:
                좁은곳.append(f"{번호 + 1}쪽 「{제목}」 위 틈 {틈:.1f}pt")
    doc.close()
    assert not 좁은곳, "장 경계가 붙어 있다: " + " / ".join(좁은곳)


def test_the_store_line_is_printed_only_once(tmp_path):
    """머리글과 「손님」장이 같은 지역·업종을 두 번 찍으면 안 된다.

    표지가 따로 있던 시절엔 둘이 다른 쪽에 있어 눈에 안 띄었다. 이제
    한 쪽에 4cm 간격으로 나란히 선다.
    """
    쪽들 = _쪽별글_밀도(tmp_path, "한번만.pdf")
    assert 쪽들[0].count("잠실새내역") == 1, (
        f"1쪽에 지역이 {쪽들[0].count('잠실새내역')}번 나온다: {쪽들[0][:220]!r}")


def test_the_floor_area_survives(tmp_path):
    """중복을 지우면서 평수까지 버리면 안 된다 — 머리글엔 평수가 없었다."""
    쪽들 = _쪽별글_밀도(tmp_path, "평수.pdf")
    assert "55평" in 쪽들[0], f"평수가 사라졌다: {쪽들[0][:220]!r}"


# ── 못 읽은 리뷰 건수를 0 으로 찍지 않는다 ─────────────────────
#
# 판독은 플레이스명만 읽혀도 통과한다. 그래서 리뷰 목록은 읽혔는데
# 방문자리뷰·블로그리뷰 건수는 못 읽은 스냅샷이 실제로 만들어진다.
# 서식이 그 자리를 `|| 0` 으로 채우면 종이에 「방문자 리뷰 0건」이 찍힌다 —
# 값이 빠지는 것보다 나쁘다. 없는 걸 0 이라고 말하는 것이다.

_REVIEWS_WITHOUT_COUNTS = {
    "수집시각": "2026-08-14T00:26:31",
    "플레이스": {"방문자리뷰": None, "블로그리뷰": None, "저장수": None},
    "순위": [], "예상매출": None,
    "진단": {"기준일": None, "비교일": None,
             "리뷰": {"방문자": [{"제목": "양꼬치가 두툼합니다", "조회수": 900,
                                  "작성일": "2026-07-16"}], "블로그": []}},
}


def test_unread_review_counts_are_not_printed_as_zero(tmp_path):
    """건수를 못 읽은 날 「방문자 리뷰 0건」이 종이에 찍히면 안 된다."""
    쪽들 = _쪽별글(dict(_BARE_CLIENT, 스냅샷=[_REVIEWS_WITHOUT_COUNTS]),
                   tmp_path, "리뷰건수없음.pdf")
    전체 = "".join(쪽들)
    assert "양꼬치가 두툼합니다" in 전체, "리뷰 목록이 사라졌다"
    assert "0건" not in 전체, f"없는 건수를 0 으로 찍었다: {전체[:400]!r}"


def test_a_real_zero_review_count_is_still_printed(tmp_path):
    """진짜 0 건은 0 으로 찍는다 — 감추면 그것도 거짓말이다."""
    진짜영 = {**_REVIEWS_WITHOUT_COUNTS,
              "플레이스": {"방문자리뷰": 0, "블로그리뷰": 0, "저장수": None}}
    쪽들 = _쪽별글(dict(_BARE_CLIENT, 스냅샷=[진짜영]), tmp_path, "리뷰0건.pdf")
    전체 = "".join(쪽들)
    assert "방문자 리뷰 0건" in 전체, f"진짜 0 건이 사라졌다: {전체[:400]!r}"
    assert "블로그 리뷰 0건" in 전체
