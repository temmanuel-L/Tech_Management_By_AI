"""
综合健康分 — 单元测试
"""

import os
# Removed LLM_PROVIDER hack

from tech_mgmt_ai.models.dora_metrics import DORALevel, DORAResult
from tech_mgmt_ai.models.hero_detector import HeroDetectionResult
from tech_mgmt_ai.models.team_state import TeamState, TeamStateResult
from tech_mgmt_ai.models.tech_debt import TechDebtResult
from tech_mgmt_ai.metrics.health_score import calculate_health_score


class TestHealthScore:
    """测试综合健康分聚合"""

    def test_excellent_health(self):
        """所有维度都优秀 → 高分"""
        result = calculate_health_score(
            dora=DORAResult(overall_score=0.9, overall_level=DORALevel.ELITE),
            tech_debt=TechDebtResult(interest_rate=0.05),
            hero=HeroDetectionResult(gini_coefficient=0.2),
            team_state=TeamStateResult(
                state=TeamState.INNOVATING, score=0.5,
                backlog_score=0, debt_score=0,
                morale_score=0, innovation_score=0,
                description="",
            ),
        )
        assert result.score >= 80
        assert result.level == "excellent"

    def test_danger_health(self):
        """所有维度都差 → 低分"""
        result = calculate_health_score(
            dora=DORAResult(overall_score=0.25, overall_level=DORALevel.LOW),
            tech_debt=TechDebtResult(interest_rate=0.6),
            hero=HeroDetectionResult(gini_coefficient=0.8),
            team_state=TeamStateResult(
                state=TeamState.FALLING_BEHIND, score=-0.5,
                backlog_score=0, debt_score=0,
                morale_score=0, innovation_score=0,
                description="",
            ),
        )
        assert result.score < 40
        assert result.level == "danger"

    def test_partial_data(self):
        """部分数据缺失 → 使用中性值, 不崩溃"""
        result = calculate_health_score(
            dora=DORAResult(overall_score=0.8, overall_level=DORALevel.HIGH),
        )
        assert 0 <= result.score <= 100

    def test_no_data(self):
        """完全无数据 → 中性分数"""
        result = calculate_health_score()
        assert 40 <= result.score <= 60  # 中性值约 50
