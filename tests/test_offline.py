"""미팅 장소에 인터넷이 없어도 도구가 온전히 돌아야 한다."""
import re

# cmo/ 기준 상대경로. 오프라인에서 열리는 파일은 전부 여기 들어와야 한다.
# templates/proposal.html 은 화면이 아니라 인쇄용 서식이지만, 미팅 장소에서
# PDF 를 뽑는 순간 똑같이 네트워크를 탄다 — 여기 외부 URL 이 하나 들어가면
# 폰트나 이미지가 빠진 제안서가 사장님 손에 간다.
SOURCES = (
    "app/index.html", "app/app.css", "app/util.js", "app/api.js",
    "app/drawer.js", "app/board.js", "app/summary.js",
    "templates/proposal.html",
)
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


def test_every_source_actually_exists(cmo_dir):
    """아래 두 검사는 없는 파일을 조용히 건너뛴다. 경로를 잘못 적으면
    "검사했는데 깨끗하다" 가 아니라 "아무것도 안 봤다" 가 되므로 여기서 막는다."""
    missing = [name for name in SOURCES if not (cmo_dir / name).exists()]
    assert not missing, f"검사 대상 파일이 없다: {missing}"


def test_no_external_urls_in_app_sources(cmo_dir):
    offenders = []
    for name in SOURCES:
        path = cmo_dir / name
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
        path = cmo_dir / name
        if not path.exists():
            continue
        for m in PROTOCOL_RELATIVE_RE.findall(path.read_text(encoding="utf-8")):
            if _is_w3_namespace(m):
                continue
            offenders.append(f"{name}: {m}")
    assert not offenders, "프로토콜 상대 URL 참조:\n" + "\n".join(offenders)


def test_font_is_bundled(cmo_dir):
    assert (cmo_dir / "app" / "fonts" / "PretendardVariable.woff2").exists()
