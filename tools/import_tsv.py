"""광고사업부 상품 시트(TSV)를 products.json 으로 옮긴다.

시트는 사람이 읽으려고 만든 물건이라 가격 표기가 제각각이다.
'₩ 30,000', '협의', '예산별', '예산의 1.3배', '셀럽별 상이'가 한 열에 섞여 있다.
여기서 계산 가능한 4유형으로 접는다. 자동으로 못 접는 예외는
overrides.json 에 손으로 적고, 규칙에 우겨넣지 않는다.

시트 행 자체가 결측(매체 공백, 가격·원가·프로세스 전부 공백 등)이라
스킵 규칙에 걸려 통째로 사라지는 상품은 overrides.json 의 "_추가" 목록에
완전한 상품 dict 로 적는다. build_products 가 판매중지 상품과 같은 방식으로
그대로 append 한다 — 스킵 규칙 자체는 건드리지 않는다.
"""
import json
import re
import sys
from pathlib import Path

CMO = Path(__file__).resolve().parent.parent
DATA = CMO / "data"

DISCONTINUED_PREFIX = "없어진 상품 :"

MULTIPLIER_RE = re.compile(r"예산의\s*([\d.]+)\s*배")
MONEY_RE = re.compile(r"^₩?\s*([\d,]+)\s*$")
COST_PAREN_RE = re.compile(r"^([\d,]+)\s*\(\s*([\d,]+)\s*\)$")
COST_OPEN_RE = re.compile(r"^([\d,]+)\s*~$")
DAYS_RE = re.compile(r"(\d+)\s*(?:-\s*(\d+))?\s*(?:영업)?일")


def _to_int(text: str) -> int:
    return int(text.replace(",", ""))


def parse_price(text: str) -> tuple[str, int | None, float | None]:
    """소비자가 칸을 (가격유형, 정가, 예산배율) 로 판정한다."""
    t = (text or "").strip()

    m = MULTIPLIER_RE.search(t)
    if m:
        return "예산배율", None, float(m.group(1))

    if t == "예산별":
        return "예산배율", None, None  # 배율은 overrides 에서 채운다

    m = MONEY_RE.match(t)
    if m:
        return "고정", _to_int(m.group(1)), None

    return "직접입력", None, None


def parse_cost(text: str) -> tuple[int | None, int | None]:
    """원가 칸을 (실비, 실비_내부이체) 로 판정한다.

    괄호 값은 먹스타계좌로 옮기는 몫이다. 실비로는 괄호 밖 금액을 쓴다.
    """
    t = (text or "").strip()

    if t in ("₩ -", "-", "₩-"):
        return 0, None

    m = COST_PAREN_RE.match(t)
    if m:
        return _to_int(m.group(1)), _to_int(m.group(2))

    m = COST_OPEN_RE.match(t)
    if m:
        return _to_int(m.group(1)), None

    m = MONEY_RE.match(t)
    if m:
        return _to_int(m.group(1)), None

    return None, None


def parse_days(process: str) -> int:
    """프로세스 문자열에서 일수 토큰을 모두 더해 소요일수를 낸다."""
    total = 0
    for m in DAYS_RE.finditer(process or ""):
        total += int(m.group(2) or m.group(1))
    return total


def make_id(media: str, name: str) -> str:
    return f"{media.strip()}-{name.strip().replace(' ', '_')}"


def parse_discontinued(first_line: str) -> list[str]:
    if DISCONTINUED_PREFIX not in first_line:
        return []
    tail = first_line.split(DISCONTINUED_PREFIX, 1)[1]
    return [s.strip() for s in tail.split("/") if s.strip()]


def build_products(tsv: str, overrides: dict) -> list[dict]:
    lines = [ln for ln in tsv.splitlines() if ln.strip()]
    discontinued = parse_discontinued(lines[0])
    rows = [ln.split("\t") for ln in lines[2:]]  # 0=안내문, 1=머리글

    products: list[dict] = []
    for row in rows:
        cells = (row + [""] * 9)[:9]
        media, name, price_text, cost_text, notice, memo, weight, process, _ = cells
        if not media.strip() or not name.strip():
            continue
        if not price_text.strip() and not cost_text.strip() and not process.strip():
            continue  # '기타 — 디자인팀/영상사업부 연계' 같은 비상품 행

        kind, list_price, mult = parse_price(price_text)
        cost, internal = parse_cost(cost_text)

        p = {
            "id": make_id(media, name),
            "매체": media.strip(),
            "상품명": name.strip(),
            "가격유형": kind,
            "정가": list_price,
            "실비": cost,
            "실비_내부이체": internal,
            "예산배율": mult,
            "등급": [],
            "단위": "건",
            "최소수량": 1,
            "고지사항": notice.strip(),
            "판매메모": memo.strip(),
            "프로세스": process.strip(),
            "소요일수": parse_days(process),
            "중요도": weight.strip() or "중",
            "판매중지": False,
        }
        p.update(overrides.get(p["id"], {}))
        p.pop("메모", None)
        products.append(p)

    for name in discontinued:
        products.append({
            "id": make_id("네이버", name),
            "매체": "네이버", "상품명": name,
            "가격유형": "직접입력",
            "정가": None, "실비": None, "실비_내부이체": None,
            "예산배율": None, "등급": [], "단위": "건", "최소수량": 1,
            "고지사항": "", "판매메모": "", "프로세스": "",
            "소요일수": 0, "중요도": "하",
            "판매중지": True,
        })

    for extra in overrides.get("_추가", []):
        p = dict(extra)
        p.pop("메모", None)
        products.append(p)

    return _drop_excluded(products, overrides.get("_제외") or {})


def _drop_excluded(products: list[dict], rule: dict) -> list[dict]:
    """상무님이 안 파는 상품을 목록에서 뺀다.

    시트는 광고사업부가 관리하는 물건이라 우리가 고칠 수 없다. 그래서
    시트는 그대로 두고 여기서 걸러낸다 — products.json 만 손으로 지우면
    다음 임포트에 그대로 되살아난다.

    빼는 기준은 셋이다:
      · `상품id` — 이름으로 지목한 것
      · `매체`  — 그 매체 전부
      · `판매중지` — 없어진 상품 전부

    판매중지 상품은 원래 목록에 남겨 잠가 뒀다. 「예전에 하던 그거」를
    사장님이 물을 때 화면에서 짚어 주려던 것이다. 안 쓰기로 했으면
    빼는 게 맞다 — 서랍이 짧을수록 미팅에서 손이 빠르다.
    """
    ids = set(rule.get("상품id") or [])
    media = set(rule.get("매체") or [])
    drop_dead = bool(rule.get("판매중지"))
    return [p for p in products
            if p["id"] not in ids
            and p["매체"] not in media
            and not (drop_dead and p["판매중지"])]


def main() -> int:
    tsv = (DATA / "_source" / "products.tsv").read_text(encoding="utf-8")
    overrides = json.loads((DATA / "overrides.json").read_text(encoding="utf-8"))
    products = build_products(tsv, overrides)
    out = DATA / "products.json"
    out.write_text(
        json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(products)}종 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
