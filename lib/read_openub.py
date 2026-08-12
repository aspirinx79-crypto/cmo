"""오픈업 화면 캡처를 읽어 값으로 바꾼다.

`read_doc.py` 와 같은 원칙을 산다 — 사무실에서 미리 하고, 실패해도 막히지
않고, **저장은 사람이 누른다.** 이 모듈도 아무것도 저장하지 않는다.

오픈업은 차트마다 큰 제목 문장에 결론 숫자 하나를 박아 두고 막대에는
라벨이 없다. 그래서 읽는 것은 제목 문장뿐이다. 1년 매출 추이는 숫자
라벨이 아예 없어 범위 밖이다 — 막대 높이를 눈대중으로 숫자화하면 그게
제안서에 찍힌다.
"""
import json
import re
from datetime import date, datetime

from .read_doc import (MAX_BYTES, MODEL, TOO_BIG, _num, _text, ask_model,
                       render_pages)

MAX_CAPTURES = 6

NOT_OPENUB = "오픈업 캡처가 아닌 것 같습니다"
MIXED_MONTHS = ("캡처들의 기준월이 서로 다릅니다. "
                "같은 달 화면만 모아서 다시 넣으십시오.")
TOO_MANY = f"캡처는 {MAX_CAPTURES}장까지 넣을 수 있습니다."
NO_FILE = "캡처를 한 장 이상 넣으십시오."

_JSON_RE = re.compile(r"\{.*\}", re.S)

# 판독 결과에서 받아들이는 칸. 화이트리스트다.
_TEXT_KEYS = ("매장명", "성별최다", "연령최다", "요일최다", "시간대최다")
_NUMBER_KEYS = ("매출하한", "매출상한", "성별최다비율", "연령최다비율",
                "요일최다비율", "평일비율", "시간대최다비율")

OPENUB_PROMPT = """이 그림들은 오픈업(openub.com)의 상권 정보 화면이다.
여러 장이 순서대로 들어온다. 전부 같은 매장의 같은 달 화면이어야 한다.

아래 JSON 만 출력하라. 설명·인사·코드 울타리를 붙이지 마라.

{
  "매장명": "화면 상단 가운데의 매장 이름",
  "기준월들": [정수],
  "매출하한": 정수,
  "매출상한": 정수,
  "성별최다": "남성 또는 여성",
  "성별최다비율": 정수,
  "연령최다": "남성 20대 처럼 성별과 연령대를 붙인 말",
  "연령최다비율": 정수,
  "요일최다": "월~일 중 한 글자",
  "요일최다비율": 정수,
  "평일비율": 정수,
  "시간대최다": "아침·점심·저녁·밤 중 하나",
  "시간대최다비율": 정수
}

규칙:
- 읽을 수 없는 값은 null 로 둬라. 짐작해서 채우지 마라.
- **막대 색을 보지 마라.** 이 화면은 차트마다 색을 다르게 쓴다 — 어떤
  차트는 남성이 분홍이고 다른 차트는 남성이 파랑이다. 색으로 판단하면
  남녀가 뒤집힌다.
- **큰 제목 문장만 읽어라.** 「전체 결제 중 65%는 남성 고객이
  결제했어요!」 처럼 결론이 글자로 박혀 있다. 그 문장의 숫자와 말을
  그대로 가져와라.
- 막대 높이를 눈대중으로 숫자로 바꾸지 마라. 제목 문장에 없는 값은
  null 이다.
- "기준월들" 은 **장마다 하나씩, 넣은 순서대로** 담아라. 화면 오른쪽
  위에 「6월」 처럼 적혀 있다. 달 숫자만 넣어라. 연도는 화면에 없으니
  넣지 마라.
- 매출은 「4,600만 ~ 5,600만 원」 처럼 적혀 있다. 원 단위 정수로 바꿔라
  (4,600만 → 46000000).
- 「지난 1년 매장 추정 매출 추이」 막대에서는 아무 값도 읽지 마라.
  숫자 라벨이 없다."""


def parse_openub(text: str) -> dict:
    """모델 응답 글자에서 판독 dict 를 꺼낸다.

    매출도 성별도 요일도 못 읽었으면 오픈업 캡처가 아니다 — ValueError 로
    끊는다. 빈 값으로 화면을 채우면 「판독됐다」로 읽힌다.

    기준월이 장마다 다르면 여기서 끊는다. 섞인 채 저장하면 6월 매출에
    7월 고객 구성이 붙는다.
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

    out = {key: (_text(raw.get(key)) or None) for key in _TEXT_KEYS}
    for key in _NUMBER_KEYS:
        out[key] = _num(raw.get(key))

    if (out["매출하한"] is None and out["성별최다"] is None
            and out["요일최다"] is None):
        raise ValueError(NOT_OPENUB)

    months = [m for m in (_num(x) for x in (raw.get("기준월들") or []))
              if m is not None]
    if len(set(months)) > 1:
        raise ValueError(MIXED_MONTHS)
    # 판독 직후에는 `기준월들` 이 오고, 저장 단계에서 화면이 돌려보내는
    # 값에는 이미 하나로 접힌 `기준월` 이 온다. 서버가 저장 전에 같은
    # 파서로 모양을 다시 검사하려면 둘 다 받아야 한다.
    out["기준월"] = months[0] if months else _num(raw.get("기준월"))
    return out


def month_to_ym(month: int, today: date) -> str:
    """화면에 연도가 없다. 오늘 기준 가장 가까운 지난 그 달로 채운다.

    오늘이 2026-08 이면 「6월」은 2026-06 이고 「12월」은 2025-12 다.
    아직 오지 않은 달은 작년으로 본다 — 9월 자료를 8월에 받을 수는 없다.
    """
    year = today.year if month <= today.month else today.year - 1
    return f"{year:04d}-{month:02d}"


def _pair(value, ratio) -> dict | None:
    """값과 비율은 짝이다. 한쪽만 읽혔으면 못 읽은 것으로 본다."""
    if value is None or ratio is None:
        return None
    return {"값": value, "비율": ratio}


def openub_entry(reading: dict, today: date | None = None) -> dict:
    """저장 형태 한 건을 만든다.

    모델에게는 납작한 모양을 시키고(잘 읽힌다) 파일에서는 값과 비율을
    묶는다(짝이 붙어 있어야 읽기 쉽다). 그 사이를 여기서 옮긴다.
    """
    today = today or date.today()
    month = reading.get("기준월")
    저점, 고점 = reading.get("매출하한"), reading.get("매출상한")
    return {
        "기준월": month_to_ym(month, today) if month else None,
        "매출": ({"하한": 저점, "상한": 고점}
                 if 저점 is not None and 고점 is not None else None),
        "성별최다": _pair(reading.get("성별최다"), reading.get("성별최다비율")),
        "연령최다": _pair(reading.get("연령최다"), reading.get("연령최다비율")),
        "요일최다": _pair(reading.get("요일최다"), reading.get("요일최다비율")),
        "평일비율": reading.get("평일비율"),
        "시간대최다": _pair(reading.get("시간대최다"),
                            reading.get("시간대최다비율")),
        "판독시각": datetime.now().isoformat(timespec="seconds"),
    }


def merge_openub(client: dict, entry: dict) -> dict:
    """오픈업 목록에 한 건을 얹은 사본을 돌려준다. 원본은 건드리지 않는다.

    **스냅샷은 손대지 않는다.** 오픈업을 스냅샷으로 쌓으면 제안서가
    마지막 스냅샷 하나만 읽는 탓에 애드로그 리뷰수·순위가 통째로
    사라진다. 오픈업은 월 단위 확정 데이터라 성격도 다르다.

    같은 기준월은 덮어쓴다 — 6월 값은 하나뿐이어야 한다.
    """
    out = dict(client)
    kept = [e for e in (out.get("오픈업") or [])
            if e.get("기준월") != entry.get("기준월")]
    out["오픈업"] = sorted(kept + [entry], key=lambda e: e.get("기준월") or "")
    return out


def read_captures(files: list[tuple[bytes, str]], api_key: str,
                  model: str = MODEL) -> dict:
    """캡처 여러 장을 한 번의 호출로 판독한다. 아무것도 저장하지 않는다.

    **한 번의 호출로 보낸다.** 성별 비율과 연령대가 다른 장에 걸쳐 있어
    같이 봐야 앞뒤가 맞는다. 애드로그 PDF 2쪽도 이미 그렇게 처리한다.

    용량은 **합계로** 본다. 한 장씩은 작아도 여섯 장을 더하면 넘는다.
    """
    if not files:
        raise ValueError(NO_FILE)
    if len(files) > MAX_CAPTURES:
        raise ValueError(TOO_MANY)
    if sum(len(data) for data, _ in files) > MAX_BYTES:
        raise ValueError(TOO_BIG)

    images = []
    for data, filename in files:
        images.extend(render_pages(data, filename))

    return parse_openub(ask_model(images, OPENUB_PROMPT, api_key, model))
