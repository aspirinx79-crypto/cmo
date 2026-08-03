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
