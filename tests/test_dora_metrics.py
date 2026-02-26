"""
DORA 指标 — 单元测试
"""

import os
# Removed LLM_PROVIDER hack

from datetime import datetime, timedelta
from tech_mgmt_ai.connectors import MergeRequestInfo, PipelineInfo
from tech_mgmt_ai.models.dora_metrics import DORALevel, calculate_dora_metrics


class TestDORAMetrics:
    """测试 DORA 四指标计算"""

    def _make_mr(self, created, merged_at=None, state="merged"):
        return MergeRequestInfo(
            id=1, title="test", author="alice",
            state=state, created_at=created, merged_at=merged_at,
        )

    def _make_pipeline(self, created, status="success", is_deploy=True):
        return PipelineInfo(
            id=1, status=status, created_at=created,
            finished_at=created + timedelta(minutes=10),
            is_deployment=is_deploy,
        )

    def test_elite_lead_time(self):
        """< 24 小时 = Elite"""
        now = datetime.now()
        mrs = [self._make_mr(now - timedelta(hours=6), now)]
        result = calculate_dora_metrics(mrs, [], 30)
        assert result.lead_time_level == DORALevel.ELITE

    def test_deploy_frequency(self):
        """每天 1 次部署 = Elite"""
        now = datetime.now()
        pipes = [self._make_pipeline(now - timedelta(days=i)) for i in range(30)]
        result = calculate_dora_metrics([], pipes, 30)
        assert result.deploy_freq_level == DORALevel.ELITE
        assert result.deploy_frequency >= 1.0

    def test_change_failure_rate(self):
        """0% 失败 = Elite"""
        now = datetime.now()
        pipes = [self._make_pipeline(now, "success") for _ in range(10)]
        result = calculate_dora_metrics([], pipes, 30)
        assert result.cfr_level == DORALevel.ELITE
        assert result.change_failure_rate == 0.0

    def test_high_failure_rate(self):
        """50% 失败 = Low"""
        now = datetime.now()
        pipes = (
            [self._make_pipeline(now, "success") for _ in range(5)]
            + [self._make_pipeline(now, "failed") for _ in range(5)]
        )
        result = calculate_dora_metrics([], pipes, 30)
        assert result.cfr_level == DORALevel.LOW

    def test_empty_data(self):
        """空数据不崩溃"""
        result = calculate_dora_metrics([], [], 30)
        assert isinstance(result.overall_score, float)
