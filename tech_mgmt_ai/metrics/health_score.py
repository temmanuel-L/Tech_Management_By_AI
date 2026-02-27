"""
综合健康分模型

═══════════════════════════════════════════════════════════════════════════════
理论依据: 《An Elegant Puzzle》附录 "管理看板"
  - 看板需要一个核心指标让管理者 "一眼看出" 团队是否健康
  - 综合健康分将所有子模型的输出聚合为 0-100 的单一分数
═══════════════════════════════════════════════════════════════════════════════

公式:
  Health = 100 × (w_dora·DORA_score + w_debt·(1 - debt_interest)
                + w_hero·(1 - gini) + w_state·state_score)

  其中:
    DORA_score     ∈ [0, 1]  — DORA 四指标综合得分
    debt_interest  ∈ [0, 1]  — 技术债利息率 (取反: 越低越健康)
    gini           ∈ [0, 1]  — 基尼系数 (取反: 越低越健康)
    state_score    ∈ [0, 1]  — 团队状态映射:
                               Innovating=1.0, PayingDownDebt=0.66,
                               TreadingWater=0.33, FallingBehind=0.0

  权重默认值 (可通过 settings 调整):
    w_dora=0.30, w_debt=0.25, w_hero=0.20, w_state=0.25

  解读:
    80-100: 优秀, 团队效能和健康度均处于高位
    60-79:  良好, 有改进空间但整体可控
    40-59:  需关注, 多个维度出现问题
    0-39:   危险, 需立即干预
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass

from tech_mgmt_ai.config import settings
from tech_mgmt_ai.models.dora_metrics import DORAResult
from tech_mgmt_ai.models.hero_detector import HeroDetectionResult
from tech_mgmt_ai.models.team_state import TeamState, TeamStateResult
from tech_mgmt_ai.models.tech_debt import TechDebtResult

logger = logging.getLogger(__name__)

# 团队状态 → 综合健康分中的团队状态得分 (25/50/75/100)
_STATE_SCORES: dict[TeamState, float] = {
    TeamState.FALLING_BEHIND: 25.0,
    TeamState.TREADING_WATER: 50.0,
    TeamState.PAYING_DOWN_DEBT: 75.0,
    TeamState.INNOVATING: 100.0,
}


@dataclass
class HealthScoreResult:
    """
    综合健康分结果

    Attributes:
        score: 综合健康分 (0-100)
        level: 等级 (excellent / good / attention / danger)
        # 维度原始得分 (0-100, 不含权重), 便于前端直接以百分制展示
        dora_score: float
        debt_score: float
        hero_score: float
        state_score: float
        # 维度贡献分 (已乘以权重后的得分, 便于诊断谁拖后腿)
        dora_contribution: float
        debt_contribution: float
        hero_contribution: float
        state_contribution: float
        # 各维度权重 (0-1), 便于前端标注
        w_dora: float
        w_debt: float
        w_hero: float
        w_state: float
        description: 可读的综合描述
    """
    score: float = 0.0
    level: str = "danger"
    dora_score: float = 0.0
    debt_score: float = 0.0
    hero_score: float = 0.0
    state_score: float = 0.0
    dora_contribution: float = 0.0
    debt_contribution: float = 0.0
    hero_contribution: float = 0.0
    state_contribution: float = 0.0
    w_dora: float = 0.0
    w_debt: float = 0.0
    w_hero: float = 0.0
    w_state: float = 0.0
    description: str = ""


def calculate_health_score(
    dora: DORAResult | None = None,
    tech_debt: TechDebtResult | None = None,
    hero: HeroDetectionResult | None = None,
    team_state: TeamStateResult | None = None,
) -> HealthScoreResult:
    """
    计算综合健康分

    此函数是管理看板的核心引擎, 将各维度模型的输出聚合为
    管理者可直观理解的单一健康分。

    设计原则 (书 2.5节):
      - 指标应 "直接服务于管理运作的执行或决策的制定"
      - 综合分不是替代各维度的深度分析, 而是 "异常检测器"
      - 当综合分下降时, 管理者应深入各维度查找根因

    Args:
        dora: DORA 四指标结果 (可选, 为 None 时该维度贡献为中性值 0.5)
        tech_debt: 技术债分析结果 (可选)
        hero: 英雄检测结果 (可选)
        team_state: 团队状态结果 (可选)

    Returns:
        HealthScoreResult: 综合健康分及各维度贡献
    """
    # 各维度的归一化分数 (0-1, 越高越健康)
    # 团队状态: 落后25/停滞50/偿债75/创新100 → 除以100 用于加权
    dora_score = dora.overall_score if dora else 0.5
    debt_score = 1.0 - (tech_debt.interest_rate if tech_debt else 0.5)
    hero_score = 1.0 - (hero.gini_coefficient if hero else 0.5)
    state_score_pct = _STATE_SCORES.get(team_state.state, 50) if team_state else 50
    state_score = state_score_pct / 100.0

    # 加权聚合
    raw_score = (
        settings.HEALTH_W_DORA * dora_score
        + settings.HEALTH_W_DEBT * debt_score
        + settings.HEALTH_W_HERO * hero_score
        + settings.HEALTH_W_STATE * state_score
    )

    # 映射到 0-100
    health = round(raw_score * 100, 1)
    health = max(0.0, min(100.0, health))

    # 等级判定
    if health >= 80:
        level = "excellent"
        level_label = "优秀"
    elif health >= 60:
        level = "good"
        level_label = "良好"
    elif health >= 40:
        level = "attention"
        level_label = "需关注"
    else:
        level = "danger"
        level_label = "危险"

    # 维度原始得分 (0-100, 不含权重)
    dora_score_pct = dora_score * 100
    debt_score_pct = debt_score * 100
    hero_score_pct = hero_score * 100
    # state_score_pct 已是 25/50/75/100

    # 各维度贡献 (已乘以权重, 用于分析哪个维度拖后腿)
    dora_contrib = settings.HEALTH_W_DORA * dora_score_pct
    debt_contrib = settings.HEALTH_W_DEBT * debt_score_pct
    hero_contrib = settings.HEALTH_W_HERO * hero_score_pct
    state_contrib = settings.HEALTH_W_STATE * state_score_pct

    desc_parts = [
        f"📊 综合健康分: {health:.0f}/100 【{level_label}】",
        f"  · DORA 效能: {dora_score_pct:.1f}分 (权重 {settings.HEALTH_W_DORA:.0%}, 贡献 {dora_contrib:.1f})",
        f"  · 技术债健康: {debt_score_pct:.1f}分 (权重 {settings.HEALTH_W_DEBT:.0%}, 贡献 {debt_contrib:.1f})",
        f"  · 协作均衡: {hero_score_pct:.1f}分 (权重 {settings.HEALTH_W_HERO:.0%}, 贡献 {hero_contrib:.1f})",
        f"  · 团队状态: {state_score_pct:.1f}分 (权重 {settings.HEALTH_W_STATE:.0%}, 贡献 {state_contrib:.1f})",
    ]

    logger.info(f"综合健康分: {health:.0f}/100 ({level})")

    return HealthScoreResult(
        score=health,
        level=level,
        dora_score=dora_score_pct,
        debt_score=debt_score_pct,
        hero_score=hero_score_pct,
        state_score=state_score_pct,
        dora_contribution=dora_contrib,
        debt_contribution=debt_contrib,
        hero_contribution=hero_contrib,
        state_contribution=state_contrib,
        w_dora=settings.HEALTH_W_DORA,
        w_debt=settings.HEALTH_W_DEBT,
        w_hero=settings.HEALTH_W_HERO,
        w_state=settings.HEALTH_W_STATE,
        description="\n".join(desc_parts),
    )
