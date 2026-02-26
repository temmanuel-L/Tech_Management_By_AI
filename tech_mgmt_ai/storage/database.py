"""
数据库连接管理

支持两种后端:
  - PostgreSQL (docker 部署, 生产环境)
  - SQLite (本地开发, 零配置)

连接方式由环境变量 DATABASE_URL 控制:
  - 有值时使用该 URL (PostgreSQL)
  - 无值时回退到本地 SQLite 文件
"""

import logging

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from tech_mgmt_ai.config import settings

logger = logging.getLogger(__name__)

# 数据库 URL: 优先 DATABASE_URL 环境变量, 回退到 SQLite
_DATABASE_URL: str | None = None

# 使用 declarative_base() 兼容 SQLAlchemy 1.4/2.x, IDE 可正确解析
Base = declarative_base()


def get_database_url() -> str:
    """获取数据库连接 URL"""
    global _DATABASE_URL
    if _DATABASE_URL:
        return _DATABASE_URL

    import os
    url = os.environ.get("DATABASE_URL")
    if url:
        _DATABASE_URL = url
    else:
        _DATABASE_URL = "sqlite:///tech_mgmt_ai.db"
        logger.info("未设置 DATABASE_URL, 使用本地 SQLite: tech_mgmt_ai.db")

    return _DATABASE_URL


def get_engine():
    """创建并返回 SQLAlchemy Engine"""
    url = get_database_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(url, connect_args=connect_args, echo=False)
    return engine


def get_session_factory() -> sessionmaker[Session]:
    """创建 Session 工厂"""
    engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    """创建所有表 (首次启动时)"""
    from tech_mgmt_ai.storage.models import MetricsSnapshot  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("数据库表已初始化")
