import json

import pytest

from cmo.lib.storage import PlanExists, Store, slugify

CLIENT = {
    "이름": "하루인 인계점", "업종": "고깃집", "지역": "수원 인계동",
    "평수": 60, "객단가": 18000, "계약시작": "2026-03", "상태": "진행중",
    "추적키워드": ["인계동 삼겹살"], "스냅샷": [],
}
PLAN = {
    "월": "2026-09", "계약가": 1000000, "진단메모": "블로그 리뷰 14건",
    "항목": [{"상품id": "네이버-블로그_일반_체험단", "수량": 10}],
}


def test_slugify_replaces_spaces():
    assert slugify("하루인 인계점") == "하루인_인계점"


def test_slugify_strips_windows_forbidden_characters():
    assert slugify('미친양꼬치/방이점:2호*') == "미친양꼬치_방이점_2호"


def test_slugify_keeps_korean():
    assert slugify("함바그또카레야") == "함바그또카레야"


def test_client_round_trip(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    assert store.client_read("하루인_인계점") == CLIENT


def test_client_file_is_utf8_readable(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    raw = (tmp_data / "clients" / "하루인_인계점" / "client.json").read_text(encoding="utf-8")
    assert "하루인 인계점" in raw
    assert json.loads(raw)["업종"] == "고깃집"


def test_clients_lists_saved_stores(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    store.client_write("우된장", {**CLIENT, "이름": "우된장"})
    assert {c["이름"] for c in store.clients()} == {"우된장", "하루인 인계점"}
    assert {c["slug"] for c in store.clients()} == {"우된장", "하루인_인계점"}


def test_plan_round_trip(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    store.plan_write("하루인_인계점", "2026-09", PLAN)
    assert store.plan_read("하루인_인계점", "2026-09") == PLAN


def test_plan_write_refuses_overwrite(tmp_data):
    """지난달 기획안을 실수로 덮어쓰면 이력이 사라진다."""
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    store.plan_write("하루인_인계점", "2026-09", PLAN)
    with pytest.raises(PlanExists):
        store.plan_write("하루인_인계점", "2026-09", {**PLAN, "계약가": 2000000})
    assert store.plan_read("하루인_인계점", "2026-09")["계약가"] == 1000000


def test_plan_write_force_overwrites(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    store.plan_write("하루인_인계점", "2026-09", PLAN)
    store.plan_write("하루인_인계점", "2026-09", {**PLAN, "계약가": 2000000}, force=True)
    assert store.plan_read("하루인_인계점", "2026-09")["계약가"] == 2000000


def test_plan_months_sorted_desc(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    for m in ["2026-03", "2026-09", "2026-06"]:
        store.plan_write("하루인_인계점", m, {**PLAN, "월": m})
    assert store.plan_months("하루인_인계점") == ["2026-09", "2026-06", "2026-03"]


def test_plan_copy_creates_new_month(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    store.plan_write("하루인_인계점", "2026-09", PLAN)
    copied = store.plan_copy("하루인_인계점", "2026-09", "2026-10")
    assert copied["월"] == "2026-10"
    assert copied["항목"] == PLAN["항목"]
    assert store.plan_read("하루인_인계점", "2026-09")["월"] == "2026-09"


def test_plan_copy_refuses_existing_target(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    store.plan_write("하루인_인계점", "2026-09", PLAN)
    store.plan_write("하루인_인계점", "2026-10", {**PLAN, "월": "2026-10"})
    with pytest.raises(PlanExists):
        store.plan_copy("하루인_인계점", "2026-09", "2026-10")


def test_missing_client_raises(tmp_data):
    with pytest.raises(FileNotFoundError):
        Store(tmp_data).client_read("없는가게")


# --- 경로 검증 (path traversal / 빈 슬러그 방어) ---

def test_slugify_symbols_only_raises():
    with pytest.raises(ValueError):
        slugify("///")
    with pytest.raises(ValueError):
        slugify("***")
    with pytest.raises(ValueError):
        slugify("   ")


def test_slugify_still_keeps_valid_korean_names():
    """회귀: 정상 한국어 이름은 여전히 통과한다."""
    assert slugify("하루인 인계점") == "하루인_인계점"
    assert slugify("함바그또카레야") == "함바그또카레야"


def test_client_write_rejects_path_traversal_slug(tmp_data):
    store = Store(tmp_data)
    with pytest.raises(ValueError):
        store.client_write("../탈출", CLIENT)


def test_client_read_rejects_path_traversal_slug(tmp_data):
    store = Store(tmp_data)
    with pytest.raises(ValueError):
        store.client_read("../탈출")


def test_client_write_rejects_absolute_slug(tmp_data):
    store = Store(tmp_data)
    with pytest.raises(ValueError):
        store.client_write("C:/Users/attacker/evil", CLIENT)


def test_client_write_rejects_bare_drive_letter_slug(tmp_data):
    """구분자 없이 드라이브 문자만 있는 경우도 절대 경로로 간주해 막는다."""
    store = Store(tmp_data)
    with pytest.raises(ValueError):
        store.client_write("C:", CLIENT)


def test_client_write_rejects_empty_slug(tmp_data):
    store = Store(tmp_data)
    with pytest.raises(ValueError):
        store.client_write("", CLIENT)


def test_plan_read_rejects_dotdot_month(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    with pytest.raises(ValueError):
        store.plan_read("하루인_인계점", "..")


def test_plan_write_rejects_dotdot_month(tmp_data):
    store = Store(tmp_data)
    store.client_write("하루인_인계점", CLIENT)
    with pytest.raises(ValueError):
        store.plan_write("하루인_인계점", "..", PLAN)


def test_rejected_slug_does_not_escape_data_dir(tmp_data):
    """경로 조각 검증에서 거부되면, 그 값으로 조합됐을 경로 바깥/안 어디에도 파일이 생기면 안 된다."""
    store = Store(tmp_data)
    slug = "../../탈출_마커"
    escaped_target = (tmp_data / "clients" / slug).resolve()
    with pytest.raises(ValueError):
        store.client_write(slug, CLIENT)
    assert not escaped_target.exists()
    assert not (escaped_target / "client.json").exists()
    # 정상 clients 폴더 내부에도 새 항목이 생기지 않았는지 확인
    assert list((tmp_data / "clients").iterdir()) == []
