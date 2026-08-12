"""시드 데이터가 실제로 도구에서 열리는지 확인한다.

시드는 카톡 원문에서 뽑았다. 원문에는 사장님 전화번호·계좌번호·사적
대화가 섞여 있다. 그래서 "열리는가" 만큼이나 "원문이 딸려 들어오지
않았는가" 를 본다.
"""
import json
import re
import subprocess

from cmo.lib.storage import Store

EXPECTED_CLIENTS = 12

# 카톡 이력에서 뽑아 넣은 12곳. 아래 규칙들은 이 시드에만 적용된다 —
# 패널로 새로 등록한 매장은 카톡 근거가 없는 게 정상이고, 그걸 요구하면
# 매장을 하나 넣을 때마다 테스트가 깨진다.
KAKAO_SEED_SLUGS = {
    "농우본수원갈비",
    "로얄피그_한남점",
    "미친양꼬치_대학로점",
    "미친양꼬치_방이점",
    "수서_가원",
    "우된장_교대본점",
    "우미회관_종각본점",
    "지리산꿀통갈비_춘의역점",
    "통큰바다한상",
    "하루인_정자본점",
    "하루인_판교점",
    "함바그또카레야",
}


def test_all_clients_registered(cmo_dir):
    store = Store(cmo_dir / "data")
    assert len(store.clients()) >= EXPECTED_CLIENTS


def test_every_client_has_name_and_status(cmo_dir):
    store = Store(cmo_dir / "data")
    for entry in store.clients():
        client = store.client_read(entry["slug"])
        assert client["이름"].strip()
        assert client["상태"] in ("진행중", "종료")


def test_unverified_clients_leave_numbers_blank(cmo_dir):
    """모르는 값은 비워 둔다. 추측한 평수가 제안서 첫 장에 실리면 안 된다."""
    store = Store(cmo_dir / "data")
    for entry in store.clients():
        client = store.client_read(entry["slug"])
        if "미확인" in client.get("메모", ""):
            assert client.get("평수") is None, f"{entry['slug']}: 미확인인데 평수가 있다"
            assert client.get("객단가") is None, f"{entry['slug']}: 미확인인데 객단가가 있다"


def test_presets_reference_real_products(cmo_dir):
    store = Store(cmo_dir / "data")
    ids = {p["id"] for p in store.products()}
    presets = store.presets()
    assert len(presets) >= 3
    for preset in presets:
        assert preset["출처"].strip(), f"{preset['이름']}: 출처가 없다"
        for item in preset["항목"]:
            assert item["상품id"] in ids, \
                f"{preset['이름']}: 없는 상품 {item['상품id']}"


def test_presets_do_not_include_discontinued(cmo_dir):
    store = Store(cmo_dir / "data")
    dead = {p["id"] for p in store.products() if p["판매중지"]}
    for preset in store.presets():
        for item in preset["항목"]:
            assert item["상품id"] not in dead, \
                f"{preset['이름']}: 판매중지 상품이 들어 있다"


def test_raw_kakao_is_not_committed(cmo_dir):
    """개인정보가 저장소에 올라가면 안 된다."""
    out = subprocess.run(
        ["git", "ls-files", "cmo/data/_raw_kakao"],
        cwd=str(cmo_dir.parent), capture_output=True, text=True,
    ).stdout.strip()
    assert out == "", f"카톡 원문이 추적되고 있다:\n{out}"


# --- 원문이 시드에 묻어 오지 않았는지 ---
#
# 위의 `test_raw_kakao_is_not_committed` 는 원본 '파일' 이 커밋되는 것만
# 막는다. 정작 위험한 건 그게 아니라, 사람이 원문을 읽고 시드를 만들다가
# 전화번호나 계좌번호를 client.json 에 옮겨 적는 쪽이다. 그건 gitignore 가
# 못 막는다 — clients/ 는 커밋되는 폴더다.
#
# 그래서 시드에 실린 문자열 자체를 검사한다.

PHONE_RE = re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}")
KAKAO_EXPORT_RE = re.compile(r"님과 카카오톡 대화|\[오전 \d|\[오후 \d")

# 계좌번호꼴: 숫자와 하이픈만으로 이어지면서 숫자가 10자리 이상.
#
# 자릿수 조건이 필요하다. `\d[\d-]{9,}` 만 쓰면 "2026-08-02"(숫자 8자리)가
# 걸려서 메모에 적은 마지막 대화일마다 실패한다. 실제 계좌번호는 은행을
# 통틀어 10자리 이상이라 이 선에서 날짜와 갈린다.
_DIGIT_RUN_RE = re.compile(r"\d[\d-]{9,}")


def _account_like(text: str) -> str | None:
    for m in _DIGIT_RUN_RE.finditer(text):
        if sum(c.isdigit() for c in m.group()) >= 10:
            return m.group()
    return None


def _seed_texts(cmo_dir):
    """시드 JSON 을 통째로 문자열화해 (경로, 내용) 으로 낸다."""
    data = cmo_dir / "data"
    out = []
    for path in sorted((data / "clients").glob("*/client.json")):
        out.append((path, path.read_text(encoding="utf-8")))
    for path in sorted((data / "presets").glob("*.json")):
        out.append((path, path.read_text(encoding="utf-8")))
    return out


# 플레이스URL 의 장소 ID 는 10자리 숫자라 계좌번호꼴 검사에 걸린다.
# 공개 식별자이고 사람이 옮겨 적은 값이 아니므로 스캔 대상에서 뺀다.
# 나머지 필드는 전부 검사한다 — 메모에 옮겨 적은 번호가 진짜 위험이다.
def _scrub_place_url(text: str) -> str:
    data = json.loads(text)
    if isinstance(data, dict) and "플레이스URL" in data:
        data["플레이스URL"] = ""
        return json.dumps(data, ensure_ascii=False)
    return text


def test_seed_carries_no_phone_or_account_numbers(cmo_dir):
    for path, text in _seed_texts(cmo_dir):
        if path.parent.parent.name == "clients":
            text = _scrub_place_url(text)
        assert not PHONE_RE.search(text), f"{path.name}: 전화번호꼴 문자열이 있다"
        hit = _account_like(text)
        assert hit is None, f"{path.name}: 계좌번호꼴 숫자열이 있다 ({hit})"


def test_seed_carries_no_raw_chat_transcript(cmo_dir):
    """카톡 내보내기 특유의 머리말·타임스탬프가 들어오면 원문을 붙인 것이다."""
    for path, text in _seed_texts(cmo_dir):
        assert not KAKAO_EXPORT_RE.search(text), \
            f"{path.name}: 카톡 원문 형식이 그대로 들어 있다"


def test_seed_json_is_utf8_and_not_escaped(cmo_dir):
    """ensure_ascii=False 로 저장돼야 폴더를 열었을 때 한글이 보인다."""
    for path, text in _seed_texts(cmo_dir):
        assert "\\u" not in text, f"{path.name}: 한글이 \\uXXXX 로 이스케이프됐다"
        json.loads(text)  # 깨진 JSON 이면 여기서 죽는다


def test_every_client_records_where_it_came_from(cmo_dir):
    """상태·계약시작은 카톡에서 추정한 값이다. 근거가 메모에 남아야 한다.

    추정을 사실처럼 감추면 상무님이 틀린 값을 그대로 들고 나간다.
    """
    store = Store(cmo_dir / "data")
    for entry in store.clients():
        if entry["slug"] not in KAKAO_SEED_SLUGS:
            continue        # 패널로 등록한 매장. 카톡 근거가 없는 게 맞다
        client = store.client_read(entry["slug"])
        메모 = client.get("메모", "")
        assert "카톡 이력에서 등록" in 메모, f"{entry['slug']}: 출처가 없다"
        assert "마지막 대화" in 메모, f"{entry['slug']}: 상태 근거가 없다"
        assert re.fullmatch(r"\d{4}-\d{2}", client["계약시작"]), \
            f"{entry['slug']}: 계약시작이 YYYY-MM 이 아니다"


def test_pinned_products_exist_and_are_sellable(cmo_dir):
    """자주 쓰는 목록은 실존·판매중인 상품만 가리켜야 한다.

    id 를 오타 내거나 상품이 판매중지되면 서랍 맨 위가 조용히 빈다.
    """
    import re

    source = (cmo_dir / "app" / "drawer.js").read_text(encoding="utf-8")
    block = re.search(r"const FREQUENT = \[(.*?)\];", source, re.S)
    assert block, "drawer.js 에서 FREQUENT 목록을 못 찾았다"
    ids = re.findall(r'"([^"]+)"', block.group(1))

    store = Store(cmo_dir / "data")
    products = {p["id"]: p for p in store.products()}

    assert ids[0] == "네이버-서비스툴관리", "서비스툴관리가 맨 위여야 한다"
    for pid in ids:
        assert pid in products, f"없는 상품: {pid}"
        assert not products[pid]["판매중지"], f"판매중지 상품: {pid}"
