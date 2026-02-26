"""
英雄检测模型 — 单元测试
"""

import os
# Removed LLM_PROVIDER hack

from datetime import datetime
from tech_mgmt_ai.connectors import CommitInfo
from tech_mgmt_ai.models.hero_detector import calculate_gini, detect_heroes


class TestGiniCoefficient:
    """测试基尼系数计算"""

    def test_equal_distribution(self):
        """完全平等分布 → Gini = 0"""
        gini = calculate_gini([10, 10, 10, 10])
        assert abs(gini) < 0.01

    def test_perfect_inequality(self):
        """完全不平等 → Gini 接近 1"""
        gini = calculate_gini([0, 0, 0, 100])
        assert gini > 0.7

    def test_moderate_concentration(self):
        """中等集中度"""
        gini = calculate_gini([5, 10, 15, 70])
        assert 0.3 < gini < 0.7

    def test_single_person(self):
        """单人 → 0"""
        assert calculate_gini([50]) == 0.0

    def test_empty(self):
        """空列表 → 0"""
        assert calculate_gini([]) == 0.0


class TestHeroDetection:
    """测试英雄检测"""

    def _make_commits(self, distribution: dict[str, int]) -> list[CommitInfo]:
        commits = []
        for author, count in distribution.items():
            for i in range(count):
                commits.append(CommitInfo(
                    sha=f"{author}_{i}", author=author,
                    message=f"commit by {author}",
                    created_at=datetime.now(),
                ))
        return commits

    def test_healthy_team(self):
        """均匀分布 → 健康"""
        commits = self._make_commits({
            "alice": 12, "bob": 10, "charlie": 11,
            "diana": 9, "eve": 10, "frank": 11,
        })
        result = detect_heroes(commits)
        assert result.level == "healthy"
        assert result.gini_coefficient < 0.4

    def test_hero_dependency(self):
        """一人独占 → 告警"""
        commits = self._make_commits({
            "hero_dev": 80, "bob": 5, "charlie": 3,
            "diana": 2, "eve": 1, "frank": 1,
        })
        result = detect_heroes(commits)
        assert result.level == "alert"
        assert result.gini_coefficient > 0.6

    def test_empty_commits(self):
        """空数据不崩溃"""
        result = detect_heroes([])
        assert result.team_size == 0
