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
