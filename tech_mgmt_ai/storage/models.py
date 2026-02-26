"""
SQLAlchemy ORM 模型 — 指标快照存储

MetricsSnapshot 表存储每次分析运行的完整结果快照。
每条记录包含: 时间戳、健康分、DORA 指标、技术债率、基尼系数、团队状态等。
支持按时间范围查询, 用于趋势分析和历史对比。
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, func

from tech_mgmt_ai.storage.database import Base


class MetricsSnapshot(Base):
    """
    指标快照 ORM 模型

    每次运行 analyze 时生成一条记录, 存储所有模型的输出结果。
    这是 tech_mgmt_ai 的 "记忆" — 不是对话记忆, 而是指标历史。
    """
    __tablename__ = "metrics_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)

    # ---- 综合健康分 ----
    health_score = Column(Float, nullable=False, default=0.0)
    health_level = Column(String(20), nullable=False, default="unknown")

    # ---- DORA 四指标 ----
    dora_lead_time_hours = Column(Float, default=0.0)
    dora_deploy_frequency = Column(Float, default=0.0)
    dora_change_failure_rate = Column(Float, default=0.0)
    dora_mttr_hours = Column(Float, default=0.0)
    dora_overall_score = Column(Float, default=0.0)
    dora_overall_level = Column(String(10), default="low")

    # ---- 技术债 ----
    tech_debt_interest_rate = Column(Float, default=0.0)
    tech_debt_level = Column(String(20), default="healthy")
    tech_debt_stock = Column(Float, default=0.0)

    # ---- 英雄检测 ----
    hero_gini_coefficient = Column(Float, default=0.0)
    hero_level = Column(String(20), default="healthy")
    hero_team_size = Column(Integer, default=0)

    # ---- 团队状态 ----
    team_state = Column(String(30), default="unknown")
    team_state_score = Column(Float, default=0.0)

    # ---- 原始数据统计 ----
    total_commits = Column(Integer, default=0)
    total_merge_requests = Column(Integer, default=0)
    total_pipelines = Column(Integer, default=0)
    total_tasks = Column(Integer, default=0)

    # ---- 详细报告 (Markdown) ----
    report_markdown = Column(Text, default="")

    # ---- 各维度详情 (JSON, 可选) ----
    details_json = Column(JSON, default=dict)

    def __repr__(self):
        return (
            f"<MetricsSnapshot(id={self.id}, "
            f"health={self.health_score:.0f}, "
            f"state={self.team_state}, "
            f"at={self.created_at})>"
        )
