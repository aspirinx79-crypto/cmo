"""data/ 아래 JSON 파일을 읽고 쓴다. 경로를 아는 유일한 모듈이다.

고객사 하나가 폴더 하나, 월 기획안 하나가 파일 하나다.
폴더를 열면 눈에 보이고 git 으로 되돌릴 수 있다.
"""
import json
import re
from pathlib import Path

FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|]+')


class PlanExists(Exception):
    """이미 있는 월 기획안을 덮어쓰려 했다."""


def slugify(name: str) -> str:
    cleaned = FORBIDDEN_RE.sub("_", (name or "").strip())
    cleaned = cleaned.replace(" ", "_")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


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

    # --- 월 기획안 ---
    def _plan_path(self, slug: str, month: str) -> Path:
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
