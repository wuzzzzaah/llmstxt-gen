from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_python_root() -> Path:
    return FIXTURES / "sample_python"


@pytest.fixture
def sample_typescript_root() -> Path:
    return FIXTURES / "sample_typescript"


@pytest.fixture
def sample_go_root() -> Path:
    return FIXTURES / "sample_go"


@pytest.fixture
def sample_express_root() -> Path:
    return FIXTURES / "sample_express"


@pytest.fixture
def sample_nextjs_root() -> Path:
    return FIXTURES / "sample_nextjs"
