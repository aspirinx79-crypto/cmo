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
        칸["월검색수"] = row.get("월검색수")
        칸["경쟁업체수"] = row.get("경쟁업체수")
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


def snapshot_from_ranks(ledger: dict) -> dict | None:
    """원장에서 스냅샷 한 건을 만든다. 값이 없으면 None 이다.

    제안서가 읽는 모양 그대로 만든다(`proposal._metrics`). 새 저장
    형식을 만들지 않는다 — `read_doc.snapshot_from()` 이 같은 이유로
    그렇게 돼 있다.

    순위는 **키워드마다 가장 늦은 체크일**을 쓴다. 키워드별로 마지막
    체크일이 달라서 한 날짜로 자르면 그날 안 돈 키워드가 통째로 빈다.

    저장수는 숫자로 접는다. 원장에는 `"8,000+"` 원문이 남아 있고,
    여기서 접는 이유는 `proposal._search()` 가 `int(값)` 으로 찍기
    때문이다 — 문자열이 그대로 가면 제안서 생성이 터진다.
    """
    from .adlog import as_int

    키워드 = ledger.get("키워드") or {}
    순위 = []
    for 이름, 칸 in 키워드.items():
        값 = _latest(칸.get("순위") or {})
        if 값 is not None:
            순위.append({"키워드": 이름, "순위": 값})

    지표 = _latest(ledger.get("매장지표") or {}) or {}
    place = {
        "방문자리뷰": 지표.get("방문자리뷰"),
        "블로그리뷰": 지표.get("블로그리뷰"),
        "저장수": as_int(지표.get("저장수")),
    }

    if not 순위 and not any(v is not None for v in place.values()):
        return None

    순위값 = [r["순위"] for r in 순위]
    return {
        "수집시각": datetime.now().isoformat(timespec="seconds"),
        "플레이스": place,
        "순위": 순위,
        "순위요약": {"총키워드": len(키워드),
                     "TOP3": sum(1 for v in 순위값 if v <= 3),
                     "TOP10": sum(1 for v in 순위값 if v <= 10)},
        "예상매출": None,
    }
