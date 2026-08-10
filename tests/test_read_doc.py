"""애드로그 종합분석 판독 — 순수 함수.

여기 테스트는 네트워크도 파일도 타지 않는다. 실고객 PDF 를 픽스처로
쓰지 않는다 — 아래 값은 전부 지어낸 것이다.
"""
import io
import json
import os
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
    got = parse_reading(json.dumps(
        {**READING, "순위": [{"키워드": "가", "순위": 3},
                             {"키워드": "나", "순위": None},
                             {"키워드": "", "순위": 5}]}, ensure_ascii=False))
    assert got["순위"] == [{"키워드": "가", "순위": 3}]


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
    assert set(snap) == {"수집시각", "플레이스", "순위", "예상매출", "순위요약"}
    assert snap["플레이스"] == {"방문자리뷰": 312, "블로그리뷰": 14, "저장수": 88}
    assert snap["순위"][0] == {"키워드": "인계동 삼겹살", "순위": 3}
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
