"""
团队状态诊断模型 — 单元测试

验证在不同的数据组合下, 状态判定是否符合预期。
"""

import os
# Removed LLM_PROVIDER hack
import pytest

from tech_mgmt_ai.models.team_state import (
    TeamState,
    TeamStateInput,
    diagnose_team_state,
)


class TestTeamStateDiagnosis:
    """测试团队四状态诊断"""

    def test_falling_behind_state(self):
        """积压增长 + 高债务 + 低创新 → 落后"""
        data = TeamStateInput(
            tasks_created=20,    # 本周新增 20 个任务
            tasks_closed=5,      # 只完成了 5 个
            total_backlog=50,    # 积压 50 个
            debt_tasks=15,       # 15 个是修复/债务
            feature_tasks=2,     # 只有 2 个是功能
            total_tasks=20,
            reviews_given=3,     # 低参与度
            team_size=8,
        )
        result = diagnose_team_state(data)
        assert result.state == TeamState.FALLING_BEHIND
        assert result.score < -0.3
        assert "落后" in result.description

    def test_treading_water_state(self):
        """积压微增 + 中等债务 → 停滞"""
        data = TeamStateInput(
            tasks_created=10,
            tasks_closed=8,
            total_backlog=30,
            debt_tasks=5,
            feature_tasks=3,
            total_tasks=10,
            reviews_given=10,
            team_size=8,
        )
        result = diagnose_team_state(data)
        assert result.state == TeamState.TREADING_WATER
        assert -0.3 <= result.score < 0.0

    def test_paying_down_debt_state(self):
        """积压减少 + 债务下降 → 偿债"""
        data = TeamStateInput(
            tasks_created=8,
            tasks_closed=12,
            total_backlog=20,
            debt_tasks=3,
            feature_tasks=5,
            total_tasks=12,
            reviews_given=20,
            team_size=8,
        )
        result = diagnose_team_state(data)
        assert result.state == TeamState.PAYING_DOWN_DEBT
        assert 0.0 <= result.score < 0.3

    def test_innovating_state(self):
        """积压大幅减少 + 低债务 + 高创新 → 创新"""
        data = TeamStateInput(
            tasks_created=5,
            tasks_closed=15,
            total_backlog=10,
            debt_tasks=1,
            feature_tasks=12,
            total_tasks=15,
            reviews_given=40,
            team_size=8,
        )
        result = diagnose_team_state(data)
        assert result.state == TeamState.INNOVATING
        assert result.score >= 0.3
        assert "创新" in result.description

    def test_empty_data_does_not_crash(self):
        """空数据不会崩溃"""
        result = diagnose_team_state(TeamStateInput())
        assert result.state in TeamState
        assert isinstance(result.score, float)
