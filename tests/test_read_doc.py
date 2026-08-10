"""애드로그 종합분석 판독 — 순수 함수.

여기 테스트는 네트워크도 파일도 타지 않는다. 실고객 PDF 를 픽스처로
쓰지 않는다 — 아래 값은 전부 지어낸 것이다.
"""
import json

import pytest

from cmo.lib.read_doc import (NOT_ADLOG, merge_into_client, parse_reading,
                              snapshot_from, store_mismatch,
                              truncation_warning)

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
