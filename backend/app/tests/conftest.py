import os
import tempfile

# 必须在 import app.db（其在导入时固化 DB_PATH）之前指定独立数据目录。
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="ladderbill-test-"))

import pytest


@pytest.fixture
def fresh_db():
    """每个用例使用全新种子库。"""
    from app import seed
    from app.db import DB_PATH

    if DB_PATH.exists():
        DB_PATH.unlink()
    seed.init_db()
    yield DB_PATH
