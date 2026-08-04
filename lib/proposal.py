"""제안서용 데이터를 조립한다.

여기서 실비·마진을 넣지 않는다. 화면에서 가리는 게 아니라
제안서 쪽으로는 값 자체가 넘어가지 않는다. 언젠가 서식을 고치다
실수하는 날이 오는데, 그때 값이 없으면 새어 나갈 수가 없다.
"""
from .pricing import line_amount
from .schedule import weekly_plan

FORBIDDEN_KEYS = ("실비", "실비_내부이체", "원가", "마진", "마진율")

# 제안서 일정표에서 걸러낼 내부 문구.
#
# 시트의 프로세스 열은 상무님이 실무용으로 쓴 문장이다. 거기엔 "누가 무엇을
# 받아서 어디로 넘기는지" 가 그대로 적혀 있고, 그건 우리 내부 사정이지
# 사장님이 산 결과물이 아니다. 실제로 나간 제안서에 "언론송출 — 컨펌된 원고
# 및 사진 김대한 대표에게 전달", "리뷰작업 — 실장님께 알바풀 전달" 같은 줄이
# 실렸다. 세 부류를 거른다.
#
#   1) 직함 — 내부 담당자를 특정하면 조직도가 고객 손에 넘어간다. 담당자가
#      바뀌면 제안서가 틀린 문서가 되기도 한다.
#   2) 내부 채널·행위 — 단톡방·소통·전달·컨트롤은 우리끼리의 업무 흐름이다.
#      고객이 돈을 낸 대상(모집·체험·포스팅·보고서)이 아니다.
#   3) 외주 구조 — 상위대행사·이관·알바풀·레뷰는 우리가 어디에 재하청을
#      주는지 드러낸다. 알고 나면 고객은 그쪽에 직접 연락한다.
#
# 목록 조정은 상무님 판단 영역이다. 과잉 필터·누락이 보이면 여기서 임의로
# 고치지 말고 보고할 것.
INTERNAL_STEP_WORDS = (
    # 직함
    "대표", "이사", "본부장", "실장",
    # 내부 채널·행위
    "단톡", "소통", "컨트롤", "전달",
    # 외주 구조
    "상위대행사", "대행가", "이관", "외주", "알바풀", "레뷰",
)

DIFFERENTIATORS = [
    "매주 결과보고서를 드립니다. 무엇을 했고 무엇이 움직였는지 주 단위로 확인하십시오.",
    "단톡방으로 바로 소통합니다. 메뉴가 바뀌거나 휴무가 생기면 그날 반영됩니다.",
    "잘 나온 마케팅은 다음 달 기획에 그대로 이어갑니다. 안 된 것은 바꿉니다.",
]


class ProposalBlocked(Exception):
    """정가가 비어 제안서를 만들 수 없다."""


def _latest_snapshot(client: dict) -> dict:
    snaps = client.get("스냅샷") or []
    return snaps[-1] if snaps else {}


def _metrics(client: dict) -> dict:
    snap = _latest_snapshot(client)
    place = snap.get("플레이스") or {}
    revenue = snap.get("예상매출") or {}
    return {
        "수집시각": snap.get("수집시각"),
        "방문자리뷰": place.get("방문자리뷰"),
        "블로그리뷰": place.get("블로그리뷰"),
        "순위": snap.get("순위") or [],
        # 오픈업 추정 매출의 절대금액은 싣지 않는다. 상대 표현만 쓴다.
        "상권순위": revenue.get("상권순위"),
    }


def _quantity_label(product: dict, item: dict) -> str:
    unit = product.get("단위") or "건"
    if product["가격유형"] == "예산배율":
        return f"월 {int(item.get('예산') or 0):,}원 집행"
    if product["가격유형"] == "직접입력":
        return item.get("수량표시") or "1식"
    qty = int(item.get("수량") or 1)
    grade = item.get("등급")
    return f"{grade} {qty}{unit}" if grade else f"{qty}{unit}"


def _client_facing_schedule(weeks: list[dict]) -> list[dict]:
    """일정표에서 내부 문구가 든 단계를 뺀 사본을 만든다.

    `schedule.weekly_plan()` 의 반환값은 손대지 않는다 — 구성판 내부 화면은
    프로세스 원문을 그대로 봐야 한다. 상무님은 실제 진행 절차를 다 봐야 하고,
    거르는 건 고객에게 나가는 제안서 쪽뿐이다.

    검사는 렌더된 줄("상품명 — 단계") 전체를 대상으로 한다. 상품명에도 내부
    문구가 들어 있을 수 있어서(시트가 손편집이다) 단계 부분만 보면 새어 나간다.
    한 상품의 단계가 전부 걸러지면 그 상품은 일정표에 안 나온다. 빈 주차는 빈
    채로 둔다 — 서식이 '—' 로 렌더한다.
    """
    return [
        {
            "주차": week["주차"],
            "항목": [line for line in week["항목"]
                    if not any(word in line for word in INTERNAL_STEP_WORDS)],
        }
        for week in weeks
    ]


def build_payload(client: dict, plan: dict, products: list[dict]) -> dict:
    by_id = {p["id"]: p for p in products}
    lines, notices = [], []
    정가합 = 0

    for item in plan["항목"]:
        product = by_id[item["상품id"]]
        if product["가격유형"] == "직접입력" and not item.get("정가"):
            raise ProposalBlocked(
                f"{product['상품명']}: 정가가 비어 있어 제안서를 만들 수 없습니다"
            )

        amount = line_amount(product, item)
        정가합 += amount["정가"]
        lines.append({
            "매체": product["매체"],
            "상품명": product["상품명"],
            "수량표시": _quantity_label(product, item),
            "정가": amount["정가"],
        })
        notice = (product.get("고지사항") or "").strip()
        if notice and notice not in notices:
            notices.append(notice)

    계약가 = int(plan.get("계약가") or 0)
    배율 = (정가합 / 계약가) if 계약가 else 0
    문구 = f"{정가합:,}원 상당을 {계약가:,}원에 (약 {배율:.1f}배)"

    return {
        "매장명": client["이름"],
        "월": plan["월"],
        "업종": client.get("업종", ""),
        "지역": client.get("지역", ""),
        "평수": client.get("평수"),
        "진단": plan.get("진단메모", ""),
        "지표": _metrics(client),
        "구성": lines,
        "정가합": 정가합,
        "계약가": 계약가,
        "혜택배율문구": 문구,
        "일정": _client_facing_schedule(weekly_plan(products, plan["항목"])),
        "고지사항": notices,
        "차별점": DIFFERENTIATORS,
    }
