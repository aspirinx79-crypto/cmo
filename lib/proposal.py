"""제안서용 데이터를 조립한다.

여기서 실비·마진을 넣지 않는다. 화면에서 가리는 게 아니라
제안서 쪽으로는 값 자체가 넘어가지 않는다. 언젠가 서식을 고치다
실수하는 날이 오는데, 그때 값이 없으면 새어 나갈 수가 없다.
"""
from .pricing import line_amount
from .schedule import weekly_plan

FORBIDDEN_KEYS = ("실비", "실비_내부이체", "원가", "마진", "마진율")

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
        "일정": weekly_plan(products, plan["항목"]),
        "고지사항": notices,
        "차별점": DIFFERENTIATORS,
    }
