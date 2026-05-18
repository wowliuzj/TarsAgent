import os
import sys
import shutil
import pytest
from sqlmodel import Session

# 将项目根目录加入 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# 确保在导入 db 前设置测试环境变量
os.environ["WORKSPACE_DIR"] = "data/test_workspace"

from app.db import engine, init_db

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """在测试会话开始前，确保数据库结构完整初始化。"""
    init_db()
    # 准备测试专用工作目录
    test_workspace = os.path.join(PROJECT_ROOT, "data", "test_workspace")
    if os.path.exists(test_workspace):
        shutil.rmtree(test_workspace)
    os.makedirs(test_workspace, exist_ok=True)
    
    yield
    
    # 清理测试工作目录
    if os.path.exists(test_workspace):
        shutil.rmtree(test_workspace)

@pytest.fixture(name="db_session")
def db_session_fixture():
    """提供自动回滚的事务级数据库 Session。测试对数据库的写入不会被真实保留。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()
