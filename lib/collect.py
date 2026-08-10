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

┌─ 애드로그 엔드포인트·필드명은 아직 추정값이다 ────────────────────────┐
│ ADLOG_ENDPOINT 와 응답 필드(`rank`·`score`·`date`)는 확인되지 않았다.  │
│ **실제 API 문서로 교정하기 전까지 순위는 수동 입력으로 쓴다.**         │
│ 추정 필드 위에 정교한 파싱을 쌓지 않는다 — 없으면 None 으로 둔다.      │
│ 확인은 `-m network` 테스트 하나로만 한다.                              │
└────────────────────────────────────────────────────────────────────────┘

스냅샷에 들어가는 값은 그대로 클라이언트 JSON 이 되고 제안서까지 흘러간다.
그래서 예외 원문을 스냅샷에 넣지 않는다. 짧은 사람 말로 바꾸고 원문은
stderr 로만 보낸다.
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

VISITOR_RE = re.compile(r"방문자\s*리뷰\s*([\d,]+)")
BLOG_RE = re.compile(r"블로그\s*리뷰\s*([\d,]+)")
SAVE_RE = re.compile(r"저장\s*([\d,]+)")

# 추정값 — 위 상자 참고. 반드시 https 여야 한다. Authorization 헤더에 키를
# 평문으로 싣기 때문에 http 로 나가면 중간에서 키가 그대로 읽힌다.
ADLOG_ENDPOINT = "https://adlog.ai.kr/api/place/rank"

# 키는 환경변수에서만 읽는다. 파일에 적지 않는다.
ADLOG_KEY_ENV = "ADLOG_API_KEY"

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


def api_key_from_env() -> str | None:
    """애드로그 키를 환경변수에서 읽는다. 없으면 None 을 돌려주고 알린다.

    키가 없다고 수집 전체가 멈추면 안 된다 — 플레이스·매출은 그대로 모으고
    순위만 건너뛴다.
    """
    import os

    key = (os.environ.get(ADLOG_KEY_ENV) or "").strip()
    if not key:
        print(f"{ADLOG_KEY_ENV} 환경변수가 없습니다. 순위 조회는 건너뜁니다"
              " (나머지 수집은 계속합니다).", file=sys.stderr)
        return None
    return key


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


def fetch_ranks(api_key: str, place_id: str, keywords: list[str]) -> list[dict]:
    """애드로그 공식 API 로 키워드별 순위를 읽는다.

    순위·지수는 10일 전 기준이다. 실시간처럼 쓰면 안 된다.
    응답 필드명은 추정값이라 없으면 None 이다(모듈 상단 상자 참고).

    키워드 하나가 실패해도 나머지는 계속 본다 — 열 개 중 하나 때문에
    아홉 개를 못 보면 그날 미팅 자료가 통째로 빈다.
    """
    require_https(ADLOG_ENDPOINT)

    out = []
    for kw in keywords:
        req = urllib.request.Request(
            f"{ADLOG_ENDPOINT}?place_id={urllib.parse.quote(str(place_id))}"
            f"&keyword={urllib.parse.quote(kw)}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                data = json.loads(res.read().decode("utf-8"))
            out.append({"키워드": kw, "순위": data.get("rank"),
                        "지수": data.get("score"), "기준일": data.get("date")})
        except Exception as exc:  # 실패해도 나머지 키워드는 계속 본다
            print(f"[애드로그] {kw!r} 조회 실패: {exc!r}", file=sys.stderr)
            out.append({"키워드": kw, "순위": None, "지수": None,
                        "오류": short_error(exc)})
    return out


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
