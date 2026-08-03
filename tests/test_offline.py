"""미팅 장소에 인터넷이 없어도 도구가 온전히 돌아야 한다."""
import re

SOURCES = ("index.html", "app.css", "api.js", "drawer.js", "board.js", "summary.js")
URL_RE = re.compile(r'https?://[^\s"\')]+')
NAMESPACE_RE = re.compile(r'^https?://(www\.)?w3\.org/')


def test_no_external_urls_in_app_sources(cmo_dir):
    offenders = []
    for name in SOURCES:
        path = cmo_dir / "app" / name
        if not path.exists():
            continue
        for m in URL_RE.findall(path.read_text(encoding="utf-8")):
            if NAMESPACE_RE.match(m):
                continue
            offenders.append(f"{name}: {m}")
    assert not offenders, "외부 URL 참조:\n" + "\n".join(offenders)


def test_font_is_bundled(cmo_dir):
    assert (cmo_dir / "app" / "fonts" / "PretendardVariable.woff2").exists()
