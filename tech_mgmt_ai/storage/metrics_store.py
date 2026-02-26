"""
指标存储与查询

提供 CRUD 操作和历史查询, 用于:
  - 保存每次分析快照
  - 查询历史数据用于趋势图
  - 获取最近一次分析结果
"""

import logging
from datetime import datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from tech_mgmt_ai.storage.database import get_session_factory
from tech_mgmt_ai.storage.models import MetricsSnapshot

logger = logging.getLogger(__name__)

_session_factory = None


def _get_session() -> Session:
    """获取数据库 Session"""
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory()


def save_snapshot(snapshot: MetricsSnapshot) -> MetricsSnapshot:
    """
    保存一条指标快照到数据库

    Args:
        snapshot: 填充好字段的 MetricsSnapshot 对象

    Returns:
        保存后的对象 (含自增 ID)
    """
    session = _get_session()
    try:
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)
        logger.info(f"指标快照已保存: id={snapshot.id}, health={snapshot.health_score:.0f}")
        return snapshot
    except Exception as e:
        session.rollback()
        logger.error(f"保存指标快照失败: {e}")
        raise
    finally:
        session.close()


def get_latest_snapshot() -> MetricsSnapshot | None:
    """获取最近一次分析快照"""
    session = _get_session()
    try:
        return (
            session.query(MetricsSnapshot)
            .order_by(desc(MetricsSnapshot.created_at))
            .first()
        )
    finally:
        session.close()


def get_history(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
) -> list[MetricsSnapshot]:
    """
    查询历史指标快照

    Args:
        since: 起始时间 (含)
        until: 结束时间 (含)
        limit: 最大返回条数

    Returns:
        按时间正序排列的快照列表
    """
    session = _get_session()
    try:
        query = session.query(MetricsSnapshot)
        if since:
            query = query.filter(MetricsSnapshot.created_at >= since)
        if until:
            query = query.filter(MetricsSnapshot.created_at <= until)
        return (
            query.order_by(MetricsSnapshot.created_at)
            .limit(limit)
            .all()
        )
    finally:
        session.close()
