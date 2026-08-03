"""가격 3층 계산.

정가  — 낱개로 살 때 가격. 고객에게 보여준다.
계약가 — 사장님이 실제 내는 월 금액.
실비  — 우리가 실제 지출. 내부 전용.

여기서 나오는 두 숫자가 서로 다른 말을 한다.
  혜택배율 = 정가합 ÷ 계약가   → "150만원치를 100만원에"
  마진율   = (계약가 − 실비합) ÷ 계약가
"""


def line_amount(product: dict, item: dict) -> dict:
    """항목 한 줄의 정가·실비를 낸다."""
    kind = product["가격유형"]

    if kind == "고정":
        qty = int(item.get("수량") or 0)
        return {"정가": (product["정가"] or 0) * qty,
                "실비": (product["실비"] or 0) * qty}

    if kind == "예산배율":
        budget = int(item.get("예산") or 0)
        rate = product.get("예산배율") or 1.0
        return {"정가": round(budget * rate), "실비": budget}

    if kind == "등급선택":
        name = item.get("등급")
        grade = next((g for g in product.get("등급", []) if g["이름"] == name), None)
        if grade is None:
            raise ValueError(f"{product['상품명']}: 알 수 없는 등급 {name!r}")
        qty = int(item.get("수량") or 1)
        return {"정가": grade["정가"] * qty, "실비": grade["실비"] * qty}

    # 직접입력
    return {"정가": int(item.get("정가") or 0), "실비": int(item.get("실비") or 0)}


def summarize(products: list[dict], items: list[dict], 계약가: int) -> dict:
    by_id = {p["id"]: p for p in products}
    정가합 = 실비합 = 0
    경고: list[str] = []
    줄별: list[dict] = []

    for item in items:
        product = by_id.get(item["상품id"])
        if product is None:
            경고.append(f"상품을 찾을 수 없습니다: {item['상품id']}")
            continue

        if product.get("판매중지"):
            경고.append(f"{product['상품명']} 은 판매중지 상품입니다")

        if product["가격유형"] == "고정":
            qty = int(item.get("수량") or 0)
            minimum = product.get("최소수량") or 1
            if qty < minimum:
                unit = product.get("단위") or "건"
                경고.append(
                    f"{product['상품명']}: {minimum}{unit} 이상이어야 합니다 (현재 {qty}{unit})"
                )

        if product["가격유형"] == "직접입력" and not item.get("정가"):
            경고.append(f"{product['상품명']}: 정가를 입력해야 제안서가 만들어집니다")

        amount = line_amount(product, item)
        정가합 += amount["정가"]
        실비합 += amount["실비"]
        줄별.append({"상품id": item["상품id"], **amount})

    마진 = 계약가 - 실비합
    return {
        "정가합": 정가합,
        "실비합": 실비합,
        "마진": 마진,
        "마진율": (마진 / 계약가) if 계약가 else None,
        "혜택배율": (정가합 / 계약가) if 계약가 else None,
        "경고": 경고,
        "줄별": 줄별,
    }
