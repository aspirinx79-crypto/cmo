import json
import threading
import time

import pytest
from playwright.sync_api import expect, sync_playwright

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


# --- 가리기가 구성판(가운데 단)의 직접입력 실비까지 가리는지 (리뷰 Important 1) ---
# #hide-internal 토글은 원래 #internal(오른쪽 단)만 가렸다. 직접입력 상품의
# 실비 입력칸은 구성판 카드 안에 있어서, 그 상태로는 사장님 쪽으로 화면을
# 돌려도 실비가 평문으로 보였다.

def test_hiding_conceals_manual_cost_on_board_card(page_with_grade_and_manual):
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="네이버-플레이스_트래픽"]')
    card = page.locator('.board-card[data-id="네이버-플레이스_트래픽"]')
    card.locator(".manual-list-price").fill("500000")
    card.locator(".manual-list-price").dispatch_event("change")
    card.locator(".manual-cost").fill("200000")
    card.locator(".manual-cost").dispatch_event("change")
    page.wait_for_timeout(300)

    # 가리기 전: 실제로 보이는 것부터 확인한다 — 이게 없으면 아래 "안
    # 보인다" 단언이 셀렉터가 틀려도 우연히 통과할 수 있다.
    assert card.locator(".manual-cost").is_visible()
    assert "200,000" in page.locator("body").inner_text()

    page.click("#hide-internal")
    assert not card.locator(".manual-cost").is_visible()
    # 화면 전체 텍스트에서도 실비 금액 문자열 자체가 사라져야 한다.
    assert "200,000" not in page.locator("body").inner_text()
    # 카드 전체가 사라진 게 아니라 실비만 가려졌다 — 정가(공개 정보)는
    # 여전히 보인다.
    assert card.locator(".manual-list-price").is_visible()

    # 가려진 동안에도 계산에 쓰이는 실제 상태값(window.Board.items())은
    # 그대로다 — 렌더만 감췄을 뿐 데이터를 지운 게 아니다.
    items = page.evaluate("window.Board.items()")
    match = next(i for i in items if i["상품id"] == "네이버-플레이스_트래픽")
    assert match["실비"] == 200000
    assert match["정가"] == 500000

    page.click("#hide-internal")
    assert card.locator(".manual-cost").is_visible()
    assert "200,000" in page.locator("body").inner_text()


def test_manual_cost_stays_hidden_even_without_the_css_has_rule(page_with_grade_and_manual):
    """은닉의 유일한 수단이 app.css 의
    `body.hide-internal label:has(> .manual-cost) { display: none; }`
    하나뿐이면 위험하다 — `:has()` 를 모르는 브라우저는 이 규칙을 파싱
    단계에서 통째로 버린다. 조용히, 콘솔 오류도 없이. 그 상황을 흉내 내려고
    로드된 스타일시트에서 실제로 이 규칙을 지운 뒤에도(=CSS 미지원 브라우저와
    동등한 상태) summary.js 가 JS로 건 hidden 속성이 은닉을 유지하는지
    확인한다."""
    page = page_with_grade_and_manual
    page.click('.add-btn[data-id="네이버-플레이스_트래픽"]')
    card = page.locator('.board-card[data-id="네이버-플레이스_트래픽"]')
    card.locator(".manual-cost").fill("123456")
    card.locator(".manual-cost").dispatch_event("change")
    page.wait_for_timeout(300)

    removed = page.evaluate(
        """
        () => {
          let removed = 0;
          for (const sheet of document.styleSheets) {
            let rules;
            try { rules = sheet.cssRules; } catch (e) { continue; }
            for (let i = rules.length - 1; i >= 0; i--) {
              if (rules[i].cssText && rules[i].cssText.includes("manual-cost")) {
                sheet.deleteRule(i);
                removed++;
              }
            }
          }
          return removed;
        }
        """
    )
    assert removed >= 1, "지울 CSS 규칙을 못 찾았다 — 이 테스트가 실제로 흉내를 못 냈다"

    page.click("#hide-internal")
    assert not card.locator(".manual-cost").is_visible(), (
        "CSS 규칙이 없는데도(:has() 미지원 흉내) 실비가 안 보여야 한다 — "
        "JS 안전망(hidden 속성)이 동작해야 한다"
    )
    assert "123,456" not in page.locator("body").inner_text()


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


# --- ③ 요약과 저장 ---

def test_summary_shows_list_total_and_multiplier(page_at):
    page_at.fill("#contract-price", "1000000")
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("50")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    assert "1,500,000" in page_at.locator("#list-total").inner_text()
    assert "1.5배" in page_at.locator("#multiplier").inner_text()


def test_summary_shows_margin_internally(page_at):
    page_at.fill("#contract-price", "1000000")
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("50")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    assert "400,000" in page_at.locator("#cost-total").inner_text()
    assert "60" in page_at.locator("#margin-rate").inner_text()


def test_hide_button_conceals_internal_figures(page_at):
    page_at.fill("#contract-price", "1000000")
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("50")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    # 가리기 전: 실비 금액 문자열이 실제로 화면에 보인다는 것부터 확인한다.
    # (이 확인이 없으면 아래 "안 보인다" 단언이 애초에 셀렉터가 틀려도 통과해버린다.)
    assert page_at.locator("#cost-total").is_visible()
    assert "400,000" in page_at.locator("#cost-total").inner_text()

    page_at.click("#hide-internal")
    internal = page_at.locator("#internal")
    assert "hidden" in (internal.get_attribute("class") or "")
    assert not page_at.locator("#cost-total").is_visible()
    # 화면 전체 텍스트에서도 실비 금액 문자열 자체가 사라져야 한다 —
    # 클래스만 바뀌고 CSS 가 실제로 감추지 않는 경우까지 잡는다.
    assert "400,000" not in page_at.locator("#summary").inner_text()


def test_hide_button_toggles_back(page_at):
    """빈 구성 상태로 시작하면 #cost-total 이 애초에 "0원"이라, 클릭
    핸들러가 아예 없어도 이 단언은 통과해버린다(리뷰에서 지적된 문제 —
    브리프 원문 그대로 두면 공허한 테스트다). 항목을 먼저 담아 실제
    금액이 들어간 상태에서 가리기→(가려진 채로 재계산)→보기를 거쳐야
    토글이 진짜로 동작하는지 알 수 있다."""
    page_at.fill("#contract-price", "1000000")
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("50")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    assert "400,000" in page_at.locator("#cost-total").inner_text()

    page_at.click("#hide-internal")
    assert not page_at.locator("#cost-total").is_visible()

    # Minor(리뷰): 가려진 상태에서 재계산이 일어나도(수량 변경) 계속
    # 가려져 있어야 한다.
    card.locator(".qty-input").fill("60")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    assert not page_at.locator("#cost-total").is_visible()
    assert "480,000" not in page_at.locator("#summary").inner_text()

    page_at.click("#hide-internal")
    assert page_at.locator("#cost-total").is_visible()
    assert "480,000" in page_at.locator("#cost-total").inner_text()


def test_budget_overrun_is_allowed_not_blocked(page_at):
    """넘쳐도 막지 않는다. 표시만 한다."""
    page_at.fill("#contract-price", "100000")
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("100")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    assert "3,000,000" in page_at.locator("#list-total").inner_text()
    assert page_at.locator("#margin").inner_text().startswith("-")


def test_zero_contract_price_does_not_show_nan_or_infinity(page_at):
    """계약가가 0이면 혜택배율·마진율은 null 이다. null/NaN/Infinity 가
    사장님 눈앞에 그대로 뜨면 안 된다."""
    page_at.fill("#contract-price", "0")
    page_at.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page_at.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page_at.wait_for_timeout(400)
    # 먼저 화면이 실제로 다시 그려졌다는 증거부터 확인한다 — 이게 없으면
    # summary.js 가 아무것도 안 해도(초기 HTML의 "—" 가 그대로 남아) 아래
    # "나쁜 문자열이 없다" 단언이 공허하게 통과해버린다.
    assert "300,000" in page_at.locator("#list-total").inner_text()
    multiplier_text = page_at.locator("#multiplier").inner_text()
    margin_rate_text = page_at.locator("#margin-rate").inner_text()
    assert multiplier_text.strip() == "—", multiplier_text
    assert margin_rate_text.strip() == "—", margin_rate_text
    for bad in ("NaN", "Infinity", "null", "undefined"):
        assert bad not in multiplier_text, multiplier_text
        assert bad not in margin_rate_text, margin_rate_text


def test_save_without_client_selected_warns_not_silent(page_at):
    dialogs = []
    page_at.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page_at.click("#save-plan")
    page_at.wait_for_timeout(150)
    assert dialogs, "고객사 미선택 저장이 아무 반응도 없다"
    assert "고객사" in dialogs[-1]


def test_copy_without_client_selected_warns_not_silent(page_at):
    dialogs = []
    page_at.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page_at.click("#copy-next")
    page_at.wait_for_timeout(150)
    assert dialogs, "고객사 미선택 복제가 아무 반응도 없다"
    assert "고객사" in dialogs[-1]


CLIENT_SLUG = "테스트고객사"


@pytest.fixture
def page_with_client(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
    client_dir = tmp_data / "clients" / CLIENT_SLUG
    client_dir.mkdir(parents=True)
    (client_dir / "client.json").write_text(
        json.dumps({"이름": "테스트 고객사", "상태": "진행중"}, ensure_ascii=False),
        encoding="utf-8")
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


def test_saving_same_month_twice_prompts_overwrite_not_silent(page_with_client):
    """같은 달에 두 번 저장하면 서버가 두 번째 요청에 409 를 낸다. 조용히
    성공한 척하거나 조용히 실패하면 안 되고, 사용자에게 명시적으로 물어야 한다."""
    page = page_with_client
    page.select_option("#client-select", CLIENT_SLUG)
    page.fill("#month", "2026-09")
    page.fill("#contract-price", "1000000")
    page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page.wait_for_timeout(300)

    dialogs = []
    page.on("dialog", lambda d: (dialogs.append((d.type, d.message)), d.accept()))

    page.click("#save-plan")
    page.wait_for_timeout(300)
    assert dialogs and dialogs[-1][0] == "alert", dialogs
    assert "저장" in dialogs[-1][1]

    dialogs.clear()
    page.click("#save-plan")
    page.wait_for_timeout(300)
    assert dialogs, "두 번째 저장이 아무 반응 없이 조용히 지나갔다"
    assert any(t == "confirm" and "이미 있습니다" in m for t, m in dialogs), dialogs


def test_declining_overwrite_confirm_keeps_original_plan(page_with_client):
    """덮어쓰기 확인창에서 취소하면 실제로 원본이 그대로 남아야 한다."""
    page = page_with_client
    page.select_option("#client-select", CLIENT_SLUG)
    page.fill("#month", "2026-09")
    page.fill("#contract-price", "1000000")
    page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page.wait_for_timeout(300)
    # 첫 저장의 성공 alert 는 수락, 두 번째 저장의 덮어쓰기 confirm 은
    # 취소한다. page.once 와 page.on 을 같이 걸면 리스너 두 개가 같은
    # 다이얼로그를 두고 경합해 "already handled" 오류가 난다 — 카운터
    # 하나로 순서를 구분한다.
    dialog_count = {"n": 0}

    def handle_dialog(dialog):
        dialog_count["n"] += 1
        if dialog_count["n"] == 1:
            dialog.accept()
        else:
            dialog.dismiss()

    page.on("dialog", handle_dialog)
    page.click("#save-plan")
    page.wait_for_timeout(300)

    # 두 번째 저장 전에 화면 값을 바꿔 둔다 — 취소했을 때 이 값이 저장되지
    # 않아야(=원본이 안 바뀌어야) 진짜로 취소가 동작한 것이다.
    page.fill("#contract-price", "9999999")
    page.click("#save-plan")
    page.wait_for_timeout(300)

    saved = page.evaluate(
        f"window.API.plan('{CLIENT_SLUG}', '2026-09').then(p => p.계약가)"
    )
    assert saved == 1000000, "취소했는데 원본이 덮어써졌다"


# --- 제안서 만들기도 저장 계약을 따라야 한다 ---
# '제안서 만들기' 는 PDF 를 만들기 전에 현재 구성판을 저장한다. 그 저장이
# force=true 로 무조건 덮어쓰면, 지난달에 확정해 둔 기획안이 확인 한 번 없이
# 사라진다. 저장 버튼은 이미 409 → confirm 계약을 지키고 있다 — 같아야 한다.

def _save_first_plan(page):
    """2026-09 기획안을 한 번 저장해 둔다(이후 저장은 409 가 난다)."""
    page.select_option("#client-select", CLIENT_SLUG)
    page.fill("#month", "2026-09")
    page.fill("#contract-price", "1000000")
    page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page.wait_for_timeout(300)
    page.once("dialog", lambda d: d.accept())   # 첫 저장 성공 alert
    page.click("#save-plan")
    page.wait_for_timeout(300)


def test_make_proposal_asks_before_overwriting_and_aborts_when_declined(page_with_client):
    """덮어쓰기를 거절하면 기존 기획안이 그대로 남고, PDF 도 만들지 않는다."""
    page = page_with_client
    _save_first_plan(page)

    # 실제 PDF 생성(무거운 Playwright 호출)까지 가지 않게 가로챈다. 동시에
    # "제안서를 만들려고 했는지" 를 세는 계기판이 된다.
    proposal_calls = {"n": 0}

    def count_and_fulfill(route):
        proposal_calls["n"] += 1
        route.fulfill(status=200, content_type="application/json",
                      body='{"\\uacbd\\ub85c": "fake.pdf"}')

    page.route("**/api/proposal", count_and_fulfill)

    dialogs = []

    def decline(dialog):
        dialogs.append((dialog.type, dialog.message))
        dialog.dismiss()

    page.on("dialog", decline)
    page.fill("#contract-price", "9999999")   # 덮어쓰면 이 값이 남는다
    page.click("#make-proposal")
    page.wait_for_timeout(500)

    assert any(t == "confirm" for t, _ in dialogs), (
        f"덮어쓰기를 묻지 않고 그냥 덮어썼다: {dialogs}")
    assert proposal_calls["n"] == 0, "덮어쓰기를 거절했는데 제안서를 만들었다"
    saved = page.evaluate(
        f"window.API.plan('{CLIENT_SLUG}', '2026-09').then(p => p.계약가)")
    assert saved == 1000000, "덮어쓰기를 거절했는데 원본이 덮어써졌다"


def test_make_proposal_proceeds_after_accepting_overwrite(page_with_client):
    """거절이 아니라 수락하면 원래대로 저장하고 제안서까지 만든다."""
    page = page_with_client
    _save_first_plan(page)

    proposal_calls = {"n": 0}

    def count_and_fulfill(route):
        proposal_calls["n"] += 1
        route.fulfill(status=200, content_type="application/json",
                      body='{"\\uacbd\\ub85c": "fake.pdf"}')

    page.route("**/api/proposal", count_and_fulfill)
    page.on("dialog", lambda d: d.accept())
    page.fill("#contract-price", "9999999")
    page.click("#make-proposal")
    page.wait_for_timeout(500)

    assert proposal_calls["n"] == 1, "덮어쓰기를 수락했는데 제안서를 안 만들었다"
    saved = page.evaluate(
        f"window.API.plan('{CLIENT_SLUG}', '2026-09').then(p => p.계약가)")
    assert saved == 9999999, "덮어쓰기를 수락했는데 저장이 안 됐다"


def test_make_proposal_on_a_fresh_month_does_not_ask(page_with_client):
    """저장된 게 없는 달이면 물을 것도 없다 — 확인창 없이 바로 만든다."""
    page = page_with_client
    page.select_option("#client-select", CLIENT_SLUG)
    page.fill("#month", "2026-11")
    page.fill("#contract-price", "1000000")
    page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page.wait_for_timeout(300)

    proposal_calls = {"n": 0}

    def count_and_fulfill(route):
        proposal_calls["n"] += 1
        route.fulfill(status=200, content_type="application/json",
                      body='{"\\uacbd\\ub85c": "fake.pdf"}')

    page.route("**/api/proposal", count_and_fulfill)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append((d.type, d.message)), d.accept()))
    page.click("#make-proposal")
    page.wait_for_timeout(500)

    assert proposal_calls["n"] == 1, f"제안서를 만들지 않았다: {dialogs}"
    assert not any(t == "confirm" for t, _ in dialogs), (
        f"덮어쓸 게 없는데 확인창을 띄웠다: {dialogs}")


def test_copy_to_next_month_carries_items_and_updates_month_field(page_with_client):
    page = page_with_client
    page.select_option("#client-select", CLIENT_SLUG)
    page.fill("#month", "2026-09")
    page.fill("#contract-price", "1000000")
    page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    card = page.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    card.locator(".qty-input").fill("10")
    card.locator(".qty-input").dispatch_event("change")
    page.wait_for_timeout(300)
    page.on("dialog", lambda d: d.accept())
    page.click("#save-plan")
    page.wait_for_timeout(300)

    page.click("#copy-next")
    page.wait_for_timeout(300)
    assert page.locator("#month").input_value() == "2026-10"
    assert page.locator(
        '.board-card[data-id="네이버-블로그_일반_체험단"]').count() == 1


# --- M-2: 기획안 없는 매장으로 바꿔도 계약가가 앞 매장 값으로 남는다 ---
# 남으면 「N배」 줄이 잘못 계산되고, 그 상태로 저장하면 새 매장 기획안에
# 앞 매장 계약가가 그대로 들어간다. index.html #contract-price 의 초기
# value(1,000,000)로 되돌린다 — 새로 도구를 연 것과 같은 화면이 된다.

def test_switching_to_client_without_plan_resets_contract_price(page_with_client):
    page = page_with_client
    _save_first_plan(page)  # 테스트고객사에 계약가 1,000,000 기획안 저장
    page.fill("#contract-price", "9999999")  # 저장은 안 하고 화면 값만 바꾼다

    page.click("#new-client")
    page.fill("#f-name", "새 매장")
    page.click("#save-client")
    # 새 매장 등록은 reloadClients(editingSlug) 로 그 매장을 자동 선택하고
    # loadClientPlan() 을 부른다 — 기획안이 없으니 이 경로를 탄다.
    page.wait_for_selector("#client-msg.ok:not(:empty)")
    page.click("#panel-close")

    assert page.locator("#contract-price").input_value() == "1000000"


def test_copy_without_existing_plan_warns_not_silent(page_with_client):
    """이번 달에 저장된 기획안이 없는데 복제를 누르면 서버가 404 를 낸다.
    조용히 넘어가면 상무님은 복제가 됐는지 안 됐는지 알 길이 없다."""
    page = page_with_client
    page.select_option("#client-select", CLIENT_SLUG)
    page.wait_for_timeout(150)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.click("#copy-next")
    page.wait_for_timeout(300)
    assert dialogs, "없는 달 복제가 아무 반응도 없다"
    assert "복제" in dialogs[-1]


# --- I-3: 기획안 읽기 실패 시 구성판이 안 비워지면 남의 매장에 저장된다 ---
# planMonths() 는 성공해서 목록에는 달이 있는데(=목록에 있는 매장으로 바꾼
# 것), 그 달의 plan() 읽기만 실패하는 경우를 재현한다 — 파일이 깨졌거나
# 서버가 순간 튀는 경우다. 목록이 아예 비어 기획안이 없는 매장(기존
# 테스트들이 이미 다루는 경우)과는 다른 경로다.

def test_plan_read_failure_clears_board_not_leaving_other_clients_items(page_with_client, tmp_data):
    import re

    page = page_with_client
    other_dir = tmp_data / "clients" / "다른매장"
    other_dir.mkdir(parents=True)
    (other_dir / "client.json").write_text(
        json.dumps({"이름": "다른매장", "상태": "진행중"}, ensure_ascii=False),
        encoding="utf-8")
    (other_dir / "plans").mkdir()
    (other_dir / "plans" / "2026-09.json").write_text(
        json.dumps({"월": "2026-09", "계약가": 500000, "항목": []}, ensure_ascii=False),
        encoding="utf-8")
    page.reload()
    page.wait_for_selector(".product-row")

    # 먼저 테스트고객사를 고르고 구성판에 항목을 담아 둔다 — 저장은 안 한다.
    page.select_option("#client-select", CLIENT_SLUG)
    page.wait_for_timeout(150)
    page.click('.add-btn[data-id="네이버-블로그_일반_체험단"]')
    page.wait_for_selector(".board-card")

    # "다른매장" 은 목록에는 달이 있지만(2026-09.json 이 실제로 있다) 그
    # 달의 개별 읽기만 실패하게 가로챈다. planMonths() 요청(달 없는
    # /plans)은 그대로 통과시켜야 재현이 된다.
    page.route(re.compile(r"/api/clients/[^/]+/plans/2026-09$"),
               lambda route: route.fulfill(status=500))

    page.select_option("#client-select", "다른매장")
    expect(page.locator(".board-card")).to_have_count(0)


# --- 고지사항이 길어도 카드가 화면을 잡아먹으면 안 된다 (app.css, CSS 만으로) ---

LONG_NOTICE_PRODUCT = [
    {"id": "네이버-서비스툴관리", "매체": "네이버", "상품명": "서비스툴관리",
     "가격유형": "고정", "정가": 50000, "실비": 20000, "최소수량": 1, "단위": "건",
     "중요도": "상", "판매중지": False, "고지사항": "약관 문구 " * 300, "프로세스": ""},
]


@pytest.fixture
def page_with_long_notice(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(LONG_NOTICE_PRODUCT, ensure_ascii=False), encoding="utf-8")
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


def test_long_notice_does_not_take_over_the_card(page_with_long_notice):
    page = page_with_long_notice
    page.click('.add-btn[data-id="네이버-서비스툴관리"]')
    card = page.locator('.board-card[data-id="네이버-서비스툴관리"]')
    notice_box = card.locator(".notice").bounding_box()
    assert notice_box is not None
    assert notice_box["height"] < 150, (
        f"고지사항이 카드 절반을 차지한다: {notice_box}")


# --- 프리셋 드롭다운 ---
# 프리셋은 "실제로 돌려 본 조합" 이다. 미팅에서 백지부터 짜지 않으려고 만들었다.
# 출처를 라벨에 같이 띄운다 — 사장님 앞에서 "어느 매장에서 돌린 조합인지" 가
# 근거가 되고, 근거 없는 조합은 그냥 우리 취향이다.

SEED_PRESETS = [
    {"이름": "기본형 — 플레이스·체험단·먹스타",
     "출처": "미친양꼬치 대학로점 2026-06",
     "설명": "가장 많이 쓰인 조합",
     "항목": [{"상품id": "네이버-블로그_일반_체험단", "수량": 10},
              {"상품id": "메타-타겟광고", "예산": 200000}]},
]


@pytest.fixture
def page_with_presets(tmp_data, cmo_dir):
    (tmp_data / "products.json").write_text(
        json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
    for i, preset in enumerate(SEED_PRESETS, 1):
        (tmp_data / "presets" / f"{i:02d}.json").write_text(
            json.dumps(preset, ensure_ascii=False), encoding="utf-8")
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


def test_preset_dropdown_lists_presets_with_their_source(page_with_presets):
    page = page_with_presets
    # <option> 은 닫힌 <select> 안에서 Playwright 기준 "hidden" 이다.
    # 보이는지가 아니라 붙었는지를 기다린다.
    page.wait_for_selector('#preset-select option[value="0"]', state="attached")
    label = page.locator('#preset-select option[value="0"]').inner_text()
    assert "기본형" in label
    assert "미친양꼬치 대학로점 2026-06" in label, (
        f"출처가 라벨에 없다: {label!r}")


def test_choosing_a_preset_loads_it_onto_the_board(page_with_presets):
    page = page_with_presets
    # <option> 은 닫힌 <select> 안에서 Playwright 기준 "hidden" 이다.
    # 보이는지가 아니라 붙었는지를 기다린다.
    page.wait_for_selector('#preset-select option[value="0"]', state="attached")
    assert page.locator(".board-card").count() == 0

    page.select_option("#preset-select", "0")
    page.wait_for_timeout(300)

    ids = page.locator(".board-card").evaluate_all(
        "els => els.map(e => e.dataset.id)")
    assert ids == ["네이버-블로그_일반_체험단", "메타-타겟광고"], ids
    card = page.locator('.board-card[data-id="네이버-블로그_일반_체험단"]')
    assert card.locator(".qty-input").input_value() == "10"


def test_app_still_opens_when_presets_cannot_be_read(page_at):
    """프리셋을 못 읽어도 고객사 목록과 서랍은 떠야 한다.

    미팅 자리에서 도구가 빈 화면으로 열리는 게 최악이다. 프리셋 로딩이
    DOMContentLoaded 를 통째로 죽이면 그렇게 된다.
    """
    page = page_at
    page.route("**/api/presets", lambda route: route.fulfill(status=500))
    page.reload()
    page.wait_for_selector(".product-row")
    assert page.locator(".product-row").count() == 3
    assert page.locator("#client-select").is_visible()


# ── 매장 준비 패널 ────────────────────────────────────────────────

@pytest.fixture
def no_network(monkeypatch):
    """cmo.lib.collect.fetch_place 를 예외로 갈아끼운다. 플레이스를 부르면
    실패하게 만들어 테스트가 실제 네트워크로 나가지 않게 막는다.

    Task 4 리뷰에서 no_network_t4 라는 이름으로 먼저 생겼다가, Task 5(이
    파일 하단의 지표 수집 테스트들)가 같은 역할의 fixture 를 필요로 해
    no_network 로 이름을 바꿨다. 같은 일을 하는 fixture 를 두 벌 두지
    않으려고 기존 것을 재사용한다."""
    import cmo.lib.collect as collect

    def _boom(url, timeout_ms=15000):
        raise RuntimeError("이 테스트에서는 네트워크 접근이 막혀 있다")

    monkeypatch.setattr(collect, "fetch_place", _boom)


def test_panel_is_closed_at_start(page_at):
    assert not page_at.locator("#client-panel").is_visible()


def test_new_client_button_opens_panel(page_at):
    page_at.click("#new-client")
    assert page_at.locator("#client-panel").is_visible()
    assert "새 매장" in page_at.locator("#panel-title").inner_text()


def test_close_button_hides_panel(page_at):
    page_at.click("#new-client")
    page_at.click("#panel-close")
    assert not page_at.locator("#client-panel").is_visible()


def test_meeting_screen_survives_panel(page_at):
    """패널을 열고 닫아도 3단 화면은 그대로 있어야 한다."""
    page_at.click("#new-client")
    page_at.click("#panel-close")
    for sel in ("#drawer", "#board", "#summary"):
        assert page_at.locator(sel).is_visible()


def test_metrics_are_locked_before_saving(page_at):
    """수집은 저장된 매장을 서버가 읽어야 돌아간다. 순서를 화면이 보여준다.

    #metrics 자체가 아니라 그 안의 입력칸(#f-revenue)을 본다 — Playwright
    의 is_disabled() 는 FIELDSET 을 네이티브 비활성 태그로 치지 않아
    fieldset 자신을 물으면 disabled 속성이 있어도 항상 False 를 돌려준다.
    자손 입력칸은 조상 fieldset 의 disabled 를 정확히 반영한다."""
    page_at.click("#new-client")
    assert page_at.locator("#f-revenue").is_disabled()


def test_saving_with_name_only_succeeds(page_at):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.click("#save-client")
    # #metrics 잠금 해제(lock(false))는 동기라 reloadClients 가 끝나기
    # 전에도 이미 풀려 있다. #client-msg.ok 는 reloadClients 가 끝난
    # 뒤에만 찍히므로 이걸 기다려야 여기서 읽는 메시지가 확정된 값이다.
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")
    assert "하루인 인계점" in page_at.locator("#client-msg").inner_text()


def test_saved_client_appears_in_dropdown(page_at):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.click("#save-client")
    # 드롭다운은 saveClient() 의 reloadClients(editingSlug) 가 채운다.
    # #metrics 잠금 해제는 그보다 먼저(동기) 일어나므로 그것만 기다리면
    # reloadClients 가 아직 안 끝난 채로 옵션을 읽어 간헐적으로 빈다.
    # reloadClients 완료 뒤에만 찍히는 #client-msg.ok 를 기다린다.
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")
    options = page_at.locator("#client-select option").all_inner_texts()
    assert "하루인 인계점" in options


def test_saved_client_is_selected_in_dropdown(page_at):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.click("#save-client")
    # 위와 같은 이유 — 선택값도 reloadClients 가 끝나야 확정된다.
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")
    assert page_at.locator("#client-select").input_value() == "하루인_인계점"


def test_empty_size_is_saved_as_null_not_zero(page_at, tmp_data):
    """0평은 제안서에 찍히고 null 은 그 줄이 안 그려진다."""
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert saved["평수"] is None
    assert saved["객단가"] is None
    assert saved["업종"] == ""


def test_typed_numbers_are_saved_as_numbers(page_at, tmp_data):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.fill("#f-size", "60")
    page_at.fill("#f-ticket", "18000")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert saved["평수"] == 60
    assert saved["객단가"] == 18000


def test_saving_without_name_shows_message_and_stays_open(page_at):
    page_at.click("#new-client")
    page_at.click("#save-client")
    # 잠자기 대신 재시도하는 expect 를 쓴다 — 느린 날에 300ms 가 모자라면
    # 제품이 멀쩡한데도 스위트가 빨개진다.
    expect(page_at.locator("#client-msg")).not_to_be_empty()
    expect(page_at.locator("#client-panel")).to_be_visible()
    expect(page_at.locator("#f-revenue")).to_be_disabled()


def test_duplicate_name_shows_message(page_at):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.click("#save-client")
    # 첫 저장이 실제로 끝난 걸 확인하고 나서 두 번째를 시도해야 "중복"을
    # 본다. 잠자기로 어림하면 느린 날에는 아직 저장되지 않은 상태에서
    # 두 번째를 눌러 409 가 아니라 201 이 두 번 나온다.
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    # 백드롭은 클릭을 막는다(제품 요구사항) — 다시 #new-client 를 누르려면
    # 먼저 패널을 닫아야 한다.
    page_at.click("#panel-close")

    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.click("#save-client")

    expect(page_at.locator("#client-msg")).to_contain_text("이미")


def test_keyword_add_and_remove(page_at):
    page_at.click("#new-client")
    page_at.fill("#f-keyword", "인계동 삼겹살")
    page_at.click("#add-keyword")
    page_at.fill("#f-keyword", "수원 고깃집")
    page_at.click("#add-keyword")
    assert page_at.locator("#keyword-list li").count() == 2

    page_at.locator("#keyword-list li", has_text="수원 고깃집").locator("button").click()
    assert page_at.locator("#keyword-list li").count() == 1
    assert "인계동 삼겹살" in page_at.locator("#keyword-list").inner_text()


def test_keywords_are_saved(page_at, tmp_data):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.fill("#f-keyword", "인계동 삼겹살")
    page_at.click("#add-keyword")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert saved["추적키워드"] == ["인계동 삼겹살"]


def test_metrics_fields_reset_between_clients(page_at, no_network):
    """앞 매장의 월매출이 다음 매장에 남으면 안 된다."""
    page_at.click("#new-client")
    page_at.fill("#f-name", "가게 하나")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")
    page_at.fill("#f-revenue", "42000000")
    page_at.fill("#f-market-rank", "상위 40%")
    page_at.click("#panel-close")

    page_at.click("#new-client")
    assert page_at.locator("#f-revenue").input_value() == ""
    assert page_at.locator("#f-market-rank").input_value() == ""


def test_registering_new_client_clears_board(page_at, no_network):
    """새 매장을 등록했는데 구성판에 앞 매장 항목이 남으면 안 된다."""
    page_at.click('.product-row[data-id="네이버-블로그_일반_체험단"] .add-btn')
    page_at.wait_for_selector(".board-card")

    page_at.click("#new-client")
    page_at.fill("#f-name", "새 가게")
    page_at.click("#save-client")
    # 구성판을 비우는 Board.load([]) 는 reloadClients 안쪽, 네트워크 왕복
    # 두 번 뒤에 실행된다. #metrics 잠금 해제만 기다리면 그 전에 읽는다.
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    # 단언도 폴링하는 쪽으로 — 인과적으로 옳은 대기 + 재시도하는 단언.
    expect(page_at.locator(".board-card")).to_have_count(0)


def test_edit_open_shows_blank_panel_until_data_arrives(page_at, no_network):
    """서버 응답을 기다리는 사이 앞 매장 값이 보이면 안 된다."""
    import re

    page_at.click("#new-client")
    page_at.fill("#f-name", "가게 하나")
    page_at.fill("#f-category", "고깃집")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")
    page_at.click("#panel-close")

    # 매장 정보 응답을 붙잡아 두고(보내지 않고) 패널을 연다.
    held = []
    page_at.route(re.compile(r"/api/clients/[^/]+$"), lambda route: held.append(route))
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")

    assert page_at.locator("#f-name").input_value() == ""
    assert page_at.locator("#f-category").input_value() == ""

    page_at.unroute(re.compile(r"/api/clients/[^/]+$"))


# --- I-4: 매장 정보 읽기가 실패하면 빈 폼이 실매장에 묶인 채 저장 가능해진다 ---
# open() 이 fetch 실패로 return 하는 시점엔 폼이 이미 fill({}) 로 비워져 있고
# editingSlug 도 세팅돼 있다. 저장 버튼을 살려 두면 이름만 다시 쳐서 저장할
# 때 업종·지역·평수·객단가·추적키워드가 전부 빈 값으로 실매장을 덮어쓴다.

def test_client_read_failure_disables_save_until_next_success(page_at, no_network):
    import re

    page_at.click("#new-client")
    page_at.fill("#f-name", "가게 하나")
    page_at.click("#save-client")
    # 드롭다운은 reloadClients 완료 뒤에만 채워진다(#client-msg.ok 로
    # 확정된다) — 그전에 #edit-client 를 누르면 "고객사를 먼저
    # 선택하십시오" 얼럿이 뜨는 경합이 생긴다.
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")
    page_at.click("#panel-close")

    page_at.route(re.compile(r"/api/clients/[^/]+$"),
                  lambda route: route.fulfill(status=500))
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")

    # open() 은 패널을 먼저 드러내고 **그 다음에** 매장 정보를 읽는다.
    # 그래서 #client-panel:not([hidden]) 은 읽기가 끝나기 전에 이미 참이고,
    # 여기서 inner_text() 같은 즉시 판정을 쓰면 왕복 한 번 사이에 끼어들어
    # 간헐적으로 깨진다(실제로 깨졌다). 재시도하는 expect 로 기다린다.
    expect(page_at.locator("#client-msg")).not_to_be_empty()
    # 메시지만 보이고 패널이 닫히면 안 된다.
    expect(page_at.locator("#client-panel")).to_be_visible()
    expect(page_at.locator("#save-client")).to_be_disabled()
    # 지표 칸도 다시 잠긴다 — 서버가 이 매장을 못 읽었으니 수집도 못 돈다.
    expect(page_at.locator("#f-revenue")).to_be_disabled()

    page_at.unroute(re.compile(r"/api/clients/[^/]+$"))
    page_at.click("#panel-close")

    # 정상 매장을 다시 열면 저장 버튼이 풀려야 한다 — 안 풀리면 다음
    # 편집이 전부 막힌다.
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    expect(page_at.locator("#f-name")).to_have_value("가게 하나")
    expect(page_at.locator("#save-client")).to_be_enabled()


# ── 지표 수집 ─────────────────────────────────────────────────
# no_network fixture 는 이 파일 상단(매장 준비 패널 섹션)에 이미 정의돼
# 있다 — Task 4 리뷰에서 no_network_t4 로 먼저 생겼고, 여기서 같은 이름을
# 다시 정의하면 fixture 를 두 벌 두는 셈이라 재사용한다.

def _register(page, name="하루인 인계점", keyword="인계동 삼겹살"):
    page.click("#new-client")
    page.fill("#f-name", name)
    if keyword:
        page.fill("#f-keyword", keyword)
        page.click("#add-keyword")
    page.click("#save-client")
    # #metrics 잠금 해제는 동기라 reloadClients 가 끝나기 전에 이미 풀린다.
    # #client-msg.ok 는 reloadClients 완료 뒤에만 찍히므로 더 늦고 안전한
    # 조건이고, 지표 칸이 열린 것도 함께 보장한다.
    page.wait_for_selector("#client-msg.ok:not(:empty)")


def test_rank_rows_follow_keywords(page_at):
    page_at.click("#new-client")
    page_at.fill("#f-keyword", "인계동 삼겹살")
    page_at.click("#add-keyword")
    page_at.fill("#f-keyword", "수원 고깃집")
    page_at.click("#add-keyword")
    assert page_at.locator("#rank-rows .rank-row").count() == 2

    page_at.locator("#keyword-list li", has_text="수원 고깃집").locator("button").click()
    assert page_at.locator("#rank-rows .rank-row").count() == 1


def test_manual_metrics_save_without_place(page_at, tmp_data, no_network):
    """체크를 끄면 플레이스 없이 손으로 넣은 값만 저장된다."""
    _register(page_at)
    page_at.uncheck("#f-fetch-place")
    page_at.fill("#rank-rows .rank-input", "17")
    page_at.fill("#f-market-rank", "상위 40%")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    snapshot = saved["스냅샷"][0]
    assert snapshot["순위"] == [{"키워드": "인계동 삼겹살", "순위": 17}]
    assert snapshot["예상매출"]["상권순위"] == "상위 40%"


def test_place_failure_shows_message_and_screen_survives(page_at, no_network):
    """네이버가 화면을 바꿔도 패널이 멈춰 서면 안 된다."""
    _register(page_at)
    page_at.fill("#f-place-url", "https://m.place.naver.com/restaurant/1")
    page_at.click("#save-client")
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    # Task 4 에서 「플레이스 직접 긁기」 기본값이 켜짐→꺼짐으로 바뀌었다
    # (평소엔 애드로그 PDF 로 받는다). 이 테스트는 긁기 실패 경로 자체를
    # 검증하는 것이므로 명시적으로 켠다.
    page_at.check("#f-fetch-place")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg:not(.ok):not(:empty)")

    assert "플레이스 함께 수집" in page_at.locator("#metrics-msg").inner_text()
    assert page_at.locator("#client-panel").is_visible()
    assert page_at.locator("#save-metrics").is_enabled()


def test_retry_after_failure_with_checkbox_off_succeeds(page_at, tmp_data, no_network):
    """실패 메시지가 알려준 대로 하면 실제로 저장돼야 한다."""
    _register(page_at)
    page_at.fill("#f-place-url", "https://m.place.naver.com/restaurant/1")
    page_at.click("#save-client")
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    # Task 4 에서 「플레이스 직접 긁기」 기본값이 켜짐→꺼짐으로 바뀌었다.
    # 이 테스트는 "긁기를 켠 채 실패 → 끄고 재시도해 성공" 흐름을
    # 검증하는 것이므로 명시적으로 켠다.
    page_at.check("#f-fetch-place")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg:not(.ok):not(:empty)")

    page_at.uncheck("#f-fetch-place")
    page_at.fill("#rank-rows .rank-input", "17")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert len(saved["스냅샷"]) == 1


def test_last_snapshot_line_updates_after_saving(page_at, no_network):
    _register(page_at)
    page_at.uncheck("#f-fetch-place")
    page_at.fill("#rank-rows .rank-input", "17")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")
    assert "마지막" in page_at.locator("#last-snapshot").inner_text()


# --- M-3: 저장 후 마지막 스냅샷 재조회가 실패해도 저장 자체는 성공이다 ---
# collect() 는 이미 통과했는데(=진짜로 저장됐는데) 뒤이은 재조회만 실패하는
# 경우다. 메시지 칸이 아무것도 안 보여주면 상무님은 저장 여부를 몰라 다시
# 눌러 스냅샷이 중복 쌓인다.

def test_metrics_save_succeeds_even_if_snapshot_readback_fails(page_at, tmp_data, no_network):
    import re

    _register(page_at)
    page_at.uncheck("#f-fetch-place")
    page_at.fill("#rank-rows .rank-input", "17")

    # collect() 자체(POST /api/collect)는 그대로 통과시키고, 그 뒤
    # paintLastSnapshot() 이 부르는 재조회(GET /api/clients/<slug>)만
    # 실패하게 만든다.
    page_at.route(re.compile(r"/api/clients/[^/]+$"),
                  lambda route: route.fulfill(status=500))
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")

    assert "저장했습니다" in page_at.locator("#metrics-msg").inner_text()
    assert page_at.locator("#save-metrics").is_enabled(), "재조회 실패로 버튼이 잠긴 채 남았다"

    page_at.unroute(re.compile(r"/api/clients/[^/]+$"))
    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert len(saved["스냅샷"]) == 1, "재조회만 실패했을 뿐 저장 자체는 성공했어야 한다"


def test_empty_rank_is_not_saved(page_at, tmp_data, no_network):
    """안 넣은 순위를 0위로 저장하면 제안서가 거짓말을 한다."""
    _register(page_at)
    page_at.uncheck("#f-fetch-place")
    page_at.fill("#f-market-rank", "상위 40%")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert saved["스냅샷"][0]["순위"] == []


def test_hide_button_conceals_revenue_field(page_at, no_network):
    """가리기는 화면마다 다르게 굴면 안 된다. 월매출칸도 같이 사라진다."""
    _register(page_at)
    page_at.click("#panel-close")
    page_at.click("#hide-internal")
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    assert not page_at.locator("#f-revenue").is_visible()


def test_revenue_field_returns_when_unhidden(page_at, no_network):
    _register(page_at)
    page_at.click("#panel-close")
    page_at.click("#hide-internal")
    page_at.click("#hide-internal")
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    assert page_at.locator("#f-revenue").is_visible()


# --- I-5: 패널이 열려 있으면 백드롭이 클릭을 막아 #hide-internal 에 손이 안
# 닿는다. 패널 안의 #panel-hide-internal 이 같은 가리기 상태를 공유해야
# 한다 — 새 로직이 아니라 같은 toggleConcealment() 를 부른다.

def test_panel_hide_internal_button_conceals_revenue_and_internal_together(page_at, no_network):
    _register(page_at)
    assert page_at.locator("#f-revenue").is_visible()
    assert page_at.locator("#panel-hide-internal").inner_text() == "가리기"

    page_at.click("#panel-hide-internal")
    assert not page_at.locator("#f-revenue").is_visible()
    # 오른쪽 #internal(요약 칸)도 같은 상태를 공유한다 — 패널 안에서 눌러도
    # 뒤 화면의 내부전용 칸이 같이 가려진다.
    assert "hidden" in (page_at.locator("#internal").get_attribute("class") or "")
    assert page_at.locator("#panel-hide-internal").inner_text() == "보기"
    # 두 버튼의 글자가 항상 같은 상태를 보여야 한다.
    assert page_at.locator("#hide-internal").inner_text() == "보기"

    page_at.click("#panel-hide-internal")
    assert page_at.locator("#f-revenue").is_visible()
    assert "hidden" not in (page_at.locator("#internal").get_attribute("class") or "")
    assert page_at.locator("#panel-hide-internal").inner_text() == "가리기"
    assert page_at.locator("#hide-internal").inner_text() == "가리기"


# ── 자료 판독 ─────────────────────────────────────────────────

DOC_OK = {
    "판독": {"플레이스ID": "1234567890", "플레이스명": "하루인 인계점",
             "카테고리": "양꼬치", "방문자리뷰": 312, "블로그리뷰": 14,
             "저장수": 88, "총키워드": 2, "TOP3": 1, "TOP10": 2,
             "순위": [{"키워드": "인계동 삼겹살", "순위": 3},
                      {"키워드": "수원 고깃집", "순위": 7}]},
    "경고": [], "저장가능": True, "불일치": None,
}
DOC_MISMATCH = {**DOC_OK, "저장가능": False,
                "불일치": "이 파일은 「미친양꼬치 잠실점」 자료입니다."}
DOC_TRUNCATED = {**DOC_OK, "경고": ["키워드가 48개인데 2개만 읽혔습니다."]}


def _doc_routes(page, result=None, ready=True):
    import re

    page.route("**/api/read-doc/ready",
               lambda r: r.fulfill(status=200, content_type="application/json",
                                   body=json.dumps({"준비됨": ready})))
    page.route(re.compile(r"/api/read-doc$"),
               lambda r: r.fulfill(status=200, content_type="application/json",
                                   body=json.dumps(result or DOC_OK,
                                                   ensure_ascii=False)))


def _drop(page, name="종합분석.pdf"):
    page.set_input_files("#doc-file", files=[{
        "name": name, "mimeType": "application/pdf", "buffer": b"%PDF-fake"}])


def test_doc_box_is_off_without_key(page_at, no_network):
    _doc_routes(page_at, ready=False)
    _register(page_at)
    expect(page_at.locator("#doc-file")).to_be_disabled()
    expect(page_at.locator("#doc-msg")).to_contain_text("키")


def test_doc_paints_the_reading(page_at, no_network):
    _doc_routes(page_at)
    _register(page_at)
    _drop(page_at)
    expect(page_at.locator("#doc-result")).to_contain_text("312")
    expect(page_at.locator("#doc-result")).to_contain_text("인계동 삼겹살")
    expect(page_at.locator("#apply-doc")).to_be_enabled()


def test_doc_mismatch_blocks_saving(page_at, no_network):
    """A 매장 화면에 B 매장 파일을 떨구면 저장이 열리면 안 된다."""
    _doc_routes(page_at, result=DOC_MISMATCH)
    _register(page_at)
    _drop(page_at)
    expect(page_at.locator("#doc-msg")).to_contain_text("미친양꼬치 잠실점")
    expect(page_at.locator("#apply-doc")).to_be_disabled()


def test_doc_truncation_warns_but_allows_saving(page_at, no_network):
    _doc_routes(page_at, result=DOC_TRUNCATED)
    _register(page_at)
    _drop(page_at)
    expect(page_at.locator("#doc-warn")).to_contain_text("48")
    expect(page_at.locator("#apply-doc")).to_be_enabled()


def test_doc_does_not_show_a_preview(page_at, no_network):
    """오픈업 캡처가 같은 칸에 들어올 때 월매출이 그림으로 박혀 있다."""
    _doc_routes(page_at)
    _register(page_at)
    _drop(page_at)
    expect(page_at.locator("#doc img")).to_have_count(0)
    expect(page_at.locator("#doc canvas")).to_have_count(0)


def test_doc_clears_between_stores(page_at, no_network):
    _doc_routes(page_at)
    _register(page_at)
    _drop(page_at)
    expect(page_at.locator("#doc-result")).to_contain_text("312")
    page_at.click("#panel-close")

    page_at.click("#new-client")
    expect(page_at.locator("#doc-result")).to_be_empty()
    expect(page_at.locator("#apply-doc")).to_be_disabled()


def test_doc_failure_leaves_a_short_message(page_at, no_network):
    import re

    page_at.route("**/api/read-doc/ready",
                  lambda r: r.fulfill(status=200,
                                      content_type="application/json",
                                      body=json.dumps({"준비됨": True})))
    page_at.route(re.compile(r"/api/read-doc$"),
                  lambda r: r.fulfill(status=400,
                                      content_type="application/json",
                                      body=json.dumps(
                                          {"오류": "애드로그 종합분석 파일이 아닌 것 같습니다"},
                                          ensure_ascii=False)))
    _register(page_at)
    _drop(page_at, name="엉뚱한.pdf")
    expect(page_at.locator("#doc-msg")).to_contain_text("애드로그")
    expect(page_at.locator("#apply-doc")).to_be_disabled()


def test_place_fetch_is_off_by_default(page_at, no_network):
    """평소엔 PDF 로 받는다. 긁기는 애드로그가 안 될 때만 켠다."""
    _doc_routes(page_at)
    page_at.click("#new-client")
    assert not page_at.locator("#f-fetch-place").is_checked()


# ── 기존 매장 편집 ────────────────────────────────────────────
# open(slug) 는 패널을 먼저 빈 값으로 연 뒤(fill({})), 서버 응답이 와야
# 실제 값을 채운다(fill(await window.API.client(slug))). 그래서
# "#client-panel:not([hidden])" 만 기다리면 패널은 보이지만 칸은 아직
# 비어 있을 수 있다 — 그 직후 값을 단언하거나 입력하면 뒤이어 도착하는
# fill() 이 덮어써 간헐적으로 깨진다. expect(...).to_have_value(...) 로
# 데이터 도착 자체를 기다린 뒤에 단언/입력한다. 단언 내용 자체는 브리프
# 그대로다 — 기다리는 대상만 고쳤다.

def test_edit_button_prefills_saved_values(page_at, no_network):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.fill("#f-category", "고깃집")
    page_at.fill("#f-size", "60")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")
    page_at.click("#panel-close")

    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    expect(page_at.locator("#f-name")).to_have_value("하루인 인계점")
    assert page_at.locator("#f-category").input_value() == "고깃집"
    assert page_at.locator("#f-size").input_value() == "60"
    assert "매장 정보" in page_at.locator("#panel-title").inner_text()


def test_edit_panel_metrics_are_unlocked(page_at, no_network):
    """이미 저장된 매장이니 지표칸이 처음부터 열려 있어야 한다."""
    _register(page_at)
    page_at.click("#panel-close")
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    # #metrics 자체(FIELDSET)는 Playwright 가 네이티브 비활성 태그로 치지
    # 않아 is_disabled() 가 항상 False 다. 자손 입력칸 #f-revenue 로
    # 확인한다 — 조상 fieldset 의 disabled 를 정확히 반영한다.
    assert not page_at.locator("#f-revenue").is_disabled()


def test_edit_keeps_snapshots(page_at, tmp_data, no_network):
    """폼에 없는 스냅샷을 저장이 지우면 수집 이력이 사라진다."""
    _register(page_at)
    page_at.uncheck("#f-fetch-place")
    page_at.fill("#rank-rows .rank-input", "17")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")
    page_at.click("#panel-close")

    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    expect(page_at.locator("#f-name")).to_have_value("하루인 인계점")
    page_at.fill("#f-category", "고깃집")
    page_at.click("#save-client")
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert len(saved["스냅샷"]) == 1
    assert saved["업종"] == "고깃집"


# --- I-1: 패널에 메모 칸 추가 ---
# 시드 12곳처럼 "미확인" 문구가 메모에 적혀 있고, 지금은 화면에서 고칠 방법이
# 없다. 등록 때 저장되는지, 편집 때 채워져 열리는지, 고쳐 저장하면 반영되되
# 스냅샷은 그대로인지 확인한다.

def test_memo_is_saved_on_registration(page_at, tmp_data):
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.fill("#f-memo", "카톡 이력에서 등록. 미확인.")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert saved["메모"] == "카톡 이력에서 등록. 미확인."


def test_memo_prefills_on_edit_and_survives_resave_with_snapshot_intact(page_at, tmp_data, no_network):
    """메모를 고쳐 저장해도 반영되고, 폼에 없는 스냅샷은 그대로 남아야 한다."""
    page_at.click("#new-client")
    page_at.fill("#f-name", "하루인 인계점")
    page_at.fill("#f-memo", "카톡 이력에서 등록. 미확인.")
    page_at.click("#save-client")
    page_at.wait_for_selector("#metrics:not([disabled])")

    # 이 매장에는 플레이스URL 이 없다. 「플레이스 함께 수집」을 켠 채로
    # 누르면 도구가 설계대로 탈출구 안내를 띄우고 저장하지 않는다 —
    # 여기서 필요한 건 스냅샷 한 건이므로 체크를 끄고 손입력만 저장한다.
    page_at.uncheck("#f-fetch-place")
    page_at.fill("#f-market-rank", "상위 40%")
    page_at.click("#save-metrics")
    page_at.wait_for_selector("#metrics-msg.ok:not(:empty)")
    page_at.click("#panel-close")

    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    expect(page_at.locator("#f-memo")).to_have_value("카톡 이력에서 등록. 미확인.")

    page_at.fill("#f-memo", "확인 완료. 평수 60평, 객단가 18000원.")
    page_at.click("#save-client")
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    saved = json.loads(
        (tmp_data / "clients" / "하루인_인계점" / "client.json")
        .read_text(encoding="utf-8"))
    assert saved["메모"] == "확인 완료. 평수 60평, 객단가 18000원."
    assert len(saved["스냅샷"]) == 1, "메모를 고쳐 저장했더니 스냅샷이 지워졌다"


def test_edit_does_not_duplicate_dropdown_entries(page_at, no_network):
    _register(page_at)
    page_at.click("#panel-close")
    page_at.click("#edit-client")
    page_at.wait_for_selector("#client-panel:not([hidden])")
    expect(page_at.locator("#f-name")).to_have_value("하루인 인계점")
    page_at.click("#save-client")
    page_at.wait_for_selector("#client-msg.ok:not(:empty)")

    options = page_at.locator("#client-select option").all_inner_texts()
    assert options.count("하루인 인계점") == 1


def test_edit_without_selection_warns(page_at):
    page_at.on("dialog", lambda d: d.accept())
    page_at.click("#edit-client")
    page_at.wait_for_timeout(200)
    assert not page_at.locator("#client-panel").is_visible()
