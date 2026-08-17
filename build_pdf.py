"""제안서·견적서 payload 를 A4 세로 PDF 로 인쇄한다.

발표덱은 1920x1080 가로 슬라이드지만 이 둘은 다른 물건이다.
사장님이 손에 들고 보고, 접어서 넣고, 배우자에게 보여준다.

서식이 둘이 되었으므로 템플릿 경로를 인자로 받는다 — 모듈 안에 박아 두면
「제안서 빌더가 견적서도 찍는다」가 되어 이름이 거짓말을 한다.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

CMO = Path(__file__).resolve().parent
PROPOSAL = CMO / "templates" / "proposal.html"
QUOTE = CMO / "templates" / "quote.html"


def build(payload: dict, out_path: Path, template: Path = PROPOSAL) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(Path(template).as_uri())
        page.evaluate("p => { window.PAYLOAD = p; render(); }", payload)
        # 웹폰트가 다 올라온 뒤에 인쇄해야 한글이 깨지지 않는다
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(300)
        page.pdf(path=str(out_path), format="A4", print_background=True)
        browser.close()

    return out_path


def main() -> int:
    import sys
    from cmo.lib.proposal import build_payload
    from cmo.lib.storage import Store

    from cmo.lib.proposal import missing_pages

    slug, month = sys.argv[1], sys.argv[2]
    store = Store(CMO / "data")
    payload = build_payload(store.client_read(slug), store.plan_read(slug, month),
                            store.products())
    out = CMO / "out" / f"{slug}_{month}_제안서.pdf"
    print(build(payload, out))

    # 빠진 진단 장은 stderr 로 알린다 — 경로만 파이프로 받아 쓰는
    # 사용처가 있어서 stdout 에 섞지 않는다. 막지는 않는다.
    for 줄 in missing_pages(payload):
        print(줄, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
