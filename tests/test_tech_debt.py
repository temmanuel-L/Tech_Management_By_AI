"""
技术债利息率模型 — 单元测试
"""

import os
# Removed LLM_PROVIDER hack

from datetime import datetime
from tech_mgmt_ai.connectors import CommitInfo
from tech_mgmt_ai.models.tech_debt import calculate_tech_debt, is_fix_commit


class TestIsFixCommit:
    """测试修复类 Commit 判定"""

    def test_fix_keyword(self):
        c = CommitInfo(sha="a", author="a", message="fix: resolve login issue", created_at=datetime.now())
        assert is_fix_commit(c) is True

    def test_bugfix_keyword(self):
        c = CommitInfo(sha="a", author="a", message="bugfix: correct calculation", created_at=datetime.now())
        assert is_fix_commit(c) is True

    def test_feature_commit(self):
        c = CommitInfo(sha="a", author="a", message="feat: add user dashboard", created_at=datetime.now())
        assert is_fix_commit(c) is False

    def test_case_insensitive(self):
        c = CommitInfo(sha="a", author="a", message="HOTFIX: urgent fix", created_at=datetime.now())
        assert is_fix_commit(c) is True


class TestTechDebt:
    """测试技术债计算"""

    def test_healthy_debt(self):
        """大部分 commit 是功能 → 健康"""
        commits = [
            CommitInfo(sha=f"c{i}", author="alice", message="feat: new feature",
                       created_at=datetime.now(), additions=100, deletions=20)
            for i in range(10)
        ]
        # 添加 1 个修复
        commits.append(CommitInfo(
            sha="fix1", author="alice", message="fix: minor bug",
            created_at=datetime.now(), additions=10, deletions=5,
        ))
        result = calculate_tech_debt(commits)
        assert result.level == "healthy"
        assert result.interest_rate < 0.15

    def test_danger_level_debt(self):
        """大部分 commit 是修复 → 危险"""
        fix_commits = [
            CommitInfo(sha=f"fix{i}", author="bob", message="fix: critical bug #{i}",
                       created_at=datetime.now(), additions=100, deletions=50)
            for i in range(8)
        ]
        feat_commits = [
            CommitInfo(sha=f"feat{i}", author="alice", message="feat: small feature",
                       created_at=datetime.now(), additions=20, deletions=5)
            for i in range(2)
        ]
        result = calculate_tech_debt(fix_commits + feat_commits)
        assert result.level == "danger"
        assert result.interest_rate >= 0.50

    def test_empty_commits(self):
        """空提交列表不崩溃"""
        result = calculate_tech_debt([])
        assert result.interest_rate == 0.0

    def test_debt_stock_accumulation(self):
        """技术债存量模型测试"""
        commits = [
            CommitInfo(sha="c1", author="a", message="feat: big feature",
                       created_at=datetime.now(), additions=1000, deletions=200)
        ]
        result = calculate_tech_debt(commits, previous_stock=100)
        # 非修复变更 1200 * 0.1 = 120 新增债务, 0 修复
        # stock = 100 + 120 - 0 = 220
        assert result.debt_stock > 100
