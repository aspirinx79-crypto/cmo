"""미팅 장소에 인터넷이 없어도 도구가 온전히 돌아야 한다."""
import re

SOURCES = ("index.html", "app.css", "util.js", "api.js", "drawer.js", "board.js", "summary.js")
URL_RE = re.compile(r'https?://[^\s"\')]+')
NAMESPACE_RE = re.compile(r'^https?://(www\.)?w3\.org/')

# 스킴을 생략한 프로토콜 상대 URL(`//host/...`)도 네트워크를 탄다.
# src=, href=, CSS url( 문맥에서만 잡는다 — 본문 텍스트의 우연한 "//" 는 대상이 아니다.
PROTOCOL_RELATIVE_RE = re.compile(
    r'(?:(?:src|href)\s*=\s*["\']|url\(\s*["\']?)(//[^\s"\')]+)',
    re.IGNORECASE,
)


def _is_w3_namespace(protocol_relative_url: str) -> bool:
    return bool(NAMESPACE_RE.match("https:" + protocol_relative_url))


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


def test_no_protocol_relative_urls_in_app_sources(cmo_dir):
    offenders = []
    for name in SOURCES:
        path = cmo_dir / "app" / name
        if not path.exists():
            continue
        for m in PROTOCOL_RELATIVE_RE.findall(path.read_text(encoding="utf-8")):
            if _is_w3_namespace(m):
                continue
            offenders.append(f"{name}: {m}")
    assert not offenders, "프로토콜 상대 URL 참조:\n" + "\n".join(offenders)


def test_font_is_bundled(cmo_dir):
    assert (cmo_dir / "app" / "fonts" / "PretendardVariable.woff2").exists()
