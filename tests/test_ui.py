import json
import threading

import pytest
from playwright.sync_api import sync_playwright

from cmo.lib.storage import Store
from cmo.server import serve

PRODUCTS = [
    {"id": "네이버-블로그_일반_체험단", "매체": "네이버", "상품명": "블로그 일반 체험단",
     "가격유형": "고정", "정가": 30000, "실비": 8000, "최소수량": 5, "단위": "팀",
     "중요도": "상", "판매중지": False, "고지사항": "공정위 문구 고지", "프로세스": ""},
    {"id": "네이버-지식인_배포", "매체": "네이버", "상품명": "지식인 배포",
     "가격유형": "직접입력", "정가": None, "실비": None, "최소수량": 1, "단위": "건",
     "중요도": "하", "판매중지": True, "고지사항": "", "프로세스": ""},
    {"id": "메타-타겟광고", "매체": "메타", "상품명": "타겟광고",
     "가격유형": "예산배율", "정가": None, "실비": None, "예산배율": 1.3,
     "최소수량": 1, "단위": "원", "중요도": "상", "판매중지": False,
     "고지사항": "", "프로세스": ""},
]


@pytest.fixture
def page_at(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
    httpd = serve(0, Store(tmp_data), cmo_dir / "app")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.wait_for_selector(".product-row")
        yield page
        browser.close()
    httpd.shutdown()


def test_three_panels_exist(page_at):
    for sel in ("#drawer", "#board", "#summary"):
        assert page_at.locator(sel).is_visible(), f"{sel} 이 보이지 않는다"


def test_drawer_groups_by_media(page_at):
    groups = page_at.locator(".media-group").all_inner_texts()
    joined = " ".join(groups)
    assert "네이버" in joined and "메타" in joined


def test_drawer_shows_all_products(page_at):
    assert page_at.locator(".product-row").count() == 3


def test_discontinued_product_is_locked(page_at):
    row = page_at.locator('.product-row[data-id="네이버-지식인_배포"]')
    assert "discontinued" in (row.get_attribute("class") or "")
    assert row.locator(".add-btn").is_disabled()


def test_search_filters_rows(page_at):
    page_at.fill("#search", "타겟")
    page_at.wait_for_timeout(150)
    visible = [r for r in page_at.locator(".product-row").all()
               if r.is_visible()]
    assert len(visible) == 1
    assert "타겟광고" in visible[0].inner_text()


def test_important_products_sort_first(page_at):
    names = page_at.locator(".product-row .name").all_inner_texts()
    assert names.index("블로그 일반 체험단") < names.index("지식인 배포")


# --- 이스케이프: 매체·상품명·id 는 시트에서 온 임의 문자열이다 ---

ESCAPE_PRODUCTS = [
    {"id": '네이버-블로그 "특별" <상위> & 노출', "매체": "네이버 & 인스타",
     "상품명": '블로그 <b>강조</b> "특별" 노출 & 할인',
     "가격유형": "고정", "정가": 10000, "실비": 3000, "최소수량": 1, "단위": "건",
     "중요도": "상", "판매중지": False, "고지사항": "", "프로세스": ""},
]


@pytest.fixture
def page_with_unsafe_names(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(ESCAPE_PRODUCTS, ensure_ascii=False), encoding="utf-8")
    httpd = serve(0, Store(tmp_data), cmo_dir / "app")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.wait_for_selector(".product-row")
        yield page
        browser.close()
    httpd.shutdown()


def test_unsafe_product_name_renders_as_text_not_markup(page_with_unsafe_names):
    page = page_with_unsafe_names
    row = page.locator(".product-row")
    assert row.count() == 1, "이름 속 <, \", & 때문에 마크업이 깨져 행이 갈라졌다"
    name_el = row.locator(".name")
    assert name_el.locator("*").count() == 0, "이름 안에 엉뚱한 엘리먼트가 끼어들었다"
    assert name_el.inner_text() == ESCAPE_PRODUCTS[0]["상품명"]
    assert row.locator("> *").count() == 3, ".name/.price/.add-btn 세 자식만 있어야 한다"


def test_unsafe_product_id_is_still_selectable_via_add_btn(page_with_unsafe_names):
    page = page_with_unsafe_names
    btn = page.locator(".add-btn")
    assert btn.count() == 1
    assert btn.get_attribute("data-id") == ESCAPE_PRODUCTS[0]["id"]
    assert btn.is_enabled()


# --- /api/products 실패 시 조용히 비지 않아야 한다 ---

@pytest.fixture
def page_with_broken_products_api(tmp_data, cmo_dir):
    # products.json 을 일부러 두지 않아 GET /api/products 가 404 로 응답하게 한다.
    httpd = serve(0, Store(tmp_data), cmo_dir / "app")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.wait_for_function(
            "document.querySelector('#warnings').textContent.trim().length > 0"
        )
        yield page
        browser.close()
    httpd.shutdown()


def test_products_api_failure_shows_warning_instead_of_blank_screen(page_with_broken_products_api):
    page = page_with_broken_products_api
    assert page.locator(".product-row").count() == 0
    warning_text = page.locator("#warnings").inner_text()
    assert warning_text.strip() != ""
    assert "상품" in warning_text
