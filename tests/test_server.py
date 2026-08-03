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
