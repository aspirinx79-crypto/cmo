"""제안서용 데이터를 조립한다.

여기서 실비·마진을 넣지 않는다. 화면에서 가리는 게 아니라
제안서 쪽으로는 값 자체가 넘어가지 않는다. 언젠가 서식을 고치다
실수하는 날이 오는데, 그때 값이 없으면 새어 나갈 수가 없다.
"""
from .pricing import line_amount
from .prescription import prescribe
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


def _has_data(snap: dict) -> bool:
    """자료가 든 스냅샷인가.

    **「진단이 있나」로 보면 안 된다.** 캡처 판독은 아무것도 못 읽은
    날에도 키를 다 채운 진단을 넣는다(`read_doc.snapshot_from`). 키가
    있으니 dict 는 참이고, 그러면 빈 캡처가 자료 있는 스냅샷 행세를
    해서 앞서 읽어 둔 것을 가린다. 칸의 값을 본다.
    """
    if _has_rank_value(snap):
        return True
    진단 = snap.get("진단") or {}
    if any(진단.get(키) for 키 in ("기준일", "대표키워드", "히든키워드")):
        return True
    if _has_review_value(snap):
        return True
    if _has_revenue_value(snap):
        return True
    return _has_place_value(snap)


def _latest_snapshot(client: dict) -> dict:
    """자료가 있는 마지막 스냅샷.

    **`snaps[-1]` 을 쓰면 안 된다.** 고장난 순위조회가 값이 전부 `null`
    인 스냅샷을 뒤에 계속 붙이는데, 그러면 애드로그로 읽어 둔 자료가
    통째로 가려진다. 실제로 그렇게 나간 제안서가 있다.
    """
    있는것 = [s for s in (client.get("스냅샷") or []) if _has_data(s)]
    return 있는것[-1] if 있는것 else {}


def _snapshot_with(client: dict, 있나) -> dict:
    """조건을 만족하는 마지막 스냅샷. 없으면 빈 dict.

    출처가 둘이다 — 애드로그(순위·조회수·리뷰수)와 캡처(히든키워드·
    리뷰 목록). 애드로그에 없는 칸이 있어서, 마지막 한 건만 보면
    갱신할 때마다 캡처가 넣어 둔 것이 가려진다. 칸마다 그 값을 가진
    마지막 스냅샷에서 읽는다.

    저장된 스냅샷은 여전히 한 시점이다. 섞는 건 읽는 쪽이고, 그래서
    장마다 기준일을 함께 찍는다.
    """
    있는것 = [s for s in (client.get("스냅샷") or []) if 있나(s)]
    return 있는것[-1] if 있는것 else {}


def _has_place_value(snap: dict) -> bool:
    return any(v is not None for v in (snap.get("플레이스") or {}).values())


def _place_value(client: dict, 칸: str):
    """플레이스 한 칸을, 그 칸에 값이 든 마지막 스냅샷에서 읽는다.

    **세 칸을 한 덩이로 고르면 안 된다.** 캡처 판독은 플레이스명만
    읽혀도 통과한다(`read_doc.parse_reading`). 그래서 저장수 한 칸만
    읽힌 판독이 실제로 만들어지는데, `_has_place_value` 로 한 번에
    고르면 그 판독이 앞선 판독의 방문자리뷰·블로그리뷰를 가린다.
    서식은 빈 자리를 `0` 으로 찍어서 종이에 「방문자 리뷰 0건」이
    나간다 — 값이 빠지는 것보다 나쁘다. 없는 걸 0 이라고 말한다.
    """
    snap = _snapshot_with(
        client, lambda s: (s.get("플레이스") or {}).get(칸) is not None)
    return (snap.get("플레이스") or {}).get(칸)


# 순위 줄에서 제안서가 실제로 종이에 찍는 칸.
#
# 키워드가 종이에 닿는 문은 둘뿐이다 — 기회표는 조회수가 있어야 서고
# (`_opportunity`), 처방은 비교순위가 있어야 선다(`_moves`). 나머지
# 세 칸(키워드·순위·순위권밖)은 이 둘이 연 문 안에서만 읽힌다.
_RANK_VALUE_KEYS = ("조회수", "비교순위")


def _has_rank_value(snap: dict) -> bool:
    """순위 줄에 제안서가 쓸 값이 들어 있나.

    **「순위 줄이 있나」로 고르면 안 된다.** 순위는 칸 하나가 아니라
    다섯 칸짜리 줄의 묶음이고, 줄이 몇 개 있다는 사실과 그 줄에 찍을
    값이 들었다는 사실은 다르다. 「지표 저장」은 손으로 친 순위를
    `{키워드, 순위}` 두 칸으로만 담는데(`collect.make_snapshot`),
    리스트가 비었나만 보면 이 얇은 줄이 캡처·애드로그의 다섯 칸짜리
    줄을 이긴다 — 상권순위 하나 넣으려고 누른 저장에 헤드라인·기회표·
    요약 카드·기준일·처방이 함께 사라졌다.

    `_has_review_value` 가 빈 dict 에서 잡은 것과 같은 착각이다.
    이번에는 dict 가 아니라 리스트 쪽이다.
    """
    return any(row.get(키) is not None
               for row in (snap.get("순위") or [])
               for 키 in _RANK_VALUE_KEYS)


def _has_summary_value(snap: dict) -> bool:
    """요약 카드 셋에 숫자가 들어 있나.

    판독기는 요약을 못 읽은 날에도 `{"총키워드": None, "TOP3": None,
    "TOP10": None}` 를 채운다(`read_doc.snapshot_from`). 키가 셋이라
    dict 자체는 참이다. 값을 본다.

    쓰는 데는 한 곳뿐이다 — 순위를 준 스냅샷이 아예 없을 때의 대비책
    (`_search`). 평소에 요약은 순위와 한 스냅샷에서 읽는다. **이걸로
    요약을 늘 따로 고르면 안 된다** — 카드와 기회표가 서로 다른 시점을
    말하는 종이가 나간다.
    """
    return any(v is not None for v in (snap.get("순위요약") or {}).values())


def _has_review_value(snap: dict) -> bool:
    """리뷰 줄에 제안서가 쓸 값이 들어 있나.

    **「리뷰 칸이 있나」로도 「리뷰 줄이 있나」로도 고르면 안 된다.**
    캡처 판독은 그날 리뷰를 못 찾아도 `{"방문자": [], "블로그": []}` 를
    채워 넣고(`read_doc.snapshot_from`), 리뷰 줄은 **제목만 읽히면**
    남긴다(`read_doc._review_rows`). 키가 둘이라 dict 가 참이고, 줄이
    하나라 리스트도 참이다. 어느 쪽이든 앞선 캡처의 리뷰를 가린다 —
    조회수를 못 읽은 한 줄짜리 캡처가 「많이 읽힌 리뷰」를 지웠다.

    리뷰가 종이에 닿는 문은 하나다 — `_reviews` 는 **조회수가 있는
    방문자 줄만** 쓴다. 블로그 줄은 한 글자도 안 나가고, 리뷰 건수 둘은
    플레이스 칸에서 온다. `_has_rank_value` 와 같은 결이다.
    """
    방문 = ((snap.get("진단") or {}).get("리뷰") or {}).get("방문자") or []
    return any(줄.get("조회수") is not None for 줄 in 방문)


def _has_revenue_value(snap: dict) -> bool:
    """예상매출에서 제안서가 읽는 칸에 값이 들어 있나.

    **예상매출 dict 가 있나로 보면 안 된다.** 「지표 저장」은 상권순위
    칸을 비운 채 월매출만 넣어도 `{"월매출": …, "상권순위": "", "출처":
    "오픈업", "입력방식": "수동"}` 을 남긴다(`app/client.js`). 네 칸 중
    셋이 차 있으니 dict 도 참이고 `is not None` 도 참이라, 그 저장이
    앞서 넣어 둔 상권순위를 가린다.

    읽는 칸은 상권순위 하나다 — 월매출 절대금액은 제안서로 안 나가고
    (`_metrics`), 출처·입력방식은 내부 기록이다. 빈 글자는 「칸을 비웠다」
    는 뜻이라 값으로 안 센다.
    """
    return bool((snap.get("예상매출") or {}).get("상권순위"))


def _metrics(client: dict) -> dict:
    """방문자리뷰·블로그리뷰는 **칸마다** 그 값을 가진 마지막 스냅샷에서 읽는다.

    애드로그 스냅샷에 리뷰수가 있으면 그게 최신이다 — 순위와 따로
    갱신될 수 있어 `_latest_snapshot` 대신 칸별로 고른다. 세 칸을 한
    덩이로 고르면 한 칸만 읽힌 판독이 나머지 둘을 지운다(`_place_value`).

    상권순위도 따로 읽는다. **플레이스 칸에 얹어 고르면 안 된다** —
    사용법이 `플레이스 직접 긁기` 를 꺼 두라고 권하므로(기본값도 꺼짐)
    상권순위만 든 스냅샷이 정상 경로인데, 그 스냅샷은 플레이스 세 칸이
    전부 `None` 이라 `_has_place_value` 로는 한 번도 안 뽑혔다. 넣은
    값이 제안서에 아예 안 갔다.
    """
    snap = _snapshot_with(client, _has_place_value)
    revenue = _snapshot_with(client, _has_revenue_value).get("예상매출") or {}
    return {
        # 이 시각은 플레이스 칸을 마지막으로 읽은 때다. 세 칸을 칸별로
        # 고르므로 그중 어떤 값은 더 앞선 판독에서 올 수 있다. 종이에는
        # 안 나간다 — 장마다 찍는 날짜는 `_search` 의 기준일이다.
        "수집시각": snap.get("수집시각"),
        "방문자리뷰": _place_value(client, "방문자리뷰"),
        "블로그리뷰": _place_value(client, "블로그리뷰"),
        # 여기 순위만 옛 규칙(`_latest_snapshot`)에 남아 있다. 이 칸은
        # 서식도 서버도 안 읽는다 — 살려 쓰려면
        # `_snapshot_with(client, _has_rank_value)` 로 바꿔야
        # `_search`·`_diagnosis` 와 같은 스냅샷을 본다. 조건 함수까지
        # 같이 바꿔야 한다. `_snapshot_with` 만 쓰고 조건을
        # `s.get("순위")` 로 두면 두 칸짜리 손입력 줄이 다시 이긴다.
        "순위": _latest_snapshot(client).get("순위") or [],
        # 오픈업 추정 매출의 절대금액은 싣지 않는다. 상대 표현만 쓴다.
        "상권순위": revenue.get("상권순위"),
    }


# 제안서로 나가는 오픈업 필드. 화이트리스트다 — 여기 없는 건 안 나간다.
# `판독시각` 은 내부 기록이고, 손입력 월매출은 기준월도 출처도 없어
# 고객에게 보일 근거가 못 된다.
_OPENUB_KEYS = ("기준월", "매출", "성별최다", "연령최다", "요일최다",
                "평일비율", "시간대최다")


def _openub(client: dict) -> dict | None:
    """가장 늦은 기준월 한 건만 낸다. 없으면 None 이다.

    여러 달이 쌓여 있어도 제안서에는 최신 달만 나간다. 자료가 아예
    없으면 카드 세 장과 각주가 통째로 빠진다 — 빈 카드를 만들지 않는다.
    """
    목록 = [e for e in (client.get("오픈업") or []) if e.get("기준월")]
    if not 목록:
        return None
    최신 = max(목록, key=lambda e: e["기준월"])
    return {k: 최신.get(k) for k in _OPENUB_KEYS}


# 상권 이름을 붙이는 문턱. 애매한 구간에 억지로 이름을 붙이지 않는다 —
# 55%를 「평일 상권」이라 부르면 그 뒤 문장이 전부 틀어진다.
#
# **60 을 올리자는 제안이 한 번 올라왔고 상무님이 그대로 가기로 했다
# (2026-08-15).** 산수만 보면 평일은 7일 중 5일이라 손님이 완전히 고르게
# 와도 71%가 나오고, 그 기준이면 60%는 오히려 주말 쪽이다. 실제 상권을
# 보는 감각이 산수보다 앞선다는 판단이다. 다시 올리자는 얘기가 나오면
# 이 결정부터 확인할 것.
WEEKDAY_FLOOR = 60
WEEKEND_CEILING = 40


def _trade_area(평일비율) -> str | None:
    """평일비율에서 상권 한 줄. 애매하면 아무 말도 하지 않는다."""
    if 평일비율 is None:
        return None
    if 평일비율 >= WEEKDAY_FLOOR:
        return "평일 상권입니다"
    if 평일비율 <= WEEKEND_CEILING:
        return "주말 상권입니다"
    return None


# 순위 줄이 없는 키워드 표기.
#
# **「30위 밖」이 아니다.** 애드로그는 30 에서 자르지 않는다 — 234 위도
# 234 로 값이 온다(실측 234·229·194·193). 그러니 이 라벨이 서는 자리는
# 「30 위보다 뒤」가 아니라 **애드로그가 이 키워드에서 우리 매장을 못
# 찾았다**는 뜻이다. 잡힌 날은 값이 오고, 안 잡힌 날은 그 날짜 줄이
# 아예 없다(`rank_num: null` 이 아니다).
#
# 몇 위인지 모르는 자리에 숫자를 지어내면 사장님이 읽는 종이가 거짓말을
# 한다. 「미노출」은 숫자를 말하지 않는다.
OUTSIDE_LABEL = "미노출"
TOP_KEYWORDS = 8
TOP_MOVES = 5
TOP_REVIEWS = 3


def _josa(word: str, 받침있을때: str, 받침없을때: str) -> str:
    """받침에 따라 조사를 고른다 — 「식당은」과 「가원는」을 가른다.

    고객이 받는 글이라 조사가 틀리면 눈에 띈다. 한글이 아닌 글자로
    끝나면(영문 상품명 등) 받침 없는 쪽을 쓴다 — 「SA는」이 자연스럽다.
    """
    if not word:
        return 받침없을때
    last = word[-1]
    if not ("가" <= last <= "힣"):
        return 받침없을때
    return 받침있을때 if (ord(last) - 0xAC00) % 28 else 받침없을때


def _rank_label(row: dict) -> str:
    if row.get("순위권밖"):
        return OUTSIDE_LABEL
    return f"{row['순위']}위" if row.get("순위") is not None else "—"


def _opportunity(ranks: list[dict]) -> list[dict] | None:
    """조회수 있는 줄만, 큰 순서로.

    조회수가 하나도 없으면 장이 통째로 빠진다 — 빈 표를 만들면
    「자료를 못 구했다」가 「그런 게 없다」로 읽힌다.

    **키워드가 종이에 닿는 문은 둘뿐이다.** 이 함수(조회수가 필요)와
    처방(비교순위가 필요). 둘 다 애드로그 판독에서 온다. 플레이스
    수집기만 돌린 매장은 순위를 갖고 있어도 한 줄도 안 찍힌다.
    **상무님이 애드로그를 항상 넣기로 했다 (2026-08-15)** — 수집기만
    돌린 매장을 위해 따로 길을 내지 않는다.
    """
    있는것 = [r for r in ranks if r.get("조회수") is not None]
    if not 있는것:
        return None
    있는것 = sorted(있는것, key=lambda r: r["조회수"], reverse=True)
    return [{"키워드": r["키워드"], "조회수": r["조회수"],
             "순위표시": _rank_label(r)} for r in 있는것[:TOP_KEYWORDS]]


def _headline(ranks: list[dict]) -> str | None:
    """조회수가 가장 큰데 안 잡힌 키워드와, 1위인데 조회수가 작은 키워드를 짝짓는다.

    **문장 틀을 코드에 고정한다.** 모델에게 문장을 짓게 하지 않는다 —
    사장님 앞에 나가는 글이고, 판독이 흔들리는 날 문장까지 흔들리면
    손쓸 수가 없다.
    """
    있는것 = [r for r in ranks if r.get("조회수") is not None]
    놓친것 = [r for r in 있는것
              if r.get("순위권밖") or (r.get("순위") or 0) > 10]
    잡은것 = [r for r in 있는것
              if not r.get("순위권밖") and (r.get("순위") or 99) <= 3]
    if not 놓친것 or not 잡은것:
        return None
    큰것 = max(놓친것, key=lambda r: r["조회수"])
    작은것 = min(잡은것, key=lambda r: r["조회수"])
    조사 = _josa(작은것["키워드"], "은", "는")
    return (f"월 {큰것['조회수']:,}번 검색되는 「{큰것['키워드']}」에서 "
            f"아직 안 보입니다. 지금 {_rank_label(작은것)}인 "
            f"「{작은것['키워드']}」{조사} 월 {작은것['조회수']:,}건짜리입니다.")


def _moves(ranks: list[dict], 진단: dict) -> dict | None:
    """비교순위가 있는 줄만. 오른 것과 내린 것을 가른다.

    **순위 없는 줄을 숫자로 치면 안 된다.** 한동안 999 위로 쳐서 낙폭을
    쟀다. 애드로그가 30 에서 자른다고 믿었을 때는 999 가 실제 순위와 안
    겹쳤지만, 실제로는 234 위도 값으로 오고 위쪽 끝이 없다. 999 위였다가
    안 잡힌 줄은 낙폭이 0 이라 어느 쪽에도 안 들어 종이에서 통째로
    사라졌고, 그보다 뒤였던 줄은 낙폭이 음수라 ▲ 오름으로 찍혔다.
    순위를 잃은 줄이 오를 수는 없다.

    그래서 두 무리로 갈라 따로 정렬한다. 순위가 있는 줄은 낙폭 크기로,
    미노출로 빠진 줄은 **비교순위가 좋았던 것부터** — 「3위였는데 이제
    안 보입니다」가 「234위였는데 안 보입니다」보다 센 말이다. ▼ 목록은
    미노출 무리를 앞에 세운다. 순위를 잃은 게 순위가 내려간 것보다
    무겁다.

    가르는 조건은 `_rank_label` 과 같은 것이어야 한다 — 종이에 「미노출」로
    찍히는 줄이 미노출 무리에 들어야 정렬 기준과 찍히는 말이 안 어긋난다.
    """
    쓸것 = [r for r in ranks
            if r.get("비교순위") is not None
            and (r.get("순위") is not None or r.get("순위권밖"))]
    if not 쓸것:
        return None

    # 위 걸러내기 덕에 `순위있음` 쪽은 `순위` 가 반드시 숫자다. 미노출
    # 쪽은 `순위` 를 숫자로 읽지 않는다 — 읽을 숫자가 애초에 없다.
    미노출 = [r for r in 쓸것 if r.get("순위권밖")]
    순위있음 = [r for r in 쓸것 if not r.get("순위권밖")]

    오름 = sorted((r for r in 순위있음 if r["순위"] < r["비교순위"]),
                  key=lambda r: r["비교순위"] - r["순위"], reverse=True)
    떨어짐 = sorted((r for r in 순위있음 if r["순위"] > r["비교순위"]),
                    key=lambda r: r["순위"] - r["비교순위"], reverse=True)
    내림 = sorted(미노출, key=lambda r: r["비교순위"]) + 떨어짐
    if not 오름 and not 내림:
        return None

    def 줄(r):
        return {"키워드": r["키워드"], "전": f"{r['비교순위']}위",
                "후": _rank_label(r)}

    return {"기준일": 진단.get("기준일"), "비교일": 진단.get("비교일"),
            "오름": [줄(r) for r in 오름[:TOP_MOVES]],
            "내림": [줄(r) for r in 내림[:TOP_MOVES]]}


def _hidden(진단: dict) -> dict | None:
    목록 = 진단.get("히든키워드") or []
    return {"개수": len(목록), "목록": 목록} if 목록 else None


def _reviews(진단: dict, metrics: dict) -> dict | None:
    """리뷰 제목만 싣는다.

    실명여부·톰바설치는 우리 내부 사정이고 작성자 아이디는 개인정보다.
    화이트리스트로 걸러 낸다 — 판독은 해 두되 여기서 안 내보낸다.
    """
    방문 = (진단.get("리뷰") or {}).get("방문자") or []
    많이 = sorted((r for r in 방문 if r.get("조회수") is not None),
                  key=lambda r: r["조회수"], reverse=True)[:TOP_REVIEWS]
    if metrics.get("방문자리뷰") is None and not 많이:
        return None
    return {
        "방문자수": metrics.get("방문자리뷰"),
        "블로그수": metrics.get("블로그리뷰"),
        "많이읽힌": [{"제목": r["제목"], "조회수": r["조회수"],
                      "작성일": r.get("작성일", "")} for r in 많이],
    }


def _customer(client: dict) -> dict | None:
    """1장 — 이 가게에 오는 손님. 오픈업이 없으면 장이 통째로 사라진다."""
    U = _openub(client)
    if not U:
        return None
    return {**U, "상권": _trade_area(U.get("평일비율"))}


def _search(client: dict, metrics: dict) -> dict:
    """2장 — 검색에서의 자리.

    `총키워드`·`TOP3`·`TOP10`·`저장수` 는 판독기가 읽어 놓고 제안서로
    한 번도 안 나가던 값이다. 여기서 쓴다.

    요약 셋은 `순위요약` 에서 읽는다. `진단` 이 아니다 — 판독기가
    쓰는 자리가 `순위요약` 이고, 한동안 여기서 `진단` 을 읽어 값이
    통째로 안 건너갔다. 읽는 자리와 쓰는 자리는 한 이름이어야 한다.

    순위·저장수는 그 값을 가진 마지막 스냅샷에서, 히든키워드는 히든키워드를
    가진 마지막 스냅샷에서 따로 읽는다 — 애드로그에는 히든키워드가 없어서,
    마지막 한 건만 보면 캡처가 넣어 둔 것이 가려진다.

    `기준일` 과 `순위요약` 은 **순위를 준 스냅샷에서** 읽는다. 다른
    스냅샷의 날짜를 끌어다 찍으면 묵은 순위가 오늘 잰 것으로 읽히고,
    요약을 따로 고르면 「총 키워드 48개」라고 적힌 카드 밑에 기회표가
    두어 줄인 종이가 나간다 — 카드와 표가 서로 다른 시점을 말한다.
    종이에 찍히는 날짜는 기준일 하나뿐이라, 카드만 남의 날에서 오면
    그 날짜를 달고 나간다.
    """
    순위스냅 = _snapshot_with(client, _has_rank_value)
    ranks = 순위스냅.get("순위") or []
    시점 = 순위스냅.get("진단") or {}
    # 순위를 준 스냅샷이 아예 없을 때만 요약을 가진 스냅샷에서 읽는다.
    # 그때는 기회표도 헤드라인도 기준일도 안 서서 카드가 어긋날 상대가
    # 없다. 거기까지 지우면 판독기가 읽어 둔 값을 그냥 버리는 것이다.
    요약 = (순위스냅.get("순위요약") if 순위스냅
            else _snapshot_with(client, _has_summary_value).get("순위요약")) or {}
    히든스냅 = _snapshot_with(client, lambda s: (s.get("진단") or {}).get("히든키워드"))

    수치 = []
    for 이름, 값 in (("추적 키워드", 요약.get("총키워드")),
                     ("TOP 3", 요약.get("TOP3")),
                     ("TOP 10", 요약.get("TOP10")),
                     ("방문자 리뷰", metrics.get("방문자리뷰")),
                     ("저장수", _place_value(client, "저장수"))):
        if 값 is not None:
            수치.append({"이름": 이름, "값": f"{int(값):,}개"
                         if 이름 != "방문자 리뷰" else f"{int(값):,}건"})

    return {
        "헤드라인": _headline(ranks),
        "수치": 수치,
        "기회표": _opportunity(ranks),
        "히든키워드": _hidden(히든스냅.get("진단") or {}),
        # 측정일이 갈린 날은 범위로 보여 준다 — 상무님이 「일부는 3 주
        # 전 것」임을 알고 말할 수 있다. 처방 장은 `비교일 → 기준일` 이라
        # 범위를 쓰면 말이 안 되므로 거기는 날짜 하나를 그대로 쓴다.
        "기준일": 시점.get("기준일범위") or 시점.get("기준일"),
    }


def _diagnosis(client: dict, metrics: dict, lines: list[dict]) -> dict:
    """진단 세 장. 값이 없는 장은 None 이고 서식이 통째로 감춘다.

    처방은 순위를 준 스냅샷의 진단(기준일·비교일)을 쓴다 — 히든키워드를
    준 캡처 스냅샷의 기준일을 쓰면 날짜가 어긋난다. 리뷰는 리뷰를 가진
    마지막 스냅샷에서 따로 읽는다(애드로그에는 리뷰 목록이 없다).
    """
    순위스냅 = _snapshot_with(client, _has_rank_value)
    ranks = 순위스냅.get("순위") or []
    시점 = 순위스냅.get("진단") or {}
    리뷰스냅 = _snapshot_with(client, _has_review_value)
    return {
        "손님": _customer(client),
        "검색": _search(client, metrics),
        "처방": prescribe(_moves(ranks, 시점), lines),
        "리뷰": _reviews(리뷰스냅.get("진단") or {}, metrics),
    }


# 빠진 진단 장 경고.
#
# 자료가 없으면 장이 사라지는 것은 **맞는 동작이다** — 빈 표를 만들면
# 「자료를 못 구했다」가 「그런 게 없다」로 읽힌다. 사고는 장이 빠지는 게
# 아니라 **빠진 줄 모르고 나가는 것**이다. 실제로 방이점 제안서가 진단
# 세 장 없이 4장짜리로 조용히 나갔고, 뽑은 사람은 그걸 사장님께 보내기
# 직전에야 알았다.
#
# ┌─ 여기는 `templates/proposal.html` 의 거울이다 ────────────────────┐
# │ 아래 세 조건은 서식이 그 장의 제목을 띄우는 `보임(...)` 세 줄과   │
# │ 글자 그대로 같은 뜻이어야 한다. 두 벌이라 언젠가 어긋나는데,      │
# │ 어긋나면 서 있는 장을 빠졌다 하거나(경고가 거짓말) 빠진 장을      │
# │ 조용히 넘긴다(경고가 무의미).                                     │
# │                                                                   │
# │   MISSING_CUSTOMER ↔ 보임("s-customer", Boolean(U))               │
# │   MISSING_SEARCH   ↔ 보임("s-search", ...)                        │
# │   MISSING_MOVES    ↔ `d-moves-title` 이 「순위 변동과 이번 달     │
# │                       처방」으로 찍히는 조건, 곧 `Boolean(R)`     │
# │                                                                   │
# │ 처방만 장 전체(`s-prescription`)가 아니라 제목 줄에 걸린다. 그    │
# │ 장은 처방과 리뷰 현황 두 덩이를 담는데, 처방이 빠져도 리뷰가 장을 │
# │ 세워 놓아서 예전에는 처방만 조용히 사라졌다. 리뷰를 같이 감추면   │
# │ 값이 있는 것을 숨기게 되므로, 서식은 남은 덩이의 이름(「리뷰      │
# │ 현황」)을 제목으로 올린다.                                        │
# │ 서식의 노출 조건을 고치면 여기도 같이 고칠 것.                    │
# │ `test_pdf.py` 가 실제로 PDF 를 찍어서 둘을 대조한다.              │
# └───────────────────────────────────────────────────────────────────┘
MISSING_CUSTOMER = ("「이 가게에 오는 손님」장이 빠집니다 — "
                    "오픈업 캡처를 판독해 넣으십시오.")
MISSING_SEARCH = ("「검색에서의 자리」장이 빠집니다 — "
                  "애드로그 캡처를 판독해 넣으십시오.")
MISSING_MOVES = ("「순위 변동과 이번 달 처방」장이 빠집니다 — "
                 "애드로그 판독에 비교순위가 있어야 합니다.")


def missing_pages(payload: dict) -> list[str]:
    """제안서에서 빠진 진단 장을 사람 말로 낸다. payload 는 읽기만 한다.

    막지 않는다. 진단 없이 나가야 하는 달도 있고, 자료가 늦는 매장도
    있다. 판단은 상무님이 하고 이 함수는 사실만 알린다.
    """
    D = payload.get("진단자료") or {}
    S = D.get("검색") or {}

    빠짐 = []
    if not D.get("손님"):
        빠짐.append(MISSING_CUSTOMER)
    if not (S.get("헤드라인") or S.get("수치") or S.get("기회표")
            or S.get("히든키워드")):
        빠짐.append(MISSING_SEARCH)
    if not D.get("처방"):
        빠짐.append(MISSING_MOVES)
    return 빠짐


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

# 상품 고지사항을 제안서에 싣던 자리가 여기 있었다. 고지사항 장을 통째로
# 빼면서 같이 지웠다 — 싣는 곳이 없는데 거르는 기계만 남으면, 나중에 이 줄을
# 보는 사람이 「고객이 고지를 받는구나」로 읽는다.
#
# 지운 것: `NOTICE_INTERNAL_WORDS`·`NOTICE_SEP`·`_client_facing_notice()`.
# 막고 있던 것은 "상위대행사에 마크업 필수" 가 제안서에 찍히는 일이었다
# (네이버 SA·DA, 구글 SA·DA, 유튜브 구글애즈 다섯 상품이 이 문구를 단다).
# **다시 고지를 어딘가 실으려면 이 필터부터 되살려야 한다.** 카탈로그
# 고지사항 원문에는 외주처 이름과 마크업 얘기가 그대로 들어 있다.
#
# 대가성 고지 한 줄은 견적서로 갔다 — `quote.py` 의 `AD_NOTICE`. 그쪽은
# 카탈로그 원문을 **읽기만 하고 찍지 않아서** 필터가 필요 없다.


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
    lines = []
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
            "상품id": product["id"],
            "매체": product["매체"],
            "상품명": product["상품명"],
            "수량표시": _quantity_label(product, item),
            "정가": amount["정가"],
        })
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
        "오픈업": _openub(client),
        "진단자료": _diagnosis(client, _metrics(client), lines),
        "구성": lines,
        "정가합": 정가합,
        "계약가": 계약가,
        "혜택배율문구": 문구,
        "일정": _client_facing_schedule(weekly_plan(products, plan["항목"])),
        "차별점": DIFFERENTIATORS,
    }
