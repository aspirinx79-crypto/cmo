"""외부 지표 수집 — 플레이스(자동) · 애드로그(API) · 오픈업(수동).

세 원칙:
  1. 수집은 미팅 전 사무실에서 한다. 현장에서 누르면 로딩 때문에 멈춰 선다.
  2. 실패해도 막히지 않는다. 전부 수동 입력으로 대체 가능해야 한다.
  3. 수집 시각을 함께 저장한다. 스냅샷이 쌓이면 그게 성과의 증거가 된다.

오픈업은 자동 수집하지 않는다. 조회 횟수 제한이 있고
화면 수집은 이용약관과 부딪힌다. 상무님이 조회한 값을 받는다.

한 번에 한 건씩만 부른다. 여기에 고객사 목록을 도는 반복문을 넣지 마라 —
상대 서버 입장에서 그건 수집이 아니라 공격이고, 계정이 막히면 도구가 아니라
거래가 끊긴다.

애드로그 순위는 `adlog.py` 가 API 로 받는다. 원장 병합과 스냅샷 파생만
여기서 한다 — 고객사 모양을 아는 건 이 모듈이다.

스냅샷에 들어가는 값은 그대로 클라이언트 JSON 이 되고 제안서까지 흘러간다.
그래서 예외 원문을 스냅샷에 넣지 않는다. 짧은 사람 말로 바꾸고 원문은
stderr 로만 보낸다.
"""
import json
import re
import urllib.error
from datetime import datetime

VISITOR_RE = re.compile(r"방문자\s*리뷰\s*([\d,]+)")
BLOG_RE = re.compile(r"블로그\s*리뷰\s*([\d,]+)")
SAVE_RE = re.compile(r"저장\s*([\d,]+)")

FETCH_FAILED = "조회 실패"
BAD_FORMAT = "응답 형식 오류"
AUTH_FAILED = "인증 실패"


def _num(match) -> int | None:
    return int(match.group(1).replace(",", "")) if match else None


def parse_place_counts(text: str) -> dict:
    """플레이스 화면 텍스트에서 숫자 셋을 뽑는다.

    반환은 `{"방문자리뷰": int|None, "블로그리뷰": int|None, "저장수": int|None}`.
    저장수까지 세 키다 — `make_snapshot()` 이 저장수를 스냅샷에 싣는다.
    못 찾은 항목은 None 이고, 그건 수동으로 넣으면 된다.
    """
    t = text or ""
    return {
        "방문자리뷰": _num(VISITOR_RE.search(t)),
        "블로그리뷰": _num(BLOG_RE.search(t)),
        "저장수": _num(SAVE_RE.search(t)),
    }


def fetch_place(url: str, timeout_ms: int = 15000) -> dict:
    """네이버 플레이스에서 공개 정보를 읽는다. 1건씩만 부른다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            name = (page.title() or "").split(":")[0].strip()
            counts = parse_place_counts(page.inner_text("body"))
        finally:
            browser.close()

    return {"매장명": name, "플레이스URL": url, **counts}


def require_https(endpoint: str) -> None:
    """평문 http 로는 요청을 만들지도 않는다.

    Bearer 키를 헤더에 싣기 때문에 http 는 곧 키 유출이다. 실패는 닫히는
    쪽으로 — 네트워크를 타기 전에 ValueError 로 끊는다.

    read_doc.py 도 이 규칙을 그대로 쓴다. 같은 함수를 두 벌 두지 않으려고 공개 이름으로 둔다.
    """
    if not (endpoint or "").lower().startswith("https://"):
        raise ValueError(
            f"애드로그 주소는 https 여야 합니다(현재: {endpoint!r}). "
            "평문 http 로는 API 키를 보내지 않습니다."
        )


def short_error(exc: Exception) -> str:
    """예외를 짧은 사람 말로 바꾼다.

    예외 원문에는 URL·응답 본문·매장 정보가 섞여 들어온다. 그게 스냅샷에
    저장되면 그대로 클라이언트 JSON 이 된다. 원문은 stderr 로만 남긴다.

    read_doc.py 도 이 규칙을 그대로 쓴다. 같은 함수를 두 벌 두지 않으려고 공개 이름으로 둔다.
    """
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
        return AUTH_FAILED
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
        return BAD_FORMAT
    return FETCH_FAILED


def make_snapshot(place: dict, ranks: list[dict], revenue: dict | None) -> dict:
    return {
        "수집시각": datetime.now().isoformat(timespec="seconds"),
        "플레이스": {k: place.get(k) for k in ("방문자리뷰", "블로그리뷰", "저장수")},
        "순위": ranks or [],
        "예상매출": revenue,
    }


def append_snapshot(client: dict, snapshot: dict) -> dict:
    """스냅샷을 뒤에 붙인 사본을 돌려준다. 원본 dict 는 건드리지 않는다."""
    updated = dict(client)
    updated["스냅샷"] = [*(updated.get("스냅샷") or []), snapshot]
    return updated


def append_or_replace_snapshot(client: dict, snapshot: dict) -> dict:
    """오늘 날짜의 애드로그 스냅샷을 전부 걸러내고 새 것을 끝에 붙인다.

    같은 날 두 번 갱신하면 스냅샷이 늘어나던 자리다. **자리를 그대로
    바꿔 끼우면 안 된다** — 그 사이 캡처가 끼면(오전 애드로그 → 낮
    캡처 → 오후 갱신) 방금 받은 최신 순위가 캡처보다 앞자리로 밀려
    `paintLastSnapshot`·`_latest_snapshot` 이 옛 캡처를 최신으로 읽는다.
    걸러내고 끝에 붙이면 그럴 일이 없다. 캡처 스냅샷은 `출처` 가 없어
    그대로 남는다.
    """
    오늘 = snapshot["수집시각"][:10]
    남길것 = [s for s in (client.get("스냅샷") or [])
              if not (s.get("출처") == "애드로그"
                      and (s.get("수집시각") or "")[:10] == 오늘)]
    return {**client, "스냅샷": [*남길것, snapshot]}


def merge_ranks(ledger: dict, 플레이스ID: str, rows: list[dict]) -> dict:
    """새로 받은 순위를 원장에 얹은 사본을 돌려준다. 원본은 안 건드린다.

    날짜가 키라서 같은 날을 두 번 넣어도 한 벌이다. 이게 빈 스냅샷이
    쌓이던 자리를 막는다 — 예전에는 누를 때마다 껍데기가 한 건씩
    늘었고, 잠실점에만 그런 게 다섯 건이다.

    지난 날짜는 지우지 않는다. 그게 다음 달 재계약 자리에서 내놓을
    증거다.
    """
    out = {**ledger}
    out["플레이스ID"] = 플레이스ID
    out["갱신시각"] = datetime.now().isoformat(timespec="seconds")

    키워드 = {k: {**v} for k, v in (ledger.get("키워드") or {}).items()}
    for row in rows:
        이름 = row["키워드"]
        칸 = {**키워드.get(이름, {})}
        칸["api_no"] = row.get("api_no")
        # 2001(30위 밖)로 답한 날은 이 둘이 안 온다. None 으로 덮으면
        # 기회표에서 그 키워드가 빠진다 — 옛 값을 지킨다.
        if row.get("월검색수") is not None:
            칸["월검색수"] = row["월검색수"]
        if row.get("경쟁업체수") is not None:
            칸["경쟁업체수"] = row["경쟁업체수"]
        칸.setdefault("월검색수", None)
        칸.setdefault("경쟁업체수", None)
        칸["순위"] = {**(칸.get("순위") or {}), **(row.get("순위") or {})}
        키워드[이름] = 칸
    out["키워드"] = 키워드

    지표 = {**(ledger.get("매장지표") or {})}
    for row in rows:
        지표.update(row.get("매장지표") or {})
    out["매장지표"] = 지표

    return out


def _latest(by_date: dict):
    """날짜 키 중 가장 늦은 것의 값. 비었으면 None."""
    if not by_date:
        return None
    return by_date[max(by_date)]


COMPARE_DAYS = 30


def _comparison(순위: dict, 기준일: str) -> tuple:
    """기준일에서 30 일 전에 가장 가까운 날짜와 그 순위.

    API 가 석 달치를 준다. 처방 장은 비교순위가 있어야 서고, 없으면
    통째로 빠진다. 30 일을 쓰는 이유는 이 도구가 월 단위로 돌기
    때문이다 — 지난달 이맘때와 견준다.

    30 일 이전 자료가 없으면 지어내지 않는다. 둘 다 None 이다.
    """
    from datetime import date

    기준 = date.fromisoformat(기준일)
    이전 = [d for d in 순위
            if d < 기준일 and 순위[d] is not None
            and (기준 - date.fromisoformat(d)).days >= COMPARE_DAYS]
    if not 이전:
        return None, None
    고른날 = max(이전)
    return 고른날, 순위[고른날]


def snapshot_from_ranks(ledger: dict, 볼키워드: list[dict] | None = None) -> dict | None:
    """원장에서 스냅샷 한 건을 만든다. 값이 없으면 None 이다.

    제안서가 읽는 모양 그대로 만든다. 순위 줄의 다섯 칸과 `진단` 의
    기준일·비교일까지 채운다 — 처음에는 키워드·순위 둘만 실었는데,
    그러면 기회표(`_opportunity`)와 처방(`_moves`)이 통째로 빠진다.
    방이점 실데이터로 기회표 8 줄이 0 줄이 되는 걸 봤다.

    `볼키워드` 는 **이번에 답을 받은** 키워드다(`client.json` 의 애드로그
    키워드와 같은 모양 — `keyword`·`month_count`). 이걸 주면 그
    키워드만 보고, 30 위 밖이라 순위가 없는 키워드의 조회수를 여기서
    가져온다. 안 주면 원장의 키워드를 전부 본다(옛 동작).

    **「연결된 키워드 전부」를 주면 안 된다.** 아래에서 순위가 없는
    키워드에 `순위권밖` 을 세우는데, 애드로그는 진짜 30 위 밖도 응답
    없음(2001)으로 답해 원장에 기록을 안 남긴다. 그래서 원장만 봐서는
    「조회 실패」와 「30 위 밖」이 구분되지 않고, 못 물어본 키워드까지
    30 위 밖으로 찍힌다 — 사흘 전 2위였던 키워드를 두고 제안서가
    「아직 안 보입니다」라고 말한 자리다. 거르는 것은 부르는 쪽 몫이다.
    """
    from .adlog import as_int

    키워드 = ledger.get("키워드") or {}
    if 볼키워드:
        볼것 = [(kw["keyword"], 키워드.get(kw["keyword"], {}),
                 kw.get("month_count")) for kw in 볼키워드]
    else:
        볼것 = [(이름, 칸, None) for 이름, 칸 in 키워드.items()]

    순위, 기준일들, 비교일들 = [], [], []
    for 이름, 칸, 목록조회수 in 볼것:
        일자별 = 칸.get("순위") or {}
        # **순위가 `None` 인 날을 걸러내고 고르면 안 된다.** 걸러내면 오늘
        # 밀려난 키워드가 며칠 전 순위로 실린다 — 9/24 에 30위 밖으로
        # 떨어진 키워드가 9/24 자 종이에 「3위」로 찍히고 TOP 3 에도 센다.
        # `series()` 가 순위 `None` 인 날을 일부러 남겨 두는 이유가 이것이다.
        최신 = max(일자별) if 일자별 else None
        값 = 일자별[최신] if 최신 else None
        비교일, 비교순위 = _comparison(일자별, 최신) if 최신 else (None, None)
        조회수 = 칸.get("월검색수")
        if 조회수 is None:
            조회수 = 목록조회수
        순위.append({
            "키워드": 이름,
            "순위": 값,
            # 30 위 밖은 애드로그가 2001 로 답해 순위가 아예 안 온다.
            # **답을 받았는데** 값이 없으면 그건 밖에 있다는 뜻이다.
            # 못 물어본 키워드는 여기 오기 전에 걸러져 있어야 한다.
            "순위권밖": 값 is None,
            "조회수": 조회수,
            "비교순위": 비교순위,
        })
        if 최신:
            기준일들.append(최신)
        if 비교일:
            비교일들.append(비교일)

    지표 = _latest(ledger.get("매장지표") or {}) or {}
    place = {
        "방문자리뷰": 지표.get("방문자리뷰"),
        "블로그리뷰": 지표.get("블로그리뷰"),
        "저장수": as_int(지표.get("저장수")),
    }

    # 신규 매장은 키워드가 대부분 30위 밖이라 순위만 보면 안 쌓인다.
    # 조회수(월검색수)는 30위 밖이어도 이미 받아온 값이라, 그거라도
    # 있으면 쌓는다 — 신규 매장일수록 기능이 안 먹는 걸 막는다.
    잡힌것 = [r["순위"] for r in 순위 if r["순위"] is not None]
    조회수있음 = any(r["조회수"] is not None for r in 순위)
    플레이스있음 = any(v is not None for v in place.values())
    if not 잡힌것 and not 조회수있음 and not 플레이스있음:
        return None

    return {
        "수집시각": datetime.now().isoformat(timespec="seconds"),
        "출처": "애드로그",
        "플레이스": place,
        "순위": 순위,
        "순위요약": {"총키워드": len(순위),
                     "TOP3": sum(1 for v in 잡힌것 if v <= 3),
                     "TOP10": sum(1 for v in 잡힌것 if v <= 10)},
        "진단": {"기준일": max(기준일들) if 기준일들 else None,
                 "비교일": max(비교일들) if 비교일들 else None},
        "예상매출": None,
    }
