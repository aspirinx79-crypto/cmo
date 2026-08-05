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
#   2) 내부 채널·행위 — 단톡방·컨트롤은 우리끼리의 업무 흐름이다. 고객이
#      돈을 낸 대상(모집·체험·포스팅·보고서)이 아니다.
#   3) 외주 구조 — 상위대행사·이관·알바풀·레뷰는 우리가 어디에 재하청을
#      주는지 드러낸다. 알고 나면 고객은 그쪽에 직접 연락한다.
#
# `소통`·`전달` 은 뺐다(수정 라운드 2). 카탈로그 전수 대조 결과 이 둘이
# 단독으로 막고 있는 유출 줄이 하나도 없었다 — 진짜 유출 줄은 전부 다른
# 단어에도 걸린다("김대한대표에게 전달"→대표, "실장님께 알바풀 전달"→실장·
# 알바풀, "단톡방 소통"→단톡, "홍인표이사와 소통"→이사, "레뷰차이나측 소통"
# →레뷰). 대신 이 둘 때문에 "클라이언트 소통 및 디자인 컨펌"(고객'과의'
# 소통이라 오히려 보여줘야 할 약속)과 "유튜버 전달 및 촬영"(카탈로그 전체에서
# `촬영` 이 든 유일한 줄)이 죽었다. 겹쳐 막느라 멀쩡한 줄을 죽이는 단어는
# 넣지 않는다. `컨트롤` 은 남긴다 — "플친 컨트롤"·"먹스타 커뮤니티 컨트롤" 은
# 컨트롤이 유일한 방어선이다.
#
# `입금요청` 은 유출이 아니라 문서 격 때문에 넣었다. 제안서의 실행 일정
# 마지막 줄이 "입금요청" 이면 안 된다.
#
# 목록 조정은 상무님 판단 영역이다. 과잉 필터·누락이 보이면 여기서 임의로
# 고치지 말고 보고할 것.
INTERNAL_STEP_WORDS = (
    # 직함
    "대표", "이사", "본부장", "실장",
    # 내부 채널·행위
    "단톡", "컨트롤", "입금요청",
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


LINE_SEP = " — "
FALLBACK_STEP = "진행"

# 시트 작성자 메모의 시작 표시.
#
# 상무님은 시트의 프로세스 열에 본인용 메모를 `_` 뒤에 붙여 쓴다. 실제로 나간
# PDF 에 이 줄들이 그대로 찍혔다:
#   블로그 일반 체험단 — 2영업일 후 보고서 (약 1달 기간) _융통성 있게
#   블로그 프리미엄 체험단 — 10일 포스팅 원칙_융통성 있게
# 사장님은 "융통성 있게" 를 "일정 대충 하겠다는 거네" 로 읽는다. 금칙어와는
# 다른 종류라(유출이 아니라 어투다) `INTERNAL_STEP_WORDS` 에 안 걸렸다.
#
# 카탈로그 전수 확인: `_` 가 든 단계는 3개이고 세 개 모두 `_융통성 있게` —
# 작성자 메모율 100%다. 그래서 `_` 뒤는 통째로 뗀다.
#
# 괄호는 **떼지 않는다.** 카탈로그 전체에서 괄호가 든 단계는
# `2영업일 후 보고서 (약 1달 기간)` 한 줄뿐이고, 내용이 "얼마나 걸리냐" 라는
# 기간 정보다. 일정표는 바로 그 질문에 답하는 표다. 표본 하나로 "괄호는 뗀다"
# 는 일반 규칙을 세우면 나중에 들어올 `(주말 제외)` 같은 고객에게 필요한
# 괄호까지 같이 죽는다. 판단은 상무님 영역이니 뒤집을 일이 있으면 보고할 것
# (뒤집는다면 `_without_author_note` 에 괄호 제거 한 줄을 더하면 된다).
AUTHOR_NOTE_MARK = "_"

# 한 달 내내 도는 단계 — 놓인 주차부터 4주차까지 매 주에 반복해 보여준다.
#
# `schedule.weekly_plan()` 은 프로세스 문장에 적힌 일수로만 주차를 잡는데,
# 카탈로그 85개 단계 중 74개에 일수가 없고 항목마다 커서가 0으로 리셋된다
# (`schedule.py:38`). 그래서 실제로 만든 PDF 가 1주차 14줄 / 2주차 3줄 /
# **3주차 0줄** / 4주차 1줄로 나왔다. 사장님 눈에는 "3주차엔 아무것도 안 하네"
# 다. 상무님 결정: "관리·운영·진행처럼 한 달 내내 하는 단계는 1~4주차에 모두
# 표시하고, 나머지 기간 없는 단계만 1주차에 둔다."
#
#   `관리` — `관리`(SA·DA·구글애즈 5개 상품), `수시 관리`, `월별 관리`.
#      광고 계정 운용은 월 단위로 계속 돈다.
#   `운영` — `운영대행`. 한 달 내내 계정을 돌리는 게 상품 자체다.
#   `보고 및 피드백` — `통계보며 보고 및 피드백`(5개 상품). 통계는 매주 본다.
#      `보고` 만 쓰면 `파워매체 — 게시 및 보고`(1회 게시 후 보고)까지 걸린다.
#   `" 진행"` — **앞 공백이 핵심이다.** `배너 진행`(2개)·`소재 비즈톡 진행`,
#      그리고 단계가 전부 걸린 상품의 대체 줄 `{상품명} — 진행` 을 잡는다.
#      앞 공백이 있어야 `상생 먹스타 파티 — 파티진행` 을 **일부러 안 잡는다** —
#      파티는 하루짜리 행사라 1~4주차에 매주 세워 두면 거짓말이 된다.
#
# 검사는 **단계 부분에만** 건다(상품명 제외, `_is_ongoing` 참고). 렌더된 줄
# 전체로 검사하면 `운영대행 — 미팅`(상품명에 `운영`) 같은 하루짜리 단계가
# 매주 반복돼 역시 거짓말이 된다.
#
# 안 걸리는 것도 전수로 확인했다: `타겟광고 — 타겟광고`(상품명이 단계로 반복된
# 경우)는 1주차에만 남는다 — 허용.
#
# 목록 조정은 상무님 판단 영역이다. 임의로 고치지 말고 보고할 것.
ONGOING_STEP_WORDS = ("관리", "운영", "보고 및 피드백", " 진행")


def _is_internal(text: str) -> bool:
    return any(word in text for word in INTERNAL_STEP_WORDS)


def _is_ongoing(step: str) -> bool:
    """이 단계가 한 달 내내 도는 종류인가. 단계만 본다 — 상품명은 안 본다.

    단계 앞에 공백 하나를 붙여 검사한다. 렌더된 줄에서 단계 앞에는 언제나
    `" — "` 의 공백이 오므로, `" 진행"` 처럼 앞 공백을 붙인 키워드가 단계의
    첫 단어(대체 줄의 `진행`)에도 똑같이 걸린다.
    """
    return any(word in f" {step}" for word in ONGOING_STEP_WORDS)


def _product_of(line: str) -> str:
    """일정표 한 줄에서 상품명을 떼어 낸다.

    `schedule.weekly_plan()` 이 f"{상품명} — {단계}" 로 만든다. 앞부분만 본다.
    """
    return line.split(LINE_SEP, 1)[0]


def _step_of(line: str) -> str:
    """일정표 한 줄에서 단계만 떼어 낸다. 상품명은 버린다."""
    return line.partition(LINE_SEP)[2]


def _without_author_note(line: str) -> str:
    """줄에서 시트 작성자 메모를 뗀 사본. 뗀 뒤 단계가 비면 빈 문자열.

    **상품명(왼쪽)은 건드리지 않는다.** `1세대 블로거 _케케케라인 12팀` 처럼
    상품명 자체에 `_` 가 든 상품이 실제로 있어서, 줄 전체에서 `_` 를 자르면
    상품명이 잘려 나간다. 첫 `" — "` 로 나눠 오른쪽만 손댄다.
    """
    name, sep, step = line.partition(LINE_SEP)
    if not sep:
        return line
    step = step.split(AUTHOR_NOTE_MARK, 1)[0].strip()
    return f"{name}{LINE_SEP}{step}" if step else ""


def _place(out: list[dict], index: int, line: str) -> None:
    """줄을 `index` 주차에 넣는다. 한 달 내내 도는 단계면 4주차까지 이어 붙인다.

    같은 주에 글자까지 같은 줄이 두 번 들어가지 않게 한다. `네이버-SA` 와
    `구글-SA` 처럼 상품명·단계가 똑같은 상품이 있어서, 둘을 같이 팔면 고객
    눈에는 같은 줄이 두 번 찍힌 오타로 보인다(반복까지 하면 네 주 내내).
    """
    last = len(out) - 1 if _is_ongoing(_step_of(line)) else index
    for week in range(index, last + 1):
        if line not in out[week]["항목"]:
            out[week]["항목"].append(line)


def _client_facing_schedule(weeks: list[dict]) -> list[dict]:
    """일정표에서 내부 문구가 든 단계를 뺀 사본을 만든다.

    `schedule.weekly_plan()` 의 반환값은 손대지 않는다 — 구성판 내부 화면은
    프로세스 원문을 그대로 봐야 한다. 상무님은 실제 진행 절차를 다 봐야 하고,
    거르는 건 고객에게 나가는 제안서 쪽뿐이다.

    검사는 렌더된 줄("상품명 — 단계") 전체를 대상으로 한다. 상품명에도 내부
    문구가 들어 있을 수 있어서(시트가 손편집이다) 단계 부분만 보면 새어 나간다.

    한 상품의 단계가 **전부** 걸러지면 그 상품의 첫 단계가 놓였을 주차에
    "{상품명} — 진행" 한 줄을 대신 넣는다. 프로세스가 한 줄뿐이고 그게 내부
    문구인 상품이 여럿이라, 그런 상품만 판 달은 일정 쪽이 통째로 빈 종이가
    됐다. 돈을 낸 사람이 자기가 산 게 일정표에 없는 걸 보면 안 된다. 내부
    절차는 안 보이고 "이 상품이 이 달에 돌아간다" 는 사실만 남는다.

    대체 줄에도 같은 필터를 건다. 상품명 자체에 금칙어가 든 상품이 있어서
    (예: "전국 대학생 동아리 단톡 침투") 대체 줄이 새 유출 경로가 될 수 있다.
    실패는 닫히는 쪽으로 — 그런 상품은 대체 줄도 안 나간다.

    프로세스가 아예 비어 원래부터 일정표에 없던 상품에는 대체 줄을 만들지
    않는다. 걸러서 사라진 것과 애초에 단계가 없던 것은 다른 경우다. 여기는
    `weekly_plan()` 이 낸 줄만 보므로 그런 상품은 자연히 대상이 아니다.

    시트 작성자 메모(`_` 뒤)는 단계 부분에서만 떼어 낸다. 메모를 떼고 나서
    단계가 통째로 비면 그 줄은 걸린 것과 똑같이 취급한다 — `{상품명} — ` 처럼
    꼬리 잘린 줄을 내보내느니 위의 대체 줄 경로로 넘긴다.

    내부 문구 검사는 **원문 줄**에 건다. 메모를 떼는 건 문구를 다듬는 일이지
    방어선을 넓히는 일이 아니다. 금칙어가 메모 안에 있었더라도 그 줄은 안
    내보낸다 — 실패는 닫히는 쪽으로.

    한 달 내내 도는 단계(`ONGOING_STEP_WORDS`)는 놓인 주차부터 4주차까지
    반복해 넣는다(`_place`). 반복은 **필터를 통과한 줄에만** 건다 — 걸린 줄은
    애초에 `_place` 까지 오지 않으므로, 반복으로 늘어난 줄에도 내부 문구
    필터가 그대로 적용된다.

    남는 빈 주차는 빈 채로 둔다 — 서식이 '—' 로 렌더한다.
    """
    kept: dict[str, int] = {}
    for week in weeks:
        for line in week["항목"]:
            name = _product_of(line)
            shown = _without_author_note(line)
            survives = bool(shown) and not _is_internal(line)
            kept[name] = kept.get(name, 0) + (1 if survives else 0)

    seen: set[str] = set()
    out: list[dict] = [{"주차": week["주차"], "항목": []} for week in weeks]
    for index, week in enumerate(weeks):
        for line in week["항목"]:
            name = _product_of(line)
            first = name not in seen
            seen.add(name)
            shown = _without_author_note(line)
            if shown and not _is_internal(line):
                _place(out, index, shown)
            elif first and kept[name] == 0:
                fallback = f"{name}{LINE_SEP}{FALLBACK_STEP}"
                if not _is_internal(fallback):
                    _place(out, index, fallback)
    return out


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
