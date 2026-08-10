import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import pytest

from cmo.lib.storage import Store
from cmo.server import serve

CLIENT = {"이름": "하루인 인계점", "업종": "고깃집", "상태": "진행중", "스냅샷": []}
PLAN = {"월": "2026-09", "계약가": 1000000, "항목": [
    {"상품id": "네이버-블로그_일반_체험단", "수량": 10}]}
PRODUCTS = [{"id": "네이버-블로그_일반_체험단", "매체": "네이버",
             "상품명": "블로그 일반 체험단", "가격유형": "고정",
             "정가": 30000, "실비": 8000, "최소수량": 5, "단위": "팀",
             "판매중지": False, "고지사항": "", "프로세스": ""}]


@pytest.fixture
def server(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
    httpd = serve(0, Store(tmp_data), cmo_dir / "app")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + quote(path, safe="/?=&")) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _post(base, path, body):
    req = urllib.request.Request(
        base + quote(path, safe="/?=&"), data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_products_endpoint(server):
    status, body = _get(server, "/api/products")
    assert status == 200
    assert body[0]["상품명"] == "블로그 일반 체험단"


def test_clients_starts_empty(server):
    status, body = _get(server, "/api/clients")
    assert status == 200 and body == []


def test_client_save_and_read(server):
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    status, body = _get(server, "/api/clients/하루인_인계점")
    assert status == 200 and body["업종"] == "고깃집"


def test_plan_save_and_read(server):
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    status, body = _get(server, "/api/clients/하루인_인계점/plans/2026-09")
    assert status == 200 and body["계약가"] == 1000000


def test_plan_overwrite_returns_409(server):
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    assert exc.value.code == 409


def test_plan_overwrite_with_force_succeeds(server):
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    status, _ = _post(server, "/api/clients/하루인_인계점/plans/2026-09?force=1",
                      {**PLAN, "계약가": 2000000})
    assert status == 200
    _, body = _get(server, "/api/clients/하루인_인계점/plans/2026-09")
    assert body["계약가"] == 2000000


def test_plan_copy(server):
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    status, body = _post(server, "/api/clients/하루인_인계점/plans/2026-09/copy",
                         {"대상월": "2026-10"})
    assert status == 200 and body["월"] == "2026-10"


def test_summary_endpoint(server):
    status, body = _post(server, "/api/summary",
                         {"항목": PLAN["항목"], "계약가": 1000000})
    assert status == 200
    assert body["정가합"] == 300000
    assert body["실비합"] == 80000


def test_unknown_api_returns_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/없는것")
    assert exc.value.code == 404


def test_index_html_is_served(server):
    with urllib.request.urlopen(server + "/") as r:
        assert r.status == 200
        assert "text/html" in r.headers["Content-Type"]


def test_get_missing_client_returns_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/clients/존재안함")
    assert exc.value.code == 404


def test_path_traversal_slug_returns_400(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/clients/..")
    assert exc.value.code == 400


def test_summary_missing_product_id_key_returns_400(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/summary",
              {"항목": [{"수량": 1}], "계약가": 1000000})
    assert exc.value.code == 400


def test_malformed_json_body_returns_400(server):
    req = urllib.request.Request(
        server + "/api/summary", data=b"not json",
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def _raw_get(base, raw_path):
    """urllib 의 URL 정규화를 우회하기 위해 소켓 요청 줄을 직접 만든다.

    ../ 같은 경로 조각을 urlopen 에 그대로 넘기면 클라이언트가
    자체적으로 정규화해버려 서버가 받는 실제 바이트를 확인할 수 없다.
    """
    import socket
    from urllib.parse import urlsplit

    parts = urlsplit(base)
    with socket.create_connection((parts.hostname, parts.port), timeout=5) as sock:
        request = (
            f"GET {raw_path} HTTP/1.1\r\n"
            f"Host: {parts.hostname}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        sock.sendall(request)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    header_block, _, body = raw.partition(b"\r\n\r\n")
    status_line = header_block.split(b"\r\n", 1)[0]
    status = int(status_line.split(b" ")[1])
    return status, body


def test_static_dotdot_slash_path_cannot_read_data_dir(server):
    status, body = _raw_get(server, "/../data/products.json")
    assert status != 200
    assert b"\xeb\xb8\x94\xeb\xa1\x9c\xea\xb7\xb8" not in body  # UTF-8 "블로그"


def test_static_percent_encoded_dotdot_cannot_read_data_dir(server):
    status, body = _raw_get(server, "/%2e%2e%2fdata%2fproducts.json")
    assert status != 200
    assert b"\xeb\xb8\x94\xeb\xa1\x9c\xea\xb7\xb8" not in body


def test_static_backslash_dotdot_cannot_read_data_dir(server):
    status, body = _raw_get(server, "/..\\data\\products.json")
    assert status != 200
    assert b"\xeb\xb8\x94\xeb\xa1\x9c\xea\xb7\xb8" not in body


def test_static_cannot_escape_into_sibling_dir_sharing_name_prefix(tmp_data, tmp_path):
    """app_dir 경계 검사가 문자열 접두사가 아니라 실제 부모 관계인지 확인한다.

    app_dir 이름과 앞글자가 같은 형제 디렉토리(app_secret)가 있어도
    거기 담긴 파일을 정적 서빙으로 읽을 수 없어야 한다. 문자열
    startswith 비교였다면 이 테스트는 막지 못하고 통과(200 + 내용 누출)했을 것이다.
    """
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")

    sibling = tmp_path / "app_secret"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("TOP-SECRET-MARKER", encoding="utf-8")

    httpd = serve(0, Store(tmp_data), app_dir)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        status, body = _raw_get(base, "/../app_secret/secret.txt")
        assert status != 200
        assert b"TOP-SECRET-MARKER" not in body
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


NEW_CLIENT = {
    "이름": "우된장 교대본점", "플레이스URL": "", "업종": "", "지역": "",
    "평수": None, "객단가": None, "계약시작": "2026-09", "상태": "진행중",
    "추적키워드": [], "스냅샷": [], "메모": "",
}


def test_create_client_returns_201_with_slug(server):
    status, body = _post(server, "/api/clients", NEW_CLIENT)
    assert status == 201
    assert body["slug"] == "우된장_교대본점"


def test_created_client_is_readable(server):
    _post(server, "/api/clients", NEW_CLIENT)
    status, body = _get(server, "/api/clients/우된장_교대본점")
    assert status == 200
    assert body["이름"] == "우된장 교대본점"
    assert body["slug"] == "우된장_교대본점"


def test_created_client_appears_in_list(server):
    _post(server, "/api/clients", NEW_CLIENT)
    _, body = _get(server, "/api/clients")
    assert [c["slug"] for c in body] == ["우된장_교대본점"]


def test_create_client_without_name_returns_400(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/clients", {**NEW_CLIENT, "이름": "  "})
    assert exc.value.code == 400


def test_create_duplicate_client_returns_409(server):
    _post(server, "/api/clients", NEW_CLIENT)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/clients", NEW_CLIENT)
    assert exc.value.code == 409


def test_editing_an_existing_client_still_overwrites(server):
    """등록은 막지만 편집은 계속 덮어쓸 수 있어야 한다."""
    _post(server, "/api/clients", NEW_CLIENT)
    _post(server, "/api/clients/우된장_교대본점", {**NEW_CLIENT, "업종": "한식"})
    _, body = _get(server, "/api/clients/우된장_교대본점")
    assert body["업종"] == "한식"


def _fake_place(monkeypatch, calls):
    from cmo.lib import collect

    def fake(url, timeout_ms=15000):
        calls.append(url)
        return {"매장명": "우된장", "플레이스URL": url,
                "방문자리뷰": 312, "블로그리뷰": 14, "저장수": 88}

    monkeypatch.setattr(collect, "fetch_place", fake)


def _boom_place(monkeypatch):
    from cmo.lib import collect

    def fake(url, timeout_ms=15000):
        raise RuntimeError("네이버가 화면을 바꿨다")

    monkeypatch.setattr(collect, "fetch_place", fake)


MANUAL_BODY = {
    "slug": "우된장_교대본점",
    "순위": [{"키워드": "교대 된장찌개", "순위": 17}],
    "예상매출": {"월매출": 42000000, "상권순위": "상위 40%",
               "출처": "오픈업", "입력방식": "수동"},
}


def test_collect_without_flag_still_fetches_place(server, monkeypatch):
    """기존 호출은 그대로 돌아야 한다. 키가 없으면 True 로 본다."""
    calls = []
    _fake_place(monkeypatch, calls)
    _post(server, "/api/clients",
                 {**NEW_CLIENT, "플레이스URL": "https://m.place.naver.com/restaurant/1"})

    status, snapshot = _post(server, "/api/collect", MANUAL_BODY)

    assert status == 200
    assert len(calls) == 1
    assert snapshot["플레이스"]["블로그리뷰"] == 14


def test_collect_with_flag_false_skips_place(server, monkeypatch):
    calls = []
    _fake_place(monkeypatch, calls)
    _post(server, "/api/clients",
                 {**NEW_CLIENT, "플레이스URL": "https://m.place.naver.com/restaurant/1"})

    status, snapshot = _post(server, "/api/collect",
                             {**MANUAL_BODY, "플레이스수집": False})

    assert status == 200
    assert calls == [], "플레이스수집이 False 인데 네트워크를 탔다"
    assert snapshot["플레이스"] == {"방문자리뷰": None, "블로그리뷰": None, "저장수": None}


def test_collect_with_flag_false_keeps_manual_values(server, monkeypatch):
    """플레이스를 건너뛰어도 손으로 넣은 값은 그대로 저장돼야 한다."""
    _boom_place(monkeypatch)
    _post(server, "/api/clients", NEW_CLIENT)

    _post(server, "/api/collect", {**MANUAL_BODY, "플레이스수집": False})

    _, client = _get(server, "/api/clients/우된장_교대본점")
    snapshot = client["스냅샷"][0]
    assert snapshot["순위"][0]["순위"] == 17
    assert snapshot["예상매출"]["상권순위"] == "상위 40%"
    assert snapshot["수집시각"]


def test_collect_with_flag_false_works_without_place_url(server, monkeypatch):
    """URL 이 없어도 수동 지표만으로 저장된다. 400 이 아니다."""
    _boom_place(monkeypatch)
    _post(server, "/api/clients", NEW_CLIENT)  # 플레이스URL 빈 문자열

    status, _ = _post(server, "/api/collect", {**MANUAL_BODY, "플레이스수집": False})

    assert status == 200


def test_collect_failure_message_tells_how_to_escape(server, monkeypatch):
    """502 메시지가 막다른 길로 끝나면 안 된다."""
    _boom_place(monkeypatch)
    _post(server, "/api/clients",
                 {**NEW_CLIENT, "플레이스URL": "https://m.place.naver.com/restaurant/1"})

    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/collect", MANUAL_BODY)

    assert exc.value.code == 502
    detail = json.loads(exc.value.read().decode("utf-8"))
    assert "플레이스 함께 수집" in detail["오류"]


def test_collect_missing_url_message_tells_how_to_escape(server, monkeypatch):
    _fake_place(monkeypatch, [])
    _post(server, "/api/clients", NEW_CLIENT)  # URL 빈 문자열

    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/collect", MANUAL_BODY)

    assert exc.value.code == 400
    detail = json.loads(exc.value.read().decode("utf-8"))
    assert "플레이스 함께 수집" in detail["오류"]


def test_collect_appends_instead_of_replacing(server, monkeypatch):
    _boom_place(monkeypatch)
    _post(server, "/api/clients", NEW_CLIENT)

    _post(server, "/api/collect", {**MANUAL_BODY, "플레이스수집": False})
    _post(server, "/api/collect", {**MANUAL_BODY, "플레이스수집": False})

    _, client = _get(server, "/api/clients/우된장_교대본점")
    assert len(client["스냅샷"]) == 2


import base64

READING = {
    "플레이스ID": "1234567890", "플레이스명": "하루인 인계점",
    "카테고리": "양꼬치", "방문자리뷰": 312, "블로그리뷰": 14, "저장수": 88,
    "총키워드": 2, "TOP3": 1, "TOP10": 2,
    "순위": [{"키워드": "인계동 삼겹살", "순위": 3},
             {"키워드": "수원 고깃집", "순위": 7}],
}


def _fake_reader(reading):
    return lambda data, filename, api_key, model=None: dict(reading)


def test_read_doc_ready_reports_missing_key(server, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    status, body = _get(server, "/api/read-doc/ready")
    assert status == 200 and body["준비됨"] is False


def test_read_doc_returns_the_reading_without_saving(server, monkeypatch,
                                                     tmp_data):
    """판독은 화면을 채우기만 한다. 파일은 그대로여야 한다."""
    import cmo.server as server_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    monkeypatch.setattr(server_mod, "_read_document", _fake_reader(READING))
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    before = (tmp_data / "clients" / "하루인_인계점" / "client.json").read_text(
        encoding="utf-8")

    status, body = _post(server, "/api/read-doc", {
        "slug": "하루인_인계점", "파일명": "종합분석.pdf",
        "내용": base64.b64encode(b"%PDF-fake").decode("ascii")})

    assert status == 200
    assert body["판독"]["방문자리뷰"] == 312
    assert body["저장가능"] is True
    after = (tmp_data / "clients" / "하루인_인계점" / "client.json").read_text(
        encoding="utf-8")
    assert after == before, "판독이 파일을 건드렸다"


def test_read_doc_blocks_a_different_store(server, monkeypatch):
    import cmo.server as server_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    monkeypatch.setattr(server_mod, "_read_document",
                        _fake_reader({**READING, "플레이스명": "미친양꼬치 잠실점"}))
    _post(server, "/api/clients/하루인_인계점", CLIENT)

    status, body = _post(server, "/api/read-doc", {
        "slug": "하루인_인계점", "파일명": "종합분석.pdf",
        "내용": base64.b64encode(b"%PDF-fake").decode("ascii")})

    assert body["저장가능"] is False
    assert "미친양꼬치 잠실점" in body["불일치"]


def test_read_doc_warns_when_the_list_is_truncated(server, monkeypatch):
    import cmo.server as server_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    monkeypatch.setattr(server_mod, "_read_document",
                        _fake_reader({**READING, "총키워드": 48}))
    _post(server, "/api/clients/하루인_인계점", CLIENT)

    status, body = _post(server, "/api/read-doc", {
        "slug": "하루인_인계점", "파일명": "종합분석.pdf",
        "내용": base64.b64encode(b"%PDF-fake").decode("ascii")})

    assert any("48" in w for w in body["경고"])
    assert body["저장가능"] is True, "잘림은 저장을 막지 않는다"


def test_read_doc_without_key_is_rejected(server, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    try:
        _post(server, "/api/read-doc", {
            "slug": "하루인_인계점", "파일명": "a.pdf",
            "내용": base64.b64encode(b"x").decode("ascii")})
        assert False, "키 없이 통과했다"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_apply_saves_snapshot_and_fills_empty_fields(server, tmp_data):
    _post(server, "/api/clients/하루인_인계점", {**CLIENT, "플레이스URL": "",
                                                 "업종": ""})
    status, _ = _post(server, "/api/read-doc/apply",
                      {"slug": "하루인_인계점", "판독": READING})
    assert status == 200

    saved = json.loads((tmp_data / "clients" / "하루인_인계점" / "client.json")
                       .read_text(encoding="utf-8"))
    assert len(saved["스냅샷"]) == 1
    assert saved["스냅샷"][0]["플레이스"]["방문자리뷰"] == 312
    assert saved["스냅샷"][0]["순위요약"]["총키워드"] == 2
    assert saved["플레이스URL"].endswith("/1234567890/home")
    assert saved["업종"] == "양꼬치"


def test_apply_checks_the_store_again_on_the_server(server):
    """화면이 막았더라도 서버가 최종 관문이다."""
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    try:
        _post(server, "/api/read-doc/apply",
              {"slug": "하루인_인계점",
               "판독": {**READING, "플레이스명": "미친양꼬치 잠실점"}})
        assert False, "다른 매장 판독이 저장됐다"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        assert "미친양꼬치 잠실점" in json.loads(exc.read().decode("utf-8"))["오류"]
