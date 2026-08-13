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
import base64
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

from .collect import require_https, short_error

# 판독 결과에서 받아들이는 칸. 화이트리스트다 — 모델이 없는 칸을
# 지어내도 통과시키지 않는다.
READING_KEYS = ("플레이스ID", "플레이스명", "카테고리", "방문자리뷰",
                "블로그리뷰", "저장수", "총키워드", "TOP3", "TOP10", "순위",
                "기준일", "비교일", "대표키워드", "히든키워드", "리뷰")

_NUMBER_KEYS = ("방문자리뷰", "블로그리뷰", "저장수", "총키워드", "TOP3", "TOP10")

NOT_ADLOG = "애드로그 종합분석 파일이 아닌 것 같습니다"

PLACE_URL = "https://m.place.naver.com/restaurant/{}/home"

_JSON_RE = re.compile(r"\{.*\}", re.S)

# 평문 http 면 API 키가 헤더째 중간에서 읽힌다.
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-sonnet-5"
KEY_ENV = "ANTHROPIC_API_KEY"

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 8
RENDER_DPI = 140

TOO_BIG = "파일이 10MB 를 넘습니다."
BAD_FILE = "파일을 열지 못했습니다. 애드로그에서 다시 내보내 보십시오."

PROMPT = """이 그림은 애드로그(adlog)의 「플레이스 종합분석」 화면이다.
아래 JSON 만 출력하라. 설명·인사·코드 울타리를 붙이지 마라.

{
  "플레이스ID": "화면 상단 검색창과 PLACE 카드의 ID",
  "플레이스명": "기본정보의 플레이스명",
  "카테고리": "기본정보의 카테고리",
  "방문자리뷰": 정수,
  "블로그리뷰": 정수,
  "저장수": 정수,
  "총키워드": 정수,
  "TOP3": 정수,
  "TOP10": 정수,
  "순위": [{"키워드": "문자열", "순위": 정수, "순위권밖": true/false,
            "조회수": 정수, "비교순위": 정수}],
  "기준일": "순위 추이 표 첫(가장 왼쪽) 날짜 열의 날짜. 08-12 처럼",
  "비교일": "순위 추이 표 마지막(가장 오른쪽) 날짜 열의 날짜",
  "대표키워드": ["기본정보의 대표키워드"],
  "히든키워드": ["히든 키워드 영역에 나열된 말들"],
  "리뷰": {
    "방문자": [{"제목": "문자열", "조회수": 정수, "작성일": "2026-07-16",
                "작성자": "문자열"}],
    "블로그": [{"제목": "문자열", "작성일": "2026-05-26",
                "실명여부": "문자열"}]
  }
}

규칙:
- 읽을 수 없는 값은 null 로 둬라. 짐작해서 채우지 마라.
- **순위 칸이 "-" 면 순위권 밖이다.** "순위권밖": true 로 하고 "순위" 는
  null 로 둬라. 못 읽은 것과 다르다 — 이건 「그 키워드에서 안 보인다」는
  사실이다.
- "조회수" 는 키워드 옆에 「5,740건」처럼 적혀 있다. 숫자만 넣어라.
- "순위" 는 추이 표의 **가장 왼쪽 날짜 열**, "비교순위" 는 **가장 오른쪽
  날짜 열**이다. 가운데 열들은 읽지 마라.
- 리뷰는 화면에 보이는 줄만 담아라. 스크롤 밖은 지어내지 마라.
- 방문자리뷰·블로그리뷰·저장수는 「일자별 추이」의 **그래프에서 읽되,
  세로 축 눈금이 아니라 가장 오른쪽 마지막 점에 붙은 라벨**을 읽어라.
  축 눈금과 실제 값은 다르다.
- "순위" 는 「키워드 순위 목록」에 보이는 줄만 담아라. 보이지 않는 줄을
  지어내지 마라. 목록이 잘려 있으면 잘린 채로 두면 된다.
- 순위 숫자는 "6위" 처럼 적혀 있다. 숫자만 넣어라.
- 「급등/급락 키워드」 쪽의 삼각형 숫자는 순위가 아니라 변동폭이다.
  그건 넣지 마라."""


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


def _rank_row(raw_row: dict) -> dict | None:
    """순위 한 줄. `-` 는 순위권 밖이고 null 은 모르는 것이다.

    둘을 섞으면 「서초맛집 순위 없음」이 「조사 안 했음」으로 읽힌다.
    실물에서 월 5,740번 검색되는 키워드가 바로 그 `-` 였다.
    """
    keyword = _text(raw_row.get("키워드"))
    if not keyword:
        return None
    rank = _num(raw_row.get("순위"))
    outside = bool(raw_row.get("순위권밖"))
    volume = _num(raw_row.get("조회수"))
    if rank is None and not outside and volume is None:
        return None            # 아무것도 못 읽은 줄이다
    return {
        "키워드": keyword,
        "순위": rank,
        "순위권밖": outside,
        "조회수": volume,
        "비교순위": _num(raw_row.get("비교순위")),
    }


def _review_rows(raw, keys: tuple[str, ...]) -> list[dict]:
    """리뷰 목록 한 갈래. 제목이 없는 줄은 버린다."""
    out = []
    for r in (raw or []):
        if not isinstance(r, dict):
            continue
        title = _text(r.get("제목"))
        if not title:
            continue
        row = {"제목": title}
        for key in keys:
            row[key] = _num(r.get(key)) if key == "조회수" else _text(r.get(key))
        out.append(row)
    return out


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
        "기준일": _text(raw.get("기준일")) or None,
        "비교일": _text(raw.get("비교일")) or None,
        "대표키워드": [_text(x) for x in (raw.get("대표키워드") or []) if _text(x)],
        "히든키워드": [_text(x) for x in (raw.get("히든키워드") or []) if _text(x)],
        "순위": [row for row in
                 (_rank_row(r) for r in (raw.get("순위") or [])
                  if isinstance(r, dict))
                 if row],
    }
    리뷰 = raw.get("리뷰") or {}
    out["리뷰"] = {
        "방문자": _review_rows(리뷰.get("방문자"), ("조회수", "작성일")),
        "블로그": _review_rows(리뷰.get("블로그"), ("작성일", "실명여부")),
    }
    for key in _NUMBER_KEYS:
        out[key] = _num(raw.get(key))

    if not out["플레이스명"] and out["방문자리뷰"] is None:
        raise ValueError(NOT_ADLOG)
    return out


def name_mismatch(읽은이름: str | None, client: dict) -> str | None:
    """이 자료가 지금 고른 매장의 것인가. 아니면 사람 말로 이유를 낸다.

    글자 그대로 같은지만 본다. 비슷하면 통과시키지 않는다.

    애드로그에서 여러 매장을 연달아 내보내면 파일명이 전부
    `플레이스_종합분석_{날짜}_{시각}.pdf` 로 똑같다. 대조가 없으면 남의
    매장 리뷰수가 조용히 들어가고 그게 제안서 첫 장에 찍힌다. 오픈업
    캡처도 파일명이 캡처 시각뿐이라 사정이 같다.

    **규칙은 한 벌이다.** 애드로그와 오픈업이 같은 함수를 부른다 — 두
    벌이면 한쪽만 고치고 잊는 사고가 난다.
    """
    찍힌이름 = (읽은이름 or "").strip()
    고른이름 = (client.get("이름") or "").strip()
    if not 찍힌이름:
        return "파일에서 매장 이름을 읽지 못했습니다. 저장하지 않습니다."
    if 찍힌이름 != 고른이름:
        return (f"이 파일은 「{찍힌이름}」 자료입니다. "
                f"지금 고른 매장은 「{고른이름}」 입니다.")
    return None


def store_mismatch(reading: dict, client: dict) -> str | None:
    """애드로그 판독의 입구. 대조 자체는 `name_mismatch` 가 한다."""
    return name_mismatch(reading.get("플레이스명"), client)


def truncation_warning(reading: dict) -> str | None:
    """총키워드와 읽어낸 개수가 다르면 알린다.

    애드로그 키워드 순위 목록은 높이가 고정된 스크롤 영역이다. 내보내기는
    그 순간 화면에 보이는 부분만 그림으로 찍는다 — 실물이 그랬다, 접힌
    상태로 총키워드 48 에 목록 17개. 「전체 펼치기」는 목록을 다 보여주는
    버튼이 아니라 키워드마다 날짜별 상세 카드를 펼치는 버튼이라, 누르면
    오히려 화면에 담기는 키워드 수가 2~3개로 줄어든다. 경고가 없으면
    31개가 조용히 사라지고 다음 달에 "왜 17개죠" 가 된다.

    상단 요약(총키워드·TOP3·TOP10)과 순위 분포 도넛은 스크롤과 무관하게
    항상 온전히 찍히므로 이 상황에서도 정확하다.

    저장을 막지는 않는다. 17개라도 없는 것보다 낫고, 알고 저장하는 것과
    모르고 저장하는 것은 다르다.
    """
    총 = reading.get("총키워드")
    읽은 = len(reading.get("순위") or [])
    if 총 is None or 총 <= 읽은:
        return None
    return (f"키워드가 {총}개인데 {읽은}개만 읽혔습니다. "
            f"애드로그 내보내기는 목록에서 화면에 보이는 만큼만 찍힙니다 — "
            f"「전체 접기」로 줄여서 다시 내보내면 더 담깁니다. "
            f"총키워드·TOP3·TOP10 요약은 이 경우에도 정확합니다.")


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


def api_key_from_env() -> str | None:
    """키를 환경변수에서만 읽는다. 없으면 None 이고, 그러면 판독이 꺼진다.

    키가 없다고 도구가 멈추면 안 된다 — 손입력은 그대로 된다.
    """
    return (os.environ.get(KEY_ENV) or "").strip() or None


def render_pages(data: bytes, filename: str) -> list[bytes]:
    """파일을 PNG 바이트 목록으로 바꾼다. **디스크에 쓰지 않는다.**

    애드로그 내보내기는 글자가 0자인 이미지 PDF 라 텍스트 추출이 안 된다.
    쪽마다 그림으로 렌더해 모델에 보낸다.

    이미지 파일은 그대로 통과시킨다 — 오픈업 캡처가 같은 통로로 들어온다.
    """
    if len(data) > MAX_BYTES:
        raise ValueError(TOO_BIG)
    if not filename.lower().endswith(".pdf"):
        return [data]

    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        print(f"[판독] PDF 열기 실패: {exc!r}", file=sys.stderr)
        raise ValueError(BAD_FILE) from None
    try:
        return [page.get_pixmap(dpi=RENDER_DPI).tobytes("png")
                for page in list(doc)[:MAX_PAGES]]
    finally:
        doc.close()


def ask_model(images: list[bytes], prompt: str, api_key: str,
              model: str = MODEL) -> str:
    """그림들과 프롬프트를 보내 **글자**를 받는다. 파싱은 부르는 쪽 몫이다.

    키는 **헤더로만** 보낸다. 본문이나 URL 에 실으면 로그에 남는다.

    호출 실패의 예외 원문에는 요청 헤더가 섞여 들어온다 — 거기에 키가
    있다. 그래서 원문을 밖으로 내보내지 않는다. stderr 에도 안 찍는다:
    `collect.short_error()` 가 낸 짧은 말만 ValueError 로 다시 던진다.
    """
    require_https(ANTHROPIC_ENDPOINT)

    content = [{"type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": base64.b64encode(png).decode("ascii")}}
               for png in images]
    content.append({"type": "text", "text": prompt})

    body = json.dumps({
        "model": model,
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": content}],
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(ANTHROPIC_ENDPOINT, data=body, headers={
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        # 원문을 print 하지 마라 — 여기에 키가 들어 있다.
        raise ValueError(f"판독 호출이 실패했습니다({short_error(exc)}).") from None

    return "".join(block.get("text", "")
                   for block in (payload.get("content") or [])
                   if isinstance(block, dict) and block.get("type") == "text")


def read_document(data: bytes, filename: str, api_key: str,
                  model: str = MODEL) -> dict:
    """파일 한 개를 판독해 정규화된 dict 를 낸다. 아무것도 저장하지 않는다."""
    pages = render_pages(data, filename)
    return parse_reading(ask_model(pages, PROMPT, api_key, model))
