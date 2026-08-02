import json
from pathlib import Path

import pytest

CMO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def cmo_dir() -> Path:
    return CMO


@pytest.fixture(scope="session")
def products() -> list[dict]:
    path = CMO / "data" / "products.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def tmp_data(tmp_path: Path) -> Path:
    """고객사 저장 테스트용 빈 data 디렉토리."""
    (tmp_path / "clients").mkdir(parents=True)
    (tmp_path / "presets").mkdir(parents=True)
    return tmp_path
