import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def client():
    import api_server
    api_server.app.config["TESTING"] = True
    return api_server.app.test_client()


@pytest.fixture(scope="session")
def ra():
    import api_server  # noqa: F401 — 블루프린트 등록(HWPX 기본 서식 등 컨텍스트)
    import reg_agent
    return reg_agent
