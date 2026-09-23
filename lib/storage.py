"""data/ 아래 JSON 파일을 읽고 쓴다. 경로를 아는 유일한 모듈이다.

고객사 하나가 폴더 하나, 월 기획안 하나가 파일 하나다.
폴더를 열면 눈에 보이고 git 으로 되돌릴 수 있다.
"""
import json
import re
from datetime import datetime
from pathlib import Path

FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|]+')
_PATH_SEP_RE = re.compile(r'[\\/]')
_DRIVE_RE = re.compile(r'^[A-Za-z]:')


class PlanExists(Exception):
    """이미 있는 월 기획안을 덮어쓰려 했다."""


class ClientExists(Exception):
    """이미 있는 매장을 새로 만들려 했다."""


def slugify(name: str) -> str:
    cleaned = FORBIDDEN_RE.sub("_", (name or "").strip())
    cleaned = cleaned.replace(" ", "_")
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_")
    if not cleaned:
        raise ValueError(f"슬러그를 만들 수 없는 이름입니다: {name!r}")
    return cleaned


def _validate_segment(value: str, label: str) -> str:
    """slug/month 가 경로 조각 하나로만 쓰이도록 검증한다.

    상위 폴더 이동(`..`)이나 절대 경로로 self.data 바깥을 가리키지 못하게 막는다.
    """
    if not value:
        raise ValueError(f"{label} 값이 비어 있습니다: {value!r}")
    if value in (".", ".."):
        raise ValueError(f"{label} 값으로 '.' 또는 '..' 을 쓸 수 없습니다: {value!r}")
    if _PATH_SEP_RE.search(value):
        raise ValueError(f"{label} 값에 경로 구분자를 포함할 수 없습니다: {value!r}")
    if _DRIVE_RE.match(value) or Path(value).is_absolute():
        raise ValueError(f"{label} 값에 절대 경로를 쓸 수 없습니다: {value!r}")
    return value


def _read(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class Store:
    def __init__(self, data_dir: Path):
        self.data = Path(data_dir)

    # --- 마스터 ---
    def products(self) -> list[dict]:
        return _read(self.data / "products.json")

    def presets(self) -> list[dict]:
        folder = self.data / "presets"
        if not folder.exists():
            return []
        return [_read(p) for p in sorted(folder.glob("*.json"))]

    # --- 고객사 ---
    def _client_dir(self, slug: str) -> Path:
        slug = _validate_segment(slug, "slug")
        return self.data / "clients" / slug

    def clients(self) -> list[dict]:
        root = self.data / "clients"
        if not root.exists():
            return []
        out = []
        for folder in sorted(root.iterdir()):
            path = folder / "client.json"
            if path.exists():
                data = _read(path)
                out.append({"slug": folder.name, "이름": data.get("이름", folder.name),
                            "상태": data.get("상태", "")})
        return out

    def client_read(self, slug: str) -> dict:
        path = self._client_dir(slug) / "client.json"
        if not path.exists():
            raise FileNotFoundError(f"고객사를 찾을 수 없습니다: {slug}")
        return _read(path)

    def client_write(self, slug: str, data: dict) -> None:
        _write(self._client_dir(slug) / "client.json", data)

    def client_create(self, data: dict) -> str:
        """이름에서 slug 를 만들어 새 폴더를 연다. 이미 있으면 거부한다.

        덮어쓰기를 막는 이유는 plan_write 와 같다. 「우된장」을 두 번
        등록하면 첫 매장에 쌓인 스냅샷 이력이 통째로 사라진다. 기존
        매장을 고치는 건 client_write(편집) 쪽 일이다.
        """
        slug = slugify(data.get("이름", ""))
        path = self._client_dir(slug) / "client.json"
        if path.exists():
            raise ClientExists(f"같은 이름의 매장이 이미 있습니다: {data.get('이름')}")
        _write(path, {**data, "slug": slug})
        return slug

    # --- 순위 원장 ---
    #
    # 스냅샷과 따로 두는 이유. 애드로그는 한 번에 석 달치 일자별 순위를
    # 준다. 그걸 스냅샷 한 건에 접으면 날짜가 뭉개지고, 날짜마다 스냅샷을
    # 쌓으면 같은 자료가 수십 건으로 불어난다. 원장은 날짜가 키라서
    # 몇 번을 갱신해도 한 벌이다.
    def _ranks_path(self, slug: str) -> Path:
        return self._client_dir(slug) / "ranks.json"

    def ranks_read(self, slug: str) -> dict:
        path = self._ranks_path(slug)
        return _read(path) if path.exists() else {}

    def ranks_write(self, slug: str, data: dict) -> None:
        _write(self._ranks_path(slug), data)

    def ranks_archive(self, slug: str, 플레이스ID: str) -> None:
        """원장을 `ranks-{플레이스ID}-{시각}.json` 으로 옮긴다. 원장 자리는 빈다.

        매장을 다시 이을 때 부른다. 옛 매장 키워드가 원장에 남으면
        다음 스냅샷에 섞여 한 제안서에 두 매장 순위가 들어간다.
        지우지 않는 이유는 그게 이미 쌓인 증거이기 때문이다.

        파일명에 시각을 붙인다. A→B→A 처럼 같은 플레이스ID 로 다시
        이으면 `ranks-{id}.json` 하나로는 옛 보관을 또 덮어쓴다 — 그것도
        쌓인 증거라 지우면 안 된다. 그래도 같은 순간에 두 번 불리면
        시각까지 겹칠 수 있어, 그런 경우엔 번호를 붙여 비켜 간다.
        """
        path = self._ranks_path(slug)
        if not path.exists():
            return
        플레이스ID = _validate_segment(플레이스ID, '플레이스ID')
        바탕 = f"ranks-{플레이스ID}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        보관 = self._client_dir(slug) / f"{바탕}.json"
        n = 1
        while 보관.exists():
            보관 = self._client_dir(slug) / f"{바탕}-{n}.json"
            n += 1
        path.rename(보관)

    # --- 애드로그 등록 목록 캐시 ---
    #
    # 목록 한 번에 20 회를 부른다. 매장 정보를 열 때마다 부르면 그것만으로
    # 하루 한도를 갉는다. 고객사 자료가 아니라 언제든 지워도 되는
    # 물건이라 `clients/` 밖에 둔다. `.gitignore` 가 `data/_cache/` 를 뺀다.
    def _adlog_cache_path(self) -> Path:
        return self.data / "_cache" / "adlog_places.json"

    def adlog_cache_read(self) -> dict:
        path = self._adlog_cache_path()
        return _read(path) if path.exists() else {}

    def adlog_cache_write(self, data: dict) -> None:
        _write(self._adlog_cache_path(), data)

    # --- 월 기획안 ---
    def _plan_path(self, slug: str, month: str) -> Path:
        month = _validate_segment(month, "month")
        return self._client_dir(slug) / "plans" / f"{month}.json"

    def plan_months(self, slug: str) -> list[str]:
        folder = self._client_dir(slug) / "plans"
        if not folder.exists():
            return []
        return sorted((p.stem for p in folder.glob("*.json")), reverse=True)

    def plan_read(self, slug: str, month: str) -> dict:
        path = self._plan_path(slug, month)
        if not path.exists():
            raise FileNotFoundError(f"기획안이 없습니다: {slug}/{month}")
        return _read(path)

    def plan_write(self, slug: str, month: str, data: dict, force: bool = False) -> None:
        path = self._plan_path(slug, month)
        if path.exists() and not force:
            raise PlanExists(f"{month} 기획안이 이미 있습니다")
        _write(path, data)

    def plan_copy(self, slug: str, src_month: str, dst_month: str) -> dict:
        source = self.plan_read(slug, src_month)
        copied = {**source, "월": dst_month}
        self.plan_write(slug, dst_month, copied)  # force 없음 → 덮어쓰기 차단
        return copied
