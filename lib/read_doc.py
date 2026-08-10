"""애드로그 종합분석 PDF 를 읽어 값으로 바꾼다.

애드로그 내보내기는 **텍스트가 0자인 이미지 PDF** 다. 파싱이 아니라
판독이라, 그림을 모델에 보내 읽힌다.

`collect.py` 의 원칙을 그대로 승계한다.
  1. 사무실에서 미리 한다. 미팅 중에 누르는 기능이 아니다.
  2. 실패해도 막히지 않는다. 전부 손입력으로 대체 가능하다.
  3. 판독은 화면을 채우기만 한다 — **저장은 사람이 누른다.**

판독이 1,082 를 108 로 읽는 날이 온다. 그게 조용히 제안서까지 가면 안 된다.
그래서 이 모듈은 아무것도 저장하지 않는다.
"""
import json
import re
from datetime import datetime

# 판독 결과에서 받아들이는 칸. 화이트리스트다 — 모델이 없는 칸을
# 지어내도 통과시키지 않는다.
READING_KEYS = ("플레이스ID", "플레이스명", "카테고리", "방문자리뷰",
                "블로그리뷰", "저장수", "총키워드", "TOP3", "TOP10", "순위")

_NUMBER_KEYS = ("방문자리뷰", "블로그리뷰", "저장수", "총키워드", "TOP3", "TOP10")

NOT_ADLOG = "애드로그 종합분석 파일이 아닌 것 같습니다"

PLACE_URL = "https://m.place.naver.com/restaurant/{}/home"

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _num(value) -> int | None:
    """못 읽은 값은 None 이다. 0 이 아니다.

    0 은 "리뷰가 없다" 는 사실이고 None 은 "모른다" 는 사실이다. 둘을
    섞으면 제안서에 "리뷰 0건" 이라고 찍힌다.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def parse_reading(text: str) -> dict:
    """모델 응답 글자에서 판독 dict 를 꺼낸다.

    모델이 ```json 울타리를 치거나 앞뒤에 말을 붙이는 날이 온다. 첫 `{`
    부터 마지막 `}` 까지만 본다.

    플레이스명도 방문자리뷰도 못 읽었으면 애드로그 파일이 아니다 —
    ValueError 로 끊는다. 빈 값으로 화면을 채우면 상무님이 "판독됐다" 로
    읽는다.
    """
    hit = _JSON_RE.search(text or "")
    if not hit:
        raise ValueError("판독 결과를 읽지 못했습니다")
    try:
        raw = json.loads(hit.group())
    except json.JSONDecodeError as exc:
        raise ValueError("판독 결과를 읽지 못했습니다") from exc
    if not isinstance(raw, dict):
        raise ValueError("판독 결과를 읽지 못했습니다")

    out = {
        "플레이스ID": _text(raw.get("플레이스ID")),
        "플레이스명": _text(raw.get("플레이스명")) or None,
        "카테고리": _text(raw.get("카테고리")),
        "순위": [
            {"키워드": _text(r.get("키워드")), "순위": _num(r.get("순위"))}
            for r in (raw.get("순위") or [])
            if isinstance(r, dict) and _text(r.get("키워드"))
            and _num(r.get("순위")) is not None
        ],
    }
    for key in _NUMBER_KEYS:
        out[key] = _num(raw.get(key))

    if not out["플레이스명"] and out["방문자리뷰"] is None:
        raise ValueError(NOT_ADLOG)
    return out


def store_mismatch(reading: dict, client: dict) -> str | None:
    """이 파일이 지금 고른 매장의 것인가. 아니면 사람 말로 이유를 낸다.

    글자 그대로 같은지만 본다. 비슷하면 통과시키지 않는다.

    애드로그에서 여러 매장을 연달아 내보내면 파일명이 전부
    `플레이스_종합분석_{날짜}_{시각}.pdf` 로 똑같다. 대조가 없으면 남의
    매장 리뷰수가 조용히 들어가고 그게 제안서 첫 장에 찍힌다.
    """
    찍힌이름 = (reading.get("플레이스명") or "").strip()
    고른이름 = (client.get("이름") or "").strip()
    if not 찍힌이름:
        return "파일에서 매장 이름을 읽지 못했습니다. 저장하지 않습니다."
    if 찍힌이름 != 고른이름:
        return (f"이 파일은 「{찍힌이름}」 자료입니다. "
                f"지금 고른 매장은 「{고른이름}」 입니다.")
    return None


def truncation_warning(reading: dict) -> str | None:
    """총키워드와 읽어낸 개수가 다르면 알린다.

    애드로그 화면에서 「전체 펼치기」를 안 누르고 내보내면 보이는 만큼만
    그림이 된다. 실물이 그랬다 — 총키워드 48 에 목록 17개. 경고가 없으면
    31개가 조용히 사라지고 다음 달에 "왜 17개죠" 가 된다.

    저장을 막지는 않는다. 17개라도 없는 것보다 낫고, 알고 저장하는 것과
    모르고 저장하는 것은 다르다.
    """
    총 = reading.get("총키워드")
    읽은 = len(reading.get("순위") or [])
    if 총 is None or 총 <= 읽은:
        return None
    return (f"키워드가 {총}개인데 {읽은}개만 읽혔습니다. "
            f"애드로그에서 「전체 펼치기」를 누르고 다시 내보내십시오.")


def snapshot_from(reading: dict) -> dict:
    """기존 스냅샷 모양 그대로 만든다.

    새 저장 형식을 만들지 않는다 — 제안서·화면이 손댈 것 없이 받는다.
    `예상매출` 은 오픈업 몫이라 여기서는 항상 None 이다.
    """
    return {
        "수집시각": datetime.now().isoformat(timespec="seconds"),
        "플레이스": {k: reading.get(k)
                     for k in ("방문자리뷰", "블로그리뷰", "저장수")},
        "순위": list(reading.get("순위") or []),
        "예상매출": None,
        "순위요약": {k: reading.get(k) for k in ("총키워드", "TOP3", "TOP10")},
    }


def merge_into_client(client: dict, reading: dict) -> dict:
    """빈 칸만 채운 사본을 돌려준다. 원본은 건드리지 않는다.

    이미 값이 있으면 덮지 않는다. 상무님이 손으로 고친 값을 판독이
    되돌리면, 고쳤다는 사실이 조용히 사라진다.
    """
    out = dict(client)
    place_id = reading.get("플레이스ID") or ""
    if place_id and not (out.get("플레이스URL") or "").strip():
        out["플레이스URL"] = PLACE_URL.format(place_id)
    category = reading.get("카테고리") or ""
    if category and not (out.get("업종") or "").strip():
        out["업종"] = category
    return out
