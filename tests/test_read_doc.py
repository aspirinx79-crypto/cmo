"""애드로그 종합분석 판독 — 순수 함수.

여기 테스트는 네트워크도 파일도 타지 않는다. 실고객 PDF 를 픽스처로
쓰지 않는다 — 아래 값은 전부 지어낸 것이다.
"""
import io
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import fitz
import pytest

from cmo.lib.read_doc import (ANTHROPIC_ENDPOINT, MAX_BYTES, MAX_PAGES, MODEL,
                              NOT_ADLOG, PROMPT, api_key_from_env,
                              merge_into_client, parse_reading,
                              read_document, render_pages, snapshot_from,
                              store_mismatch, truncation_warning)

READING = {
    "플레이스ID": "1234567890",
    "플레이스명": "하루인 인계점",
    "카테고리": "고깃집",
    "방문자리뷰": 312,
    "블로그리뷰": 14,
    "저장수": 88,
    "총키워드": 3,
    "TOP3": 1,
    "TOP10": 2,
    "순위": [{"키워드": "인계동 삼겹살", "순위": 3},
             {"키워드": "수원 고깃집", "순위": 7},
             {"키워드": "인계동 맛집", "순위": 12}],
}


def test_parse_reading_accepts_a_fenced_json_block():
    """모델이 ```json 울타리를 치는 날이 온다. 그것 때문에 죽으면 안 된다."""
    text = "여기 있습니다.\n```json\n" + json.dumps(READING, ensure_ascii=False) + "\n```\n"
    assert parse_reading(text)["플레이스명"] == "하루인 인계점"


def test_parse_reading_keeps_only_known_keys():
    """모델이 없는 칸을 지어내도 안 받는다."""
    dirty = {**READING, "월매출": 42000000, "메모": "추정입니다"}
    got = parse_reading(json.dumps(dirty, ensure_ascii=False))
    assert "월매출" not in got
    assert "메모" not in got
    assert "42000000" not in json.dumps(got, ensure_ascii=False)


def test_parse_reading_turns_unreadable_numbers_into_none_not_zero():
    """0 은 "리뷰가 없다" 는 사실이고 null 은 "모른다" 는 사실이다."""
    got = parse_reading(json.dumps({**READING, "저장수": "-", "TOP3": None},
                                   ensure_ascii=False))
    assert got["저장수"] is None
    assert got["TOP3"] is None


def test_parse_reading_drops_rank_rows_without_a_number():
    """순위도 조회수도 순위권밖 표시도 없는 줄은 버린다. 이름 없는 줄도.

    줄 모양이 넓어졌다(조회수·순위권밖·비교순위가 붙었다). 여기서 보는
    것은 「무엇을 버리는가」이므로 남은 키워드로 단언한다 — 모양을 통째로
    고정하면 칸이 하나 늘 때마다 이 테스트가 뜻 없이 깨진다.
    """
    got = parse_reading(json.dumps(
        {**READING, "순위": [{"키워드": "가", "순위": 3},
                             {"키워드": "나", "순위": None},
                             {"키워드": "", "순위": 5}]}, ensure_ascii=False))
    assert [r["키워드"] for r in got["순위"]] == ["가"]
    assert got["순위"][0]["순위"] == 3


@pytest.mark.parametrize("text", ["", "못 읽었습니다", "{", "[]"])
def test_parse_reading_raises_on_unreadable_output(text):
    with pytest.raises(ValueError):
        parse_reading(text)


def test_parse_reading_rejects_a_document_that_is_not_adlog():
    """플레이스명도 리뷰수도 없으면 애드로그 파일이 아니다."""
    with pytest.raises(ValueError, match=NOT_ADLOG):
        parse_reading(json.dumps({"플레이스명": None, "방문자리뷰": None},
                                 ensure_ascii=False))


def test_store_mismatch_blocks_a_different_store():
    """A 매장 화면에 B 매장 PDF 를 떨구는 건 일어나게 되어 있는 일이다.

    애드로그 내보내기 파일명은 매장이 달라도 똑같다.
    """
    msg = store_mismatch(READING, {"이름": "미친양꼬치 잠실점"})
    assert msg and "하루인 인계점" in msg


def test_store_mismatch_passes_only_on_exact_name():
    assert store_mismatch(READING, {"이름": "하루인 인계점"}) is None
    assert store_mismatch(READING, {"이름": "하루인"}) is not None


def test_store_mismatch_blocks_when_the_pdf_has_no_name():
    assert store_mismatch({**READING, "플레이스명": None},
                          {"이름": "하루인 인계점"}) is not None


def test_truncation_warning_when_list_is_shorter_than_total():
    """실물이 그랬다 — 총키워드 48 인데 목록에는 17개만 찍혀 있었다."""
    short = {**READING, "총키워드": 48}
    assert "48" in truncation_warning(short)
    assert "3" in truncation_warning(short)


def test_truncation_warning_is_silent_when_counts_agree():
    assert truncation_warning(READING) is None


def test_truncation_warning_is_silent_when_total_is_unknown():
    assert truncation_warning({**READING, "총키워드": None}) is None


def test_snapshot_matches_the_existing_shape():
    """새 저장 형식을 만들지 않는다 — 제안서·화면이 그대로 받아야 한다."""
    snap = snapshot_from(READING)
    assert set(snap) == {"수집시각", "플레이스", "순위", "예상매출", "순위요약",
                         "진단"}
    assert snap["플레이스"] == {"방문자리뷰": 312, "블로그리뷰": 14, "저장수": 88}
    # 줄에 조회수·순위권밖·비교순위가 붙었다. 여기서 보는 것은 「기존
    # 모양을 지켰는가」이므로 값으로 단언한다.
    assert snap["순위"][0]["키워드"] == "인계동 삼겹살"
    assert snap["순위"][0]["순위"] == 3
    assert snap["예상매출"] is None
    assert snap["순위요약"] == {"총키워드": 3, "TOP3": 1, "TOP10": 2}


def test_merge_fills_only_empty_fields():
    client = {"이름": "하루인 인계점", "플레이스URL": "", "업종": ""}
    got = merge_into_client(client, READING)
    assert got["플레이스URL"] == "https://m.place.naver.com/restaurant/1234567890/home"
    assert got["업종"] == "고깃집"


def test_merge_never_overwrites_what_a_person_typed():
    """손으로 고친 값을 판독이 되돌리면 고쳤다는 사실이 조용히 사라진다."""
    client = {"이름": "하루인 인계점",
              "플레이스URL": "https://직접넣은주소",
              "업종": "손으로 적은 업종"}
    got = merge_into_client(client, READING)
    assert got["플레이스URL"] == "https://직접넣은주소"
    assert got["업종"] == "손으로 적은 업종"


def test_merge_does_not_mutate_the_original():
    client = {"이름": "하루인 인계점", "플레이스URL": "", "업종": ""}
    merge_into_client(client, READING)
    assert client["플레이스URL"] == ""


def _pdf_bytes(pages: int = 2) -> bytes:
    """글자 없는 그림 PDF 를 만든다 — 실물과 같은 조건이다."""
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=300, height=400)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_api_key_absent_is_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert api_key_from_env() is None


def test_endpoint_is_https():
    assert ANTHROPIC_ENDPOINT.startswith("https://")


def test_render_pdf_gives_one_png_per_page():
    pages = render_pages(_pdf_bytes(2), "플레이스_종합분석.pdf")
    assert len(pages) == 2
    assert all(p.startswith(b"\x89PNG") for p in pages)


def test_render_caps_page_count():
    pages = render_pages(_pdf_bytes(MAX_PAGES + 3), "긴.pdf")
    assert len(pages) == MAX_PAGES


def test_render_passes_an_image_through_untouched():
    png = render_pages(_pdf_bytes(1), "한쪽.pdf")[0]
    assert render_pages(png, "캡처.png") == [png]


def test_render_rejects_a_file_over_the_limit():
    with pytest.raises(ValueError, match="10MB"):
        render_pages(b"x" * (MAX_BYTES + 1), "큰.pdf")


def test_render_reports_a_broken_pdf_in_human_words():
    with pytest.raises(ValueError):
        # 브리프 원문은 `b"%PDF-1.4 깨진파일"` (bytes 리터럴에 비ASCII 문자) —
        # 파이썬 bytes 리터럴은 ASCII 만 허용해 SyntaxError 가 난다. 같은
        # 내용을 UTF-8 로 인코딩해 동일한 "깨진 PDF" 의도를 유지한다.
        render_pages("%PDF-1.4 깨진파일".encode("utf-8"), "깨진.pdf")


def test_read_document_sends_key_in_header_and_never_in_body(monkeypatch):
    seen = {}

    class FakeResponse:
        def read(self):
            return json.dumps({"content": [
                {"type": "text",
                 "text": json.dumps(READING, ensure_ascii=False)}]}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = req.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    got = read_document(_pdf_bytes(1), "종합분석.pdf", "sk-비밀키")

    assert got["플레이스명"] == "하루인 인계점"
    assert seen["headers"]["X-api-key"] == "sk-비밀키"
    assert "sk-비밀키" not in seen["body"]
    assert "sk-비밀키" not in seen["url"]
    assert json.loads(seen["body"])["model"] == MODEL


def test_prompt_forbids_reading_numbers_off_the_graph_axis():
    """축 눈금과 마지막 점의 라벨이 다르다. 읽어야 하는 건 라벨이다."""
    assert "그래프" in PROMPT and "축" in PROMPT


def test_key_never_reaches_stderr_even_when_the_call_fails(monkeypatch,
                                                           capsys):
    """실패 경로가 키를 흘리는 흔한 자리다.

    urllib 의 예외 문자열에는 요청 정보가 섞여 들어온다. 그걸 그대로
    print 하면 키가 콘솔에 남고, 콘솔은 화면 공유로 남는다.
    """
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, f"bad key {dict(req.header_items())}", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(Exception):
        read_document(_pdf_bytes(1), "종합분석.pdf", "sk-비밀키")

    out = capsys.readouterr()
    assert "sk-비밀키" not in out.err
    assert "sk-비밀키" not in out.out


def test_read_document_writes_nothing_to_disk(monkeypatch, tmp_path):
    """판독한 파일이 어딘가에 남으면 관리할 개인정보가 하나 는다."""
    class FakeResponse:
        def read(self):
            return json.dumps({"content": [
                {"type": "text",
                 "text": json.dumps(READING, ensure_ascii=False)}]}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse())
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    read_document(_pdf_bytes(2), "종합분석.pdf", "키")
    assert set(tmp_path.rglob("*")) == before


@pytest.mark.network
def test_real_reading_of_an_adlog_export():
    """실제 애드로그 PDF 로 확인하는 유일한 자리.

    파일은 저장소에 없다(실고객 자료다). 환경변수 ADLOG_SAMPLE_PDF 에
    경로를 넣고 돌린다. 없으면 건너뛴다.
    """
    key = api_key_from_env()
    path = os.environ.get("ADLOG_SAMPLE_PDF")
    if not key or not path:
        pytest.skip("ANTHROPIC_API_KEY 또는 ADLOG_SAMPLE_PDF 가 없다")
    data = Path(path).read_bytes()
    got = read_document(data, Path(path).name, key)
    assert got["플레이스명"], "플레이스명을 못 읽었다"
    assert got["방문자리뷰"] is not None, "방문자리뷰를 못 읽었다"
    assert got["순위"], "키워드 순위를 하나도 못 읽었다"


def test_ask_model_returns_text_not_a_dict(monkeypatch):
    """ask_model 은 글자만 낸다. 파싱은 부르는 쪽 몫이다."""
    from cmo.lib import read_doc

    보낸것 = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "content": [{"type": "text", "text": "안녕"}]
            }).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        보낸것["헤더"] = dict(req.headers)
        보낸것["본문"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    # 진짜 PNG 머리(8바이트)로 시작해야 한다 — `ask_model` 이 바이트를 보고
    # 형식을 정하기 때문에 「PNG 비슷한 것」으로는 통과하지 않는다.
    got = read_doc.ask_model([b"\x89PNG\r\n\x1a\n1", b"\x89PNG\r\n\x1a\n2"],
                             "읽어라", "sk-test")

    assert got == "안녕"
    # 키는 헤더로만 간다. 본문·URL 에 실으면 로그에 남는다.
    assert 보낸것["헤더"]["X-api-key"] == "sk-test"
    assert "sk-test" not in json.dumps(보낸것["본문"], ensure_ascii=False)
    # 그림 두 장과 프롬프트 한 개가 이 순서로 들어간다.
    content = 보낸것["본문"]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]
    assert content[-1]["text"] == "읽어라"


def test_ask_model_never_leaks_the_key_on_failure(monkeypatch, capsys):
    """예외 원문에는 요청 헤더가 섞이고 키가 바로 그 헤더다."""
    from cmo.lib import read_doc

    def boom(req, timeout=None):
        raise RuntimeError("HTTP 401 x-api-key: sk-secret-key")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ValueError) as err:
        read_doc.ask_model([b"\x89PNG"], "읽어라", "sk-secret-key")

    assert "sk-secret-key" not in str(err.value)
    캡처 = capsys.readouterr()
    assert "sk-secret-key" not in 캡처.out
    assert "sk-secret-key" not in 캡처.err


def test_name_mismatch_is_the_one_rule():
    """대조 규칙은 한 벌이다. store_mismatch 도 이 함수를 부른다."""
    from cmo.lib.read_doc import name_mismatch, store_mismatch

    client = {"이름": "하루인 인계점"}
    assert name_mismatch("하루인 인계점", client) is None
    assert "하루인 인계점" in name_mismatch("미친양꼬치 잠실점", client)
    assert "매장 이름을 읽지 못했습니다" in name_mismatch("", client)
    # 애드로그 쪽 입구는 그대로 돈다.
    assert store_mismatch({"플레이스명": "하루인 인계점"}, client) is None


# ── 보강 판독: 조회수·순위권밖·비교순위·히든키워드·리뷰 ──────────

RICH = {
    "플레이스ID": "2038790815",
    "플레이스명": "서경한우프라자 예술의전당점",
    "카테고리": "육류,고기요리",
    "방문자리뷰": 775, "블로그리뷰": 1415, "저장수": 100,
    "총키워드": 51, "TOP3": 6, "TOP10": 11,
    "기준일": "08-12", "비교일": "07-29",
    "대표키워드": ["방배역가족모임밥집", "서초역고기집회식"],
    "히든키워드": ["예술의전당한우", "방배역 곰탕"],
    "순위": [
        {"키워드": "서초맛집", "순위": None, "순위권밖": True,
         "조회수": 5740, "비교순위": 81},
        {"키워드": "방배동맛집", "순위": 77, "조회수": 4900, "비교순위": 18},
        {"키워드": "예술의전당정육식당", "순위": 1, "조회수": 50, "비교순위": 1},
    ],
    "리뷰": {
        "방문자": [{"제목": "아이들이 한우 먹고싶다고", "조회수": 1479,
                    "작성일": "2026-07-16", "작성자": "ljw20566"}],
        "블로그": [{"제목": "방배동 소고기 맛집 추천", "작성일": "2026-05-26",
                    "실명여부": "톰바미설치"}],
    },
}


def test_parse_reads_search_volume_and_outside_rank():
    got = parse_reading(json.dumps(RICH, ensure_ascii=False))
    첫줄 = got["순위"][0]
    assert 첫줄["키워드"] == "서초맛집"
    assert 첫줄["조회수"] == 5740
    assert 첫줄["순위권밖"] is True
    assert 첫줄["순위"] is None
    assert 첫줄["비교순위"] == 81


def test_outside_rank_is_not_confused_with_unknown():
    """`-` 는 순위권 밖이라는 사실이고 null 은 모른다는 사실이다."""
    raw = json.loads(json.dumps(RICH, ensure_ascii=False))
    raw["순위"].append({"키워드": "모르는키워드", "순위": None, "조회수": 12})
    got = parse_reading(json.dumps(raw, ensure_ascii=False))
    모름 = next(r for r in got["순위"] if r["키워드"] == "모르는키워드")
    assert 모름["순위권밖"] is False
    assert 모름["순위"] is None


def test_parse_reads_the_two_dates():
    got = parse_reading(json.dumps(RICH, ensure_ascii=False))
    assert got["기준일"] == "08-12"
    assert got["비교일"] == "07-29"


def test_parse_reads_keyword_lists():
    got = parse_reading(json.dumps(RICH, ensure_ascii=False))
    assert got["히든키워드"] == ["예술의전당한우", "방배역 곰탕"]
    assert got["대표키워드"][0] == "방배역가족모임밥집"


def test_parse_reads_reviews_including_internal_marks():
    """실명여부까지 읽어 둔다. 제안서에서 빼는 건 proposal 쪽 일이다."""
    got = parse_reading(json.dumps(RICH, ensure_ascii=False))
    방문 = got["리뷰"]["방문자"][0]
    assert 방문["제목"].startswith("아이들이")
    assert 방문["조회수"] == 1479
    assert got["리뷰"]["블로그"][0]["실명여부"] == "톰바미설치"


def test_old_readings_without_the_new_fields_still_parse():
    """기존 PDF 한 장만 넣으면 새 칸이 없다. 그래도 통과해야 한다."""
    got = parse_reading(json.dumps(READING, ensure_ascii=False))
    assert got["기준일"] is None
    assert got["히든키워드"] == []
    assert got["리뷰"] == {"방문자": [], "블로그": []}
    assert got["순위"][0]["조회수"] is None
    assert got["순위"][0]["순위권밖"] is False


def test_read_captures_sends_every_page_in_one_call(monkeypatch):
    """애드로그도 여러 장을 한 번의 호출로 보낸다.

    조회수는 순위 추이 표에, 리뷰 목록은 기본정보 화면에 있다. 나눠 보내면
    한 매장의 그림이 안 맞춰진다.
    """
    from cmo.lib import captures, read_doc

    본것 = {}

    def fake_ask(images, prompt, api_key, model=None):
        본것["장수"] = len(images)
        본것["프롬프트"] = prompt
        return json.dumps(RICH, ensure_ascii=False)

    monkeypatch.setattr(captures, "ask_model", fake_ask)
    got = read_doc.read_captures(
        [(b"\x89PNG-1", "a.png"), (b"\x89PNG-2", "b.png")], "sk-test")

    assert 본것["장수"] == 2
    assert 본것["프롬프트"] is read_doc.PROMPT
    assert got["순위"][0]["조회수"] == 5740


def test_read_captures_keeps_the_same_limits(monkeypatch):
    """장수 상한은 오픈업과 같은 한 곳에서 온다."""
    from cmo.lib import captures, read_doc

    monkeypatch.setattr(captures, "ask_model",
                        lambda *a, **k: json.dumps(RICH, ensure_ascii=False))
    files = [(b"\x89PNG", f"{i}.png") for i in range(captures.MAX_CAPTURES + 1)]
    with pytest.raises(ValueError, match="장까지"):
        read_doc.read_captures(files, "sk-test")


# ── 그림 종류를 사실대로 적어 보낸다 ───────────────────────────
#
# `ask_model` 이 모든 그림을 `image/png` 로 못박아 보내고 있었다. 화면은
# `accept="image/*"` 로 JPG 를 받는데(`index.html:98·109`), JPG 를 PNG 라고
# 우기면 API 가 400 으로 되돌린다. 상무님에게는 「판독 호출이 실패했습니다」
# 한 줄로만 보이고, 애드로그도 오픈업도 같은 통로라 **둘 다** 죽는다.

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 20
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 20
GIF_BYTES = b"GIF89a" + b"0" * 20
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 20


def _capture_sent_body(monkeypatch, images):
    """ask_model 이 실제로 보낸 본문을 돌려준다."""
    from cmo.lib import read_doc

    보낸것 = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"content": [{"type": "text", "text": "{}"}]}
                              ).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        보낸것["본문"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    read_doc.ask_model(images, "읽어라", "sk-test")
    return 보낸것["본문"]


@pytest.mark.parametrize("바이트,기대", [
    (PNG_BYTES, "image/png"),
    (JPEG_BYTES, "image/jpeg"),
    (GIF_BYTES, "image/gif"),
    (WEBP_BYTES, "image/webp"),
])
def test_media_type_follows_the_actual_bytes(monkeypatch, 바이트, 기대):
    """파일명이 아니라 **바이트**를 보고 정한다 — 확장자는 거짓말을 한다."""
    본문 = _capture_sent_body(monkeypatch, [바이트])
    assert 본문["messages"][0]["content"][0]["source"]["media_type"] == 기대


def test_mixed_captures_each_keep_their_own_type(monkeypatch):
    """PDF 에서 렌더한 PNG 와 손으로 찍은 JPG 가 한 번에 섞여 들어온다."""
    본문 = _capture_sent_body(monkeypatch, [PNG_BYTES, JPEG_BYTES, PNG_BYTES])
    보낸종류 = [c["source"]["media_type"]
                for c in 본문["messages"][0]["content"] if c["type"] == "image"]
    assert 보낸종류 == ["image/png", "image/jpeg", "image/png"]


def test_unknown_image_type_is_refused_with_a_usable_message(monkeypatch):
    """모르는 형식을 PNG 라고 우기면 API 가 400 을 주고 이유는 안 남는다.

    아이폰 기본 형식(HEIC)이 여기로 들어온다. 「실패했습니다」 대신
    무엇을 어떻게 하라는 말을 준다.
    """
    from cmo.lib import read_doc

    with pytest.raises(ValueError) as err:
        read_doc.ask_model([b"ftypheic" + b"0" * 20], "읽어라", "sk-test")
    말 = str(err.value)
    assert "PNG" in 말 and "JPG" in 말


def test_refusal_happens_before_the_network_call(monkeypatch):
    """모르는 형식이면 부르지도 않는다 — 어차피 거절당할 요청이다."""
    from cmo.lib import read_doc

    def boom(req, timeout=None):
        raise AssertionError("보내면 안 되는 요청을 보냈다")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ValueError) as err:
        read_doc.ask_model([PNG_BYTES, b"ftypheic" + b"0" * 20], "읽어라", "k")

    # `ValueError` 만 보면 안 된다. ask_model 은 호출 중 **아무 예외나** 잡아
    # 「판독 호출이 실패했습니다」라는 ValueError 로 바꿔 던진다 — boom 이
    # 터져도 그 모양이 되니, 형식을 안 보고 그냥 보내도 이 시험이 통과해
    # 버렸다(실제로 그렇게 확인했다). 낸 말이 형식 거절인지까지 본다.
    assert "PNG" in str(err.value), f"보내고 나서 실패한 것이다: {err.value}"


# ── 400 이 왜 났는지 말하게 한다 ────────────────────────────────
#
# 위의 형식 사고가 며칠을 먹은 진짜 이유는 형식이 틀렸다는 게 아니라
# **틀린 줄 몰랐다는 것**이다. API 는 「image/png 라고 했는데 jpeg 로
# 보인다」고 정확히 알려줬는데, `short_error` 가 그걸 「조회 실패」로
# 뭉갰다. 상무님 화면에는 「판독 호출이 실패했습니다(조회 실패)」만
# 남았다.
#
# `short_error` 자체는 못 건드린다 — `collect.py` 도 같이 쓰는데 거기
# 응답 본문에는 매장 정보가 들어 있고 그게 클라이언트 JSON 에 박힌다.
# 그래서 여기 400 자리에서만 API 가 준 이유를 꺼내 붙인다.


def _http_error(code, body):
    return urllib.error.HTTPError(
        ANTHROPIC_ENDPOINT, code, "err", {},
        io.BytesIO(json.dumps(body).encode("utf-8")))


def _ask_with_error(monkeypatch, err):
    from cmo.lib import read_doc

    def fake_urlopen(req, timeout=None):
        raise err

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ValueError) as caught:
        read_doc.ask_model([PNG_BYTES], "읽어라", "sk-ant-SECRET")
    return str(caught.value)


def test_a_400_repeats_what_the_api_actually_said(monkeypatch):
    """400 은 대개 우리가 잘못 보낸 것이다. 뭘 잘못했는지가 필요하다."""
    말 = _ask_with_error(monkeypatch, _http_error(400, {"error": {
        "type": "invalid_request_error",
        "message": "The image was specified using the image/png media type, "
                   "but the image appears to be a image/jpeg image"}}))
    assert "image/jpeg" in 말, f"API 가 준 이유가 사라졌다: {말}"


def test_the_key_never_rides_along_in_the_400_message(monkeypatch):
    """본문에 키처럼 생긴 게 섞여 있어도 화면·로그로 내보내지 않는다.

    응답 본문은 우리가 만든 글이 아니다. 언젠가 요청 일부를 되비추면
    거기 키가 실릴 수 있다. 그 한 번이면 키가 클라이언트 JSON 에 박힌다.
    """
    말 = _ask_with_error(monkeypatch, _http_error(400, {"error": {
        "message": "bad header x-api-key: sk-ant-SECRET"}}))
    assert "sk-ant-SECRET" not in 말, f"키가 새어 나왔다: {말}"


def test_auth_failures_keep_their_own_short_message(monkeypatch):
    """401 은 이유를 되풀이할 게 없다 — 키가 틀린 것이고 본문은 군더더기다."""
    말 = _ask_with_error(monkeypatch, _http_error(401, {"error": {
        "message": "invalid x-api-key"}}))
    assert "invalid x-api-key" not in 말


def test_a_400_without_a_readable_body_still_fails_cleanly(monkeypatch):
    """본문이 JSON 이 아니어도 터지면 안 된다 — 프록시가 HTML 을 준다."""
    err = urllib.error.HTTPError(ANTHROPIC_ENDPOINT, 400, "err", {},
                                 io.BytesIO(b"<html>Bad Request</html>"))
    말 = _ask_with_error(monkeypatch, err)
    assert 말 and "판독" in 말
