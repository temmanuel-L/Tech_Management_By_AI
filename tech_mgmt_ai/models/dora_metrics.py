"""
DORA 四指标计算模型

═══════════════════════════════════════════════════════════════════════════════
理论依据:
  - 《An Elegant Puzzle》2.1节: "系统思维, 最普适的工具"
    书中明确提出的四个开发人员速度关键指标
  - 《Accelerate》(Nicole Forsgren, Jez Humble, Gene Kim)
    DORA 研究的四个关键指标, 是衡量软件交付效能的行业标准
═══════════════════════════════════════════════════════════════════════════════

四个关键指标:

  1. Lead Time for Changes (变更前置时间)
     定义: 从代码首次提交到成功部署上线的时间
     计算: mean(merged_at - created_at) for all merged MRs
     分级: Elite(<24h), High(<7d), Medium(<30d), Low(≥30d)

  2. Deployment Frequency (部署频率)
     定义: 单位时间内成功部署到生产环境的次数
     计算: count(successful_deploy_pipelines) / time_window_days
     分级: Elite(≥1/天), High(≥1/周), Medium(≥1/月), Low(<1/月)

  3. Change Failure Rate (变更失败率)
     定义: 导致生产环境故障的变更占总变更的比例
     计算: failed_deploy_pipelines / total_deploy_pipelines
     分级: Elite(<5%), High(<10%), Medium(<15%), Low(≥15%)

  4. Mean Time to Recovery (平均恢复时间, MTTR)
     定义: 从生产故障发生到服务恢复的平均时间
     计算: mean(recovery_time) — 通过连续失败/成功 Pipeline 时间差估算
     分级: Elite(<1h), High(<24h), Medium(<7d), Low(≥7d)

综合评级:
  每个指标独立评级, 综合评级取四项的中位水平。
  DORA 分数 = 各等级映射为数值后的加权平均 (Elite=1.0, High=0.75, Medium=0.5, Low=0.25)
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum

from tech_mgmt_ai.config import settings
from tech_mgmt_ai.connectors import MergeRequestInfo, PipelineInfo

logger = logging.getLogger(__name__)


class DORALevel(IntEnum):
    """
    DORA 效能等级

    基于 DORA State of DevOps Report 的分级标准。
    数值越高表示效能越好, 可用于数值计算和比较。
    """
    LOW = 1         # 低: 行业下四分位
    MEDIUM = 2      # 中: 行业中位
    HIGH = 3        # 高: 行业上四分位
    ELITE = 4       # 精英: 行业顶尖 (如 Google, Netflix)

    @property
    def score(self) -> float:
        """将等级转换为 0-1 分数, 用于综合健康分计算"""
        return {
            DORALevel.LOW: 0.25,
            DORALevel.MEDIUM: 0.50,
            DORALevel.HIGH: 0.75,
            DORALevel.ELITE: 1.00,
        }[self]

    @property
    def label(self) -> str:
        """中文标签"""
        return {
            DORALevel.LOW: "低",
            DORALevel.MEDIUM: "中",
            DORALevel.HIGH: "高",
            DORALevel.ELITE: "精英",
        }[self]


@dataclass
class DORAResult:
    """
    DORA 四指标计算结果

    Attributes:
        lead_time_hours: 变更前置时间 (小时)
        lead_time_level: 前置时间评级
        deploy_frequency: 部署频率 (次/天)
        deploy_freq_level: 部署频率评级
        change_failure_rate: 变更失败率 (0.0-1.0)
        cfr_level: 失败率评级
        mttr_hours: 平均恢复时间 (小时)
        mttr_level: 恢复时间评级
        overall_score: 综合 DORA 得分 (0.0-1.0)
        overall_level: 综合评级
        description: 可读的分析描述
    """
    lead_time_hours: float = 0.0
    lead_time_level: DORALevel = DORALevel.LOW
    deploy_frequency: float = 0.0
    deploy_freq_level: DORALevel = DORALevel.LOW
    change_failure_rate: float = 0.0
    cfr_level: DORALevel = DORALevel.LOW
    mttr_hours: float = 0.0
    mttr_level: DORALevel = DORALevel.LOW
    overall_score: float = 0.0
    overall_level: DORALevel = DORALevel.LOW
    description: str = ""


def _classify_lead_time(hours: float) -> DORALevel:
    """
    Lead Time for Changes 分级

    阈值来源: DORA State of DevOps Report
    可通过 DORA_LEAD_TIME_*_HOURS 环境变量调整
    """
    if hours < settings.DORA_LEAD_TIME_ELITE_HOURS:
        return DORALevel.ELITE
    elif hours < settings.DORA_LEAD_TIME_HIGH_HOURS:
        return DORALevel.HIGH
    elif hours < settings.DORA_LEAD_TIME_MEDIUM_HOURS:
        return DORALevel.MEDIUM
    else:
        return DORALevel.LOW


def _classify_deploy_freq(per_day: float) -> DORALevel:
    """
    Deployment Frequency 分级

    阈值来源: DORA State of DevOps Report
    可通过 DORA_DEPLOY_FREQ_*_PER_DAY 环境变量调整
    """
    if per_day >= settings.DORA_DEPLOY_FREQ_ELITE_PER_DAY:
        return DORALevel.ELITE
    elif per_day >= settings.DORA_DEPLOY_FREQ_HIGH_PER_DAY:
        return DORALevel.HIGH
    elif per_day >= settings.DORA_DEPLOY_FREQ_MEDIUM_PER_DAY:
        return DORALevel.MEDIUM
    else:
        return DORALevel.LOW


def _classify_cfr(rate: float) -> DORALevel:
    """
    Change Failure Rate 分级

    注意: CFR 越低越好, 所以判定逻辑与其他指标相反
    """
    if rate < settings.DORA_CFR_ELITE:
        return DORALevel.ELITE
    elif rate < settings.DORA_CFR_HIGH:
        return DORALevel.HIGH
    elif rate < settings.DORA_CFR_MEDIUM:
        return DORALevel.MEDIUM
    else:
        return DORALevel.LOW


def _classify_mttr(hours: float) -> DORALevel:
    """
    Mean Time to Recovery 分级

    MTTR 越低越好
    """
    if hours < settings.DORA_MTTR_ELITE_HOURS:
        return DORALevel.ELITE
    elif hours < settings.DORA_MTTR_HIGH_HOURS:
        return DORALevel.HIGH
    elif hours < settings.DORA_MTTR_MEDIUM_HOURS:
        return DORALevel.MEDIUM
    else:
        return DORALevel.LOW


def calculate_dora_metrics(
    merge_requests: list[MergeRequestInfo],
    pipelines: list[PipelineInfo],
    time_window_days: float = 30.0,
) -> DORAResult:
    """
    计算 DORA 四指标

    此函数是系统的核心度量引擎之一, 将原始的 MR 和 Pipeline 数据
    转化为行业标准化的软件交付效能指标。

    映射书 2.1节的系统思维:
    - Lead Time 和 Deploy Frequency 衡量 "流量" (交付速度)
    - CFR 和 MTTR 衡量 "质量" (系统稳定性)

    映射书 2.4节的目标四要素:
    - 指标: DORA 四指标
    - 基线: 当前计算值
    - 趋势: 通过 trend.py 跟踪时序变化
    - 时间框架: time_window_days

    Args:
        merge_requests: 合并请求列表 (来自 GitLab)
        pipelines: CI/CD Pipeline 列表 (来自 GitLab)
        time_window_days: 分析的时间窗口 (天), 默认 30 天

    Returns:
        DORAResult: 四指标的计算值、评级和综合分析
    """
    # === 1. Lead Time for Changes ===
    # 计算所有已合并 MR 的前置时间
    lead_times_hours: list[float] = []
    for mr in merge_requests:
        if mr.state == "merged" and mr.merged_at:
            delta = mr.merged_at - mr.created_at
            lead_times_hours.append(delta.total_seconds() / 3600)

    avg_lead_time = (
        sum(lead_times_hours) / len(lead_times_hours)
        if lead_times_hours else 0.0
    )
    lead_time_level = _classify_lead_time(avg_lead_time)

    # === 2. Deployment Frequency ===
    # 统计部署类 Pipeline 的成功次数
    deploy_pipelines = [p for p in pipelines if p.is_deployment]
    successful_deploys = [p for p in deploy_pipelines if p.status == "success"]
    deploy_freq = len(successful_deploys) / max(time_window_days, 1)
    deploy_freq_level = _classify_deploy_freq(deploy_freq)

    # === 3. Change Failure Rate ===
    # 部署失败次数 / 总部署次数
    failed_deploys = [p for p in deploy_pipelines if p.status == "failed"]
    total_deploys = len(deploy_pipelines)
    cfr = len(failed_deploys) / max(total_deploys, 1) if total_deploys > 0 else 0.0
    # 注意: 当没有任何部署 Pipeline 时, 无法客观评估失败率, 这里采用“中性”评级
    cfr_level = _classify_cfr(cfr) if total_deploys > 0 else DORALevel.MEDIUM

    # === 4. MTTR ===
    # 估算恢复时间: 寻找 "失败→成功" 的 Pipeline 对, 计算时间差
    mttr_hours_list: list[float] = []
    sorted_deploys = sorted(deploy_pipelines, key=lambda p: p.created_at)
    last_failure_time: datetime | None = None

    for p in sorted_deploys:
        if p.status == "failed":
            last_failure_time = p.created_at
        elif p.status == "success" and last_failure_time:
            recovery_time = (p.created_at - last_failure_time).total_seconds() / 3600
            mttr_hours_list.append(recovery_time)
            last_failure_time = None  # 重置

    avg_mttr = (
        sum(mttr_hours_list) / len(mttr_hours_list)
        if mttr_hours_list else 0.0
    )
    # 同理, 没有任何“失败→成功”的恢复样本时, MTTR 也视为“中性”评级
    mttr_level = _classify_mttr(avg_mttr) if mttr_hours_list else DORALevel.MEDIUM

    # === 综合评分 ===
    # 四指标各自的 score (0-1) 取平均
    levels = [lead_time_level, deploy_freq_level, cfr_level, mttr_level]
    overall_score = sum(l.score for l in levels) / 4
    # 综合等级取最接近的 DORALevel
    sorted_levels = sorted(levels)
    overall_level = sorted_levels[1]  # 取中位偏低值, 保守评估

    # === 生成描述 ===
    no_deploy_data = total_deploys == 0
    if no_deploy_data:
        cfr_desc = "无部署数据, 无法评估 → 中性评级"
        mttr_desc = "无故障恢复数据, 无法评估 → 中性评级"
    else:
        cfr_desc = f"{cfr:.1%} → {cfr_level.label}级"
        mttr_desc = f"{avg_mttr:.1f}h → {mttr_level.label}级"

    desc_parts = [
        f"📊 DORA 综合评级: 【{overall_level.label}】(得分 {overall_score:.2f})",
        f"  · 变更前置时间: {avg_lead_time:.1f}h → {lead_time_level.label}级",
        f"  · 部署频率: {deploy_freq:.2f}次/天 → {deploy_freq_level.label}级",
        f"  · 变更失败率: {cfr_desc}",
        f"  · 平均恢复时间: {mttr_desc}",
    ]
    description = "\n".join(desc_parts)

    logger.info(f"DORA 指标: overall={overall_level.name} ({overall_score:.2f})")

    return DORAResult(
        lead_time_hours=avg_lead_time,
        lead_time_level=lead_time_level,
        deploy_frequency=deploy_freq,
        deploy_freq_level=deploy_freq_level,
        change_failure_rate=cfr,
        cfr_level=cfr_level,
        mttr_hours=avg_mttr,
        mttr_level=mttr_level,
        overall_score=overall_score,
        overall_level=overall_level,
        description=description,
    )
