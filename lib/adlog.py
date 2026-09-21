"""애드로그 OpenAPI. HTTP 와 응답 모양만 안다.

고객사도 스냅샷도 모른다 — 그건 `collect.py` 몫이다. 이 경계를 지키는
이유는 애드로그가 바뀌는 날 고쳐야 할 파일이 하나이기 때문이다.

**실패가 HTTP 로 오지 않는다.** 애드로그는 200 을 주고 본문 `code` 에
적는다. `code != "0000"` 을 먼저 본다. 이걸 놓치면 실패한 응답을
성공으로 읽어 빈 원장을 덮어쓴다.

문서: https://www.adlog.kr/api/doc/
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from .collect import require_https

BASE = "https://api.adlog.kr/api"
LIST = f"{BASE}/getKeywordList.php"
DETAIL = f"{BASE}/getKeywordListDetail.php"

# 플레이스 순위 체크. 통합웹(1061)·가격비교(1067)·블로그(1040)는 안 쓴다.
PLACE_MENU = "1064"

KEY_ENV = "ADLOG_API_KEY"
USER_ENV = "ADLOG_USER_ID"

OK = "0000"
NO_DATA = "2001"      # 조회 조건에 맞는 데이터가 없다. 실패가 아니다.

# 사람이 읽고 다음에 뭘 할지 알 수 있는 말로 바꾼다. 코드 번호를 그대로
# 보여주면 "4004" 를 들고 아무것도 못 한다.
MESSAGES = {
    "4000": "애드로그 계정 정보를 확인하십시오.",
    "4001": "애드로그 계정 정보를 확인하십시오.",
    "4002": "애드로그 계정 정보를 확인하십시오.",
    "4003": "애드로그 메뉴 코드가 잘못됐습니다.",
    "4100": "애드로그 메뉴 코드가 잘못됐습니다.",
    "4004": "이 PC 의 IP 를 애드로그에 등록해야 합니다.",
    "4009": "애드로그 서비스 기간이 만료됐습니다.",
    "2000": "조회할 키워드 번호가 없습니다.",
}
FALLBACK = "애드로그 조회에 실패했습니다."

_DIGITS_RE = re.compile(r"[^\d]")


class AdlogError(Exception):
    """애드로그가 `code` 로 돌려준 실패. 메시지는 이미 사람 말이다."""


def as_int(value) -> int | None:
    """`"8,000+"` 같은 문자열에서 숫자만 뽑는다. 못 읽으면 None.

    저장수가 문자열로 온다. 원장에는 원문을 두고 스냅샷에만 이 값을
    싣는다 — `proposal._search()` 가 `int(값)` 으로 찍어서, 문자열이
    그대로 가면 제안서 생성이 통째로 터진다.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = _DIGITS_RE.sub("", str(value))
    return int(digits) if digits else None


def series(items: list[dict]) -> dict:
    """일자별 순위를 `{날짜: 순위}` 로 접는다.

    순위가 `None` 인 날도 남긴다. 날짜를 지우면 "그날 못 봤다"가
    "그날은 없었다"로 읽힌다.
    """
    out = {}
    for row in items or []:
        date = row.get("rank_date")
        if not date:
            continue
        out[date] = row.get("rank_num")
    return out


def metrics_by_date(items: list[dict]) -> dict:
    """날짜별 매장 지표를 낸다.

    리뷰수·저장수는 키워드가 아니라 매장의 값이라 키워드마다 같은 수가
    온다. 키워드 아래 두면 같은 값이 쉰 벌 복사된다.

    `저장수` 는 원문 그대로 둔다(`"8,000+"`). 숫자로 접는 건 스냅샷을
    만들 때 한 번만 한다.
    """
    out = {}
    for row in items or []:
        date = row.get("rank_date")
        if not date:
            continue
        out[date] = {
            "방문자리뷰": as_int(row.get("visit_review_count")),
            "블로그리뷰": as_int(row.get("blog_review_count")),
            "저장수": row.get("save_count"),
            "경쟁업체수": as_int(row.get("place_count")),
            "월검색수": as_int(row.get("total_month_count")),
        }
    return out


def credentials() -> tuple[str, str] | None:
    """키와 아이디를 환경변수에서 읽는다. 하나라도 없으면 None 이다.

    둘 다 있어야 부를 수 있다 — 애드로그는 `user_id` 를 본문에 요구한다.
    없다고 수집 전체가 멈추면 안 된다. 순위만 건너뛰고 나머지는 계속한다.
    """
    key = (os.environ.get(KEY_ENV) or "").strip()
    uid = (os.environ.get(USER_ENV) or "").strip()
    if not key or not uid:
        print(f"{KEY_ENV}/{USER_ENV} 가 없습니다. 애드로그 조회는 건너뜁니다"
              " (나머지 수집은 계속합니다).", file=sys.stderr)
        return None
    return key, uid


_RETRY_DELAYS = (1, 2)  # 재시도 사이 대기(초). 연달아 때리지 않는다.


def _is_timeout(exc: Exception) -> bool:
    """느려서 끊긴 것만 골라낸다. `urlopen` 은 타임아웃을 두 모양으로 낸다.

    응답을 기다리다 끊기면 `TimeoutError` 가 그대로 올라오고, 요청을
    보내다 끊기면 `URLError` 가 감싸서 올라온다(`reason` 이 그 안에 든다).
    """
    if isinstance(exc, TimeoutError):
        return True
    return isinstance(getattr(exc, "reason", None), TimeoutError)


def _call(url: str, key: str, uid: str, body: dict,
          timeout: int = 20, retries: int = 2) -> dict:
    """한 번 부르고 JSON 을 돌려준다. `code` 는 여기서 안 본다.

    느려서 끊긴 요청만 다시 부른다. 애드로그는 이따금 한 페이지를
    20 초 넘게 붙들고, 목록은 스무 번을 이어 부르므로 한 번만 걸려도
    전체가 무너진다 — 953 건짜리 계정에서 10 페이지가 20.02 초로
    끊기는 걸 세 번 재현했다.

    `AdlogError` 는 다시 부르지 않는다. 서버가 명확히 거절한 건 다시
    물어도 같은 답이 온다.
    """
    require_https(url)
    payload = {"user_id": uid, "api_menu": PLACE_MENU, **body}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"authorization": f"Bearer {key}",
                 "content-Type": "application/json"},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError) as exc:
            if not _is_timeout(exc) or attempt == retries:
                raise
            wait = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            print(f"애드로그 응답이 늦어 다시 부릅니다"
                  f"({attempt + 1}/{retries}, {wait}초 뒤): {url}",
                  file=sys.stderr)
            time.sleep(wait)


def _items(data: dict) -> list[dict]:
    """`code` 를 보고 items 를 꺼낸다. 실패면 사람 말로 멈춘다.

    `2001`(데이터 없음)은 실패가 아니다 — 아직 순위가 안 잡힌 키워드이고,
    이걸 예외로 만들면 새 키워드 하나 때문에 갱신 전체가 멈춘다.
    """
    code = str(data.get("code") or "")
    if code == NO_DATA:
        return []
    if code != OK:
        raise AdlogError(MESSAGES.get(code, FALLBACK))
    return data.get("items") or []


def keywords(key: str, uid: str, sleep: float = 0.3) -> list[dict]:
    """등록된 플레이스 키워드를 전부 읽는다. 한 페이지 50 건이다.

    `total_count` 를 채우면 멈춘다. 이 조건이 없으면 마지막 페이지를
    영원히 다시 부른다 — 하루 한도를 한 번에 태우는 길이다.
    """
    out: list[dict] = []
    page = 1
    while True:
        data = _call(LIST, key, uid, {"page": page})
        items = _items(data)
        out += items
        total = int(data.get("total_count") or 0)
        if not items or len(out) >= total:
            break
        page += 1
        if sleep:
            time.sleep(sleep)
    return out


def ranks(key: str, uid: str, api_no: int) -> list[dict]:
    """키워드 하나의 일자별 순위를 읽는다. 없으면 빈 목록이다."""
    return _items(_call(DETAIL, key, uid, {"api_no": api_no}))
