"""오픈업 캡처 판독 — 순수 함수.

여기 테스트는 네트워크도 파일도 타지 않는다. 실고객 캡처를 픽스처로
쓰지 않는다 — 아래 값은 전부 지어낸 것이다.
"""
import json
from datetime import date

import pytest

from cmo.lib.read_openub import (MAX_CAPTURES, MIXED_MONTHS, NOT_OPENUB,
                                 merge_openub, month_to_ym, openub_entry,
                                 parse_openub)

TODAY = date(2026, 8, 12)

RAW = {
    "매장명": "하루인 인계점",
    "기준월들": [6, 6, 6],
    "매출하한": 46000000,
    "매출상한": 56000000,
    "성별최다": "남성",
    "성별최다비율": 65,
    "연령최다": "남성 20대",
    "연령최다비율": 26,
    "요일최다": "토",
    "요일최다비율": 25,
    "평일비율": 65,
    "시간대최다": "밤",
    "시간대최다비율": 40,
}


def test_parse_reads_every_field():
    got = parse_openub(json.dumps(RAW, ensure_ascii=False))
    assert got["매장명"] == "하루인 인계점"
    assert got["기준월"] == 6
    assert got["매출하한"] == 46000000
    assert got["매출상한"] == 56000000
    assert got["성별최다"] == "남성"
    assert got["성별최다비율"] == 65
    assert got["연령최다"] == "남성 20대"
    assert got["시간대최다비율"] == 40


def test_parse_survives_a_fence_and_chatter():
    """모델이 ```json 울타리를 치거나 앞뒤에 말을 붙이는 날이 온다."""
    text = "네, 읽었습니다.\n```json\n" + json.dumps(RAW, ensure_ascii=False) + "\n```"
    assert parse_openub(text)["기준월"] == 6


def test_parse_rejects_a_file_that_is_not_openub():
    """매출도 성별도 요일도 못 읽었으면 오픈업 캡처가 아니다."""
    with pytest.raises(ValueError, match=NOT_OPENUB):
        parse_openub(json.dumps({"매장명": "하루인 인계점", "기준월들": [6]}))


def test_parse_blocks_mixed_months():
    """6월 캡처와 7월 캡처를 섞어 넣는 건 실제로 일어난다."""
    raw = dict(RAW, 기준월들=[6, 7, 6])
    with pytest.raises(ValueError, match=MIXED_MONTHS):
        parse_openub(json.dumps(raw, ensure_ascii=False))


def test_parse_keeps_partial_readings():
    """일부만 못 읽은 건 막지 않는다. 읽힌 것만 담는다."""
    raw = dict(RAW)
    raw["시간대최다"] = None
    raw["시간대최다비율"] = None
    got = parse_openub(json.dumps(raw, ensure_ascii=False))
    assert got["시간대최다"] is None
    assert got["매출하한"] == 46000000


def test_missing_numbers_are_none_not_zero():
    raw = dict(RAW)
    raw["평일비율"] = None
    assert parse_openub(json.dumps(raw, ensure_ascii=False))["평일비율"] is None


def test_year_is_the_nearest_past_occurrence():
    assert month_to_ym(6, TODAY) == "2026-06"      # 두 달 전
    assert month_to_ym(8, TODAY) == "2026-08"      # 이번 달
    assert month_to_ym(12, TODAY) == "2025-12"     # 작년 12월
    assert month_to_ym(9, TODAY) == "2025-09"      # 아직 안 온 9월은 작년


def test_entry_nests_value_and_ratio():
    entry = openub_entry(parse_openub(json.dumps(RAW, ensure_ascii=False)), TODAY)
    assert entry["기준월"] == "2026-06"
    assert entry["매출"] == {"하한": 46000000, "상한": 56000000}
    assert entry["성별최다"] == {"값": "남성", "비율": 65}
    assert entry["연령최다"] == {"값": "남성 20대", "비율": 26}
    assert entry["평일비율"] == 65
    assert entry["판독시각"]


def test_entry_drops_a_pair_that_was_not_read():
    raw = dict(RAW, 요일최다=None, 요일최다비율=None)
    entry = openub_entry(parse_openub(json.dumps(raw, ensure_ascii=False)), TODAY)
    assert entry["요일최다"] is None


def test_merge_overwrites_the_same_month():
    """6월 값은 하나뿐이어야 한다."""
    first = openub_entry(parse_openub(json.dumps(RAW, ensure_ascii=False)), TODAY)
    client = merge_openub({"이름": "하루인 인계점"}, first)
    raw2 = dict(RAW, 매출하한=50000000, 매출상한=60000000)
    second = openub_entry(parse_openub(json.dumps(raw2, ensure_ascii=False)), TODAY)
    client = merge_openub(client, second)
    assert len(client["오픈업"]) == 1
    assert client["오픈업"][0]["매출"]["하한"] == 50000000


def test_merge_keeps_other_months_sorted():
    june = openub_entry(parse_openub(json.dumps(RAW, ensure_ascii=False)), TODAY)
    july = openub_entry(
        parse_openub(json.dumps(dict(RAW, 기준월들=[7, 7, 7]), ensure_ascii=False)),
        TODAY)
    client = merge_openub(merge_openub({}, july), june)
    assert [e["기준월"] for e in client["오픈업"]] == ["2026-06", "2026-07"]


def test_merge_does_not_touch_snapshots():
    """이번 설계의 핵심 — 오픈업은 애드로그 값을 지우지 않는다."""
    client = {"이름": "하루인 인계점",
              "스냅샷": [{"수집시각": "2026-08-12T08:00:00",
                          "플레이스": {"방문자리뷰": 1082}}]}
    entry = openub_entry(parse_openub(json.dumps(RAW, ensure_ascii=False)), TODAY)
    out = merge_openub(client, entry)
    assert out["스냅샷"] == client["스냅샷"]
    assert out["스냅샷"][0]["플레이스"]["방문자리뷰"] == 1082


def test_merge_does_not_mutate_the_original():
    client = {"이름": "하루인 인계점"}
    entry = openub_entry(parse_openub(json.dumps(RAW, ensure_ascii=False)), TODAY)
    merge_openub(client, entry)
    assert "오픈업" not in client


def test_capture_limit_is_six():
    assert MAX_CAPTURES == 6


def test_parse_also_accepts_an_already_folded_month():
    """저장 단계에서 화면이 돌려보내는 판독에는 `기준월` 하나만 들어 있다.

    서버가 저장 전에 같은 파서로 모양을 다시 검사하므로 둘 다 읽혀야
    한다. 안 그러면 판독은 되는데 저장이 "기준월을 못 읽었다"로 막힌다.
    """
    raw = dict(RAW)
    del raw["기준월들"]
    raw["기준월"] = 6
    assert parse_openub(json.dumps(raw, ensure_ascii=False))["기준월"] == 6


def test_read_captures_sends_every_page_in_one_call(monkeypatch):
    """세 장을 한 번의 호출로 보낸다 — 성별과 연령이 다른 장에 걸쳐 있다."""
    from cmo.lib import captures, read_openub

    본것 = {}

    def fake_ask(images, prompt, api_key, model=None):
        본것["장수"] = len(images)
        본것["프롬프트"] = prompt
        return json.dumps(RAW, ensure_ascii=False)

    monkeypatch.setattr(captures, "ask_model", fake_ask)
    got = read_openub.read_captures(
        [(b"\x89PNG-1", "a.png"), (b"\x89PNG-2", "b.png"),
         (b"\x89PNG-3", "c.png")], "sk-test")

    assert 본것["장수"] == 3
    assert 본것["프롬프트"] is read_openub.OPENUB_PROMPT
    assert got["기준월"] == 6


def test_read_captures_blocks_too_many(monkeypatch):
    from cmo.lib import captures, read_openub

    monkeypatch.setattr(captures, "ask_model",
                        lambda *a, **k: json.dumps(RAW, ensure_ascii=False))
    files = [(b"\x89PNG", f"{i}.png") for i in range(MAX_CAPTURES + 1)]
    with pytest.raises(ValueError, match="장까지"):
        read_openub.read_captures(files, "sk-test")


def test_read_captures_blocks_too_big(monkeypatch):
    """합계로 본다. 한 장씩은 작아도 다 더하면 넘을 수 있다."""
    from cmo.lib import captures, read_doc, read_openub

    monkeypatch.setattr(captures, "ask_model",
                        lambda *a, **k: json.dumps(RAW, ensure_ascii=False))
    절반 = b"x" * (read_doc.MAX_BYTES // 2 + 1)
    with pytest.raises(ValueError):
        read_openub.read_captures([(절반, "a.png"), (절반, "b.png")], "sk-test")


def test_read_captures_needs_at_least_one_file(monkeypatch):
    from cmo.lib import captures, read_openub

    with pytest.raises(ValueError):
        read_openub.read_captures([], "sk-test")


@pytest.mark.network
def test_real_captures_read_gender_from_the_headline():
    r"""색이 뒤집힌 성별 차트에서 남녀를 바로 읽는지는 실물로만 확인된다.

    실행하려면 두 가지가 있어야 한다:
      $env:ANTHROPIC_API_KEY = "sk-..."
      $env:OPENUB_SAMPLE_DIR = "C:\...\캡처가 든 폴더"
    폴더의 이미지를 이름순으로 전부 넣는다. 저장소에 캡처를 복사하지 마라.
    """
    import os
    from pathlib import Path

    from cmo.lib.read_doc import api_key_from_env
    from cmo.lib.read_openub import read_captures

    key = api_key_from_env()
    folder = os.environ.get("OPENUB_SAMPLE_DIR")
    if not key or not folder:
        pytest.skip("ANTHROPIC_API_KEY 또는 OPENUB_SAMPLE_DIR 가 없다")

    paths = sorted(p for p in Path(folder).iterdir()
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    got = read_captures([(p.read_bytes(), p.name) for p in paths], key)

    assert got["매장명"]
    assert got["기준월"] in range(1, 13)
    assert got["성별최다"] in ("남성", "여성")
    assert 50 <= got["성별최다비율"] <= 100      # 최다인데 절반 미만일 수 없다
    assert got["매출하한"] < got["매출상한"]
