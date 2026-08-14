"""견적서 payload 를 만든다.

**금액은 계약가 하나에서만 온다.** 정가·정가합·실비·마진은 한 글자도
들어가지 않는다 — 견적서는 고객이 받는 문서고, 정가를 섞으면 받은 분이
어느 숫자를 내야 하는지 헷갈린다.

**회사 정보는 이 파일 상수 하나에서만 온다.** 받은 견적서 세 건에서
사업장·전화·계좌가 전부 달랐다. 매번 예전 파일을 복사해 고쳐 쓴 탓이다.
"""
import os
from datetime import date

from cmo.lib.prescription import SUPPORT, role_of

# 공정위 대가성 문구.
#
# 제안서에서 고지사항 장을 뺐다. 이 한 줄까지 사라지면 사장님이
# 「내 블로그 리뷰에 광고 표기가 붙는다」는 사실을 모른 채 계약한다.
# 계약 문서 쪽에 남긴다.
#
# 받치기 갈래가 곧 대가성 표기 대상이라 목록을 따로 만들지 않는다 —
# 분류표 하나를 제안서와 견적서가 같이 쓴다.
AD_NOTICE = "체험단·배포 콘텐츠에는 공정위 규정에 따른 대가성 문구가 삽입됩니다."

VAT_RATE = 0.1

# 계좌번호는 환경변수에서만 온다.
#
# 저장소에 적으면 히스토리에 영원히 남고, 저장소는 언젠가 공개되거나
# 다른 사람 손에 들어간다. 나머지 발주처 정보(상호·사업자등록번호·주소)는
# 견적서에 찍혀 고객에게 나가는 값이라 여기 둔다 — 계좌만 다르다.
BANK_ENV = "CMO_BANK_ACCOUNT"

# 발주처. 서식이 아니라 여기서만 고친다.
QUOTE_ISSUER = {
    "상호": "㈜먹스타",
    "사업자등록번호": "356-88-02874",
    "대표자": "이인선",
    "사업장": "서울시 강남구 압구정로2길 60, MG타워 6층",
    "담당자": "이인선 대표 010-4754-1667",
    "전화번호": "1688-2633",
    "팩스번호": "050-4024-9029",
    "이메일": "ssavengers@ssagroup.co.kr",
    "홈페이지": "winwin-avengers.com",
}


def issuer() -> dict:
    """발주처 정보에 계좌를 얹은 사본. 계좌는 환경변수에서 읽는다.

    환경변수가 없으면 빈 글자다 — 견적서에서 그 줄이 통째로 빠진다.
    지어내지 않는다.
    """
    return {**QUOTE_ISSUER, "계좌": (os.environ.get(BANK_ENV) or "").strip()}

NO_PRICE = "계약가를 먼저 넣으십시오. 0원짜리 견적서는 만들지 않습니다."


class QuoteBlocked(Exception):
    """계약가가 없어 견적서를 만들 수 없다."""


def _detail(product: dict, item: dict) -> str:
    """내역 한 줄. **금액을 붙이지 않는다.**

    상품명과 수량만 적는다. 항목별 금액을 찍으면 원가 구조가 드러난다 —
    `proposal.py` 가 실비·마진을 막아온 것과 같은 선이다.
    """
    unit = product.get("단위") or "건"
    if product.get("가격유형") == "예산배율":
        return f"{product['상품명']} 집행"
    if product.get("가격유형") == "직접입력":
        return f"{product['상품명']} {item.get('수량표시') or '1식'}"
    return f"{product['상품명']} {int(item.get('수량') or 1)}{unit}"


def build_quote_payload(client: dict, plan: dict, products: list[dict], *,
                        부가세별도: bool = False, 내역펼침: bool = True,
                        today: date | None = None) -> dict:
    """견적서 한 장에 들어갈 값을 만든다. 아무것도 저장하지 않는다."""
    계약가 = int(plan.get("계약가") or 0)
    if 계약가 <= 0:
        raise QuoteBlocked(NO_PRICE)

    by_id = {p["id"]: p for p in products}
    세부 = []
    if 내역펼침:
        for item in plan.get("항목") or []:
            product = by_id.get(item.get("상품id"))
            if product:                      # 지워진 상품은 그 줄만 빠진다
                세부.append(_detail(product, item))

    받치기있음 = any(role_of(it.get("상품id", "")) == SUPPORT
                     for it in (plan.get("항목") or []))

    부가세 = 0 if 부가세별도 else int(round(계약가 * VAT_RATE))
    이름 = client["이름"]
    today = today or date.today()

    return {
        "견적내용": f"{이름} CMO 서비스",
        "요청인": f"{이름} 귀하",
        "견적일자": today.isoformat(),
        "유효일": "15일",
        "납기일": "협의",
        "월": plan.get("월", ""),
        "항목": [{"번호": 1, "이름": "CMO 서비스", "수량": 1,
                  "단가": 계약가, "합": 계약가, "세부": 세부}],
        "합계": 계약가,
        "부가세": 부가세,
        "총합": 계약가 + 부가세,
        "부가세문구": "총합 (vat별도)" if 부가세별도 else "총합 (vat포함)",
        "발주처": issuer(),
        "고지": AD_NOTICE if 받치기있음 else "",
    }
