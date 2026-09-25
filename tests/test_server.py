import inspect
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime
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
    """판독 한 겹을 갈아 끼운다.

    이제 캡처 여러 장을 받는다 — `[(바이트, 파일명)]` 이 첫 인자다.
    """
    return lambda files, api_key, model=None: dict(reading)


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


OPENUB_READING = {
    "매장명": "하루인 인계점",
    "기준월": 6,
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

OPENUB_SLUG = "하루인_인계점"


def _capture(name="a.png"):
    return {"파일명": name,
            "내용": base64.b64encode(b"\x89PNG").decode("ascii")}


def _fake_captures(reading):
    def fake(files, api_key):
        return dict(reading)
    return fake


def _post_error(base, path, body):
    """오류 응답은 urllib 가 예외로 올린다. 코드와 본문을 함께 본다."""
    try:
        _post(base, path, body)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))
    raise AssertionError("오류가 나야 하는데 성공했다")


def test_read_openub_returns_the_reading_without_saving(server, monkeypatch,
                                                        tmp_data):
    """판독은 화면만 채운다. 파일은 그대로여야 한다."""
    import cmo.server as server_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    monkeypatch.setattr(server_mod, "_read_captures",
                        _fake_captures(OPENUB_READING))
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)
    before = (tmp_data / "clients" / OPENUB_SLUG / "client.json").read_text(
        encoding="utf-8")

    status, body = _post(server, "/api/read-openub",
                         {"slug": OPENUB_SLUG, "캡처": [_capture()]})

    assert status == 200
    assert body["저장가능"] is True
    assert body["판독"]["매출하한"] == 46000000
    after = (tmp_data / "clients" / OPENUB_SLUG / "client.json").read_text(
        encoding="utf-8")
    assert after == before, "판독이 파일을 건드렸다"


def test_read_openub_needs_a_key(server, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    status, body = _post_error(server, "/api/read-openub",
                               {"slug": OPENUB_SLUG, "캡처": [_capture()]})

    assert status == 400
    assert "키" in body["오류"]


def test_read_openub_blocks_a_different_store(server, monkeypatch):
    """오픈업 캡처도 파일명이 캡처 시각뿐이라 남의 매장 것을 넣기 쉽다."""
    import cmo.server as server_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    monkeypatch.setattr(server_mod, "_read_captures",
                        _fake_captures({**OPENUB_READING,
                                        "매장명": "미친양꼬치 잠실점"}))
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    status, body = _post(server, "/api/read-openub",
                         {"slug": OPENUB_SLUG, "캡처": [_capture()]})

    assert body["저장가능"] is False
    assert "미친양꼬치 잠실점" in body["불일치"]


def test_apply_openub_keeps_one_entry_per_month(server, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    _post(server, "/api/read-openub/apply",
          {"slug": OPENUB_SLUG, "판독": dict(OPENUB_READING)})
    _post(server, "/api/read-openub/apply",
          {"slug": OPENUB_SLUG, "판독": dict(OPENUB_READING)})

    status, saved = _get(server, f"/api/clients/{OPENUB_SLUG}")
    assert len(saved["오픈업"]) == 1
    assert saved["오픈업"][0]["매출"] == {"하한": 46000000, "상한": 56000000}
    assert saved["오픈업"][0]["기준월"].endswith("-06")


def test_apply_openub_does_not_touch_snapshots(server, monkeypatch):
    """이번 설계의 핵심 — 애드로그 값이 살아남는다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    client = {**CLIENT,
              "스냅샷": [{"수집시각": "2026-08-12T08:00:00",
                          "플레이스": {"방문자리뷰": 1082}}]}
    _post(server, f"/api/clients/{OPENUB_SLUG}", client)

    _post(server, "/api/read-openub/apply",
          {"slug": OPENUB_SLUG, "판독": dict(OPENUB_READING)})

    status, saved = _get(server, f"/api/clients/{OPENUB_SLUG}")
    assert saved["스냅샷"][0]["플레이스"]["방문자리뷰"] == 1082
    assert saved["오픈업"][0]["기준월"].endswith("-06")


def test_apply_openub_checks_the_store_again(server, monkeypatch):
    """화면이 막았더라도 서버가 최종 관문이다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    status, body = _post_error(server, "/api/read-openub/apply",
                               {"slug": OPENUB_SLUG,
                                "판독": {**OPENUB_READING,
                                         "매장명": "미친양꼬치 잠실점"}})

    assert status == 400
    assert "미친양꼬치 잠실점" in body["오류"]
    _, saved = _get(server, f"/api/clients/{OPENUB_SLUG}")
    assert "오픈업" not in saved


def test_apply_openub_blocks_a_reading_without_a_month(server, monkeypatch):
    """기준월 없이 저장하면 어느 달 값인지 영영 알 수 없다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    status, body = _post_error(server, "/api/read-openub/apply",
                               {"slug": OPENUB_SLUG,
                                "판독": {**OPENUB_READING, "기준월": None}})

    assert status == 400
    _, saved = _get(server, f"/api/clients/{OPENUB_SLUG}")
    assert "오픈업" not in saved


def test_apply_openub_rechecks_the_shape(server, monkeypatch):
    """화면이 보낸 dict 를 그대로 믿고 저장하지 않는다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    status, body = _post_error(server, "/api/read-openub/apply",
                               {"slug": OPENUB_SLUG,
                                "판독": {"매장명": "하루인 인계점", "기준월": 6}})

    assert status == 400
    _, saved = _get(server, f"/api/clients/{OPENUB_SLUG}")
    assert "오픈업" not in saved


def test_read_openub_blocks_too_many_captures(server, monkeypatch):
    """화면에서 먼저 끊지만 서버도 같은 상한을 본다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "키")
    _post(server, f"/api/clients/{OPENUB_SLUG}", CLIENT)

    status, body = _post_error(server, "/api/read-openub",
                               {"slug": OPENUB_SLUG,
                                "캡처": [_capture(f"{i}.png") for i in range(7)]})

    assert status == 400


def test_quote_endpoint_makes_a_pdf(server, tmp_data):
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)

    status, body = _post(server, "/api/quote",
                         {"slug": "하루인_인계점", "월": "2026-09"})

    assert status == 200
    assert body["경로"].endswith("견적서.pdf")
    assert Path(body["경로"]).exists()


def test_quote_without_a_contract_price_is_blocked(server):
    """0원짜리 견적서가 고객에게 가는 게 최악이다."""
    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09",
          {**PLAN, "계약가": 0})

    status, body = _post_error(server, "/api/quote",
                               {"slug": "하루인_인계점", "월": "2026-09"})

    assert status == 400
    assert "계약가" in body["오류"]


# ── 제안서 응답이 빠진 진단 장을 알린다 ────────────────────────
#
# 자료 없는 매장의 제안서가 4장으로 조용히 나갔고, 뽑은 사람은 사장님께
# 보내기 직전에야 알았다. 경고를 응답에 실어 화면이 그 자리에서 띄운다.

def test_proposal_response_warns_about_missing_diagnosis_pages(server,
                                                               monkeypatch):
    """PDF 는 찍지 않는다 — 여기서 보는 건 경고가 실려 오는가 하나다."""
    import cmo.build_pdf
    monkeypatch.setattr(cmo.build_pdf, "build",
                        lambda payload, out, **kw: out)

    _post(server, "/api/clients/하루인_인계점", CLIENT)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    status, body = _post(server, "/api/proposal",
                         {"slug": "하루인_인계점", "월": "2026-09"})

    assert status == 200
    assert body["경로"]
    붙인것 = " ".join(body["경고"])
    assert "이 가게에 오는 손님" in 붙인것
    assert "검색에서의 자리" in 붙인것
    assert "순위 변동과 이번 달 처방" in 붙인것


def test_proposal_response_is_quiet_when_nothing_is_missing(server,
                                                            monkeypatch):
    """늘 짖는 경고는 아무도 안 본다."""
    import cmo.build_pdf
    monkeypatch.setattr(cmo.build_pdf, "build",
                        lambda payload, out, **kw: out)

    client = dict(CLIENT, 스냅샷=[{
        "수집시각": "2026-08-14T00:26:31",
        "플레이스": {"방문자리뷰": 1082, "블로그리뷰": 170, "저장수": 100},
        "순위": [{"키워드": "인계동맛집", "순위": 3, "순위권밖": False,
                 "조회수": 4800, "비교순위": 7}],
        "진단": {"기준일": "08-13", "비교일": "07-30",
                "리뷰": {"방문자": [], "블로그": []}},
    }], 오픈업=[{"기준월": "2026-07",
                "매출": {"하한": 46000000, "상한": 56000000},
                "성별최다": {"값": "남성", "비율": 62},
                "연령최다": {"값": "남성 30대", "비율": 28},
                "요일최다": {"값": "금", "비율": 22},
                "시간대최다": {"값": "밤", "비율": 45}, "평일비율": 64}])
    _post(server, "/api/clients/하루인_인계점", client)
    _post(server, "/api/clients/하루인_인계점/plans/2026-09", PLAN)
    _, body = _post(server, "/api/proposal",
                    {"slug": "하루인_인계점", "월": "2026-09"})

    assert body["경고"] == []


# --- 애드로그 ---------------------------------------------------------

ADLOG_KEYWORDS = [
    {"api_no": 1, "place_id": "2069074461", "place_name": "미친양꼬치 잠실점",
     "keyword": "잠실새내 맛집", "month_count": 22160, "group_name": "기본"},
    {"api_no": 2, "place_id": "9999", "place_name": "남의 가게",
     "keyword": "남의 키워드", "month_count": 100, "group_name": "기본"},
]
ADLOG_DETAIL = [
    {"api_no": 1, "rank_date": "2026-09-19", "rank_num": 26,
     "visit_review_count": 895, "blog_review_count": 619,
     "save_count": "8,000+", "place_count": 2520, "total_month_count": 22160},
]
LINKED = {"이름": "잠실점", "애드로그": {
    "플레이스ID": "2069074461",
    "키워드": [{"api_no": 1, "keyword": "잠실새내 맛집"}]}}


def _adlog_env(monkeypatch):
    monkeypatch.setenv("ADLOG_API_KEY", "키값")
    monkeypatch.setenv("ADLOG_USER_ID", "테스트아이디")


def test_adlog_places_lists_registered_keywords(server, monkeypatch):
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_keywords", lambda key, uid: ADLOG_KEYWORDS)

    status, got = _get(server, "/api/adlog/places")

    assert status == 200
    assert len(got["items"]) == 2
    assert got["갱신시각"]


def test_adlog_places_uses_the_cache_on_the_second_call(server, monkeypatch):
    """목록 한 번에 20 회를 부른다. 열 때마다 부르면 한도를 갉는다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    부른횟수 = []

    def counting(key, uid):
        부른횟수.append(1)
        return ADLOG_KEYWORDS

    monkeypatch.setattr(srv, "_adlog_keywords", counting)

    _get(server, "/api/adlog/places")
    _get(server, "/api/adlog/places")

    assert len(부른횟수) == 1


def test_adlog_places_refresh_skips_the_cache(server, monkeypatch):
    from cmo import server as srv

    _adlog_env(monkeypatch)
    부른횟수 = []

    def counting(key, uid):
        부른횟수.append(1)
        return ADLOG_KEYWORDS

    monkeypatch.setattr(srv, "_adlog_keywords", counting)

    _get(server, "/api/adlog/places")
    _get(server, "/api/adlog/places?refresh=1")

    assert len(부른횟수) == 2


def test_adlog_places_without_key_says_what_to_do(server, monkeypatch):
    monkeypatch.delenv("ADLOG_API_KEY", raising=False)
    monkeypatch.delenv("ADLOG_USER_ID", raising=False)

    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/adlog/places")

    assert exc.value.code == 400
    assert "ADLOG_API_KEY" in json.loads(exc.value.read())["오류"]


def test_adlog_sync_writes_the_ledger(server, tmp_data, monkeypatch):
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200
    assert got["갱신"] == 1
    원장 = store.ranks_read("잠실점")
    assert 원장["키워드"]["잠실새내 맛집"]["순위"] == {"2026-09-19": 26}
    assert 원장["플레이스ID"] == "2069074461"


def test_adlog_sync_appends_one_snapshot(server, tmp_data, monkeypatch):
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(LINKED)

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    스냅샷 = store.client_read("잠실점")["스냅샷"]
    assert len(스냅샷) == 1
    줄 = 스냅샷[0]["순위"][0]
    assert 줄["키워드"] == "잠실새내 맛집"
    assert 줄["순위"] == 26
    assert 줄["순위권밖"] is False
    assert 줄["조회수"] == 22160
    assert 스냅샷[0]["플레이스"]["저장수"] == 8000


def test_adlog_sync_twice_keeps_one_ledger_entry(server, tmp_data, monkeypatch):
    """같은 날 두 번 눌러도 원장은 한 벌이다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(LINKED)

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})
    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    원장 = store.ranks_read("잠실점")
    assert 원장["키워드"]["잠실새내 맛집"]["순위"] == {"2026-09-19": 26}


def test_adlog_sync_of_an_unlinked_client_says_so(server, tmp_data, monkeypatch):
    _adlog_env(monkeypatch)
    Store(tmp_data).client_create({"이름": "농우본"})

    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/adlog/sync", {"slug": "농우본"})

    assert exc.value.code == 400
    assert "애드로그" in json.loads(exc.value.read())["오류"]


def test_adlog_sync_without_values_adds_no_snapshot(server, tmp_data, monkeypatch):
    """순위가 안 잡힌 새 키워드만 걸린 매장. 껍데기를 안 쌓는다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: [])

    store = Store(tmp_data)
    store.client_create(LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert got["스냅샷"] is None
    assert store.client_read("잠실점").get("스냅샷") in (None, [])


def test_adlog_sync_keeps_going_when_one_keyword_fails(server, tmp_data,
                                                         monkeypatch):
    """열 개 중 하나 때문에 아홉 개를 못 보면 그날 미팅 자료가 통째로 빈다."""
    from cmo import server as srv
    from cmo.lib.adlog import AdlogError

    _adlog_env(monkeypatch)

    def 하나만_실패(key, uid, api_no):
        if api_no == 2:
            raise AdlogError("조회할 키워드 번호가 없습니다.")
        return ADLOG_DETAIL

    monkeypatch.setattr(srv, "_adlog_ranks", 하나만_실패)

    store = Store(tmp_data)
    store.client_create({"이름": "잠실점", "애드로그": {
        "플레이스ID": "2069074461",
        "키워드": [{"api_no": 1, "keyword": "잠실새내 맛집"},
                   {"api_no": 2, "keyword": "안 잡히는 키워드"}]}})

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200
    assert got["갱신"] == 1
    assert got["경고"]
    원장 = store.ranks_read("잠실점")
    assert "잠실새내 맛집" in 원장["키워드"]
    assert "안 잡히는 키워드" not in 원장["키워드"]


def test_adlog_sync_says_how_many_it_was_asked_for(server, tmp_data,
                                                    monkeypatch):
    """절반 성공한 갱신은 못 받은 키워드가 이번 제안서에서 통째로 빠진다.

    화면이 그 말을 하려면 몇 개 중 몇 개를 받았는지 서버가 알려줘야
    한다. 지금은 받은 개수만 가서, 쉰 개 중 셋만 받은 것과 셋을 다
    받은 것이 화면에서 같아 보인다.
    """
    from cmo import server as srv
    from cmo.lib.adlog import AdlogError

    _adlog_env(monkeypatch)

    def 둘째는_실패(key, uid, api_no):
        if api_no == 2:
            raise AdlogError("조회할 키워드 번호가 없습니다.")
        return ADLOG_DETAIL

    monkeypatch.setattr(srv, "_adlog_ranks", 둘째는_실패)

    store = Store(tmp_data)
    store.client_create(_HALF_LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200
    assert got["요청"] == 2
    assert got["갱신"] == 1


def test_adlog_sync_asked_matches_got_when_nothing_failed(server, tmp_data,
                                                           monkeypatch):
    """다 받은 날은 두 수가 같다 — 화면이 「몇 개 중」을 안 붙이는 근거다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200
    assert got["요청"] == got["갱신"] == 1


def test_adlog_error_does_not_leak_the_original(server, tmp_data, monkeypatch):
    """예외 원문에 URL·키가 섞인다. 화면에는 사람 말만 간다."""
    from cmo import server as srv
    from cmo.lib.adlog import AdlogError

    _adlog_env(monkeypatch)

    def boom(key, uid, no):
        raise AdlogError("이 PC 의 IP 를 애드로그에 등록해야 합니다.")

    monkeypatch.setattr(srv, "_adlog_ranks", boom)
    Store(tmp_data).client_create(LINKED)

    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert exc.value.code == 502
    본문 = exc.value.read().decode("utf-8")
    assert "IP 를 애드로그에 등록" in json.loads(본문)["오류"]
    assert "키값" not in 본문


def test_adlog_sync_of_a_missing_client_returns_404(server, monkeypatch):
    _adlog_env(monkeypatch)

    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/api/adlog/sync", {"slug": "없는가게"})

    assert exc.value.code == 404


def test_adlog_sync_twice_in_a_day_keeps_one_snapshot(server, tmp_data, monkeypatch):
    """인수 기준 3. 원장만이 아니라 스냅샷도 한 건이어야 한다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(LINKED)

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})
    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert len(store.client_read("잠실점")["스냅샷"]) == 1


def test_adlog_sync_does_not_replace_a_capture_snapshot(server, tmp_data, monkeypatch):
    """캡처로 넣은 스냅샷은 애드로그가 덮지 않는다. 출처가 다르다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create({**LINKED, "스냅샷": [
        {"수집시각": "2026-09-19T09:00:00",
         "플레이스": {"방문자리뷰": 1, "블로그리뷰": 1, "저장수": 1},
         "순위": [{"키워드": "캡처키워드", "순위": 3}]},
    ]})

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    스냅샷 = store.client_read("잠실점")["스냅샷"]
    assert len(스냅샷) == 2
    assert 스냅샷[0]["순위"][0]["키워드"] == "캡처키워드"


def test_adlog_sync_counts_only_linked_keywords(server, tmp_data, monkeypatch):
    """원장에 옛 매장 키워드가 남아 있어도 스냅샷에는 연결된 것만 든다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(LINKED)
    store.ranks_write("잠실점", {
        "플레이스ID": "2069074461",
        "키워드": {"남의 키워드": {"api_no": 999, "월검색수": 1,
                                  "순위": {"2026-09-19": 1}}},
        "매장지표": {}})

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    snap = store.client_read("잠실점")["스냅샷"][-1]
    assert [r["키워드"] for r in snap["순위"]] == ["잠실새내 맛집"]


def test_adlog_sync_stops_on_an_account_level_error(server, tmp_data, monkeypatch):
    """4004(IP 미등록)는 다음 키워드를 불러도 같은 답이다. 바로 멈춘다."""
    from cmo import server as srv
    from cmo.lib.adlog import AdlogError

    _adlog_env(monkeypatch)
    부른횟수 = []

    def ip_막힘(key, uid, api_no):
        부른횟수.append(api_no)
        raise AdlogError("이 PC 의 IP 를 애드로그에 등록해야 합니다.")

    monkeypatch.setattr(srv, "_adlog_ranks", ip_막힘)

    store = Store(tmp_data)
    store.client_create({"이름": "잠실점", "애드로그": {
        "플레이스ID": "2069074461",
        "키워드": [{"api_no": 1, "keyword": "가"}, {"api_no": 2, "keyword": "나"},
                   {"api_no": 3, "keyword": "다"}]}})

    with pytest.raises(urllib.error.HTTPError):
        _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert len(부른횟수) == 1


def test_adlog_sync_stops_after_a_timeout(server, tmp_data, monkeypatch):
    """애드로그가 느린 날은 키워드마다 느리다. 하나에 63초까지 가는데
    이 서버는 요청을 하나씩 처리한다 — 57개면 한 시간을 멈춘다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    부른횟수 = []

    def 느림(key, uid, api_no):
        부른횟수.append(api_no)
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(srv, "_adlog_ranks", 느림)

    store = Store(tmp_data)
    store.client_create({"이름": "잠실점", "애드로그": {
        "플레이스ID": "2069074461",
        "키워드": [{"api_no": 1, "keyword": "가"}, {"api_no": 2, "keyword": "나"},
                   {"api_no": 3, "keyword": "다"}]}})

    with pytest.raises(urllib.error.HTTPError):
        _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert len(부른횟수) == 1


def test_adlog_sync_sleeps_between_keywords(server, tmp_data, monkeypatch):
    """애드로그가 과도한 트래픽을 사전 안내 없이 차단한다고 경고한다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    잔횟수 = []
    monkeypatch.setattr(srv.time, "sleep", lambda s: 잔횟수.append(s))
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create({"이름": "잠실점", "애드로그": {
        "플레이스ID": "2069074461",
        "키워드": [{"api_no": 1, "keyword": "가"}, {"api_no": 2, "keyword": "나"}]}})

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert 잔횟수, "키워드 사이에 쉬지 않았다"


def test_relinking_a_client_archives_the_old_ledger(server, tmp_data):
    """플레이스ID 가 바뀌면 옛 원장을 옆으로 치운다.

    화면의 「다시 잇기」는 `linkAdlog` 가 `POST /api/clients/{slug}` 로
    새 애드로그 블록을 보내는 경로를 쓴다 — 그 자리가 옛 원장을
    보관하는 곳이다.
    """
    store = Store(tmp_data)
    store.client_create({"이름": "잠실점", "애드로그": {
        "플레이스ID": "옛날", "키워드": [{"api_no": 1, "keyword": "가"}]}})
    store.ranks_write("잠실점", {"플레이스ID": "옛날", "키워드": {"가": {}}})

    _post(server, "/api/clients/잠실점", {"이름": "잠실점", "애드로그": {
        "플레이스ID": "새것", "키워드": [{"api_no": 2, "keyword": "나"}]}})

    assert store.ranks_read("잠실점") == {}
    보관 = list((tmp_data / "clients" / "잠실점").glob("ranks-옛날-*.json"))
    assert len(보관) == 1


def test_adlog_sync_after_a_same_day_capture_keeps_order(server, tmp_data, monkeypatch):
    """오전에 이미 애드로그로 갱신했고, 낮에 캡처를 넣은 뒤 오후에 다시
    갱신해도 최신 갱신이 마지막에 와야 한다.

    자리를 바꿔 끼우면(리스트를 거꾸로 훑어 첫 자리를 덮으면) 방금 받은
    순위가 그사이에 낀 캡처보다 앞자리로 간다. `paintLastSnapshot`·
    `_latest_snapshot` 은 마지막 스냅샷을 보므로 그러면 옛 캡처가
    최신으로 읽힌다.
    """
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: ADLOG_DETAIL)

    오늘 = datetime.now().strftime("%Y-%m-%d")
    store = Store(tmp_data)
    store.client_create({**LINKED, "스냅샷": [
        {"수집시각": f"{오늘}T09:00:00", "출처": "애드로그",
         "플레이스": {"방문자리뷰": 1, "블로그리뷰": 1, "저장수": 1},
         "순위": [{"키워드": "잠실새내 맛집", "순위": 30}]},
        {"수집시각": f"{오늘}T11:00:00",
         "플레이스": {"방문자리뷰": 2, "블로그리뷰": 2, "저장수": 2},
         "순위": [{"키워드": "캡처키워드", "순위": 3}]},
    ]})

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    스냅샷 = store.client_read("잠실점")["스냅샷"]
    assert len(스냅샷) == 2
    assert 스냅샷[-1].get("출처") == "애드로그"
    assert 스냅샷[-1]["순위"][0]["순위"] == 26  # 방금 갱신한 값(ADLOG_DETAIL)
    assert 스냅샷[0]["순위"][0]["키워드"] == "캡처키워드"


def test_adlog_sync_stops_after_a_timeout_but_keeps_what_it_got(server, tmp_data,
                                                                  monkeypatch):
    """하나는 성공하고 둘째에서 타임아웃이 나면, 받은 것까지는 저장하고
    경고를 함께 돌려준다. 세 번째는 부르지 않는다."""
    from cmo import server as srv

    _adlog_env(monkeypatch)
    부른횟수 = []

    def 하나는_성공_둘째는_타임아웃(key, uid, api_no):
        부른횟수.append(api_no)
        if api_no == 2:
            raise TimeoutError("The read operation timed out")
        return ADLOG_DETAIL

    monkeypatch.setattr(srv, "_adlog_ranks", 하나는_성공_둘째는_타임아웃)

    store = Store(tmp_data)
    store.client_create({"이름": "잠실점", "애드로그": {
        "플레이스ID": "2069074461",
        "키워드": [{"api_no": 1, "keyword": "잠실새내 맛집"},
                   {"api_no": 2, "keyword": "나"}, {"api_no": 3, "keyword": "다"}]}})

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200
    assert got["갱신"] == 1
    assert got["경고"]
    assert len(부른횟수) == 2
    원장 = store.ranks_read("잠실점")
    assert "잠실새내 맛집" in 원장["키워드"]


# ── 조회 실패와 30위 밖을 가른다 ───────────────────────────────
#
# 애드로그는 30위 밖을 `rank_num: 0` 이나 `null` 로 주지 않는다. 응답
# 자체를 안 준다(`code: 2001`). `_items()` 가 그걸 빈 목록으로 돌려주고
# `merge_ranks` 는 거기서 아무것도 안 쌓으므로, **원장만 봐서는 「조회
# 실패」와 「30위 밖」이 구분되지 않는다.** 그래서 서버가 이번에 답을
# 받은 키워드 목록을 따로 들고 스냅샷에 넘긴다.

_HALF_LINKED = {"이름": "잠실점", "애드로그": {
    "플레이스ID": "2069074461",
    "키워드": [{"api_no": 1, "keyword": "잠실양꼬치", "month_count": 3000},
               {"api_no": 2, "keyword": "잠실새내맛집", "month_count": 22160}]}}


def test_a_keyword_that_never_answered_gets_no_row(server, tmp_data, monkeypatch):
    """못 물어본 키워드를 「순위권밖」으로 세우면 안 된다.

    타임아웃 한 번에 사흘 전 2위였던 키워드가 30위 밖으로 찍힌다.
    이번 스냅샷에는 그 키워드가 아예 없는 것이 맞다.
    """
    from cmo import server as srv

    _adlog_env(monkeypatch)

    def 둘째는_타임아웃(key, uid, api_no):
        if api_no == 2:
            raise TimeoutError("The read operation timed out")
        return ADLOG_DETAIL

    monkeypatch.setattr(srv, "_adlog_ranks", 둘째는_타임아웃)

    store = Store(tmp_data)
    store.client_create(_HALF_LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200 and got["경고"]
    snap = store.client_read("잠실점")["스냅샷"][-1]
    assert [r["키워드"] for r in snap["순위"]] == ["잠실양꼬치"]
    assert snap["순위요약"]["총키워드"] == 1


def test_a_keyword_with_no_data_still_gets_an_outside_row(server, tmp_data,
                                                          monkeypatch):
    """30위 밖(2001)은 조회 성공이다. 줄을 만들고 조회수를 함께 싣는다.

    이 줄이 빠지면 「월 22,160번 검색되는 곳에서 아직 안 보입니다」라는
    가장 센 근거가 사라진다. 실패와 달리 여기서는 답을 받았다.
    """
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(
        srv, "_adlog_ranks",
        lambda key, uid, api_no: [] if api_no == 2 else ADLOG_DETAIL)

    store = Store(tmp_data)
    store.client_create(_HALF_LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200 and got["경고"] is None
    줄별 = {r["키워드"]: r
            for r in store.client_read("잠실점")["스냅샷"][-1]["순위"]}
    밖 = 줄별["잠실새내맛집"]
    assert 밖["순위권밖"] is True
    assert 밖["순위"] is None
    assert 밖["조회수"] == 22160


def test_a_keyword_that_answered_with_no_rank_today_is_outside(
        server, tmp_data, monkeypatch):
    """애드로그가 오늘 `rank_num: null` 로 답하면 30위 밖이다.

    이건 조회 실패가 아니다 — 물어봤고 답도 받았다. 며칠 전 순위를 오늘
    것으로 실으면 9/24 자 종이에 「3위」가 찍히고 TOP 3 에도 센다.
    """
    from cmo import server as srv

    _adlog_env(monkeypatch)
    monkeypatch.setattr(srv, "_adlog_ranks", lambda key, uid, no: [
        {"api_no": 1, "rank_date": "2026-09-20", "rank_num": 3,
         "visit_review_count": 895, "blog_review_count": 619,
         "save_count": "8,000+", "place_count": 2520,
         "total_month_count": 22160},
        {"api_no": 1, "rank_date": "2026-09-24", "rank_num": None,
         "visit_review_count": 900, "blog_review_count": 620,
         "save_count": "8,100+", "place_count": 2520,
         "total_month_count": 22160},
    ])

    store = Store(tmp_data)
    store.client_create(LINKED)

    status, got = _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    assert status == 200 and got["경고"] is None
    snap = store.client_read("잠실점")["스냅샷"][-1]
    줄 = snap["순위"][0]
    assert 줄["순위"] is None
    assert 줄["순위권밖"] is True
    assert snap["순위요약"]["TOP3"] == 0
    assert snap["진단"]["기준일"] == "2026-09-24"


def test_a_half_failed_sync_never_calls_a_ranked_keyword_invisible(
        server, tmp_data, monkeypatch):
    """사장님이 가장 먼저 읽는 문장이 타임아웃 한 번에 거짓말하면 안 된다."""
    from cmo import server as srv
    from cmo.lib.proposal import build_payload

    _adlog_env(monkeypatch)

    def 둘째는_타임아웃(key, uid, api_no):
        if api_no == 2:
            raise TimeoutError("The read operation timed out")
        return ADLOG_DETAIL

    monkeypatch.setattr(srv, "_adlog_ranks", 둘째는_타임아웃)

    store = Store(tmp_data)
    store.client_create({**_HALF_LINKED, "스냅샷": [{
        "수집시각": "2026-09-19T10:00:00",
        "플레이스": {"방문자리뷰": 895, "블로그리뷰": 619, "저장수": 8000},
        "순위": [{"키워드": "잠실새내맛집", "순위": 2, "순위권밖": False,
                  "조회수": 22160, "비교순위": 5},
                 {"키워드": "잠실양꼬치", "순위": 1, "순위권밖": False,
                  "조회수": 3000, "비교순위": 1}],
        "순위요약": {"총키워드": 2, "TOP3": 2, "TOP10": 2},
        "진단": {"기준일": "2026-09-19", "비교일": "2026-08-19"},
    }]})

    _post(server, "/api/adlog/sync", {"slug": "잠실점"})

    검색 = build_payload(store.client_read("잠실점"),
                         PLAN, PRODUCTS)["진단자료"]["검색"]
    assert "잠실새내맛집" not in (검색["헤드라인"] or "")
    표 = {r["키워드"]: r["순위표시"] for r in (검색["기회표"] or [])}
    assert 표.get("잠실새내맛집") != "30위 밖"


# ── .env 로더 ─────────────────────────────────────────────────
#
# `.env.example` 이 "옆에 .env 를 만들어 넣으라" 고 시키는데 그 파일을
# 읽는 코드가 없었다. 여는 법은 `run_cmo.bat` 더블클릭 하나뿐이라 셸이
# 없고, 그래서 넣었다고 믿는 사람에게 「환경변수에 넣으십시오」가 떴다.


@pytest.fixture
def 빈환경(monkeypatch):
    """`os.environ` 을 사본으로 갈아 끼우고 애드로그 키를 비운다.

    로더가 넣은 값이 다른 시험으로 새지 않고, 개발자 PC 의 실제
    환경변수가 결과를 가리지도 않는다.
    """
    사본 = {k: v for k, v in os.environ.items()
            if k not in ("ADLOG_API_KEY", "ADLOG_USER_ID")}
    monkeypatch.setattr(os, "environ", 사본)
    return 사본


def _env_file(tmp_path, 내용: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(내용, encoding="utf-8")
    return path


def test_load_env_fills_a_missing_value(tmp_path, 빈환경):
    from cmo import server as srv

    srv.load_env(_env_file(tmp_path, "ADLOG_API_KEY=키값\nADLOG_USER_ID=아이디\n"))

    assert os.environ["ADLOG_API_KEY"] == "키값"
    assert os.environ["ADLOG_USER_ID"] == "아이디"


def test_load_env_does_not_overwrite_what_is_already_set(tmp_path, 빈환경):
    """`setx`·CI·`monkeypatch` 가 계속 이겨야 한다.

    이걸 어기면 스위트가 여럿 깨진다 — 키를 지우고 400 을 보는 시험들이
    파일에서 되살아난 값을 집는다.
    """
    빈환경["ADLOG_API_KEY"] = "이미있는값"

    srv_load(tmp_path, "ADLOG_API_KEY=파일값\nADLOG_USER_ID=아이디\n")

    assert os.environ["ADLOG_API_KEY"] == "이미있는값"
    assert os.environ["ADLOG_USER_ID"] == "아이디"


def srv_load(tmp_path, 내용: str) -> None:
    from cmo import server as srv

    srv.load_env(_env_file(tmp_path, 내용))


def test_load_env_strips_a_bom_and_crlf_and_quotes(tmp_path, 빈환경):
    """메모장으로 저장하면 BOM 이 붙어 이름이 `\ufeffADLOG_API_KEY` 가 된다.

    그러면 "넣었는데 안 된다" 가 그대로 재발한다. 줄 끝 `\r` 과 값을
    감싼 따옴표도 같이 벗긴다.
    """
    from cmo import server as srv

    path = tmp_path / ".env"
    path.write_bytes('\ufeffADLOG_API_KEY="키값"\r\nADLOG_USER_ID=\'아이디\'\r\n'
                     .encode("utf-8"))

    srv.load_env(path)

    assert os.environ["ADLOG_API_KEY"] == "키값"
    assert os.environ["ADLOG_USER_ID"] == "아이디"


def test_load_env_skips_comments_and_lines_without_an_equals(tmp_path, 빈환경):
    srv_load(tmp_path, "\n# 애드로그 OpenAPI 키\n이건줄만있다\nADLOG_API_KEY=키값\n")

    assert os.environ["ADLOG_API_KEY"] == "키값"
    assert "이건줄만있다" not in os.environ


def test_load_env_without_a_file_is_quiet(tmp_path, 빈환경):
    """없는 게 정상인 설치도 있다. 셸이나 `setx` 로 넣은 PC 가 그렇다."""
    from cmo import server as srv

    srv.load_env(tmp_path / ".env")          # 만들지 않는다

    assert "ADLOG_API_KEY" not in os.environ


def test_the_env_file_sits_next_to_the_code_not_the_cwd():
    """`run_cmo.bat` 이 `cd ..` 로 들어온다. cwd 를 보면 못 찾는다."""
    from cmo import server as srv

    assert srv.ENV_FILE == srv.CMO / ".env"


def test_env_is_read_only_when_the_server_starts():
    """import 시점에 읽으면 시험이 개발자 PC 의 실제 키를 집는다."""
    from cmo import server as srv

    줄들 = inspect.getsource(srv).splitlines()
    assert not [줄 for 줄 in 줄들 if 줄.startswith("load_env(")]
    assert "load_env(" in inspect.getsource(srv.main)


def test_main_reads_the_env_file_before_serving(tmp_path, monkeypatch, 빈환경):
    """`.bat` 더블클릭이 유일한 여는 법이라 여기서 읽지 않으면 아무도 안 읽는다."""
    from cmo import server as srv

    monkeypatch.setattr(
        srv, "ENV_FILE", _env_file(tmp_path, "ADLOG_API_KEY=파일값\n"))

    class 바로멈추는서버:
        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(srv, "serve", lambda *a, **k: 바로멈추는서버())
    monkeypatch.setattr(srv.webbrowser, "open", lambda url: None)

    assert srv.main() == 0
    assert os.environ["ADLOG_API_KEY"] == "파일값"
