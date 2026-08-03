import json
import threading
import time

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


# --- ② 구성판 ---

def test_add_puts_card_on_board(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    assert page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]').count() == 1


def test_adding_twice_does_not_duplicate(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    assert page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]').count() == 1


def test_fixed_card_shows_quantity_input(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    assert card.locator(".qty-input").is_visible()
    assert card.locator(".budget-input").count() == 0


def test_budget_card_shows_budget_input(page_at):
    page_at.click('.add-btn[data-id="메타-타겟광고"]')
    card = page_at.locator('.board-card[data-id="메타-타겟광고"]')
    assert card.locator(".budget-input").is_visible()
    assert card.locator(".qty-input").count() == 0


def test_quantity_change_updates_line_total(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(300)
    assert "300,000" in card.locator(".line-total").inner_text()


def test_meta_budget_applies_1_3_multiplier(page_at):
    page_at.click('.add-btn[data-id="메타-타겟광고"]')
    card = page_at.locator('.board-card[data-id="메타-타겟광고"]')
    card.locator(".budget-input").fill("1000000")
    card.locator(".budget-input").dispatch_event("change")
    page_at.wait_for_timeout(300)
    assert "1,300,000" in card.locator(".line-total").inner_text()


def test_below_minimum_quantity_shows_warning(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("3")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(300)
    assert "5" in page_at.locator("#warnings").inner_text()


def test_notice_is_shown_on_card(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    assert "공정위" in card.inner_text()


def test_remove_button_clears_card(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"] .remove-btn').click()
    assert page_at.locator(".board-card").count() == 0


def test_unsafe_product_name_on_board_card_is_escaped(page_with_unsafe_names):
    """상품명·매체 문자열이 시트에서 오는 그대로 카드 마크업에 꽂히면
    <b>강조</b> 같은 부분이 실제 엘리먼트로 파싱돼 카드가 깨진다."""
    page = page_with_unsafe_names
    page.click(".add-btn")
    card = page.locator(".board-card")
    assert card.count() == 1, "이름·매체 속 특수문자 때문에 카드 마크업이 깨졌다"
    assert card.locator("b").count() == 0, "상품명 속 <b> 가 실제 엘리먼트로 파싱됐다"
    text = card.inner_text()
    assert ESCAPE_PRODUCTS[0]["상품명"] in text
    assert ESCAPE_PRODUCTS[0]["매체"] in text


# --- window.Board.items() 가 실제 화면 조작을 반영하는지 ---
# 카드에 입력 필드가 그려지는 것만으로는 부족하다. 값을 바꾼 뒤
# window.Board.items() 를 직접 읽어 진짜 상태가 바뀌었는지 확인한다.

def test_board_items_have_required_keys(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    items = page_at.evaluate("window.Board.items()")
    assert len(items) == 1
    assert set(items[0].keys()) == {"상품id", "수량", "예산", "등급", "정가", "실비"}


def test_quantity_change_is_reflected_in_board_items(page_at):
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    items = page_at.evaluate("window.Board.items()")
    match = next(i for i in items if i["상품id"] == "네이버-블로그_일반_체험단")
    assert match["수량"] == 10


def test_budget_change_is_reflected_in_board_items(page_at):
    page_at.click('.add-btn[data-id="메타-타겟광고"]')
    card = page_at.locator('.board-card[data-id="메타-타겟광고"]')
    card.locator(".budget-input").fill("1000000")
    card.locator(".budget-input").dispatch_event("change")
    items = page_at.evaluate("window.Board.items()")
    match = next(i for i in items if i["상품id"] == "메타-타겟광고")
    assert match["예산"] == 1000000


# --- 등급선택·직접입력 상품 (page_at 의 고정 fixture 에는 없다) ---

# 등급선택 상품(포털-언론송출)의 실제 시트 레코드는 최상위 정가·실비가 채워져
# 있다(등급 목록이 생기기 전에 쓰던 값이 남아 있는 것으로 보인다). 여기 None
# 을 쓰면, 누가 나중에 "가격유형" 분기보다 앞에 `if (p.정가) {...}` 같은
# 지름길을 넣어도 이 값이 falsy 라 그 지름길이 활성화되지 않아 테스트가 못
# 잡는다. 일부러 등급 목록의 어떤 값과도 겹치지 않는 값으로 채운다.
GRADE_AND_MANUAL_PRODUCTS = [
    {"id": "포털-언론송출", "매체": "포털", "상품명": "언론송출",
     "가격유형": "등급선택", "정가": 999999, "실비": 999999, "최소수량": 1, "단위": "건",
     "중요도": "상", "판매중지": False, "고지사항": "", "프로세스": "",
     "등급": [
         {"이름": "일반~B급", "정가": 150000, "실비": 100000},
         {"이름": "A급", "정가": 300000, "실비": 200000},
     ]},
    {"id": "네이버-플레이스_트래픽", "매체": "네이버", "상품명": "플레이스 트래픽",
     "가격유형": "직접입력", "정가": None, "실비": None, "최소수량": 1, "단위": "건",
     "중요도": "중", "판매중지": False, "고지사항": "", "프로세스": ""},
]


@pytest.fixture
def page_with_grade_and_manual(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(GRADE_AND_MANUAL_PRODUCTS, ensure_ascii=False), encoding="utf-8")
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


def test_grade_card_shows_grade_select(page_with_grade_and_manual):
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="포털-언론송출"]')
    card = page.locator('.board-card[data-id="포털-언론송출"]')
    assert card.locator(".grade-select").is_visible()


def test_manual_card_shows_manual_price_inputs(page_with_grade_and_manual):
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="네이버-플레이스_트래픽"]')
    card = page.locator('.board-card[data-id="네이버-플레이스_트래픽"]')
    assert card.locator(".manual-list-price").is_visible()
    assert card.locator(".manual-cost").is_visible()


def test_grade_selection_is_reflected_in_board_items(page_with_grade_and_manual):
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="포털-언론송출"]')
    card = page.locator('.board-card[data-id="포털-언론송출"]')
    card.locator(".grade-select").select_option("A급")
    items = page.evaluate("window.Board.items()")
    match = next(i for i in items if i["상품id"] == "포털-언론송출")
    assert match["등급"] == "A급"


def test_manual_price_input_is_reflected_in_board_items(page_with_grade_and_manual):
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="네이버-플레이스_트래픽"]')
    card = page.locator('.board-card[data-id="네이버-플레이스_트래픽"]')
    card.locator(".manual-list-price").fill("500000")
    card.locator(".manual-list-price").dispatch_event("change")
    card.locator(".manual-cost").fill("200000")
    card.locator(".manual-cost").dispatch_event("change")
    items = page.evaluate("window.Board.items()")
    match = next(i for i in items if i["상품id"] == "네이버-플레이스_트래픽")
    assert match["정가"] == 500000
    assert match["실비"] == 200000


def test_grade_selection_updates_line_total_not_top_level_price(page_with_grade_and_manual):
    """등급선택 상품도 최상위 정가를 갖는다(포털-언론송출 999999로 일부러
    맞춰 둔 값). 가격유형 분기보다 앞서 최상위 정가를 읽는 지름길이 생기면
    줄별 합계가 999,999 로 나와 여기서 잡힌다."""
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="포털-언론송출"]')
    card = page.locator('.board-card[data-id="포털-언론송출"]')
    card.locator(".grade-select").select_option("A급")
    page.wait_for_timeout(300)
    total = card.locator(".line-total").inner_text()
    assert "300,000" in total
    assert "999,999" not in total


# --- Important 1: /api/summary 실패가 화면에 안 나타나면 사장님 앞에서
#     숫자가 안 바뀌는데 이유를 알 수 없다 ---

BROKEN_GRADE_PRODUCT = [
    {"id": "포털-빈등급", "매체": "포털", "상품명": "등급 없는 상품",
     "가격유형": "등급선택", "정가": 100000, "실비": 50000, "최소수량": 1, "단위": "건",
     "중요도": "상", "판매중지": False, "고지사항": "", "프로세스": "",
     "등급": []},  # 손편집 시트에서 등급 목록이 비면 실제로 이런 모양이 된다
]


@pytest.fixture
def page_with_broken_grade(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(BROKEN_GRADE_PRODUCT, ensure_ascii=False), encoding="utf-8")
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


def test_summary_api_failure_shows_warning(page_with_broken_grade):
    """등급 목록이 빈 등급선택 상품을 담으면 add()가 등급을 null 로 잡고,
    그 null 로 /api/summary 를 부르면 서버가 400 을 낸다. try/catch 가
    없으면 promise 가 조용히 깨지고 #warnings 는 계속 비어 있다."""
    page = page_with_broken_grade
    page.click('.add-btn[data-id="포털-빈등급"]')
    page.wait_for_function(
        "document.querySelector('#warnings').textContent.trim().length > 0",
        timeout=5000,
    )
    warning_text = page.locator("#warnings").inner_text()
    assert warning_text.strip() != ""


# --- Important 2: 담기 클릭이 초기 로딩 중 유실될 수 있다 ---
# drawer.js 와 board.js 는 각자 /api/products 를 독립적으로 fetch 한다.
# drawer 의 fetch 가 board 보다 먼저 끝나면 .add-btn 이 그려지고 클릭
# 핸들러가 붙는데, 그 핸들러가 부르는 addHandler 는 board 의 fetch 가
# 끝나야 add 로 교체된다. board.js 가 onAdd 등록을 자기 fetch 뒤로 미루면
# 그 사이의 클릭은 기본 no-op 으로 들어가 소리 없이 사라진다.
# 두 번째 /api/products 요청(=board 의 fetch, drawer 가 먼저 실행되므로
# 첫 요청은 항상 drawer 의 것이다)만 인위적으로 늦춰서 그 창을 실제로
# 만들고, 그 안에서 누른 클릭이 결국 카드가 되는지 확인한다.

def test_add_click_during_slow_board_load_still_creates_card(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
    httpd = serve(0, Store(tmp_data), cmo_dir / "app")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"

    calls = {"n": 0}

    def delay_second_call(route):
        calls["n"] += 1
        if calls["n"] >= 2:
            time.sleep(0.5)
        route.continue_()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.route("**/api/products", delay_second_call)
        page.goto(url)
        page.wait_for_selector('.add-btn[data-id="네이버-블로그_일반_체험단"]')
        # 이 시점에서 drawer 의 fetch 는 끝났지만(버튼이 보인다) board 의
        # fetch 는 아직 진행 중이다(0.5초 지연). 바로 클릭한다.
        page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
        page.wait_for_selector(
            '.board-card[data-id="네이버-블로그_일반_체험단"]', timeout=5000)
        assert page.locator(
            '.board-card[data-id="네이버-블로그_일반_체험단"]').count() == 1
        browser.close()
    httpd.shutdown()
