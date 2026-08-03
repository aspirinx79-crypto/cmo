"""상품의 프로세스 문장에서 1개월차 실행 일정표를 만든다.

시트의 프로세스 열에는 이미 기간이 들어 있다.
  "양식 받기 -> 5-7일 모집 / 1일 선정 / 14-20일 체험,포스팅 / 2영업일 후 보고서"
따로 일정을 쓰지 않고 이 문장을 그대로 쓴다.

일수 범위는 큰 쪽을 잡는다. 일정이 늦어지는 쪽으로 틀리는 게
빨라지는 쪽으로 틀리는 것보다 사고가 작다.
"""
import re

STEP_SPLIT_RE = re.compile(r"->|→|/")
DAYS_RE = re.compile(r"(\d+)\s*(?:-\s*(\d+))?\s*(?:영업)?일")
WEEKS = 4


def parse_steps(process: str) -> list[dict]:
    steps: list[dict] = []
    for chunk in STEP_SPLIT_RE.split(process or ""):
        label = chunk.strip().strip(",")
        if not label:
            continue
        m = DAYS_RE.search(label)
        days = int(m.group(2) or m.group(1)) if m else 0
        steps.append({"단계": label, "일수": days})
    return steps


def weekly_plan(products: list[dict], items: list[dict]) -> list[dict]:
    by_id = {p["id"]: p for p in products}
    buckets: list[list[str]] = [[] for _ in range(WEEKS)]

    for item in items:
        product = by_id.get(item["상품id"])
        if product is None:
            continue

        cursor = 0
        for step in parse_steps(product.get("프로세스", "")):
            week = min(cursor // 7, WEEKS - 1)
            buckets[week].append(f"{product['상품명']} — {step['단계']}")
            cursor += step["일수"]

    return [{"주차": i + 1, "항목": buckets[i]} for i in range(WEEKS)]
