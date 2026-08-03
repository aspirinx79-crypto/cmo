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
